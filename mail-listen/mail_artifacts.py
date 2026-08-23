from __future__ import annotations

import hashlib
import os
import re
import tempfile
from datetime import date
from pathlib import Path, PurePosixPath


class MailArtifactError(ValueError):
    pass


class SourceEmailArchiveError(MailArtifactError):
    pass


def _positive_integer(
    value: object,
    field_name: str,
    error_type: type[MailArtifactError] = MailArtifactError,
) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise error_type(f"{field_name} 必须是正整数")
    return value


def _normalized_mailbox_address(mailbox_address: object) -> str:
    if not isinstance(mailbox_address, str) or not mailbox_address.strip():
        raise MailArtifactError("收件邮箱不能为空")
    return mailbox_address.strip().casefold()


def legacy_mailbox_storage_key(mailbox_address: object) -> str:
    normalized_address = _normalized_mailbox_address(mailbox_address)
    digest = hashlib.sha256(normalized_address.encode("utf-8")).hexdigest()[:24]
    return f"mailbox-{digest}"


def mailbox_storage_key(mailbox_address: object) -> str:
    normalized_address = _normalized_mailbox_address(mailbox_address)
    readable = "".join(
        character if character.isalnum() or character in "@._+" else "-"
        for character in normalized_address
    )
    readable = re.sub(r"-+", "-", readable).strip("-.")[:80].rstrip("-.")
    if not readable:
        readable = "mailbox"
    digest = hashlib.sha256(normalized_address.encode("utf-8")).hexdigest()[:8]
    return f"mailbox-{readable}-{digest}"


def message_storage_directory(
    data_dir: Path,
    *,
    mailbox_address: object,
    email_uid: object,
) -> Path:
    uid = _positive_integer(email_uid, "邮件 UID")
    return (
        data_dir
        / "mail_store"
        / "mailboxes"
        / mailbox_storage_key(mailbox_address)
        / "messages"
        / str(uid)
    )


def source_email_archive_path(
    data_dir: Path,
    *,
    mailbox_address: object,
    email_uid: object,
) -> Path:
    try:
        return message_storage_directory(
            data_dir,
            mailbox_address=mailbox_address,
            email_uid=email_uid,
        ) / f"source-email-{email_uid}.eml"
    except MailArtifactError as error:
        raise SourceEmailArchiveError(str(error)) from error


def email_attachment_directory(
    data_dir: Path,
    *,
    mailbox_address: object,
    email_uid: object,
) -> Path:
    return message_storage_directory(
        data_dir,
        mailbox_address=mailbox_address,
        email_uid=email_uid,
    ) / "attachments"


def customer_excel_path(
    data_dir: Path,
    *,
    mailbox_address: object,
    email_uid: object,
    filename: object,
) -> Path:
    if (
        not isinstance(filename, str)
        or not filename
        or Path(filename).name != filename
        or Path(filename).suffix.lower() != ".xlsx"
    ):
        raise MailArtifactError("客户线路 Excel 文件名无效")
    return (
        message_storage_directory(
            data_dir,
            mailbox_address=mailbox_address,
            email_uid=email_uid,
        )
        / "cutover"
        / "customer"
        / filename
    )


def report_artifact_directory(
    data_dir: Path,
    *,
    mailbox_address: object,
    email_uid: object,
    report_date: object,
    email_record_id: object,
    task_id: object,
    report_id: object | None,
) -> Path:
    if not isinstance(report_date, str):
        raise MailArtifactError("上报日期格式无效")
    try:
        parsed_date = date.fromisoformat(report_date)
    except ValueError as error:
        raise MailArtifactError("上报日期格式无效") from error
    if parsed_date.isoformat() != report_date:
        raise MailArtifactError("上报日期格式无效")
    record_id = _positive_integer(email_record_id, "邮件记录 ID")
    normalized_task_id = _positive_integer(task_id, "割接任务 ID")
    if report_id is None:
        report_key = "adhoc"
    else:
        report_key = str(_positive_integer(report_id, "上报记录 ID"))
    return (
        message_storage_directory(
            data_dir,
            mailbox_address=mailbox_address,
            email_uid=email_uid,
        )
        / "cutover"
        / "reports"
        / report_date
        / str(record_id)
        / f"{normalized_task_id}_{report_key}"
    )


def resolve_canonical_attachment_path(
    data_dir: Path,
    relative_path: object,
) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path:
        return None
    logical_path = PurePosixPath(relative_path)
    parts = logical_path.parts
    if (
        logical_path.is_absolute()
        or len(parts) != 7
        or parts[0:2] != ("mail_store", "mailboxes")
        or not (
            re.fullmatch(r"mailbox-[\w@.+-]+-[0-9a-f]{8}", parts[2])
            or re.fullmatch(r"mailbox-[0-9a-f]{24}", parts[2])
        )
        or parts[3] != "messages"
        or not parts[4].isdigit()
        or parts[5] != "attachments"
        or parts[6] in ("", ".", "..")
    ):
        return None
    root = data_dir.resolve()
    candidate = (root / logical_path).resolve()
    if not candidate.is_relative_to(root / "mail_store" / "mailboxes"):
        return None
    return candidate


def write_private_bytes(
    data_dir: Path,
    target_path: Path,
    content: bytes,
) -> Path:
    root = data_dir.resolve()
    target = target_path.resolve()
    if not target.is_relative_to(root):
        raise MailArtifactError("文件路径超出数据目录")
    temporary_path: Path | None = None
    file_descriptor = -1
    try:
        root.mkdir(parents=True, exist_ok=True)
        relative_parent = target.parent.relative_to(root)
        current = root
        for part in relative_parent.parts:
            current /= part
            current.mkdir(mode=0o700, exist_ok=True)
            current.chmod(0o700)

        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            dir=target.parent,
        )
        temporary_path = Path(temporary_name)
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "wb") as stream:
            file_descriptor = -1
            _ = stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
        target.chmod(0o600)
    except OSError as error:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise MailArtifactError(f"保存文件失败：{error}") from error
    return target_path


def save_source_email_archive(
    data_dir: Path,
    *,
    mailbox_address: object,
    email_uid: object,
    raw_message: object,
) -> Path:
    if not isinstance(raw_message, bytes) or not raw_message:
        raise SourceEmailArchiveError("原始邮件 EML 不能为空")
    archive_path = source_email_archive_path(
        data_dir,
        mailbox_address=mailbox_address,
        email_uid=email_uid,
    )
    try:
        return write_private_bytes(data_dir, archive_path, raw_message)
    except MailArtifactError as error:
        raise SourceEmailArchiveError(
            f"保存原始邮件 EML 失败：{error}"
        ) from error


def read_source_email_archive(
    data_dir: Path,
    *,
    mailbox_address: object,
    email_uid: object,
) -> bytes:
    archive_path = source_email_archive_path(
        data_dir,
        mailbox_address=mailbox_address,
        email_uid=email_uid,
    )
    try:
        raw_message = archive_path.read_bytes()
    except OSError as error:
        raise SourceEmailArchiveError(
            f"读取原始邮件 EML 失败：{error}"
        ) from error
    if not raw_message:
        raise SourceEmailArchiveError("原始邮件 EML 为空")
    return raw_message
