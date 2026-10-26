import codecs
import csv
import io
import re
import tempfile
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from charset_normalizer import from_bytes
from loguru import logger

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


def is_calendar_attachment(filename: str, content_type: str = "") -> bool:
    """日历附件不落盘、不参与 AI 提取；兼容大小写扩展名及日历 MIME。"""
    return str(filename or "").strip().lower().endswith(".ics") or (
        str(content_type or "").split(";", 1)[0].strip().lower() == "text/calendar"
    )


def get_attachment_dir() -> Path:
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    return ATTACHMENT_DIR


def sanitize_attachment_filename(filename: str) -> str:
    safe_name = Path(str(filename or "attachment")).name.strip()
    safe_name = re.sub(r"[^\w.\- ]+", "_", safe_name)
    safe_name = safe_name.strip(" .")
    return safe_name or "attachment"


def _decode_text_attachment(content: bytes, charset: str | None) -> tuple[str, str]:
    # UTF-32 LE 与 UTF-16 LE 的 BOM 前两字节相同，必须先检查 UTF-32。
    for signatures, encoding in (
        ((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE), 'utf-32'),
        ((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE), 'utf-16'),
        ((codecs.BOM_UTF8,), 'utf-8-sig'),
    ):
        if content.startswith(signatures):
            return content.decode(encoding), encoding
    try:
        return content.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        pass
    if charset:
        return content.decode(charset), charset

    # 检测分数只是启发式信号。短文本、多种编码同样合理时不强行选第一项。
    candidates = sorted(
        (match for match in from_bytes(content, enable_fallback=False) if match.chaos <= 0.05),
        key=lambda match: match.coherence, reverse=True,
    )
    if not candidates or candidates[0].coherence < 0.2:
        raise ValueError('encoding_uncertain')
    best = candidates[0]
    if any(best.coherence - other.coherence < 0.1 and str(best) != str(other)
           for other in candidates[1:]):
        raise ValueError('encoding_ambiguous')
    return content.decode(best.encoding), best.encoding


def normalize_text_attachment(filename: str, content: bytes, *, charset: str | None = None) -> bytes:
    """CSV/TXT 保存为 UTF-8；无法可靠转换时保留原始字节，仅记录失败日志。"""
    extension = Path(filename).suffix.lower()
    if extension not in ('.csv', '.txt') or not content:
        return content
    try:
        text, encoding = _decode_text_attachment(content, charset)
        if re.search(r'[\x00-\x08\x0b\x0e-\x1f\x7f\ufffd]', text):
            raise ValueError('invalid_text_characters')
        if extension == '.csv':
            try:
                dialect = csv.Sniffer().sniff(text, delimiters=',\t')
                delimiter = dialect.delimiter
            except csv.Error:
                if '\t' in text:
                    raise ValueError('csv_delimiter_uncertain')
                delimiter = ','  # 普通逗号 CSV 或单列 CSV。
            output = io.StringIO(newline='')
            writer = csv.writer(output)
            for row in csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True):
                writer.writerow(row)
            text = output.getvalue()
        normalized = text.encode('utf-8')
    except (UnicodeError, LookupError, ValueError, csv.Error) as exc:
        logger.warning('附件转换失败，保留原文件 filename={} reason_code=attachment_normalization_failed error={}',
                       filename, type(exc).__name__)
        return content
    if normalized != content:
        logger.info('附件已转为 UTF-8 filename={} source_encoding={} reason_code=attachment_normalized',
                    filename, encoding)
    return normalized


def save_attachment(
    mailbox_address: str,
    uid: int,
    filename: str,
    content: bytes,
    *,
    charset: str | None = None,
) -> str:
    attachment_dir = email_attachment_directory(
        DATA_DIR,
        mailbox_address=mailbox_address,
        email_uid=uid,
    )
    safe_name = sanitize_attachment_filename(filename)
    attachment_path = attachment_dir / f"{uuid.uuid4().hex}-{safe_name}"
    write_private_bytes(DATA_DIR, attachment_path,
                        normalize_text_attachment(safe_name, content or b"", charset=charset))
    return attachment_path.relative_to(DATA_DIR).as_posix()


def save_preview_attachment(filename: str, content: bytes, *, charset: str | None = None) -> str:
    """保存提取预览上传的附件，与监听邮件附件使用相同的存储结构。"""
    preview_dir = get_attachment_dir() / "preview-extract"
    preview_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_attachment_filename(filename)
    attachment_path = preview_dir / f"{uuid.uuid4().hex}-{safe_name}"
    attachment_path.write_bytes(normalize_text_attachment(safe_name, content or b"", charset=charset))
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
