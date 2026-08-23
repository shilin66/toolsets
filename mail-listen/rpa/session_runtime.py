import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from .session_config import PortalSessionSettings
from .session_models import (
    PortalEnvironment,
    PortalSessionError,
    SessionState,
    SessionStatus,
)


class PortalSessionRuntime:
    def __init__(self, settings: PortalSessionSettings) -> None:
        self.settings = settings
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    def status(self, environment: PortalEnvironment) -> SessionStatus:
        return self._status(environment, persist_state=False)

    def keep_alive(self, environment: PortalEnvironment) -> SessionStatus:
        return self._status(environment, persist_state=True)

    def _status(
        self,
        environment: PortalEnvironment,
        *,
        persist_state: bool,
    ) -> SessionStatus:
        checked_at = datetime.now(UTC)
        info = self.settings.describe_environment(environment)
        if not info.configured:
            return SessionStatus(
                SessionState.UNAVAILABLE,
                False,
                checked_at,
                "当前综调环境地址未配置，请检查 .env",
                environment,
                False,
                info.password_login_url,
                info.mobile_login_url,
                info.state_path,
            )
        target = self.settings.resolve_environment(environment)
        if not target.state_path.is_file():
            return SessionStatus(
                SessionState.LOGIN_REQUIRED,
                False,
                checked_at,
                "尚未建立综调会话，请登录",
                environment,
                True,
                target.login_url,
                target.mobile_login_url,
                target.state_path,
            )
        inactive_path = self.settings.inactive_state_path(environment)
        if inactive_path == target.state_path:
            return SessionStatus(
                SessionState.UNAVAILABLE,
                False,
                checked_at,
                "测试与生产环境不能使用同一个会话文件",
                environment,
                True,
                target.login_url,
                target.mobile_login_url,
                target.state_path,
            )
        if inactive_path.is_file():
            if (
                inactive_path.stat().st_mtime_ns
                >= target.state_path.stat().st_mtime_ns
            ):
                return SessionStatus(
                    SessionState.LOGIN_REQUIRED,
                    False,
                    checked_at,
                    "另一环境已登录，如需切换请重新登录当前环境",
                    environment,
                    True,
                    target.login_url,
                    target.mobile_login_url,
                    target.state_path,
                )
            try:
                inactive_path.unlink()
            except OSError:
                return SessionStatus(
                    SessionState.UNAVAILABLE,
                    False,
                    checked_at,
                    "无法停用原环境会话，请检查会话文件权限",
                    environment,
                    True,
                    target.login_url,
                    target.mobile_login_url,
                    target.state_path,
                )
        context: BrowserContext | None = None
        try:
            context = self.ensure_browser().new_context(
                storage_state=str(target.state_path),
                ignore_https_errors=self.settings.ignore_https_errors,
                viewport=self.viewport(),
            )
            page = context.new_page()
            page.set_default_timeout(self.settings.timeout_ms)
            self.open(page, target.session_check_url)
            if self._login_form_visible(page):
                return SessionStatus(
                    SessionState.LOGIN_REQUIRED,
                    False,
                    checked_at,
                    "综调会话已失效，请重新登录",
                    environment,
                    True,
                    target.login_url,
                    target.mobile_login_url,
                    target.state_path,
                )
            ready = self.settings.post_login_ready_selector
            if ready:
                page.locator(ready).first.wait_for(state="visible", timeout=self.settings.timeout_ms)
            if persist_state:
                self.save_storage_state(context, target.state_path)
            return SessionStatus(
                SessionState.AUTHENTICATED,
                True,
                checked_at,
                "综调会话有效，可以执行上报",
                environment,
                True,
                target.login_url,
                target.mobile_login_url,
                target.state_path,
            )
        except PlaywrightTimeoutError:
            return SessionStatus(
                SessionState.LOGIN_REQUIRED,
                False,
                checked_at,
                "未检测到有效综调会话，请重新登录",
                environment,
                True,
                target.login_url,
                target.mobile_login_url,
                target.state_path,
            )
        except PlaywrightError:
            return SessionStatus(
                SessionState.UNAVAILABLE,
                False,
                checked_at,
                "综调系统暂时无法访问，请稍后重试",
                environment,
                True,
                target.login_url,
                target.mobile_login_url,
                target.state_path,
            )
        finally:
            if context is not None:
                context.close()

    def save_storage_state(
        self,
        context: BrowserContext,
        path: Path,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as state_file:
            temporary_path = Path(state_file.name)
        try:
            context.storage_state(path=str(temporary_path))
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, path)
        except (OSError, PlaywrightError) as error:
            raise PortalSessionError(
                "RPA_UNAVAILABLE",
                "无法更新综调会话文件，请检查数据目录权限",
            ) from error
        finally:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    def ensure_browser(self) -> Browser:
        if self._browser is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.settings.headless,
                slow_mo=self.settings.slow_mo_ms,
            )
        return self._browser

    def open(self, page: Page, url: str) -> None:
        page.goto(url, wait_until="domcontentloaded", timeout=self.settings.timeout_ms)

    def viewport(self) -> dict[str, int]:
        return {
            "width": self.settings.viewport_width,
            "height": self.settings.viewport_height,
        }

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def _login_form_visible(self, page: Page) -> bool:
        for selector in (self.settings.username_selector, self.settings.mobile_phone_selector):
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible():
                return True
        return False
