"""处理集团综合调度系统页面的浏览器状态。"""

from dataclasses import dataclass
from typing import Final

from playwright.sync_api import Locator, Page

from rpa.captcha import RpaError


_WAIT_FOR_CAPTCHA_IMAGE_READY: Final[str] = """
async (element) => {
    if (!(element instanceof HTMLImageElement)) {
        return;
    }
    if (!element.complete || element.naturalWidth === 0) {
        await new Promise((resolve, reject) => {
            element.addEventListener("load", resolve, {once: true});
            element.addEventListener(
                "error",
                () => reject(new Error("captcha image failed to load")),
                {once: true},
            );
        });
    }
    await element.decode();
}
"""
_ANTI_DEVTOOLS_MESSAGE: Final[str] = "网页已禁用开发者工具"


@dataclass(frozen=True, slots=True)
class PortalPageBlockedError(RpaError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def capture_captcha_image(
    captcha_image: Locator,
    *,
    timeout_ms: int,
) -> bytes:
    """等待验证码加载完成并截取该元素。"""
    captcha_image.wait_for(
        state="visible",
        timeout=timeout_ms,
    )
    captcha_image.evaluate(
        _WAIT_FOR_CAPTCHA_IMAGE_READY,
        timeout=timeout_ms,
    )
    return captcha_image.screenshot(
        type="png",
        animations="disabled",
    )


def reload_once_if_anti_devtools_page(
    page: Page,
    *,
    timeout_ms: int,
    page_name: str,
) -> None:
    """反调试页面出现时刷新一次，并拒绝持续拦截。"""
    body = page.locator("body")
    body.wait_for(
        state="visible",
        timeout=timeout_ms,
    )
    if _ANTI_DEVTOOLS_MESSAGE not in body.inner_text():
        return

    page.reload(
        wait_until="domcontentloaded",
        timeout=timeout_ms,
    )
    body.wait_for(
        state="visible",
        timeout=timeout_ms,
    )
    if _ANTI_DEVTOOLS_MESSAGE in body.inner_text():
        raise PortalPageBlockedError(
            reason=(
                f"{page_name}连续两次提示"
                "“网页已禁用开发者工具”；"
                "浏览器已自动刷新一次但页面仍被拦截"
            )
        )
