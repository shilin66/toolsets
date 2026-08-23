from __future__ import annotations

# pyright: reportImplicitRelativeImport=false

import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath

from .mail_artifact_migration_models import (
    ArtifactMigrationError,
    DatabaseUpdate,
)
from .mail_artifact_migration_support import (
    MigrationPlanningState,
    is_mail_store_reference,
)
from mail_artifacts import report_artifact_directory


type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)

_DATE_PATTERN = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_COMPACT_DATE_PATTERN = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})T")
_ERROR_SCREENSHOT_PATTERN = re.compile(
    r"(data/rpa/artifacts/cutover-report-[^\s；，。]+\.png|"
    r"mail_store/mailboxes/[^\s；，。]+\.png)"
)


def _parse_result(raw_value: str | None, report_id: int) -> dict[str, JsonValue]:
    if not raw_value:
        return {}
    try:
        value: JsonValue = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise ArtifactMigrationError(
            f"上报记录 {report_id} 的结果字段不是有效 JSON"
        ) from error
    if not isinstance(value, dict):
        raise ArtifactMigrationError(f"上报记录 {report_id} 的结果字段格式无效")
    return value


def _report_date(*values: str | None) -> str:
    for value in values:
        if not value:
            continue
        date_match = _DATE_PATTERN.search(value)
        compact_match = _COMPACT_DATE_PATTERN.search(value)
        candidates = (
            [date_match.group(0)]
            if date_match is not None
            else ["-".join(compact_match.groups())]
            if compact_match is not None
            else []
        )
        for candidate in candidates:
            try:
                return datetime.strptime(candidate, "%Y-%m-%d").date().isoformat()
            except ValueError:
                continue
    raise ArtifactMigrationError("无法确定上报截图日期")


def _legacy_report_source(state: MigrationPlanningState, value: str) -> Path:
    logical_path = PurePosixPath(value)
    if logical_path.is_absolute():
        return Path(value)
    if logical_path.parts and logical_path.parts[0] == "data":
        return state.project_dir / Path(*logical_path.parts)
    return state.data_dir / "rpa" / "artifacts" / Path(*logical_path.parts)


def _migrate_reference(
    state: MigrationPlanningState,
    value: str,
    target_directory: Path,
) -> str:
    source = (
        state.data_dir / Path(*PurePosixPath(value).parts)
        if is_mail_store_reference(value)
        else _legacy_report_source(state, value)
    )
    target = target_directory / source.name
    state.add_file("report-screenshot", source, target)
    return state.relative_path(target)


def _screenshot_references(result: dict[str, JsonValue]) -> list[str]:
    references: list[str] = []
    operation_log = result.get("operation_log")
    if isinstance(operation_log, list):
        for step in operation_log:
            if not isinstance(step, dict):
                continue
            value = step.get("screenshot_filename")
            if isinstance(value, str) and value:
                references.append(value)
    screenshot_path = result.get("screenshot_path")
    if isinstance(screenshot_path, str) and screenshot_path:
        references.append(screenshot_path)
    error_text = result.get("error")
    if isinstance(error_text, str):
        match = _ERROR_SCREENSHOT_PATTERN.search(error_text)
        if match is not None:
            references.append(match.group(0))
    return references


def _migrate_result_references(
    state: MigrationPlanningState,
    result: dict[str, JsonValue],
    target_directory: Path,
) -> bool:
    changed = False
    operation_log = result.get("operation_log")
    if isinstance(operation_log, list):
        for step in operation_log:
            if not isinstance(step, dict):
                continue
            value = step.get("screenshot_filename")
            if isinstance(value, str) and value:
                migrated = _migrate_reference(state, value, target_directory)
                if migrated != value:
                    step["screenshot_filename"] = migrated
                    changed = True
    screenshot_path = result.get("screenshot_path")
    if isinstance(screenshot_path, str) and screenshot_path:
        migrated = _migrate_reference(state, screenshot_path, target_directory)
        if migrated != screenshot_path:
            result["screenshot_path"] = migrated
            changed = True
    error_text = result.get("error")
    if isinstance(error_text, str):
        match = _ERROR_SCREENSHOT_PATTERN.search(error_text)
        if match is not None:
            old_path = match.group(0)
            migrated = _migrate_reference(state, old_path, target_directory)
            if migrated != old_path:
                result["error"] = error_text.replace(old_path, migrated)
                changed = True
    return changed


def plan_reports(state: MigrationPlanningState) -> None:
    rows = state.connection.execute(
        "SELECT r.id, r.task_id, r.result, r.create_time, "
        "t.email_records_id, e.email_id, e.receiver "
        "FROM cutover_reports AS r "
        "JOIN cutover_tasks AS t ON t.id = r.task_id "
        "JOIN email_records AS e ON e.id = t.email_records_id "
        "ORDER BY r.id"
    ).fetchall()
    for row in rows:
        report_id = int(row["id"])
        result = _parse_result(row["result"], report_id)
        references = _screenshot_references(result)
        if not references:
            continue
        target_directory = report_artifact_directory(
            state.data_dir,
            mailbox_address=str(row["receiver"]),
            email_uid=int(row["email_id"]),
            report_date=_report_date(*references, str(row["create_time"] or "")),
            email_record_id=int(row["email_records_id"]),
            task_id=int(row["task_id"]),
            report_id=report_id,
        )
        if _migrate_result_references(state, result, target_directory):
            state.updates.append(DatabaseUpdate(
                "cutover_reports",
                report_id,
                "result",
                json.dumps(result, ensure_ascii=False),
                row["result"],
            ))
