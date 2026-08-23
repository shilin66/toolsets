from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Event, Lock, Thread
from typing import assert_never

from .session_browser import PortalSessionBrowser
from .session_config import PortalSessionSettings
from .session_models import (
    LoginAttempt,
    LoginMode,
    PortalEnvironment,
    PortalSessionError,
    SessionKeepaliveState,
    SessionKeepaliveStatus,
    SessionState,
    SessionStatus,
    SmsRequestResult,
)


class PortalSessionService:
    def __init__(
        self, settings: PortalSessionSettings | None = None,
        keepalive_allowed: Callable[[], bool] | None = None,
    ) -> None:
        self.settings = settings or PortalSessionSettings()
        self._keepalive_allowed = keepalive_allowed or (lambda: True)
        self._browser = PortalSessionBrowser(self.settings)
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="portal-session",
        )
        self._closed = False
        self._keepalive_stop = Event()
        self._keepalive_lock = Lock()
        keepalive_enabled = self.settings.session_keepalive_enabled
        self._keepalive_status = SessionKeepaliveStatus(
            enabled=keepalive_enabled,
            interval_seconds=self.settings.session_keepalive_interval_seconds,
            state=(
                SessionKeepaliveState.WAITING
                if keepalive_enabled
                else SessionKeepaliveState.DISABLED
            ),
            checked_at=None,
            successful_at=None,
            environment=None,
            message=(
                "登录保持已开启，等待已登录会话"
                if keepalive_enabled
                else "登录保持已关闭"
            ),
        )
        self._keepalive_thread: Thread | None = None
        if keepalive_enabled:
            self._keepalive_thread = Thread(
                target=self._keepalive_loop,
                name="portal-session-keepalive",
                daemon=True,
            )
            self._keepalive_thread.start()

    def status(
        self,
        environment: PortalEnvironment | None = None,
    ) -> SessionStatus:
        selected = environment or self.settings.default_environment
        status = self._executor.submit(self._browser.status, selected).result()
        self._record_observed_failure(status)
        return self._with_keepalive(status)

    def keep_alive(
        self,
        environment: PortalEnvironment | None = None,
    ) -> SessionStatus | None:
        if not self._keepalive_allowed():
            self._record_keepalive_paused()
            return None
        selected = environment or self._active_environment()
        if selected is None:
            return None
        status = self._executor.submit(
            self._browser.keep_alive,
            selected,
        ).result()
        self._record_keepalive_result(status)
        return self._with_keepalive(status)

    def keepalive_status(self) -> SessionKeepaliveStatus:
        with self._keepalive_lock:
            return self._keepalive_status

    def begin(
        self,
        mode: LoginMode,
        environment: PortalEnvironment | None = None,
    ) -> LoginAttempt:
        selected = environment or self.settings.default_environment
        return self._executor.submit(
            self._browser.begin,
            mode,
            selected,
        ).result()

    def refresh_captcha(self, attempt_id: str) -> LoginAttempt:
        return self._executor.submit(
            self._browser.refresh_captcha,
            attempt_id,
        ).result()

    def login_with_password(
        self,
        attempt_id: str,
        username: str,
        password: str,
        captcha: str,
    ) -> SessionStatus:
        status = self._executor.submit(
            self._browser.login_with_password,
            attempt_id,
            username,
            password,
            captcha,
        ).result()
        self._record_login(status)
        return self._with_keepalive(status)

    def request_sms(
        self,
        attempt_id: str,
        phone: str,
        password: str,
        captcha: str,
    ) -> SmsRequestResult:
        return self._executor.submit(
            self._browser.request_sms,
            attempt_id,
            phone,
            password,
            captcha,
        ).result()

    def verify_sms(self, attempt_id: str, sms_code: str) -> SessionStatus:
        status = self._executor.submit(
            self._browser.verify_sms,
            attempt_id,
            sms_code,
        ).result()
        self._record_login(status)
        return self._with_keepalive(status)

    def _active_environment(self) -> PortalEnvironment | None:
        candidates: list[tuple[int, PortalEnvironment]] = []
        for environment in PortalEnvironment:
            info = self.settings.describe_environment(environment)
            if not info.configured or not info.state_path.is_file():
                continue
            try:
                modified_at = info.state_path.stat().st_mtime_ns
            except OSError:
                continue
            candidates.append((modified_at, environment))
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]

    def _keepalive_loop(self) -> None:
        interval = self.settings.session_keepalive_interval_seconds
        while not self._keepalive_stop.wait(interval):
            if self._closed:
                return
            try:
                self.keep_alive()
            except (OSError, PortalSessionError, RuntimeError) as error:
                if self._closed:
                    return
                self._record_keepalive_error(str(error))

    def _record_keepalive_result(self, status: SessionStatus) -> None:
        previous = self.keepalive_status()
        if not previous.enabled:
            return
        match status.state:
            case SessionState.AUTHENTICATED:
                state = SessionKeepaliveState.ACTIVE
                successful_at = status.checked_at
                message = "登录保持运行正常，会话已自动刷新"
            case SessionState.LOGIN_REQUIRED:
                state = SessionKeepaliveState.LOGIN_REQUIRED
                successful_at = previous.successful_at
                message = "登录保持检测到会话已失效，请重新登录"
            case SessionState.UNAVAILABLE:
                state = SessionKeepaliveState.UNAVAILABLE
                successful_at = previous.successful_at
                message = "登录保持暂时无法访问综调系统"
            case unreachable:
                assert_never(unreachable)
        with self._keepalive_lock:
            self._keepalive_status = SessionKeepaliveStatus(
                enabled=previous.enabled,
                interval_seconds=previous.interval_seconds,
                state=state,
                checked_at=status.checked_at,
                successful_at=successful_at,
                environment=status.environment,
                message=message,
            )

    def _record_observed_failure(self, status: SessionStatus) -> None:
        if status.authenticated:
            return
        self._record_keepalive_result(status)

    def _record_login(self, status: SessionStatus) -> None:
        previous = self.keepalive_status()
        if not previous.enabled:
            return
        with self._keepalive_lock:
            self._keepalive_status = SessionKeepaliveStatus(
                enabled=True,
                interval_seconds=previous.interval_seconds,
                state=SessionKeepaliveState.WAITING,
                checked_at=None,
                successful_at=None,
                environment=status.environment,
                message="登录成功，等待首次自动保活",
            )

    def _record_keepalive_error(self, message: str) -> None:
        previous = self.keepalive_status()
        with self._keepalive_lock:
            self._keepalive_status = replace(
                previous,
                state=SessionKeepaliveState.UNAVAILABLE,
                checked_at=datetime.now(UTC),
                message=message or "登录保持执行失败",
            )

    def _record_keepalive_paused(self) -> None:
        previous = self.keepalive_status()
        if not previous.enabled:
            return
        with self._keepalive_lock:
            self._keepalive_status = replace(
                previous,
                state=SessionKeepaliveState.PAUSED,
                checked_at=datetime.now(UTC),
                message="存在排队或执行中的上报任务，本轮登录保持已跳过",
            )

    def _with_keepalive(self, status: SessionStatus) -> SessionStatus:
        return replace(status, keepalive=self.keepalive_status())

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        self._keepalive_stop.set()
        if self._keepalive_thread is not None:
            self._keepalive_thread.join()
        try:
            close_future = self._executor.submit(self._browser.close)
        except RuntimeError:
            return

        try:
            close_future.result()
        finally:
            self._executor.shutdown(wait=True, cancel_futures=True)
