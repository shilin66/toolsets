import unittest
from unittest.mock import patch

from tests.api import test_cutover_task_api as fixtures
from rpa.report_jobs import get_job
from rpa.session_models import PortalSessionError


class ReportQueueLifecycleApiTest(unittest.TestCase):
    def setUp(self):
        self.api = fixtures.CutoverTaskApiTest()
        self.api.setUp()
        self.addCleanup(self.api.tearDown)
        self.tasks = self.api.fill_tasks(self.api.post_fill_mixed(self.api.mixed_fill_payload()))
        for task in self.tasks:
            self.api.db.update_cutover_task(task['id'], status='confirmed')
        self.scheduled = []
        scheduling = patch.object(fixtures.api_server, 'submit_cutover_report_job', side_effect=self.scheduled.append)
        scheduling.start()
        self.addCleanup(scheduling.stop)
        self.reports = []
        for task in self.tasks:
            response = self.post(f'/api/cutover/tasks/{task["id"]}/report')
            self.assertEqual(response.status_code, 202, response.get_json())
            self.reports.append(response.get_json()['data']['report_id'])

    def post(self, path, body=None):
        return self.api.report_client.post(path, headers=self.api.report_headers, json=body or {})

    def test_login_expiry_pauses_all_then_password_login_automatically_wakes_queue(self):
        with patch.object(fixtures.api_server, 'report_cutover_task',
                          side_effect=PortalSessionError('RPA_SESSION_REQUIRED', '登录失效')) as report:
            self.scheduled[0]()
        self.assertEqual(report.call_count, 1)
        self.assertEqual([get_job(self.api.db, rid)['status'] for rid in self.reports],
                         ['waiting_login', 'waiting_login'])
        response = self.post('/api/rpa/session/attempts', {'mode': 'password', 'environment': 'test'})
        self.assertEqual(response.status_code, 201, response.get_json())
        attempt = response.get_json()['data']['attempt_id']
        count = len(self.scheduled)
        response = self.post(f'/api/rpa/session/attempts/{attempt}/password',
                             {'username':'portal-admin', 'password':'password', 'captcha':'42'})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(len(self.scheduled), count + 1)
        with patch.object(fixtures.api_server, 'report_cutover_task', return_value={'status':'success'}), \
                patch.object(fixtures.api_server, 'ensure_source_email_archived'):
            self.scheduled[-1]()
        self.assertEqual([get_job(self.api.db, rid)['status'] for rid in self.reports], ['success', 'success'])

    def test_pause_and_resume_are_idempotent_and_require_operation_permission(self):
        rid = self.reports[0]
        for _ in range(2):
            self.assertEqual(self.post(f'/api/cutover/reports/{rid}/pause').status_code, 200)
        self.assertEqual(get_job(self.api.db, rid)['status'], 'paused')
        self.assertEqual(self.post(f'/api/cutover/reports/{rid}/resume').status_code, 200)
        self.assertEqual(get_job(self.api.db, rid)['status'], 'pending')
        self.api.access_repo.set_grants(self.api.operator['id'], [])
        self.assertEqual(self.post(f'/api/cutover/reports/{rid}/pause').status_code, 404)

    def test_post_submit_login_expiry_requires_reconciliation(self):
        with patch.object(fixtures.api_server, 'report_cutover_task',
                          side_effect=PortalSessionError('RPA_SESSION_REQUIRED_AFTER_SUBMIT', '提交后登录失效')):
            self.scheduled[0]()
        self.assertEqual(get_job(self.api.db, self.reports[0])['status'], 'interrupted')
        self.assertEqual(get_job(self.api.db, self.reports[1])['status'], 'waiting_login')
        self.assertEqual(self.post(f'/api/cutover/tasks/{self.tasks[0]["id"]}/report').status_code, 400)
        self.assertEqual(self.post(f'/api/cutover/reports/{self.reports[0]}/resolve',
            {'resolution':'failed','note':'已确认综调没有该任务'}).status_code, 200)

    def test_main_startup_automatically_schedules_recovered_pending_jobs(self):
        import main
        from rpa.report_jobs import finish_job
        finish_job(self.api.db, self.reports[0], 'running')
        self.api.db.update_cutover_report(self.reports[0], status='running')
        count = len(self.scheduled)
        with patch.object(main.app, 'run') as serve:
            main.MainService.__new__(main.MainService).start_api_server()
        serve.assert_called_once()
        self.assertEqual(get_job(self.api.db, self.reports[0])['status'], 'interrupted')
        self.assertEqual(len(self.scheduled), count + 1)

    def test_sms_login_restores_queue_using_the_original_account(self):
        from rpa.report_queue import pause_for_login
        from types import SimpleNamespace
        pause_for_login(self.api.db, self.reports[0], 'RPA_SESSION_REQUIRED', 'expired')
        attempt = self.post('/api/rpa/session/attempts', {'mode':'mobile','environment':'test'}).get_json()['data']['attempt_id']
        pending = self.api.session_service.pending
        with patch.object(pending, 'request_sms', create=True, return_value=SimpleNamespace(attempt_id=attempt, sms_requested=True)):
            response = self.post(f'/api/rpa/session/attempts/{attempt}/sms',
                {'phone':'portal-admin','password':'password','captcha':'42'})
        self.assertEqual(response.status_code, 200, response.get_json())
        with patch.object(pending, 'verify_sms', create=True,
                side_effect=lambda aid, code: pending.login_with_password(aid, 'portal-admin', 'password', '42')):
            response = self.post(f'/api/rpa/session/attempts/{attempt}/sms/verify', {'sms_code':'123456'})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual([get_job(self.api.db, rid)['status'] for rid in self.reports], ['pending','pending'])
