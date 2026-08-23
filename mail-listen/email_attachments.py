import re
import tempfile
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from config import settings
from mail_artifacts import (
    email_attachment_directory,
    resolve_canonical_attachment_path,
    write_private_bytes,
)


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ATTACHMENT_DIR = DATA_DIR / "email_attachments"
ATTACHMENT_URL_PREFIX = "/api/email/attachments"


def get_attachment_dir() -> Path:
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    return ATTACHMENT_DIR


def sanitize_attachment_filename(filename: str) -> str:
    safe_name = Path(str(filename or "attachment")).name.strip()
    safe_name = re.sub(r"[^\w.\- ]+", "_", safe_name)
    safe_name = safe_name.strip(" .")
    return safe_name or "attachment"


def save_attachment(
    mailbox_address: str,
    uid: int,
    filename: str,
    content: bytes,
) -> str:
    attachment_dir = email_attachment_directory(
        DATA_DIR,
        mailbox_address=mailbox_address,
        email_uid=uid,
    )
    safe_name = sanitize_attachment_filename(filename)
    attachment_path = attachment_dir / f"{uuid.uuid4().hex}-{safe_name}"
    write_private_bytes(DATA_DIR, attachment_path, content or b"")
    return attachment_path.relative_to(DATA_DIR).as_posix()


def save_preview_attachment(filename: str, content: bytes) -> str:
    """保存提取预览上传的附件，与监听邮件附件使用相同的存储结构。"""
    preview_dir = get_attachment_dir() / "preview-extract"
    preview_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_attachment_filename(filename)
    attachment_path = preview_dir / f"{uuid.uuid4().hex}-{safe_name}"
    attachment_path.write_bytes(content or b"")
    return attachment_path.relative_to(DATA_DIR).as_posix()


def build_attachment_url(relative_path: str) -> str:
    base_url = (settings.fe_domain or settings.api_public_base_url).strip().rstrip("/")
    if not base_url:
        base_url = f"http://localhost:{settings.api_port}"
    return f"{base_url}{ATTACHMENT_URL_PREFIX}/{quote(relative_path, safe='/')}"


def attachment_path_from_relative(
    relative_path: str,
    *,
    data_dir: Path | None = None,
) -> Optional[Path]:
    if not relative_path:
        return None

    root = data_dir if data_dir is not None else DATA_DIR
    canonical_path = resolve_canonical_attachment_path(root, relative_path)
    if canonical_path is not None:
        return canonical_path

    candidate = (root / relative_path).resolve()
    attachment_dir = (root / "email_attachments").resolve()
    try:
        candidate.relative_to(attachment_dir)
    except ValueError:
        return None
    return candidate
