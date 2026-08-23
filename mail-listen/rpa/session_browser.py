from .session_attempt import PortalLoginAttempt
from .session_config import PortalSessionSettings
from .session_models import (
    LoginAttempt,
    LoginMode,
    PortalEnvironment,
    SessionStatus,
    SmsRequestResult,
)
from .session_runtime import PortalSessionRuntime


class PortalSessionBrowser:
    def __init__(self, settings: PortalSessionSettings) -> None:
        self._runtime = PortalSessionRuntime(settings)
        self._attempt = PortalLoginAttempt(self._runtime)

    def status(self, environment: PortalEnvironment) -> SessionStatus:
        return self._runtime.status(environment)

    def keep_alive(self, environment: PortalEnvironment) -> SessionStatus:
        return self._runtime.keep_alive(environment)

    def begin(
        self,
        mode: LoginMode,
        environment: PortalEnvironment,
    ) -> LoginAttempt:
        return self._attempt.begin(mode, environment)

    def refresh_captcha(self, attempt_id: str) -> LoginAttempt:
        return self._attempt.refresh_captcha(attempt_id)

    def login_with_password(
        self,
        attempt_id: str,
        username: str,
        password: str,
        captcha: str,
    ) -> SessionStatus:
        return self._attempt.login_with_password(
            attempt_id,
            username,
            password,
            captcha,
        )

    def request_sms(
        self,
        attempt_id: str,
        phone: str,
        password: str,
        captcha: str,
    ) -> SmsRequestResult:
        return self._attempt.request_sms(attempt_id, phone, password, captcha)

    def verify_sms(self, attempt_id: str, sms_code: str) -> SessionStatus:
        return self._attempt.verify_sms(attempt_id, sms_code)

    def close(self) -> None:
        self._attempt.close()
        self._runtime.close()
