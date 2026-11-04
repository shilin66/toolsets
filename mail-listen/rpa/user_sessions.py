"""Personal portal sessions. Legacy global cookies are never inherited."""
import hashlib
import os
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

from .isolation import session_lock
from .session_config import PortalSessionSettings
from .session_models import PortalEnvironment, PortalSessionError, SessionState, SessionStatus
from .session_service import PortalSessionService


class PortalSessionRegistry:
    def __init__(self, db, data_dir, settings=None, *, service_factory=PortalSessionService):
        self.db, self.root = db, Path(data_dir) / 'rpa' / 'users'
        self.settings = settings or PortalSessionSettings()
        self.factory = service_factory
        self.services = {}
        self.lock = RLock()

    def for_principal(self, principal):
        if principal.is_admin:
            raise PortalSessionError('ADMIN_RPA_FORBIDDEN', '综调会话仅限普通用户账号使用')
        with self.lock:
            if principal.key not in self.services:
                self.services[principal.key] = PersonalPortalSession(self, principal)
            return self.services[principal.key]

    def close(self):
        for service in self.services.values():
            service.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class PersonalPortalSession:
    def __init__(self, registry, principal):
        self.registry, self.principal = registry, principal
        self.root = registry.root / principal.key
        self.lock_path = self.root / 'activity.lock'
        self.binding_lock_path = self.root / 'binding.lock'
        self.pending = None
        self.attempt = None
        self.phone = None
        self.active = {}

    def _record(self, environment):
        with self.registry.db.get_connection() as conn:
            row = conn.execute('SELECT * FROM portal_sessions WHERE principal_key=? AND environment=?',
                               (self.principal.key, str(environment))).fetchone()
        return dict(row) if row else None

    def _settings(self, directory, *, pending=False):
        return self.registry.settings.model_copy(update={
            'test_state_path': directory / 'auth-test.json',
            'production_state_path': directory / 'auth-production.json',
            'artifact_dir': directory / 'artifacts',
            'session_lock_path': None if pending else self.lock_path,
            'session_keepalive_enabled': False if pending else self.registry.settings.session_keepalive_enabled,
        })

    def _assert_idle(self, *, allow_reauthentication=False):
        from .report_queue import login_required
        with self.registry.db.get_connection() as conn:
            jobs = conn.execute("SELECT status FROM rpa_report_jobs WHERE principal_key=? AND status IN ('pending','running','paused','waiting_login')",
                                (self.principal.key,)).fetchall()
            if allow_reauthentication and not any(row['status'] == 'running' for row in jobs):
                if login_required(conn, self.principal.key) or all(row['status'] == 'paused' for row in jobs):
                    return
        if jobs:
            raise PortalSessionError('RPA_BUSY', '当前用户有排队或执行中的上报，请完成后再切换账号')

    def _assert_queue_identity(self, environment, username=None):
        with self.registry.db.get_connection() as conn:
            jobs = conn.execute("""SELECT username,environment FROM rpa_report_jobs WHERE principal_key=?
                AND (status IN ('pending','running','paused','waiting_login') OR
                     (status='interrupted' AND EXISTS (SELECT 1 FROM rpa_report_queues q
                         WHERE q.principal_key=rpa_report_jobs.principal_key AND q.login_required=1)))""",
                (self.principal.key,)).fetchall()
        if any(row['environment'] != str(environment) or
               (username is not None and row['username'].casefold() != username.casefold()) for row in jobs):
            raise PortalSessionError('QUEUE_IDENTITY_MISMATCH', '请使用队列原有的综调账号和环境重新登录')
        return bool(jobs)

    def _active_service(self, path, version, environment):
        def allowed():
            if self._login_pending():
                return False
            current = self._record(environment)
            if not current or current['version'] != version:
                return False
            try:
                self._assert_idle()
                return True
            except PortalSessionError:
                return False
        return self.registry.factory(self._settings(path.parent), keepalive_allowed=allowed)

    def _login_pending(self):
        attempt = self.attempt
        return self.pending is not None and attempt is not None and attempt.expires_at > datetime.now(UTC)

    def begin(self, mode, environment=None):
        with session_lock(self.binding_lock_path, blocking=True), session_lock(self.lock_path):
            self._assert_idle(allow_reauthentication=True)
            environment = environment or self.registry.settings.default_environment
            if self._assert_queue_identity(environment):
                with self.registry.db.get_connection() as conn:
                    conn.execute('INSERT INTO rpa_report_queues VALUES (?,1) ON CONFLICT(principal_key) '
                                 'DO UPDATE SET login_required=1', (self.principal.key,))
                    conn.commit()
            if self.pending:
                self.pending.close()
            self.pending = self.attempt = self.phone = None
            directory = self.root / 'sessions' / uuid4().hex
            directory.mkdir(parents=True, mode=0o700)
            self.pending = self.registry.factory(self._settings(directory, pending=True))
            try:
                self.attempt = self.pending.begin(mode, environment or self.registry.settings.default_environment)
            except Exception:
                self.pending.close()
                self.pending = None
                raise
            return self.attempt

    def _pending(self, attempt_id):
        if not self.pending or not self.attempt or self.attempt.attempt_id != attempt_id:
            raise PortalSessionError('ATTEMPT_NOT_FOUND', '当前用户的登录请求不存在或已失效，请重新获取验证码')
        if self.attempt.expires_at < datetime.now(UTC):
            self.pending.close()
            self.pending = None
            raise PortalSessionError('ATTEMPT_EXPIRED', '登录请求已过期，请重新获取验证码')
        return self.pending

    def refresh_captcha(self, attempt_id):
        with session_lock(self.lock_path):
            self.attempt = self._pending(attempt_id).refresh_captcha(attempt_id)
            return self.attempt

    def _account_available(self, username):
        environment = str(self.attempt.environment)
        account_key = self._canonical_account(username).casefold()
        with self.registry.db.get_connection() as conn:
            row = conn.execute('SELECT principal_key FROM portal_sessions WHERE environment=? AND account_key=?',
                (environment, account_key)).fetchone()
        if row and row['principal_key'] == 'admin':
            # Retire only the obsolete binding, never inherit its cookies. The old
            # activity lock also protects an in-flight worker/keepalive during upgrade.
            with session_lock(self.registry.root / 'admin' / 'activity.lock'):
                with self.registry.db.get_connection() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    if conn.execute("SELECT 1 FROM rpa_report_jobs WHERE principal_key='admin' AND status IN ('pending','running','interrupted')").fetchone():
                        raise PortalSessionError('RPA_BUSY', '旧管理员上报尚未结束或待核对，请先处理上报记录再登录')
                    conn.execute("DELETE FROM portal_sessions WHERE principal_key='admin' AND environment=? AND account_key=?",
                                 (environment, account_key))
                    row = conn.execute('SELECT principal_key FROM portal_sessions WHERE environment=? AND account_key=?',
                                       (environment, account_key)).fetchone()
                    conn.commit()
        if row and row['principal_key'] != self.principal.key:
            raise PortalSessionError('ACCOUNT_IN_USE', '该综调账号已被其他用户绑定，请使用独立账号')

    def _canonical_account(self, username):
        aliases = {key.strip().casefold(): value.strip() for key, value in self.registry.settings.account_aliases.items()}
        return aliases.get(username.strip().casefold(), username.strip())

    def _login(self, attempt_id, username, callback):
        with session_lock(self.binding_lock_path, blocking=True), session_lock(self.lock_path):
            self._assert_idle(allow_reauthentication=True)
            service = self._pending(attempt_id)
            username = self._canonical_account(username)
            self._assert_queue_identity(self.attempt.environment, username)
            account_key = username.casefold()
            account_lock = self.registry.root / 'accounts' / hashlib.sha256(
                f'{self.attempt.environment}:{account_key}'.encode()).hexdigest()
            with session_lock(account_lock):
                self._account_available(username)
                status = callback(service)
                if not status.authenticated:
                    return status
                path = status.state_path.resolve()
                os.chmod(path, 0o600)
                version = path.parent.name
                try:
                    with self.registry.db.get_connection() as conn:
                        conn.execute('BEGIN IMMEDIATE')
                        conn.execute('DELETE FROM portal_sessions WHERE principal_key=?', (self.principal.key,))
                        conn.execute('INSERT INTO portal_sessions VALUES (?,?,?,?,?,?)',
                            (self.principal.key, str(status.environment), username.strip(), account_key, version, str(path)))
                        from .report_queue import rebind_waiting_jobs
                        rebind_waiting_jobs(conn, self.principal.key, username, str(status.environment), version,
                                            path, self._settings(path.parent).model_dump_json())
                        conn.commit()
                except sqlite3.IntegrityError as error:
                    path.unlink(missing_ok=True)
                    raise PortalSessionError('ACCOUNT_IN_USE', '该综调账号已被其他用户绑定') from error
                for previous in self.active.values():
                    previous.close()
                self.active.clear()
                service.close()
                self.pending = None
                # Start this user's independent keepalive after successful authentication.
                self.active[version] = self._active_service(path, version, status.environment)
                return replace(status, portal_username=username.strip(), session_version=version)

    def login_with_password(self, attempt_id, username, password, captcha):
        return self._login(attempt_id, username,
            lambda service: service.login_with_password(attempt_id, username, password, captcha))

    def request_sms(self, attempt_id, phone, password, captcha):
        with session_lock(self.lock_path):
            self._assert_idle(allow_reauthentication=True)
            service = self._pending(attempt_id)
            self._assert_queue_identity(self.attempt.environment, self._canonical_account(phone))
            self._account_available(phone)
            result = service.request_sms(attempt_id, phone, password, captcha)
            self.phone = phone
            return result

    def verify_sms(self, attempt_id, sms_code):
        if not self.phone:
            raise PortalSessionError('ATTEMPT_NOT_FOUND', '请先获取短信验证码')
        return self._login(attempt_id, self.phone, lambda service: service.verify_sms(attempt_id, sms_code))

    def _reporting_status(self, record, environment):
        return SessionStatus(SessionState.UNAVAILABLE, False, datetime.now(UTC),
            '该账号正在处理上报队列，可继续提交任务，系统将按顺序执行', environment,
            portal_username=record['username'], session_version=record['version'], reporting=True)

    def status(self, environment=None):
        environment = environment or self.registry.settings.default_environment
        record = self._record(environment)
        if not record:
            info = self.registry.settings.describe_environment(environment)
            return SessionStatus(SessionState.LOGIN_REQUIRED if info.configured else SessionState.UNAVAILABLE,
                False, datetime.now(UTC), '请使用个人综调账号登录' if info.configured else '当前环境地址未配置',
                environment, info.configured, info.password_login_url, info.mobile_login_url,
                self.root / 'not-authenticated.json')
        version = record['version']
        from .report_queue import login_required, WAITING_NOTE
        with self.registry.db.get_connection() as conn:
            if login_required(conn, self.principal.key):
                info = self.registry.settings.describe_environment(environment)
                return SessionStatus(SessionState.LOGIN_REQUIRED, False, datetime.now(UTC), WAITING_NOTE,
                    environment, info.configured, info.password_login_url, info.mobile_login_url,
                    Path(record['state_path']), portal_username=record['username'])
        try:
            self._assert_idle()
        except PortalSessionError:
            return self._reporting_status(record, environment)
        if self._login_pending():
            info = self.registry.settings.describe_environment(environment)
            return SessionStatus(SessionState.LOGIN_REQUIRED, False, datetime.now(UTC),
                '正在登录，请完成验证码验证', environment, info.configured,
                info.password_login_url, info.mobile_login_url, Path(record['state_path']),
                portal_username=record['username'])
        with self.registry.lock:
            if version not in self.active:
                self.active[version] = self._active_service(Path(record['state_path']), version, environment)
            service = self.active[version]
        try:
            status = service.status(environment)
        except PortalSessionError as error:
            if error.code == 'RPA_BUSY':
                # A report can start after the idle check but before the browser locks.
                try:
                    self._assert_idle()
                except PortalSessionError:
                    return self._reporting_status(record, environment)
            raise
        # Preserve the last account for display; only an authenticated check yields a usable version.
        return replace(status, portal_username=record['username'],
                       session_version=version if status.authenticated else None)

    def report_binding(self, environment):
        # Caller holds binding.lock; reports may queue while activity.lock is held.
        if self._login_pending():
            raise PortalSessionError('LOGIN_REQUIRED', '正在登录，请完成验证码验证后再上报')
        from .report_queue import login_required, WAITING_NOTE
        with self.registry.db.get_connection() as conn:
            if login_required(conn, self.principal.key):
                raise PortalSessionError('LOGIN_REQUIRED', WAITING_NOTE)
        record = self._record(environment)
        if not record or not Path(record['state_path']).is_file():
            raise PortalSessionError('LOGIN_REQUIRED', '请先登录所选环境的个人综调账号')
        return {**record, 'settings_json': self._settings(Path(record['state_path']).parent).model_dump_json()}

    def logout(self):
        with session_lock(self.binding_lock_path, blocking=True), session_lock(self.lock_path):
            self._assert_idle()
            self.close()
            with self.registry.db.get_connection() as conn:
                conn.execute('DELETE FROM portal_sessions WHERE principal_key=?', (self.principal.key,))
                conn.commit()

    def close(self):
        if self.pending:
            self.pending.close()
            self.pending = None
        for service in self.active.values():
            service.close()
        self.active.clear()
