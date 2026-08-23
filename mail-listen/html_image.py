"""
HTML 邮件截图工具。
"""
from html import escape
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from loguru import logger

from config import settings


IMAGE_DIR = Path(tempfile.gettempdir()) / "mail-listen-images"
IMAGE_URL_PREFIX = "/api/email/images"


def get_image_dir() -> Path:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGE_DIR


def build_image_url(filename: str) -> str:
    base_url = (settings.fe_domain or settings.api_public_base_url).strip().rstrip("/")
    if not base_url:
        base_url = f"http://localhost:{settings.api_port}"
    return f"{base_url}{IMAGE_URL_PREFIX}/{filename}"


def image_path_from_filename(filename: str) -> Optional[Path]:
    if not filename.endswith(".png"):
        return None

    path = (get_image_dir() / filename).resolve()
    image_dir = get_image_dir().resolve()

    try:
        path.relative_to(image_dir)
    except ValueError:
        return None

    return path


def _plain_text_to_html(text_content: str) -> str:
    escaped_content = escape(text_content or "")
    return (
        "<!doctype html>"
        "<html>"
        "<head>"
        "<meta charset=\"utf-8\">"
        "<style>"
        "body{margin:24px;font:14px/1.5 -apple-system,BlinkMacSystemFont,"
        "'Segoe UI',Arial,sans-serif;color:#1f2328;background:#fff;}"
        "pre{white-space:pre-wrap;word-break:break-word;margin:0;}"
        "</style>"
        "</head>"
        "<body>"
        f"<pre>{escaped_content}</pre>"
        "</body>"
        "</html>"
    )


def render_email_body_to_image_url(
    html_content: Optional[str],
    text_content: Optional[str],
    uid: int,
) -> Optional[str]:
    """将邮件正文渲染为本地 PNG，并返回可访问 URL。"""
    if html_content and html_content.strip():
        render_content = html_content
    elif text_content and text_content.strip():
        render_content = _plain_text_to_html(text_content)
    else:
        return None

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        logger.warning("未安装 playwright，无法将邮件正文转为图片")
        return None

    filename = f"email-{uid}-{uuid.uuid4().hex}.png"
    image_path = get_image_dir() / filename

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
            page.set_content(render_content, wait_until="networkidle")
            page.screenshot(path=str(image_path), full_page=True)
            browser.close()

        logger.info(f"邮件正文已转为图片: {image_path}")
        return build_image_url(filename)
    except Exception as e:
        logger.error(f"邮件正文转图片失败: {e}")
        return None


def render_html_to_image_url(html_content: str, uid: int) -> Optional[str]:
    """兼容旧调用：将 HTML 正文渲染为本地 PNG，并返回可访问 URL。"""
    return render_email_body_to_image_url(html_content, None, uid)
