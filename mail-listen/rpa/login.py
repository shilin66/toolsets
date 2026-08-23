"""使用 Playwright 登录集团综合调度系统。"""

from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
from typing import assert_never

from playwright.sync_api import (
    BrowserContext,
    Error as PlaywrightError,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from rpa.captcha import (
    CaptchaParseError,
    CaptchaRecognitionError,
    RpaError,
    solve_captcha,
)
from rpa.config import CaptchaRecognizerMode, RpaSettings
from rpa.portal_page import (
    PortalPageBlockedError,
    capture_captcha_image,
    reload_once_if_anti_devtools_page,
)
from rpa.vision import (
    CaptchaRecognizer,
    OpenAICompatibleCaptchaRecognizer,
)


@dataclass(frozen=True, slots=True)
class LoginResult:
    final_url: str
    storage_state_path: Path
    success_screenshot_path: Path


@dataclass(frozen=True, slots=True)
class LoginFailedError(RpaError):
    reason: str
    screenshot_path: Path | None = None

    def __str__(self) -> str:
        if self.screenshot_path is None:
            return self.reason
        return f"{self.reason}；失败截图：{self.screenshot_path}"


def build_captcha_recognizer(
    settings: RpaSettings,
) -> CaptchaRecognizer:
    """根据环境配置创建验证码识别器。"""
    match settings.captcha_recognizer:
        case CaptchaRecognizerMode.MULTIMODAL:
            api_key = settings.openai_compatible_api_key
            model = settings.openai_compatible_model
            assert api_key is not None
            assert model is not None
            return OpenAICompatibleCaptchaRecognizer(
                base_url=str(settings.openai_compatible_base_url),
                api_key=api_key.get_secret_value(),
                model=model,
                timeout_seconds=(
                    settings.openai_compatible_timeout_seconds
                ),
            )
        case CaptchaRecognizerMode.OCR:
            from rpa.ocr import RapidOcrCaptchaRecognizer

            return RapidOcrCaptchaRecognizer()
        case unreachable:
            assert_never(unreachable)


class PortalLoginRpa:
    """执行一次登录并保存可供后续 RPA 复用的浏览器会话。"""

    def __init__(
        self,
        settings: RpaSettings,
        captcha_recognizer: CaptchaRecognizer | None = None,
    ) -> None:
        self._settings = settings
        self._captcha_recognizer = (
            captcha_recognizer
            if captcha_recognizer is not None
            else build_captcha_recognizer(settings)
        )

    def login(self) -> LoginResult:
        """登录门户，成功后以仅当前用户可读写的权限保存会话。"""
        settings = self._settings
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    headless=settings.headless,
                    slow_mo=settings.slow_mo_ms,
                )
            except PlaywrightError as error:
                raise LoginFailedError(
                    reason="无法启动 Chromium，请确认已安装浏览器运行时"
                ) from error

            context: BrowserContext | None = None
            page: Page | None = None
            try:
                context = browser.new_context(
                    ignore_https_errors=settings.ignore_https_errors,
                )
                page = context.new_page()
                page.set_default_timeout(settings.timeout_ms)
                self._open_login_page(page)
                username_input = page.locator(settings.username_selector)
                username_input.fill(settings.username)
                page.locator(settings.password_selector).fill(
                    settings.password.get_secret_value()
                )

                captcha_image = page.locator(
                    settings.captcha_image_selector
                )
                captcha_png = capture_captcha_image(
                    captcha_image,
                    timeout_ms=settings.timeout_ms,
                )
                captcha_text = self._captcha_recognizer.recognize(
                    captcha_png
                )
                page.locator(settings.captcha_input_selector).fill(
                    solve_captcha(captcha_text)
                )
                page.locator(settings.submit_selector).click()

                self._wait_for_success_signal(page, username_input)
                page.wait_for_load_state(
                    "load",
                    timeout=settings.timeout_ms,
                )
                page.locator("body").wait_for(
                    state="visible",
                    timeout=settings.timeout_ms,
                )
                reload_once_if_anti_devtools_page(
                    page,
                    timeout_ms=settings.timeout_ms,
                    page_name="登录后页面",
                )
                self._wait_for_success_signal(page, username_input)
                success_screenshot_path = (
                    self._capture_success_screenshot(page)
                )

                settings.state_path.parent.mkdir(parents=True, exist_ok=True)
                settings.state_path.touch(mode=0o600, exist_ok=True)
                os.chmod(settings.state_path, 0o600)
                context.storage_state(path=str(settings.state_path))
                os.chmod(settings.state_path, 0o600)
                return LoginResult(
                    final_url=page.url,
                    storage_state_path=settings.state_path,
                    success_screenshot_path=success_screenshot_path,
                )
            except (
                CaptchaParseError,
                CaptchaRecognitionError,
                PortalPageBlockedError,
                PlaywrightError,
            ) as error:
                screenshot_path = (
                    self._capture_failure_screenshot(page)
                    if page is not None
                    else None
                )
                match error:
                    case CaptchaParseError():
                        reason = str(error)
                    case CaptchaRecognitionError():
                        reason = str(error)
                    case PortalPageBlockedError():
                        reason = str(error)
                    case PlaywrightTimeoutError():
                        reason = "登录超时：未检测到页面跳转或登录表单消失"
                    case PlaywrightError():
                        reason = "浏览器执行登录流程失败"
                    case unreachable:
                        assert_never(unreachable)
                raise LoginFailedError(
                    reason=reason,
                    screenshot_path=screenshot_path,
                ) from error
            finally:
                try:
                    if context is not None:
                        context.close()
                finally:
                    browser.close()

    def _open_login_page(self, page: Page) -> None:
        """打开登录页；网站误报开发者工具时只刷新一次。"""
        settings = self._settings
        page.goto(
            str(settings.login_url),
            wait_until="domcontentloaded",
            timeout=settings.timeout_ms,
        )
        reload_once_if_anti_devtools_page(
            page,
            timeout_ms=settings.timeout_ms,
            page_name="登录页",
        )

    def _wait_for_success_signal(
        self,
        page: Page,
        username_input: Locator,
    ) -> None:
        """等待配置的成功 URL，或等待登录表单消失。"""
        settings = self._settings
        if settings.success_url_pattern:
            page.wait_for_url(
                settings.success_url_pattern,
                timeout=settings.timeout_ms,
            )
            return
        username_input.wait_for(
            state="hidden",
            timeout=settings.timeout_ms,
        )

    def _capture_success_screenshot(self, page: Page) -> Path:
        """保存完整的登录后页面，并限制截图文件权限。"""
        screenshot_path = self._settings.success_screenshot_path
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path.touch(mode=0o600, exist_ok=True)
        os.chmod(screenshot_path, 0o600)
        page.screenshot(
            path=str(screenshot_path),
            full_page=True,
            animations="disabled",
        )
        os.chmod(screenshot_path, 0o600)
        return screenshot_path

    def _capture_failure_screenshot(self, page: Page) -> Path | None:
        """清除表单中的敏感数据后保存失败截图。"""
        try:
            for selector in (
                self._settings.username_selector,
                self._settings.password_selector,
                self._settings.captcha_input_selector,
            ):
                field = page.locator(selector).first
                if field.is_visible():
                    field.fill("")

            artifact_dir = self._settings.artifact_dir
            artifact_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            screenshot_path = artifact_dir / f"login-failure-{timestamp}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            return screenshot_path
        except PlaywrightError:
            return None
