import json
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from database import EmailDatabase
from rpa.session_config import PortalSessionSettings
from rpa.session_models import LoginAttempt, LoginMode, PortalEnvironment, SessionState, SessionStatus
from user_access import Principal


class FakeSessionService:
    def __init__(self, settings, **kwargs):
        self.settings = settings
        self.keepalive_allowed = kwargs.get('keepalive_allowed', lambda: True)
        self.attempt = None
        self.closed = False

    def begin(self, mode, environment):
        self.attempt = LoginAttempt(str(id(self)), mode, 'data:image/png;base64,test',
                                    datetime.now(UTC) + timedelta(minutes=5), environment)
        return self.attempt

    def login_with_password(self, attempt_id, username, password, captcha):
        if not self.attempt or attempt_id != self.attempt.attempt_id:
            from rpa.session_models import PortalSessionError
            raise PortalSessionError('ATTEMPT_NOT_FOUND', 'missing')
        path = self.settings.resolve_environment(self.attempt.environment).state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'cookies': [{'name': 'user', 'value': username}], 'origins': []}))
        return self.status(self.attempt.environment)

    def status(self, environment):
        target = self.settings.resolve_environment(environment)
        authenticated = target.state_path.exists()
        return SessionStatus(SessionState.AUTHENTICATED if authenticated else SessionState.LOGIN_REQUIRED,
                             authenticated, datetime.now(UTC), 'test', environment, state_path=target.state_path)

    def close(self):
        self.closed = True


