from datetime import datetime
from pathlib import Path
from collections.abc import Callable, Mapping

from loguru import logger
from pydantic import ValidationError

from cutover_task import validate_task_for_submission
from email_attachments import attachment_path_from_relative
from mail_artifacts import (
    MailArtifactError,
    customer_excel_path,
    report_artifact_directory,
    source_email_archive_path,
)
from rpa.cutover_report import (
    BackboneReportResult,
    CutoverReportManualInterventionError as RpaManualInterventionError,
    CutoverReportOperationStep,
    CutoverReportRpaError,
    PortalCutoverReportRpa,
)
from rpa.session_config import PortalSessionSettings
from rpa.session_models import PortalEnvironment, PortalSessionError


class CutoverReportError(Exception):
    def __init__(self, message: str, *, result: Mapping[str, object] | None = None):
        super().__init__(message)
        self.result = dict(result or {})


class CutoverReportManualInterventionError(CutoverReportError):
    pass


def report_cutover_task(
    task: Mapping[str, object],
    *,
    environment: PortalEnvironment,
    data_dir: Path | None = None,
    report_id: int | None = None,
    progress_callback: Callable[[Mapping[str, object]], None] | None = None,
) -> dict[str, object]:
    task_id = task.get("id")
    line_type = task.get("line_type")
    if line_type not in ("customer", "backbone"):
        raise CutoverReportError(f"不支持的割接任务类型：{line_type}")
    settings = _load_portal_session_settings()
    storage_root = (
        data_dir
        if data_dir is not None
        else Path(__file__).resolve().parent / "data"
    )
    try:
        artifact_dir = _report_artifact_directory(
            storage_root,
            task,
            report_id,
        )
    except MailArtifactError as error:
        raise CutoverReportError(f"割接任务文件标识无效：{error}") from error
    completed_operation_log: list[CutoverReportOperationStep] = []
    live_operation_log: list[CutoverReportOperationStep] = []

    def emit_operation_step(step: CutoverReportOperationStep) -> None:
        live_operation_log.append(step)
        if progress_callback is None:
            return
        progress_callback({
            "phase": "running",
            "current_step": step.step,
            "current_step_label": step.label,
            "note": step.label,
            "operation_log": _serialize_operation_log(
                tuple(live_operation_log),
                artifact_root=storage_root,
            ),
        })

    try:
        rpa = PortalCutoverReportRpa(
            settings,
            operation_step_callback=emit_operation_step,
        )
        if line_type == "customer":
            excel_path = _resolve_customer_excel(task, data_dir=data_dir)
            result = rpa.upload_customer_excel(
                excel_path,
                environment=environment,
                screenshot_path=artifact_dir / "report-success.png",
            )
            outcome = _customer_report_outcome(result, storage_root)
        else:
            forms = _resolve_backbone_forms(task)
            attachments = (
                *_resolve_email_attachments(task, data_dir=data_dir),
                _resolve_source_email_attachment(task, data_dir=data_dir),
            )
            results = []
            for index, form in enumerate(forms, start=1):
                filename = (
                    "report-success.png"
                    if len(forms) == 1
                    else f"report-{index:02d}-success.png"
                )
                result = rpa.fill_backbone_form(
                    form,
                    attachment_paths=attachments,
                    environment=environment,
                    screenshot_path=artifact_dir / filename,
                )
                results.append(result)
                completed_operation_log.extend(result.operation_log)
            outcome = _backbone_report_outcome(results, storage_root)
    except PortalSessionError:
        raise
    except RpaManualInterventionError as error:
        raise CutoverReportManualInterventionError(
            str(error),
            result={
                "error": error.reason,
                "manual_intervention_required": True,
                "operation_log": _serialize_operation_log(
                    tuple(completed_operation_log) + error.operation_log,
                    artifact_root=storage_root,
                ),
            },
        ) from error
    except CutoverReportRpaError as error:
        raise CutoverReportError(
            str(error),
            result={
                "error": error.reason,
                "operation_log": _serialize_operation_log(
                    tuple(completed_operation_log) + error.operation_log,
                    artifact_root=storage_root,
                ),
            },
        ) from error

    logger.info("割接任务上报成功: id={}, line_type={}", task_id, line_type)
    return outcome


def _customer_report_outcome(
    result,
    artifact_root: Path,
) -> dict[str, object]:
    return {
        "status": "success",
        "final_url": result.final_url,
        "uploaded_filename": result.uploaded_filename,
        "screenshot_path": str(result.success_screenshot_path),
        "portal_task_number": result.portal_task_number,
        "operation_log": _serialize_operation_log(
            result.operation_log,
            artifact_root=artifact_root,
        ),
    }


def _backbone_report_outcome(
    results: list[BackboneReportResult],
    artifact_root: Path,
) -> dict[str, object]:
    task_numbers = [
        result.portal_task_number
        for result in results
        if result.portal_task_number
    ]
    operation_log = tuple(
        step
        for result in results
        for step in result.operation_log
    )
    uploaded_filenames = list(dict.fromkeys(
        filename
        for result in results
        for filename in result.uploaded_filenames
    ))
    return {
        "status": "success",
        "final_url": results[-1].final_url,
        "uploaded_filenames": uploaded_filenames,
        "screenshot_path": str(results[-1].success_screenshot_path),
        "portal_task_number": "、".join(task_numbers),
        "portal_task_numbers": task_numbers,
        "operation_log": _serialize_operation_log(
            operation_log,
            artifact_root=artifact_root,
        ),
    }


