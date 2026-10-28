import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from database import EmailDatabase
from mail_artifacts import customer_excel_path
from rpa.isolation import session_lock
from rpa.report_jobs import claim_report, get_job, finish_job, run_report_process, _finish_process_failure
from rpa.report_worker import execute
from rpa.session_models import LoginMode, PortalEnvironment, PortalSessionError
from rpa.session_config import PortalSessionSettings
from rpa.user_sessions import PortalSessionRegistry
from tests.rpa.test_user_sessions import FakeSessionService
from user_access import Principal, UserAccessRepository


class ReportIsolationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = EmailDatabase(str(self.root / 'test.db'))
        self.repo = UserAccessRepository(self.db)
        self.account = self.db.add_mail_account({'email_address': 'shared@example.com', 'imap_server': 'example.com'})
        self.db.add_email_record(17, receiver='shared@example.com', content='historical mail')
        self.email_id = self.db.get_email_record(17)['id']
        self.task_id = self.db.upsert_cutover_task(email_records_id=self.email_id, line_type='customer',
            fill_result={'circuits': [{'circuit': 'original'}]}, customer_excel_filename='original.xlsx')
        self.db.update_cutover_task(self.task_id, status='confirmed')
        self.excel = customer_excel_path(self.root, mailbox_address='shared@example.com', email_uid=17, filename='original.xlsx')
        self.excel.parent.mkdir(parents=True)
        self.excel.write_bytes(b'original workbook')
        self.registry = PortalSessionRegistry(self.db, self.root,
            PortalSessionSettings.model_construct(test_login_url='http://localhost/login',
                test_mobile_login_url='http://localhost/mobile', test_session_check_url='http://localhost/home',
                session_keepalive_enabled=False), service_factory=FakeSessionService)
        self.addCleanup(self.registry.close)
        self.people = []
        for name in ('alice', 'bob'):
            user = self.repo.create_user(name, 'secure-password')
            principal = self.repo.get_principal(user['id'])
            self.repo.set_grants(user['id'], [{'account_id': self.account, 'can_operate': True}])
            service = self.registry.for_principal(principal)
            attempt = service.begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
            service.login_with_password(attempt.attempt_id, f'portal-{name}', 'secret', '42')
            self.people.append((principal, service))

    def claim(self, index=0):
        principal, service = self.people[index]
        return claim_report(self.db, principal, service, self.task_id, PortalEnvironment.TEST, self.root)

    def test_admin_claim_is_rejected_before_session_access(self):
        service = Mock()
        with self.assertRaises(PortalSessionError) as caught:
            claim_report(self.db, Principal.admin(), service, self.task_id, PortalEnvironment.TEST, self.root)
        self.assertEqual(caught.exception.code, 'ADMIN_RPA_FORBIDDEN')
        service.report_binding.assert_not_called()
        self.assertEqual(self.db.get_cutover_reports(self.task_id), [])

    def test_preexisting_admin_queued_job_cannot_execute(self):
        report_id, _ = self.claim()
        with self.db.get_connection() as conn:
            conn.execute("UPDATE rpa_report_jobs SET principal_key='admin', user_id=NULL WHERE report_id=?", (report_id,))
            conn.commit()
        action = Mock()
        execute(self.db, self.root, report_id, action)
        action.assert_not_called()
        self.assertEqual(self.db.get_cutover_report(report_id)['result']['error_code'], 'ADMIN_RPA_FORBIDDEN')
        self.assertEqual(get_job(self.db, report_id)['status'], 'failed')

    def test_shared_task_can_only_be_claimed_once_concurrently(self):
        barrier = threading.Barrier(2)
        def submit(index):
            barrier.wait()
            try:
                return self.claim(index)[0]
            except PortalSessionError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, [0, 1]))
        self.assertEqual(sum(type(value) is int for value in results), 1)
        self.assertIn('TASK_BUSY', results)
        self.assertEqual(len(self.db.get_cutover_reports(self.task_id)), 1)

    def test_binding_and_excel_are_frozen_and_other_user_is_independent(self):
        report_id, result = self.claim()
        self.excel.write_bytes(b'changed later')
        binding = get_job(self.db, report_id)
        snapshot = json.loads(binding['task_snapshot'])
        self.assertEqual(Path(snapshot['_report_excel_path']).read_bytes(), b'original workbook')
        self.assertEqual(result['execution_identity']['username'], 'portal-alice')
        self.assertEqual(result['execution_identity']['workbench_username'], 'alice')
        with self.assertRaises(PortalSessionError):
            self.people[0][1].begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
        self.assertTrue(self.people[1][1].status(PortalEnvironment.TEST).authenticated)

    def test_legacy_identity_resolves_username_without_rewriting_stored_report(self):
        original = {'execution_identity': {'principal_key': self.people[0][0].key,
                    'username': 'portal-alice', 'environment': 'test', 'session_version': 'old'}}
        report_id = self.db.add_cutover_report(self.task_id, 'customer', 'success', original)
        for report in (self.db.get_cutover_report(report_id), self.db.get_cutover_reports(self.task_id)[0]):
            self.assertEqual(report['result']['execution_identity']['workbench_username'], 'alice')
            self.assertEqual(report['result']['execution_identity']['username'], 'portal-alice')
        with self.db.get_connection() as conn:
            stored = conn.execute('SELECT result FROM cutover_reports WHERE id=?', (report_id,)).fetchone()[0]
        self.assertEqual(json.loads(stored), original)

    def test_workbench_username_snapshot_survives_progress_and_manual_resolution(self):
        report_id, _ = self.claim()
        with self.db.get_connection() as conn:
            conn.execute('UPDATE app_users SET username=? WHERE id=?', ('renamed-later', self.people[0][0].user_id))
            conn.commit()
        self.db.update_cutover_report(report_id, status='running', result={'phase': 'running'})
        self.assertEqual(get_job(self.db, report_id)['workbench_username'], 'alice')
        self.assertEqual(self.db.get_cutover_report(report_id)['result']['execution_identity']['workbench_username'], 'alice')

    def test_admin_missing_user_and_pre_identity_reports_are_readable(self):
        for key, expected in [('admin', 'admin'), ('user-99999', None)]:
            report_id = self.db.add_cutover_report(self.task_id, 'customer', 'success',
                {'execution_identity': {'principal_key': key, 'username': 'portal-old'}})
            self.assertEqual(self.db.get_cutover_report(report_id)['result']['execution_identity']['workbench_username'], expected)
        report_id = self.db.add_cutover_report(self.task_id, 'customer', 'success', {'note': 'legacy'})
        self.assertEqual(self.db.get_cutover_report(report_id)['result'], {'note': 'legacy'})

    def test_worker_rechecks_revoked_authorization_before_any_external_action(self):
        report_id, _ = self.claim()
        self.repo.set_grants(self.people[0][0].user_id, [])
        action = Mock()
        execute(self.db, self.root, report_id, action)
        action.assert_not_called()
        report = self.db.get_cutover_report(report_id)
        self.assertEqual(report['result']['error_code'], 'ACCESS_DENIED')
        self.assertEqual(report['result']['execution_identity']['username'], 'portal-alice')
        self.assertEqual(get_job(self.db, report_id)['status'], 'failed')

    def test_worker_waits_for_status_check_lock_without_losing_job(self):
        report_id, _ = self.claim()
        entered = threading.Event()
        def complete(*args, **kwargs):
            entered.set()
            self.db.update_cutover_report(report_id, status='success', result={'phase': 'success'})
        with ThreadPoolExecutor(max_workers=1) as pool:
            with session_lock(self.people[0][1].lock_path):
                future = pool.submit(execute, self.db, self.root, report_id, complete)
                self.assertFalse(entered.wait(.1))
            future.result(timeout=5)
        self.assertTrue(entered.is_set())
        self.assertEqual(get_job(self.db, report_id)['status'], 'success')

    def test_worker_does_not_execute_a_claim_twice(self):
        report_id, _ = self.claim()
        action = Mock(side_effect=lambda *args, **kwargs: self.db.update_cutover_report(report_id, status='success'))
        execute(self.db, self.root, report_id, action)
        execute(self.db, self.root, report_id, action)
        action.assert_called_once()

    def test_process_start_failure_cannot_overwrite_manual_resolution_or_new_attempt(self):
        report_id, _ = self.claim()
        def resolve_then_fail(*args, **kwargs):
            self.db.update_cutover_report(report_id, status='success', result={'resolved_by': 'admin'})
            finish_job(self.db, report_id, 'success')
            self.db.add_cutover_report(self.task_id, status='pending')
            self.db.update_cutover_task(self.task_id, status='reporting')
            raise OSError('mock process creation failure')
        with patch('rpa.report_jobs.subprocess.Popen', side_effect=resolve_then_fail):
            run_report_process(self.db, self.root, report_id)
        self.assertEqual(self.db.get_cutover_report(report_id)['status'], 'success')
        self.assertEqual(self.db.get_cutover_task(self.task_id)['status'], 'reporting')
        _finish_process_failure(self.db, report_id, outcome_unknown=True)
        self.assertEqual(self.db.get_cutover_report(report_id)['status'], 'success')

    def test_resolved_queued_job_does_not_start_a_process(self):
        report_id, _ = self.claim()
        finish_job(self.db, report_id, 'success')
        with patch('rpa.report_jobs.subprocess.Popen') as process:
            run_report_process(self.db, self.root, report_id)
        process.assert_not_called()

    def test_authorized_resolution_obeys_active_worker_lock_and_updates_atomically(self):
        import api_server
        report_id, _ = self.claim()
        client = api_server.app.test_client()
        with patch.object(api_server, 'email_db', self.db), patch.object(api_server, 'API_KEY', 'test-key'):
            token, csrf = self.repo.create_session(self.people[0][0], 'test-key')
            client.set_cookie('noc_session', token)
            path = f'/api/cutover/reports/{report_id}/resolve'
            body = {'resolution': 'success', 'note': '已核对模拟综调记录'}
            self.repo.set_grants(self.people[0][0].user_id, [{'account_id': self.account, 'can_operate': False}])
            self.assertEqual(client.post(path, json=body, headers={'X-CSRF-Token': csrf}).status_code, 403)
            self.repo.set_grants(self.people[0][0].user_id, [])
            self.assertEqual(client.post(path, json=body, headers={'X-CSRF-Token': csrf}).status_code, 404)
            self.repo.set_grants(self.people[0][0].user_id, [{'account_id': self.account, 'can_operate': True}])
            with session_lock(self.people[0][1].lock_path):
                self.assertEqual(client.post(path, json=body, headers={'X-CSRF-Token': csrf}).status_code, 409)
                self.assertEqual(client.post(path, json=body, headers={'Authorization': 'Bearer test-key'}).status_code, 409)
            self.assertEqual(client.post(path, json=body, headers={'X-CSRF-Token': csrf}).status_code, 200)
        self.assertEqual(get_job(self.db, report_id)['status'], 'success')
        self.assertEqual(self.db.get_cutover_task(self.task_id)['status'], 'reported')
        self.assertEqual(self.db.get_cutover_report(report_id)['result']['execution_identity']['username'], 'portal-alice')
        self.assertEqual(self.db.get_cutover_report(report_id)['result']['resolved_by'], 'alice')

