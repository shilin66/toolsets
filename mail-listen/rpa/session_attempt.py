import base64
import secrets
from datetime import UTC, datetime, timedelta
from typing import assert_never

from playwright.sync_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from .portal_page import capture_captcha_image
from .session_models import (
    LoginAttempt,
    LoginMode,
    PortalEnvironment,
    PortalSessionError,
    ResolvedPortalEnvironment,
    SessionState,
    SessionStatus,
    SmsRequestResult,
)
from .session_runtime import PortalSessionRuntime


class PortalLoginAttempt:
    def __init__(self, runtime: PortalSessionRuntime) -> None:
        self._runtime = runtime
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._id: str | None = None
        self._mode: LoginMode | None = None
        self._target: ResolvedPortalEnvironment | None = None
        self._expires_at: datetime | None = None

    def begin(
        self,
        mode: LoginMode,
        environment: PortalEnvironment,
    ) -> LoginAttempt:
        self.close()
        settings = self._runtime.settings
        target = settings.resolve_environment(environment)
        try:
            self._context = self._runtime.ensure_browser().new_context(
                ignore_https_errors=settings.ignore_https_errors,
                viewport=self._runtime.viewport(),
            )
            page = self._context.new_page()
            page.set_default_timeout(settings.timeout_ms)
            match mode:
                case LoginMode.PASSWORD:
                    login_url = target.login_url
                case LoginMode.MOBILE:
                    login_url = target.mobile_login_url
                case unreachable:
                    assert_never(unreachable)
            self._runtime.open(page, login_url)
            self._page = page
            self._id = secrets.token_urlsafe(24)
            self._mode = mode
            self._target = target
            self._expires_at = datetime.now(UTC) + timedelta(seconds=settings.attempt_ttl_seconds)
            return self._result()
        except PlaywrightError as error:
            self.close()
            raise PortalSessionError(
                "RPA_UNAVAILABLE",
                "无法打开综调登录页，请检查网络和浏览器运行环境",
            ) from error

    def refresh_captcha(self, attempt_id: str) -> LoginAttempt:
        page = self._require(attempt_id)
        try:
            page.locator(self._captcha_selector()).first.click()
            page.wait_for_timeout(self._runtime.settings.captcha_refresh_wait_ms)
            return self._result()
        except PlaywrightError as error:
            raise PortalSessionError(
                "RPA_UNAVAILABLE",
                "刷新图形验证码失败，请重新发起登录",
            ) from error

    def login_with_password(
        self,
        attempt_id: str,
        username: str,
        password: str,
        captcha: str,
    ) -> SessionStatus:
        page = self._require_mode(attempt_id, LoginMode.PASSWORD)
        settings = self._runtime.settings
        try:
            page.locator(settings.username_selector).fill(username)
            page.locator(settings.password_selector).fill(password)
            page.locator(settings.captcha_input_selector).fill(captcha)
            page.locator(settings.submit_selector).click()
            self._wait_for_login(page, settings.username_selector)
            return self._save_state()
        except PlaywrightTimeoutError as error:
            raise PortalSessionError(
                "LOGIN_FAILED",
                "登录未成功，请检查账号、密码和图形验证码",
            ) from error
        except PlaywrightError as error:
            raise PortalSessionError("RPA_UNAVAILABLE", "综调登录页面操作失败") from error

    def request_sms(
        self,
        attempt_id: str,
        phone: str,
        password: str,
        captcha: str,
    ) -> SmsRequestResult:
        page = self._require_mode(attempt_id, LoginMode.MOBILE)
        settings = self._runtime.settings
        try:
            page.locator(settings.mobile_phone_selector).fill(phone)
            page.locator(settings.mobile_password_selector).fill(password)
            page.locator(settings.mobile_captcha_input_selector).fill(captcha)
            page.locator(settings.mobile_sms_button_selector).click()
            return SmsRequestResult(attempt_id, True)
        except PlaywrightError as error:
            raise PortalSessionError("RPA_UNAVAILABLE", "获取手机验证码失败") from error

    def verify_sms(self, attempt_id: str, sms_code: str) -> SessionStatus:
        page = self._require_mode(attempt_id, LoginMode.MOBILE)
        settings = self._runtime.settings
        try:
            page.locator(settings.mobile_sms_input_selector).fill(sms_code)
            page.locator(settings.mobile_submit_selector).click()
            self._wait_for_login(page, settings.mobile_phone_selector)
            return self._save_state()
        except PlaywrightTimeoutError as error:
            raise PortalSessionError("LOGIN_FAILED", "手机验证码登录未成功") from error
        except PlaywrightError as error:
            raise PortalSessionError("RPA_UNAVAILABLE", "综调登录页面操作失败") from error

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        self._context = None
        self._page = None
        self._id = None
        self._mode = None
        self._target = None
        self._expires_at = None

    def _require(self, attempt_id: str) -> Page:
        if self._id != attempt_id or self._page is None:
            raise PortalSessionError(
                "ATTEMPT_NOT_FOUND",
                "登录尝试不存在，请重新获取验证码",
            )
        if self._expires_at is None or datetime.now(UTC) >= self._expires_at:
            self.close()
            raise PortalSessionError(
                "ATTEMPT_EXPIRED",
                "登录尝试已过期，请重新获取验证码",
            )
        return self._page

    def _require_mode(self, attempt_id: str, mode: LoginMode) -> Page:
        page = self._require(attempt_id)
        if self._mode is not mode:
            raise PortalSessionError(
                "ATTEMPT_NOT_FOUND",
                "登录方式已切换，请重新获取验证码",
            )
        return page

    def _result(self) -> LoginAttempt:
        if (
            self._id is None
            or self._mode is None
            or self._target is None
            or self._expires_at is None
        ):
            raise PortalSessionError("ATTEMPT_NOT_FOUND", "登录尝试不存在")
        page = self._require(self._id)
        image = capture_captcha_image(
            page.locator(self._captcha_selector()).first,
            timeout_ms=self._runtime.settings.timeout_ms,
        )
        data_url = "data:image/png;base64," + base64.b64encode(image).decode(
            "ascii"
        )
        return LoginAttempt(
            self._id,
            self._mode,
            data_url,
            self._expires_at,
            self._target.environment,
        )

    def _captcha_selector(self) -> str:
        settings = self._runtime.settings
        match self._mode:
            case LoginMode.PASSWORD:
                return settings.captcha_image_selector
            case LoginMode.MOBILE:
                return settings.mobile_captcha_image_selector
            case None:
                raise PortalSessionError("ATTEMPT_NOT_FOUND", "登录尝试不存在")
            case unreachable:
                assert_never(unreachable)

    def _wait_for_login(self, page: Page, form_selector: str) -> None:
        settings = self._runtime.settings
        if settings.success_url_pattern:
            page.wait_for_url(settings.success_url_pattern, timeout=settings.timeout_ms)
        else:
            page.locator(form_selector).first.wait_for(state="hidden", timeout=settings.timeout_ms)
        if settings.post_login_ready_selector:
            page.locator(settings.post_login_ready_selector).first.wait_for(
                state="visible",
                timeout=settings.timeout_ms,
            )

    def _save_state(self) -> SessionStatus:
        if self._context is None or self._target is None:
            raise PortalSessionError("ATTEMPT_NOT_FOUND", "登录尝试不存在")
        target = self._target
        path = target.state_path
        inactive_path = self._runtime.settings.inactive_state_path(
            target.environment
        )
        if inactive_path == path:
            raise PortalSessionError(
                "RPA_UNAVAILABLE",
                "测试与生产环境不能使用同一个会话文件",
            )
        try:
            inactive_path.unlink(missing_ok=True)
        except OSError as error:
            raise PortalSessionError(
                "RPA_UNAVAILABLE",
                "无法停用原环境会话，请检查会话文件权限",
            ) from error
        self._runtime.save_storage_state(self._context, path)
        self.close()
        return SessionStatus(
            SessionState.AUTHENTICATED,
            True,
            datetime.now(UTC),
            "登录成功，综调会话已建立",
            target.environment,
            True,
            target.login_url,
            target.mobile_login_url,
            target.state_path,
        )