def _load_portal_session_settings() -> PortalSessionSettings:
    try:
        return PortalSessionSettings()
    except ValidationError as error:
        raise CutoverReportError(
            "RPA 配置无效，请检查 .env 中的 RPA_ 配置"
        ) from error


def _current_report_date() -> str:
    return datetime.now().astimezone().date().isoformat()


def _report_artifact_directory(
    data_dir: Path,
    task: Mapping[str, object],
    report_id: int | None,
) -> Path:
    return report_artifact_directory(
        data_dir,
        mailbox_address=task.get("source_mailbox_address"),
        email_uid=task.get("source_email_uid"),
        report_date=_current_report_date(),
        email_record_id=task.get("email_records_id"),
        task_id=task.get("id"),
        report_id=report_id,
    )


def _serialize_operation_log(
    operation_log: tuple[CutoverReportOperationStep, ...],
    *,
    artifact_root: Path,
) -> list[dict[str, str]]:
    return [
        {
            "step": entry.step,
            "label": entry.label,
            "screenshot_filename": entry.screenshot_path.resolve()
            .relative_to(artifact_root.resolve())
            .as_posix(),
            "captured_at": entry.captured_at,
        }
        for entry in operation_log
    ]


def _resolve_customer_excel(
    task: Mapping[str, object],
    *,
    data_dir: Path | None,
) -> Path:
    try:
        validate_task_for_submission({**task, "line_type": "customer"})
    except ValueError as error:
        raise CutoverReportError(str(error)) from error
    filename = task.get("customer_excel_filename")
    if not isinstance(filename, str) or not filename:
        raise CutoverReportError("客户线路割接任务没有可上报的 Excel")
    if Path(filename).name != filename or Path(filename).suffix.lower() != ".xlsx":
        raise CutoverReportError("客户线路割接任务的 Excel 文件名无效")

    root = (
        data_dir
        if data_dir is not None
        else Path(__file__).resolve().parent / "data"
    ).resolve()
    try:
        canonical_path = customer_excel_path(
            root,
            mailbox_address=task.get("source_mailbox_address"),
            email_uid=task.get("source_email_uid"),
            filename=filename,
        ).resolve()
    except MailArtifactError as error:
        raise CutoverReportError(f"客户线路割接文件标识无效：{error}") from error
    if canonical_path.is_file():
        return canonical_path
    legacy_path = (root / filename).resolve()
    if legacy_path.parent == root and legacy_path.is_file():
        return legacy_path
    raise CutoverReportError(f"客户线路割接 Excel 不存在：{filename}")


def _resolve_backbone_forms(
    task: Mapping[str, object],
) -> list[Mapping[str, object]]:
    fill_result = task.get("fill_result")
    if not isinstance(fill_result, Mapping):
        raise CutoverReportError("骨干线路任务没有可上报的表单数据")
    forms = fill_result.get("backbone_circuits")
    if not isinstance(forms, list) or not forms:
        raise CutoverReportError("骨干线路任务没有可上报的表单数据")
    if not all(isinstance(form, Mapping) and form for form in forms):
        raise CutoverReportError("骨干线路任务的表单数据格式无效")
    return forms


def _resolve_email_attachments(
    task: Mapping[str, object],
    *,
    data_dir: Path | None,
) -> tuple[Path, ...]:
    values = task.get("email_attachments") or []
    if not isinstance(values, list) or not all(
        isinstance(value, str) and value for value in values
    ):
        raise CutoverReportError("邮件附件列表格式无效")
    root = (
        data_dir
        if data_dir is not None
        else Path(__file__).resolve().parent / "data"
    ).resolve()
    resolved = []
    for value in values:
        candidate = attachment_path_from_relative(value, data_dir=root)
        if candidate is None:
            raise CutoverReportError(f"邮件附件路径无效：{value}")
        if not candidate.is_file():
            raise CutoverReportError(f"邮件附件不存在：{Path(value).name}")
        resolved.append(candidate)
    return tuple(resolved)


def _resolve_source_email_attachment(
    task: Mapping[str, object],
    *,
    data_dir: Path | None,
) -> Path:
    root = (
        data_dir
        if data_dir is not None
        else Path(__file__).resolve().parent / "data"
    ).resolve()
    try:
        eml_path = source_email_archive_path(
            root,
            mailbox_address=task.get("source_mailbox_address"),
            email_uid=task.get("source_email_uid"),
        ).resolve()
    except MailArtifactError as error:
        raise CutoverReportError(f"骨干线路原始邮件标识无效：{error}") from error
    if not eml_path.is_file() or eml_path.stat().st_size <= 0:
        raise CutoverReportError("骨干线路割接任务缺少原始邮件 EML")
    return eml_path
