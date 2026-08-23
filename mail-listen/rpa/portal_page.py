from time import monotonic, sleep

from playwright.sync_api import Locator, TimeoutError as PlaywrightTimeoutError


def capture_captcha_image(
    captcha_image: Locator,
    *,
    timeout_ms: int,
) -> bytes:
    captcha_image.wait_for(
        state="visible",
        timeout=timeout_ms,
    )
    deadline = monotonic() + timeout_ms / 1000
    while monotonic() < deadline:
        if captcha_image.get_attribute("src"):
            return captcha_image.screenshot(type="png")
        sleep(0.05)
    raise PlaywrightTimeoutError("图形验证码图片未加载")
