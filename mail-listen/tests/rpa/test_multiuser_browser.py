import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from database import EmailDatabase
from mail_artifacts import customer_excel_path
from rpa.report_jobs import claim_report, run_report_process
from rpa.session_config import PortalSessionSettings
from rpa.session_models import LoginMode, PortalEnvironment
from rpa.user_sessions import PortalSessionRegistry
from tests.rpa.test_rpa_cutover_report import REPORT_PAGE
from tests.rpa.test_rpa_session_service import LOGIN_PAGE, DASHBOARD_PAGE
from user_access import UserAccessRepository


class MultiuserPortalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        cookie = self.headers.get('Cookie', '')
        if 'portal_auth=1' not in cookie:
            body = LOGIN_PAGE.replace(b"=== 'operator'", b".startsWith('portal-')").replace(
                b"document.cookie = 'portal_auth=1; path=/';",
                b"document.cookie = 'portal_auth=1; path=/'; document.cookie = 'portal_user=' + document.querySelector('#user').value + '; path=/';")
        elif self.path.startswith('/portal/'):
            self.server.report_cookies.append(cookie)
            body = REPORT_PAGE
        else:
            body = DASHBOARD_PAGE
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class MultiuserBrowserIsolationTest(unittest.TestCase):
    def test_two_real_logins_and_concurrent_report_processes_keep_their_cookies(self):
        with tempfile.TemporaryDirectory() as temp, ThreadingHTTPServer(('127.0.0.1', 0), MultiuserPortalHandler) as server:
            server.report_cookies = []
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = Path(temp)
            origin = f'http://127.0.0.1:{server.server_port}'
            settings = PortalSessionSettings(_env_file=None,
                test_login_url=origin + '/login', test_mobile_login_url=origin + '/login',
                test_session_check_url=origin + '/dashboard', username_selector='#user',
                password_selector='#password', captcha_input_selector='#captcha-input',
                captcha_image_selector='#captcha', submit_selector='#login', post_login_ready_selector='#ready',
                session_keepalive_enabled=False, timeout_ms=5000, report_action_delay_ms=0)
            db = EmailDatabase(str(root / 'test.db'))
            repo = UserAccessRepository(db)
            try:
                with PortalSessionRegistry(db, root, settings) as registry:
                    entries = []
                    for name in ('alice', 'bob'):
                        user = repo.create_user(name, 'secure-password')
                        principal = repo.get_principal(user['id'])
                        account = db.add_mail_account({'email_address': name + '@example.com', 'imap_server': 'example.com'})
                        repo.set_grants(user['id'], [{'account_id': account, 'can_operate': True}])
                        db.add_email_record(17, receiver=name + '@example.com', content='test')
                        email = db.get_email_record(17, receiver=name + '@example.com')
                        task_id = db.upsert_cutover_task(email_records_id=email['id'], line_type='customer',
                            fill_result={'circuits': [{'id': name}]}, customer_excel_filename='report.xlsx')
                        db.update_cutover_task(task_id, status='confirmed')
                        excel = customer_excel_path(root, mailbox_address=email['receiver'], email_uid=17, filename='report.xlsx')
                        excel.parent.mkdir(parents=True)
                        excel.write_bytes(name.encode())
                        service = registry.for_principal(principal)
                        attempt = service.begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
                        entries.append((name, principal, service, attempt, task_id))
                    reports = []
                    for name, principal, service, attempt, task_id in entries:
                        status = service.login_with_password(attempt.attempt_id, 'portal-' + name, 'secret', '42')
                        self.assertTrue(status.authenticated)
                        cookies = json.loads(status.state_path.read_text())['cookies']
                        self.assertEqual(next(cookie['value'] for cookie in cookies if cookie['name'] == 'portal_user'), 'portal-' + name)
                        reports.append(claim_report(db, principal, service, task_id, PortalEnvironment.TEST, root)[0])
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [pool.submit(run_report_process, db, root, report_id) for report_id in reports]
                        for future in futures:
                            future.result(timeout=90)
                    for report_id, (name, *_) in zip(reports, entries):
                        report = db.get_cutover_report(report_id)
                        self.assertEqual(report['status'], 'success', report)
                        self.assertEqual(report['result']['execution_identity']['username'], 'portal-' + name)
                    self.assertTrue(any('portal_user=portal-alice' in value for value in server.report_cookies))
                    self.assertTrue(any('portal_user=portal-bob' in value for value in server.report_cookies))
                    # Expired saved cookies must not leave relogin competing with
                    # checks/keepalive from the old session or affect another user.
                    alice, bob = entries[0][2], entries[1][2]
                    old = alice.status(PortalEnvironment.TEST)
                    old.state_path.write_text('{"cookies": [], "origins": []}')
                    self.assertFalse(alice.status(PortalEnvironment.TEST).authenticated)
                    previous = alice.active[old.session_version]
                    attempt = alice.begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
                    self.assertTrue(alice.refresh_captcha(attempt.attempt_id).captcha_data_url)
                    self.assertIsNone(previous.keep_alive(PortalEnvironment.TEST))
                    self.assertFalse(alice.status(PortalEnvironment.TEST).authenticated)
                    renewed = alice.login_with_password(attempt.attempt_id, 'portal-alice', 'secret', '42')
                    self.assertTrue(renewed.authenticated)
                    self.assertNotEqual(renewed.session_version, old.session_version)
                    self.assertTrue(alice.status(PortalEnvironment.TEST).authenticated)
                    self.assertTrue(bob.status(PortalEnvironment.TEST).authenticated)
            finally:
                server.shutdown()
                thread.join(timeout=5)
