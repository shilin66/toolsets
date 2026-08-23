from __future__ import annotations

# pyright: reportImplicitRelativeImport=false

import json
import re
from itertools import chain
from pathlib import Path, PurePosixPath

from .mail_artifact_migration_models import (
    ArtifactMigrationError,
    DatabaseUpdate,
    EmailRecord,
)
from .mail_artifact_migration_support import (
    MigrationPlanningState,
    is_mail_store_reference,
)
from mail_artifacts import (
    customer_excel_path,
    email_attachment_directory,
    legacy_mailbox_storage_key,
    mailbox_storage_key,
    source_email_archive_path,
)


type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)

_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
_UID_PATTERN = re.compile(r"(?:UID-|source-email-)(\d+)\.eml$", re.IGNORECASE)


def _parse_attachment_list(raw_value: str | None, row_id: int) -> list[str]:
    if not raw_value:
        return []
    try:
        value: JsonValue = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise ArtifactMigrationError(
            f"邮件记录 {row_id} 的附件字段不是有效 JSON"
        ) from error
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ArtifactMigrationError(f"邮件记录 {row_id} 的附件字段格式无效")
    return [item for item in value if isinstance(item, str)]


def plan_attachments(state: MigrationPlanningState) -> None:
    rows = state.connection.execute(
        "SELECT id, email_id, receiver, attachments "
        "FROM email_records ORDER BY id"
    ).fetchall()
    for row in rows:
        record = EmailRecord(
            int(row["id"]),
            int(row["email_id"]),
            str(row["receiver"]),
        )
        state.records[record.record_id] = record
        old_attachments = _parse_attachment_list(
            row["attachments"],
            record.record_id,
        )
        new_attachments: list[str] = []
        for value in old_attachments:
            logical_path = PurePosixPath(value)
            source = state.data_dir / Path(*logical_path.parts)
            target = email_attachment_directory(
                state.data_dir,
                mailbox_address=record.receiver,
                email_uid=record.email_uid,
            ) / source.name
            state.add_file("email-attachment", source, target)
            new_attachments.append(state.relative_path(target))
        if new_attachments != old_attachments:
            state.updates.append(DatabaseUpdate(
                "email_records",
                record.record_id,
                "attachments",
                json.dumps(new_attachments, ensure_ascii=False),
                row["attachments"],
            ))


def _existing_excel_source(
    state: MigrationPlanningState,
    record: EmailRecord,
    filename: str,
) -> Path:
    root_source = state.data_dir / filename
    legacy_source = (
        state.data_dir
        / "mail_store"
        / "mailboxes"
        / legacy_mailbox_storage_key(record.receiver)
        / "messages"
        / str(record.email_uid)
        / "cutover"
        / "customer"
        / filename
    )
    target = customer_excel_path(
        state.data_dir,
        mailbox_address=record.receiver,
        email_uid=record.email_uid,
        filename=filename,
    )
    for candidate in (root_source, legacy_source, target):
        if candidate.is_file():
            return candidate
    return root_source


def plan_customer_excels(state: MigrationPlanningState) -> None:
    rows = state.connection.execute(
        "SELECT id, email_records_id, customer_excel_filename "
        "FROM cutover_tasks WHERE customer_excel_filename IS NOT NULL "
        "ORDER BY id"
    ).fetchall()
    for row in rows:
        filename = str(row["customer_excel_filename"] or "").strip()
        if not filename:
            continue
        record_id = int(row["email_records_id"])
        record = state.records.get(record_id)
        if record is None:
            raise ArtifactMigrationError(
                f"割接任务 {row['id']} 找不到邮件记录 {record_id}"
            )
        target = customer_excel_path(
            state.data_dir,
            mailbox_address=record.receiver,
            email_uid=record.email_uid,
            filename=filename,
        )
        state.add_file(
            "customer-excel",
            _existing_excel_source(state, record, filename),
            target,
        )


def _source_record(
    state: MigrationPlanningState,
    source: Path,
    email_uid: int,
) -> EmailRecord:
    relative_parts = source.relative_to(state.data_dir).parts
    if is_mail_store_reference(source.relative_to(state.data_dir).as_posix()):
        mailbox_key = relative_parts[2]
        candidates = [
            record
            for record in state.records.values()
            if record.email_uid == email_uid
            and mailbox_key in {
                mailbox_storage_key(record.receiver),
                legacy_mailbox_storage_key(record.receiver),
            }
        ]
    else:
        path_record: EmailRecord | None = None
        for part_index, part in enumerate(relative_parts):
            if (
                _DATE_PATTERN.fullmatch(part) is not None
                and part_index + 1 < len(relative_parts)
                and relative_parts[part_index + 1].isdigit()
            ):
                path_record = state.records.get(int(relative_parts[part_index + 1]))
                break
        candidates = (
            [path_record]
            if path_record is not None
            else [
                record
                for record in state.records.values()
                if record.email_uid == email_uid
            ]
        )
    valid_candidates = [
        record
        for record in candidates
        if record is not None and record.email_uid == email_uid
    ]
    if len(valid_candidates) != 1:
        raise ArtifactMigrationError(
            f"无法唯一确定 EML 对应的邮箱和邮件记录：{source}"
        )
    return valid_candidates[0]


def plan_source_emails(state: MigrationPlanningState) -> None:
    sources = chain(
        sorted((state.data_dir / "rpa").rglob("*.eml")),
        sorted((state.data_dir / "mail_store").rglob("source-email-*.eml")),
    )
    for source in sources:
        uid_match = _UID_PATTERN.search(source.name)
        if uid_match is None:
            continue
        record = _source_record(state, source, int(uid_match.group(1)))
        target = source_email_archive_path(
            state.data_dir,
            mailbox_address=record.receiver,
            email_uid=record.email_uid,
        )
        state.add_file("source-eml", source, target)