class UserPortalSessionsTest(unittest.TestCase):
    def setUp(self):
        from rpa.user_sessions import PortalSessionRegistry
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = EmailDatabase(str(self.root / 'test.db'))
        self.settings = PortalSessionSettings.model_construct(
            test_login_url='http://localhost/login', test_mobile_login_url='http://localhost/mobile',
            test_session_check_url='http://localhost/dashboard', session_keepalive_enabled=False)
        self.registry = PortalSessionRegistry(self.db, self.root, self.settings, service_factory=FakeSessionService)
        self.addCleanup(self.registry.close)
        self.alice = Principal(1, 'alice', 'Alice')
        self.bob = Principal(2, 'bob', 'Bob')

    def login(self, principal, account):
        session = self.registry.for_principal(principal)
        attempt = session.begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
        return session.login_with_password(attempt.attempt_id, account, 'secret', '42')

    def test_admin_cannot_create_personal_portal_service(self):
        from rpa.session_models import PortalSessionError
        with self.assertRaises(PortalSessionError) as caught:
            self.registry.for_principal(Principal.admin())
        self.assertEqual(caught.exception.code, 'ADMIN_RPA_FORBIDDEN')
        self.assertNotIn('admin', self.registry.services)

    def test_relogin_pauses_old_session_checks_until_attempt_expires(self):
        from unittest.mock import patch
        self.login(self.alice, 'portal-a')
        service = self.registry.for_principal(self.alice)
        active = next(iter(service.active.values()))
        self.assertTrue(active.keepalive_allowed())
        service.begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
        self.assertFalse(active.keepalive_allowed())
        with patch.object(active, 'status', side_effect=AssertionError('old browser must stay idle')):
            status = service.status(PortalEnvironment.TEST)
        self.assertFalse(status.authenticated)
        self.assertIsNone(status.session_version)
        self.assertEqual(status.portal_username, 'portal-a')
        service.attempt = replace(service.attempt, expires_at=datetime.now(UTC) - timedelta(seconds=1))
        self.assertTrue(active.keepalive_allowed())
        self.assertTrue(service.status(PortalEnvironment.TEST).authenticated)

    def seed_legacy_admin_binding(self):
        path = self.root / 'legacy-admin.json'
        path.write_text('{"cookies": [{"name": "old", "value": "never-inherit"}]}')
        with self.db.get_connection() as conn:
            conn.execute('INSERT INTO portal_sessions VALUES (?,?,?,?,?,?)',
                         ('admin', 'test', 'portal-a', 'portal-a', 'legacy', str(path)))
            conn.commit()
        return path

    def test_failed_relogin_begin_clears_attempt_and_resumes_old_session_checks(self):
        from unittest.mock import patch
        from rpa.session_models import PortalSessionError
        self.login(self.alice, 'portal-a')
        service = self.registry.for_principal(self.alice)
        service.begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
        active = next(iter(service.active.values()))
        with patch.object(FakeSessionService, 'begin', side_effect=PortalSessionError('RPA_UNAVAILABLE', 'test')):
            with self.assertRaises(PortalSessionError):
                service.begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
        self.assertIsNone(service.pending)
        self.assertIsNone(service.attempt)
        self.assertTrue(active.keepalive_allowed())
        self.assertTrue(service.status(PortalEnvironment.TEST).authenticated)

    def test_user_can_reauthenticate_account_previously_bound_to_admin(self):
        old_path = self.seed_legacy_admin_binding()
        logged_in = self.login(self.alice, 'portal-a')
        self.assertTrue(logged_in.authenticated)
        self.assertNotEqual(logged_in.state_path, old_path)
        self.assertNotIn('never-inherit', logged_in.state_path.read_text())
        self.assertIn('never-inherit', old_path.read_text())
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT principal_key FROM portal_sessions').fetchone()[0], self.alice.key)

    def test_old_admin_activity_and_unresolved_jobs_block_binding_release(self):
        from rpa.isolation import session_lock
        from rpa.session_models import PortalSessionError
        self.seed_legacy_admin_binding()
        service = self.registry.for_principal(self.alice)
        attempt = service.begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
        with session_lock(self.registry.root / 'admin' / 'activity.lock'):
            with self.assertRaises(PortalSessionError):
                service.login_with_password(attempt.attempt_id, 'portal-a', 'secret', '42')
        with self.db.get_connection() as conn:
            conn.execute('''INSERT INTO rpa_report_jobs (report_id,principal_key,username,environment,
                session_version,state_path,task_snapshot,settings_json) VALUES (1,'admin','portal-a','test','old','','{}','{}')''')
            conn.commit()
        with self.assertRaises(PortalSessionError) as caught:
            service.login_with_password(attempt.attempt_id, 'portal-a', 'secret', '42')
        self.assertEqual(caught.exception.code, 'RPA_BUSY')
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT principal_key FROM portal_sessions').fetchone()[0], 'admin')

    def test_two_users_keep_independent_attempts_and_states(self):
        alice = self.registry.for_principal(self.alice)
        bob = self.registry.for_principal(self.bob)
        first = alice.begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
        second = bob.begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
        a = alice.login_with_password(first.attempt_id, 'portal-a', 'secret', '42')
        b = bob.login_with_password(second.attempt_id, 'portal-b', 'secret', '42')
        self.assertNotEqual(a.state_path, b.state_path)
        self.assertEqual(a.portal_username, 'portal-a')
        self.assertEqual(b.portal_username, 'portal-b')
        self.assertEqual(json.loads(a.state_path.read_text())['cookies'][0]['value'], 'portal-a')
        self.assertTrue(alice.status(PortalEnvironment.TEST).authenticated)

    def test_another_users_attempt_cannot_be_used(self):
        from rpa.session_models import PortalSessionError
        attempt = self.registry.for_principal(self.alice).begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
        with self.assertRaises(PortalSessionError):
            self.registry.for_principal(self.bob).refresh_captcha(attempt.attempt_id)

    def test_expired_session_retains_account_label_without_authorizing_reporting(self):
        old = self.login(self.alice, 'portal-a')
        old.state_path.unlink()
        status = self.registry.for_principal(self.alice).status(PortalEnvironment.TEST)
        self.assertEqual(status.state, SessionState.LOGIN_REQUIRED)
        self.assertFalse(status.authenticated)
        self.assertEqual(status.portal_username, 'portal-a')
        self.assertIsNone(status.session_version)
        never_logged_in = self.registry.for_principal(self.bob).status(PortalEnvironment.TEST)
        self.assertIsNone(never_logged_in.portal_username)

    def test_same_remote_account_cannot_be_bound_to_two_users(self):
        from rpa.session_models import PortalSessionError
        self.login(self.alice, 'portal-a')
        with self.assertRaises(PortalSessionError) as error:
            self.login(self.bob, 'PORTAL-A')
        self.assertEqual(error.exception.code, 'ACCOUNT_IN_USE')

    def test_relogin_gets_new_version_without_overwriting_previous_state(self):
        old = self.login(self.alice, 'portal-a')
        old_data = old.state_path.read_bytes()
        new = self.login(self.alice, 'portal-c')
        self.assertNotEqual(old.session_version, new.session_version)
        self.assertNotEqual(old.state_path, new.state_path)
        self.assertEqual(old.state_path.read_bytes(), old_data)

    def test_mobile_login_without_mapping_uses_phone_and_prevents_duplicate_binding(self):
        from unittest.mock import patch
        from rpa.session_models import PortalSessionError
        phone = '13800000000'
        service = self.registry.for_principal(self.alice)
        attempt = service.begin(LoginMode.MOBILE, PortalEnvironment.TEST)
        pending = service.pending
        with patch.object(pending, 'request_sms', return_value='sent', create=True) as send:
            self.assertEqual(service.request_sms(attempt.attempt_id, phone, 'password', '42'), 'sent')
            send.assert_called_once_with(attempt.attempt_id, phone, 'password', '42')
        with patch.object(pending, 'verify_sms', create=True,
                          side_effect=lambda attempt_id, code: pending.login_with_password(attempt_id, phone, 'password', '42')):
            status = service.verify_sms(attempt.attempt_id, '123456')
        self.assertTrue(status.authenticated)
        self.assertEqual(status.portal_username, phone)
        other = self.registry.for_principal(self.bob)
        other_attempt = other.begin(LoginMode.MOBILE, PortalEnvironment.TEST)
        with patch.object(other.pending, 'request_sms', create=True) as send:
            with self.assertRaises(PortalSessionError) as error:
                other.request_sms(other_attempt.attempt_id, phone, 'password', '42')
            send.assert_not_called()
        self.assertEqual(error.exception.code, 'ACCOUNT_IN_USE')

    def test_mobile_login_with_optional_mapping_still_checks_canonical_account(self):
        from unittest.mock import patch
        from rpa.session_models import PortalSessionError
        self.registry.settings = self.settings.model_copy(update={'account_aliases': {'13800000000': 'portal-a'}})
        self.login(self.alice, 'portal-a')
        service = self.registry.for_principal(self.bob)
        attempt = service.begin(LoginMode.MOBILE, PortalEnvironment.TEST)
        with patch.object(service.pending, 'request_sms', create=True) as send:
            with self.assertRaises(PortalSessionError) as error:
                service.request_sms(attempt.attempt_id, '13800000000', 'password', '42')
            send.assert_not_called()
        self.assertEqual(error.exception.code, 'ACCOUNT_IN_USE')

    def test_alias_cannot_bypass_duplicate_account_check(self):
        from rpa.session_models import PortalSessionError
        self.registry.settings = self.settings.model_copy(update={'account_aliases': {'13800000000': 'portal-a'}})
        self.login(self.alice, 'portal-a')
        with self.assertRaises(PortalSessionError) as error:
            self.login(self.bob, '13800000000')
        self.assertEqual(error.exception.code, 'ACCOUNT_IN_USE')

    def test_global_legacy_state_is_not_adopted_by_any_user(self):
        # Use a private fixture, never the configured production state path.
        isolated = self.settings.model_copy(update={'test_state_path': self.root / 'legacy.json'})
        isolated.test_state_path.write_text('{"cookies": [], "origins": []}')
        from rpa.user_sessions import PortalSessionRegistry
        with PortalSessionRegistry(self.db, self.root / 'second', isolated, service_factory=FakeSessionService) as registry:
            self.assertFalse(registry.for_principal(self.alice).status(PortalEnvironment.TEST).authenticated)
