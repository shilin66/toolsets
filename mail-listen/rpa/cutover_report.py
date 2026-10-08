import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, time_ns
from urllib.parse import quote, urlsplit, urlunsplit

from playwright.sync_api import (
    Locator,
    Page,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from .captcha import RpaError
from .session_config import PortalSessionSettings
from .session_models import PortalEnvironment, PortalSessionError


def build_cutover_report_url(
    session_check_url: str,
    *,
    timestamp_ms: int | None = None,
) -> str:
    parsed = urlsplit(session_check_url)
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    inner_url = (
        f"{origin}/orderHandle/index.html"
        "#/emOrderCreate/eeOrderCoEffect"
    )
    current_timestamp_ms = (
        timestamp_ms
        if timestamp_ms is not None
        else time_ns() // 1_000_000
    )
    return (
        f"{origin}/portal/?ignoreDisableDevtool=true#/iframe/"
        f"{quote(inner_url, safe='')}_iframePath/"
        f"{quote('割接影响', safe='')}/?t={current_timestamp_ms}"
    )


def build_backbone_report_url(
    session_check_url: str,
    *,
    timestamp_ms: int | None = None,
) -> str:
    parsed = urlsplit(session_check_url)
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    inner_url = (
        f"{origin}/orderHandle/index.html"
        "#/emOrderCreate/eeOrderTransNetworkCreate"
    )
    current_timestamp_ms = (
        timestamp_ms
        if timestamp_ms is not None
        else time_ns() // 1_000_000
    )
    return (
        f"{origin}/portal/?ignoreDisableDevtool=true#/iframe/"
        f"{quote(inner_url, safe='')}_iframePath/"
        f"{quote('传输一干', safe='')}/?t={current_timestamp_ms}"
    )


@dataclass(frozen=True, slots=True)
class CutoverReportResult:
    final_url: str
    uploaded_filename: str
    success_screenshot_path: Path
    portal_task_number: str
    operation_log: tuple["CutoverReportOperationStep", ...]


@dataclass(frozen=True, slots=True)
class BackboneReportResult:
    final_url: str
    uploaded_filenames: tuple[str, ...]
    success_screenshot_path: Path
    portal_task_number: str
    submitted: bool
    operation_log: tuple["CutoverReportOperationStep", ...]


@dataclass(frozen=True, slots=True)
class CutoverReportOperationStep:
    step: str
    label: str
    screenshot_path: Path
    captured_at: str


class CutoverReportRpaError(RpaError):
    def __init__(
        self,
        reason: str,
        screenshot_path: Path | None = None,
        operation_log: tuple[CutoverReportOperationStep, ...] = (),
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.screenshot_path = screenshot_path
        self.operation_log = operation_log

    def __str__(self) -> str:
        if self.screenshot_path is None:
            return self.reason
        return f"{self.reason}；失败截图：{self.screenshot_path}"


class CutoverReportManualInterventionError(CutoverReportRpaError):
    pass


class PortalCutoverReportRpa:
    _BACKBONE_SECTION_STEPS = {
        "基本信息": ("backbone_basic_info_filled", "骨干线路基本信息已填写"),
        "割接对象": ("backbone_cutover_object_filled", "骨干线路割接对象已填写"),
        "人员信息": ("backbone_people_filled", "骨干线路人员信息已填写"),
        "其他": ("backbone_other_filled", "骨干线路其他信息已填写"),
        "确认项": (
            "backbone_confirmations_checked",
            "骨干线路确认项已勾选",
        ),
        "关联网络资源变更单": (
            "backbone_related_change_filled",
            "关联网络资源变更单信息已填写",
        ),
    }
    _BACKBONE_FIELD_ORDER = {
        "基本信息": (
            "标题",
            "割接分类",
            "割接原因分类",
            "涉及系统（网络）",
            "操作厂家",
            "设备名称",
            "割接省份",
            "变更操作内容",
            "变更操作等级",
            "调度方式",
            "中断类型",
            "中断原因",
            "中断时间 (分钟)",
            "需要配合的省",
            "是否涉及集团维护设备或业务影响超出本省范围",
            "是否有回退应急预案和舆情应对方案",
            "割接地点",
            "是否跨专业",
        ),
        "割接对象": (
            "割接类型",
            "割接对象所属机构",
            "割接对象类型",
            "系统名称",
            "割接开始时间",
            "割接结束时间",
        ),
        "人员信息": (
            "现场指挥人员名称",
            "现场指挥人电话",
            "现场指挥人单位",
            "支撑人员",
            "支撑人电话",
            "支撑人单位",
            "省公司审核人姓名",
            "省公司审核人电话",
            "省公司审核人单位",
            "业务测试人员",
            "业务测试人员电话",
            "业务测试人单位",
            "操作审核人姓名",
            "操作审核人电话",
            "操作审核人单位",
            "业务复核人姓名",
            "业务复核人电话",
            "业务复核人单位",
        ),
        "其他": (
            "是否增加、删除或更改光开关(OLP)",
            "是否变更网管中网元管理对象配置",
            "是否需要集团网管配置操作",
            "是否影响联通",
            "影响军队",
            "割接原因",
            "风险操作影响范围",
            "是否为境外运营商割接或联通割接(跳过变更操作方案校验)",
        ),
        "确认项": (
            "该割接已按照集团相关文件要求经过省公司领导审批。",
            "为避免省内跨专业的割接冲突影响CN2网，经和省数据专业确认，此割接操作不会与数据割接冲突。",
            "生成多张独立通道割接方案。",
        ),
        "关联网络资源变更单": ("是否设计网络资源变更",),
    }
    _BACKBONE_PORTAL_LINKED_FIELDS = frozenset({
        "涉及系统（网络）",
        "操作厂家",
        "设备名称",
        "变更操作等级",
    })
    _BACKBONE_LABEL_ALIASES = {
        "割接开始时间": ("割接开始时间", "割接开始(北京时间)"),
        "割接结束时间": ("割接结束时间", "割接结束(北京时间)"),
        "现场指挥人员名称": ("现场指挥人员名称", "现场指挥人姓名"),
        "现场指挥人电话": ("现场指挥人电话", "现场指挥人手机"),
        "支撑人员": ("支撑人员", "支撑人员姓名"),
        "支撑人电话": ("支撑人电话", "支撑人员手机"),
        "支撑人单位": ("支撑人单位", "支撑人员单位"),
        "省公司审核人电话": ("省公司审核人电话", "省公司审核人手机"),
        "业务测试人员": ("业务测试人员", "业务测试人姓名"),
        "业务测试人员电话": ("业务测试人员电话", "业务测试人手机"),
        "操作审核人姓名": ("操作审核人姓名", "操作复核人姓名"),
        "操作审核人电话": (
            "操作审核人电话",
            "操作审核人手机",
            "操作复核人电话",
        ),
        "操作审核人单位": ("操作审核人单位", "操作复核人单位"),
        "业务测试人单位": ("业务测试人单位", "业务测试人员单位"),
        "业务复核人电话": ("业务复核人电话", "业务复核人手机"),
        "是否设计网络资源变更": (
            "是否设计网络资源变更",
            "是否关联变更操作需求单",
        ),
    }

    def __init__(
        self,
        settings: PortalSessionSettings,
        *,
        operation_step_callback: Callable[[CutoverReportOperationStep], None]
        | None = None,
    ) -> None:
        self._settings = settings
        self._operation_step_callback = operation_step_callback

    def upload_customer_excel(
        self,
        excel_path: Path,
        *,
        environment: PortalEnvironment,
        screenshot_path: Path,
    ) -> CutoverReportResult:
        settings = self._settings
        target = settings.resolve_environment(environment)
        if not target.state_path.is_file():
            raise CutoverReportRpaError("登录会话文件不存在，无法执行割接上报")
        if not excel_path.is_file():
            raise CutoverReportRpaError(f"待上报 Excel 不存在：{excel_path.name}")

        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    headless=settings.headless,
                    slow_mo=settings.slow_mo_ms,
                )
            except PlaywrightError as error:
                raise CutoverReportRpaError(
                    "无法启动 Chromium，请确认已安装浏览器运行时"
                ) from error

            context = None
            page = None
            operation_log: list[CutoverReportOperationStep] = []
            try:
                context = browser.new_context(
                    storage_state=str(target.state_path),
                    ignore_https_errors=settings.ignore_https_errors,
                    viewport={
                        "width": settings.viewport_width,
                        "height": settings.viewport_height,
                    },
                )
                page = context.new_page()
                page.set_default_timeout(settings.timeout_ms)
                page.goto(
                    build_cutover_report_url(target.session_check_url),
                    wait_until="domcontentloaded",
                    timeout=settings.timeout_ms,
                )
                self._click_with_pacing(page, self._wait_for_report_page(page))

                dialog = self._find_visible(
                    page,
                    settings.report_dialog_selector,
                )
                file_input = self._find_attached(
                    page,
                    settings.report_file_input_selector,
                )
                file_input.set_input_files(str(excel_path))
                uploaded_value = file_input.input_value()
                if not uploaded_value.endswith(excel_path.name):
                    raise CutoverReportRpaError("综调系统未接收到待上报 Excel")

                self._capture_operation_step(
                    page,
                    screenshot_path,
                    operation_log,
                    "excel_selected",
                    "已选择上报 Excel",
                )

                self._click_with_pacing(
                    page,
                    self._find_visible(page, settings.report_submit_selector),
                )
                self._capture_operation_step(
                    page,
                    screenshot_path,
                    operation_log,
                    "submit_clicked",
                    "已提交 Excel，等待综调系统校验",
                )
                portal_task_number = self._complete_import_dialogs(
                    page,
                    dialog,
                    screenshot_path,
                    operation_log,
                )
                self._capture_operation_step(
                    page,
                    screenshot_path,
                    operation_log,
                    "import_log",
                    f"导入成功，综调任务号 {portal_task_number}",
                )
                self._capture_screenshot(page, screenshot_path)
                return CutoverReportResult(
                    final_url=page.url,
                    uploaded_filename=excel_path.name,
                    success_screenshot_path=screenshot_path,
                    portal_task_number=portal_task_number,
                    operation_log=tuple(operation_log),
                )
            except CutoverReportRpaError as error:
                if error.screenshot_path is not None:
                    raise
                failure_path = self._capture_failure_screenshot(
                    page,
                    screenshot_path.parent,
                )
                self._append_failure_step(
                    operation_log,
                    failure_path,
                    error.reason,
                )
                raise CutoverReportRpaError(
                    reason=error.reason,
                    screenshot_path=failure_path,
                    operation_log=tuple(operation_log),
                ) from error
            except (
                PlaywrightError,
            ) as error:
                failure_path = self._capture_failure_screenshot(
                    page,
                    screenshot_path.parent,
                )
                if isinstance(error, PlaywrightTimeoutError):
                    reason = "综调系统页面操作超时，请检查上报页面和选择器配置"
                else:
                    reason = str(error) or "综调系统割接上报页面操作失败"
                self._append_failure_step(operation_log, failure_path, reason)
                raise CutoverReportRpaError(
                    reason=reason,
                    screenshot_path=failure_path,
                    operation_log=tuple(operation_log),
                ) from error
            finally:
                try:
                    if context is not None:
                        context.close()
                finally:
                    browser.close()

    def fill_backbone_form(
        self,
        form_data: Mapping[str, object],
        *,
        attachment_paths: tuple[Path, ...],
        environment: PortalEnvironment,
        screenshot_path: Path,
        submit: bool = True,
    ) -> BackboneReportResult:
        settings = self._settings
        target = settings.resolve_environment(environment)
        if not target.state_path.is_file():
            raise CutoverReportRpaError("登录会话文件不存在，无法执行割接上报")
        if not form_data:
            raise CutoverReportRpaError("骨干线路任务没有可填报的表单数据")
        for attachment_path in attachment_paths:
            if not attachment_path.is_file():
                raise CutoverReportRpaError(
                    f"邮件附件不存在：{attachment_path.name}"
                )

        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    headless=settings.headless,
                    slow_mo=settings.slow_mo_ms,
                )
            except PlaywrightError as error:
                raise CutoverReportRpaError(
                    "无法启动 Chromium，请确认已安装浏览器运行时"
                ) from error

            context = None
            page = None
            operation_log: list[CutoverReportOperationStep] = []
            try:
                context = browser.new_context(
                    storage_state=str(target.state_path),
                    ignore_https_errors=settings.ignore_https_errors,
                    viewport={
                        "width": settings.viewport_width,
                        "height": settings.viewport_height,
                    },
                )
                page = context.new_page()
                page.set_default_timeout(settings.timeout_ms)
                page.goto(
                    build_backbone_report_url(target.session_check_url),
                    wait_until="domcontentloaded",
                    timeout=settings.timeout_ms,
                )
                self._wait_for_backbone_report_page(page)
                self._capture_operation_step(
                    page,
                    screenshot_path,
                    operation_log,
                    "backbone_form_ready",
                    "骨干线路填报页面已加载",
                )

                for section, (step, label) in self._BACKBONE_SECTION_STEPS.items():
                    fields = form_data.get(section)
                    if not isinstance(fields, Mapping):
                        continue
                    fields_to_fill = tuple(
                        (str(field_name), value)
                        for field_name, value in self._ordered_backbone_field_items(
                            section,
                            fields,
                        )
                        if value is not None and value != "" and value != []
                    )
                    filled = bool(fields_to_fill)
                    if section == "人员信息":
                        self._fill_backbone_personnel_fields(page, fields_to_fill)
                    else:
                        if section == "割接对象":
                            self._assert_backbone_basic_info_retained(page, form_data)
                        for field_name, value in fields_to_fill:
                            if section == "割接对象" and field_name == "系统名称":
                                self._assert_backbone_basic_info_retained(page, form_data)
                            self._set_backbone_field(
                                page,
                                section,
                                field_name,
                                value,
                            )
                        if section == "割接对象":
                            self._assert_backbone_basic_info_retained(page, form_data)
                    if filled:
                        self._capture_operation_step(
                            page,
                            screenshot_path,
                            operation_log,
                            step,
                            label,
                        )

                self._assert_backbone_basic_info_retained(page, form_data)
                uploaded_filenames = self._upload_backbone_attachments(
                    page,
                    attachment_paths,
                )
                if uploaded_filenames:
                    self._capture_operation_step(
                        page,
                        screenshot_path,
                        operation_log,
                        "backbone_attachments_uploaded",
                        f"已上传 {len(uploaded_filenames)} 个割接方案附件",
                    )

                if not submit:
                    self._capture_screenshot(page, screenshot_path)
                    return BackboneReportResult(
                        final_url=page.url,
                        uploaded_filenames=uploaded_filenames,
                        success_screenshot_path=screenshot_path,
                        portal_task_number="",
                        submitted=False,
                        operation_log=tuple(operation_log),
                    )

                portal_task_number = self._submit_backbone_form(page)
                self._capture_operation_step(
                    page,
                    screenshot_path,
                    operation_log,
                    "backbone_submit_succeeded",
                    (
                        f"骨干线路提交成功，综调任务号 {portal_task_number}"
                        if portal_task_number
                        else "骨干线路提交成功"
                    ),
                )
                self._capture_screenshot(page, screenshot_path)
                return BackboneReportResult(
                    final_url=page.url,
                    uploaded_filenames=uploaded_filenames,
                    success_screenshot_path=screenshot_path,
                    portal_task_number=portal_task_number,
                    submitted=True,
                    operation_log=tuple(operation_log),
                )
            except PortalSessionError:
                raise
            except CutoverReportManualInterventionError as error:
                if error.screenshot_path is not None:
                    raise
                if page is None:
                    raise CutoverReportManualInterventionError(
                        reason=error.reason,
                        operation_log=tuple(operation_log),
                    ) from error
                step = self._capture_operation_step(
                    page,
                    screenshot_path,
                    operation_log,
                    "manual_intervention_required",
                    error.reason,
                )
                raise CutoverReportManualInterventionError(
                    reason=error.reason,
                    screenshot_path=step.screenshot_path,
                    operation_log=tuple(operation_log),
                ) from error
            except CutoverReportRpaError as error:
                if error.screenshot_path is not None:
                    raise
                failure_path = self._capture_failure_screenshot(
                    page,
                    screenshot_path.parent,
                )
                self._append_failure_step(
                    operation_log,
                    failure_path,
                    error.reason,
                )
                raise CutoverReportRpaError(
                    reason=error.reason,
                    screenshot_path=failure_path,
                    operation_log=tuple(operation_log),
                ) from error
            except PlaywrightError as error:
                failure_path = self._capture_failure_screenshot(
                    page,
                    screenshot_path.parent,
                )
                reason = (
                    "综调系统骨干线路页面操作超时，请检查填报页面和选择器配置"
                    if isinstance(error, PlaywrightTimeoutError)
                    else str(error) or "综调系统骨干线路填报页面操作失败"
                )
                self._append_failure_step(operation_log, failure_path, reason)
                raise CutoverReportRpaError(
                    reason=reason,
                    screenshot_path=failure_path,
                    operation_log=tuple(operation_log),
                ) from error
            finally:
                try:
                    if context is not None:
                        context.close()
                finally:
                    browser.close()

    @classmethod
    def _ordered_backbone_field_items(
        cls,
        section: str,
        fields: Mapping[str, object],
    ) -> tuple[tuple[str, object], ...]:
        configured_order = cls._BACKBONE_FIELD_ORDER.get(section, ())
        ordered_names = [
            field_name
            for field_name in configured_order
            if field_name in fields
        ]
        ordered_names.extend(
            str(field_name)
            for field_name in fields
            if str(field_name) not in configured_order
        )
        return tuple(
            (field_name, fields[field_name])
            for field_name in ordered_names
            if not (
                section == "基本信息"
                and field_name in cls._BACKBONE_PORTAL_LINKED_FIELDS
            )
        )

    def _wait_for_backbone_report_page(self, page: Page) -> None:
        deadline = monotonic() + self._settings.timeout_ms / 1000
        while monotonic() < deadline:
            if self._first_visible(page, (
                self._settings.username_selector,
                self._settings.mobile_phone_selector,
            )) is not None:
                raise PortalSessionError(
                    "RPA_SESSION_REQUIRED",
                    "综调会话已失效，请前往综调会话重新登录",
                )
            ready = self._find_locator_once(
                page,
                self._settings.report_backbone_ready_selector,
                require_visible=True,
            )
            submit = self._find_locator_once(
                page,
                self._settings.report_backbone_submit_selector,
                require_visible=True,
            )
            if ready is not None and submit is not None:
                self._wait_for_page_settled(page)
                return
            page.wait_for_timeout(200)
        raise CutoverReportRpaError("综调系统未加载骨干线路填报页面")

    def _set_backbone_field(
        self,
        page: Page,
        section: str,
        field_name: str,
        value: object,
    ) -> None:
        aliases = self._BACKBONE_LABEL_ALIASES.get(field_name, (field_name,))
        if section == "确认项":
            self._set_checkbox_by_text(page, aliases, value == "是")
            return

        values = value if isinstance(value, list) else [value]
        text_values = [str(item) for item in values]

        if section == "基本信息" and field_name == "中断时间 (分钟)":
            text_input = self._find_backbone_interruption_minutes_input(page)
            self._pace_before_action(page)
            text_input.fill(text_values[0])
            text_input.press("Tab")
            self._wait_for_page_settled(page)
            return

        form_item = self._find_form_item(page, aliases)

        if section == "割接对象" and field_name == "系统名称":
            self._select_backbone_system_names(page, form_item, text_values)
            return
        if section == "割接对象" and field_name in (
            "割接开始时间",
            "割接结束时间",
        ):
            self._set_backbone_datetime(
                page,
                form_item,
                field_name,
                text_values[0],
            )
            return

        native_select = form_item.locator("select").first
        if native_select.count() > 0:
            if native_select.get_attribute("multiple") is not None:
                native_select.select_option(label=text_values)
            else:
                native_select.select_option(label=text_values[0])
            self._wait_for_page_settled(page)
            return

        radios = form_item.locator('input[type="radio"]')
        if radios.count() > 0:
            self._select_radio(page, form_item, text_values[0])
            return

        element_select = form_item.locator(
            ".el-select, .el-cascader, [role=combobox]"
        ).first
        if element_select.count() > 0:
            self._select_element_values(page, element_select, text_values)
            return

        textarea = form_item.locator("textarea:visible").first
        if textarea.count() > 0:
            self._pace_before_action(page)
            textarea.fill(text_values[0])
            self._wait_for_page_settled(page)
            return

        text_input = form_item.locator(
            'input:visible:not([type="radio"]):not([type="checkbox"]):not([type="file"])'
        ).first
        if text_input.count() > 0:
            if text_input.is_disabled():
                if text_input.input_value().strip() == text_values[0]:
                    return
                raise CutoverReportRpaError(
                    f"骨干线路字段不可编辑且值不匹配：{field_name}"
                )
            if text_input.get_attribute("readonly") is not None:
                self._select_element_values(page, text_input, text_values)
                return
            self._pace_before_action(page)
            text_input.fill(text_values[0])
            text_input.press("Tab")
            self._wait_for_page_settled(page)
            return

        raise CutoverReportRpaError(f"骨干线路表单未找到字段控件：{field_name}")

    def _fill_backbone_personnel_fields(
        self,
        page: Page,
        fields: tuple[tuple[str, object], ...],
    ) -> None:
        if not fields:
            return

        self._wait_for_page_settled(page)
        filled_controls: list[tuple[str, Locator, str]] = []
        for field_name, value in fields:
            aliases = self._BACKBONE_LABEL_ALIASES.get(
                field_name,
                (field_name,),
            )
            form_item = self._find_form_item(page, aliases)
            text_input = form_item.locator(
                'input:visible:not([type="radio"]):not([type="checkbox"]):not([type="file"])'
            ).first
            if text_input.count() == 0:
                raise CutoverReportRpaError(
                    f"骨干线路表单未找到人员字段控件：{field_name}"
                )

            text_value = str(value[0] if isinstance(value, list) else value)
            if text_input.is_disabled():
                if text_input.input_value().strip() != text_value:
                    raise CutoverReportRpaError(
                        f"骨干线路字段不可编辑且值不匹配：{field_name}"
                    )
                continue

            if text_input.get_attribute("readonly") is not None:
                if text_input.input_value().strip() != text_value:
                    self._wait_for_page_settled(page)
                    self._select_element_values(
                        page,
                        text_input,
                        [text_value],
                    )
            else:
                text_input.fill(text_value)
            filled_controls.append((field_name, text_input, text_value))

        self._wait_for_page_settled(page)
        for field_name, text_input, expected_value in filled_controls:
            if text_input.input_value().strip() != expected_value:
                raise CutoverReportRpaError(
                    f"骨干线路人员字段填写未生效：{field_name}"
                )

    def _find_backbone_interruption_minutes_input(self, page: Page) -> Locator:
        deadline = monotonic() + self._settings.timeout_ms / 1000
        while monotonic() < deadline:
            for frame in page.frames:
                units = frame.get_by_text("分钟", exact=True)
                try:
                    for index in range(units.count()):
                        unit = units.nth(index)
                        if not unit.is_visible():
                            continue
                        control = unit.locator(
                            "xpath=ancestor::*[.//input[not(@type='radio') "
                            "and not(@type='checkbox') and not(@type='file')]][1]"
                        )
                        input_control = control.locator(
                            'input:visible:not([type="radio"]):not([type="checkbox"]):not([type="file"])'
                        ).first
                        if input_control.count() > 0:
                            return input_control
                except PlaywrightError:
                    continue
            page.wait_for_timeout(200)
        raise CutoverReportRpaError(
            "骨干线路表单未找到字段控件：中断时间 (分钟)"
        )

    def _set_backbone_datetime(
        self,
        page: Page,
        form_item: Locator,
        field_name: str,
        value: str,
    ) -> None:
        input_control = form_item.locator("input:visible").first
        if input_control.count() == 0:
            raise CutoverReportRpaError(
                f"骨干线路表单未找到时间控件：{field_name}"
            )
        raw_value = value.strip()
        parsed_value: datetime | None = None
        for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed_value = datetime.strptime(raw_value, date_format)
                break
            except ValueError:
                continue
        if parsed_value is None:
            raise CutoverReportRpaError(
                f"骨干线路时间字段格式错误：{field_name}"
            )
        model_value = parsed_value.strftime("%Y-%m-%d %H:%M:%S")
        display_value = parsed_value.strftime("%Y-%m-%d %H:%M")
        self._pace_before_action(page)
        model_updated = input_control.evaluate(
            "(element, value) => { const root = element.parentElement; "
            "const component = root && root.__vue__; "
            "const vnode = component && component.$vnode; "
            "const model = vnode && vnode.data && vnode.data.model; "
            "if (!model || typeof model.callback !== 'function') return false; "
            "model.callback(value); "
            "if ('userInput' in component) component.userInput = null; "
            "if ('pickerVisible' in component) component.pickerVisible = false; "
            "return true; }",
            model_value,
        )
        if not model_updated:
            raise CutoverReportRpaError(
                f"骨干线路时间控件无法写入绑定值：{field_name}"
            )
        self._wait_for_page_settled(page)
        if input_control.input_value().strip() != display_value:
            raise CutoverReportRpaError(
                f"骨干线路时间字段填写未生效：{field_name}"
            )

    def _find_form_item(
        self,
        page: Page,
        aliases: tuple[str, ...],
    ) -> Locator:
        normalized_aliases = {self._normalize_label(alias) for alias in aliases}
        deadline = monotonic() + self._settings.timeout_ms / 1000
        while monotonic() < deadline:
            for frame in page.frames:
                labels = frame.locator(
                    ".el-form-item__label, .form-label, label"
                )
                try:
                    for index in range(labels.count()):
                        label = labels.nth(index)
                        if not label.is_visible():
                            continue
                        if self._normalize_label(label.inner_text()) not in normalized_aliases:
                            continue
                        form_item = label.locator(
                            "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' el-form-item ')][1]"
                        )
                        if form_item.count() > 0:
                            return form_item
                        return label.locator("xpath=..")
                except PlaywrightError:
                    continue
            page.wait_for_timeout(200)
        raise CutoverReportRpaError(
            f"骨干线路表单未找到字段：{' / '.join(aliases)}"
        )

    @staticmethod
    def _normalize_label(value: str) -> str:
        normalized = (value or "").translate(str.maketrans("（）", "()"))
        return re.sub(r"^[*＊]\s*|[：:]$|\s+", "", normalized)

    def _select_radio(self, page: Page, form_item: Locator, value: str) -> None:
        radios = form_item.locator('input[type="radio"]')
        for index in range(radios.count()):
            radio = radios.nth(index)
            radio_value = radio.get_attribute("value") or ""
            radio_label = radio.locator("xpath=ancestor::label[1]")
            label_text = radio_label.inner_text() if radio_label.count() else ""
            if value not in (radio_value.strip(), label_text.strip()):
                continue
            if radio.is_checked():
                return
            if radio_label.count() and radio_label.is_visible():
                self._click_with_pacing(page, radio_label)
            else:
                self._pace_before_action(page)
                radio.check(force=True)
                self._wait_for_page_settled(page)
            if not radio.is_checked():
                raise CutoverReportRpaError(
                    f"骨干线路单选项选择未生效：{value}"
                )
            return
        raise CutoverReportRpaError(f"骨干线路单选项不存在：{value}")

    def _select_element_values(
        self,
        page: Page,
        control: Locator,
        values: list[str],
    ) -> None:
        for value in values:
            self._pace_before_action(page)
            option = self._find_visible_option_once(page, value)
            if option is None:
                control.click()
            input_control = control.locator("input:visible").first
            if (
                input_control.count() == 0
                and control.get_attribute("role") == "combobox"
            ):
                input_control = control
            if (
                input_control.count() > 0
                and input_control.get_attribute("readonly") is None
            ):
                input_control.fill(value)
            option = self._find_visible_option(page, value)
            self._click_with_pacing(page, option)

    def _select_backbone_system_names(
        self,
        page: Page,
        form_item: Locator,
        values: list[str],
    ) -> None:
        control = form_item.locator("textarea:visible, input:visible").first
        self._pace_before_action(page)
        for field_name in ("割接对象所属机构", "割接对象类型"):
            self._assert_backbone_field_value(page, field_name)
        # The fixed footer can cover an in-viewport input; forced clicks hit Reset.
        control.evaluate(
            "element => element.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'})"
        )
        control.click()
        self._wait_for_page_settled(page)

        deadline = monotonic() + self._settings.timeout_ms / 1000
        dialog = self._visible_dialog_containing(page, "选择系统名称")
        while dialog is None and monotonic() < deadline:
            page.wait_for_timeout(200)
            dialog = self._visible_dialog_containing(page, "选择系统名称")
        if dialog is None:
            raise CutoverReportRpaError("综调系统未打开系统名称选择窗口")

        search = dialog.locator('input[placeholder="请输入电路名"]:visible').first
        query = dialog.get_by_role("button", name="查询", exact=True).first
        for value in values:
            row = self._find_backbone_system_row(dialog, value)
            if row is None:
                self._pace_before_action(page)
                search.fill(value)
                self._click_with_pacing(page, query)
                row = self._find_backbone_system_row(dialog, value)
            if row is None:
                raise CutoverReportManualInterventionError(
                    f"综调系统中系统名称不存在：{value}，请转人工处理"
                )

            checkbox = row.locator('input[type="checkbox"]').first
            wrapper = row.locator(".el-checkbox__input:visible").first
            if wrapper.count() > 0:
                self._click_with_pacing(page, wrapper)
            else:
                self._pace_before_action(page)
                checkbox.check(force=True)
                self._wait_for_page_settled(page)
            if not checkbox.is_checked():
                raise CutoverReportRpaError(
                    f"综调系统名称选择未生效：{value}"
                )

        confirm = dialog.get_by_role("button", name="确定", exact=True).last
        self._click_with_pacing(page, confirm)
        selected_value = control.input_value()
        if not all(value in selected_value for value in values):
            raise CutoverReportManualInterventionError(
                "综调系统未保留全部系统名称选择，请转人工处理"
            )

    def _assert_backbone_basic_info_retained(
        self,
        page: Page,
        form_data: Mapping[str, object],
    ) -> None:
        fields = form_data.get("基本信息")
        if not isinstance(fields, Mapping):
            return
        for field_name in ("标题", "割接分类", "割接原因分类", "割接省份"):
            expected = fields.get(field_name)
            if expected is not None and expected != "":
                self._assert_backbone_field_value(page, field_name, str(expected))

    def _assert_backbone_field_value(
        self,
        page: Page,
        field_name: str,
        expected: str | None = None,
    ) -> None:
        aliases = self._BACKBONE_LABEL_ALIASES.get(field_name, (field_name,))
        form_item = self._find_form_item(page, aliases)
        native_select = form_item.locator("select").first
        if native_select.count() > 0:
            selected = native_select.locator("option:checked")
            actual = (
                selected.first.inner_text().strip()
                if native_select.input_value().strip() and selected.count()
                else ""
            )
        else:
            control = form_item.locator(
                'textarea:visible, input:visible:not([type="radio"]):not([type="checkbox"]):not([type="file"])'
            ).first
            actual = control.input_value().strip()
        if not actual or (expected is not None and actual != expected.strip()):
            raise CutoverReportRpaError(
                f"骨干线路字段为空或填报值已改变：{field_name}，已停止填报"
            )

    @staticmethod
    def _find_backbone_system_row(
        dialog: Locator,
        value: str,
    ) -> Locator | None:
        rows = dialog.locator("tbody tr:visible")
        for index in range(rows.count()):
            row = rows.nth(index)
            cells = row.locator("td")
            if any(
                cells.nth(cell_index).inner_text().strip() == value
                for cell_index in range(cells.count())
            ):
                return row
        return None

    def _find_visible_option(self, page: Page, value: str) -> Locator:
        deadline = monotonic() + self._settings.timeout_ms / 1000
        while monotonic() < deadline:
            option = self._find_visible_option_once(page, value)
            if option is not None:
                return option
            page.wait_for_timeout(200)
        raise CutoverReportRpaError(f"骨干线路下拉选项不存在：{value}")

    @staticmethod
    def _find_visible_option_once(page: Page, value: str) -> Locator | None:
        selectors = (
            ".el-select-dropdown__item:visible",
            ".el-cascader-node:visible",
            '[role="option"]:visible',
        )
        for frame in page.frames:
            for selector in selectors:
                options = frame.locator(selector)
                try:
                    for index in range(options.count()):
                        option = options.nth(index)
                        if option.inner_text().strip() == value:
                            return option
                except PlaywrightError:
                    continue
        return None

    def _set_checkbox_by_text(
        self,
        page: Page,
        aliases: tuple[str, ...],
        checked: bool,
    ) -> None:
        normalized_aliases = {self._normalize_label(alias) for alias in aliases}
        deadline = monotonic() + self._settings.timeout_ms / 1000
        while monotonic() < deadline:
            for frame in page.frames:
                labels = frame.locator("label.el-checkbox, label")
                try:
                    label_count = labels.count()
                except PlaywrightError:
                    continue
                for index in range(label_count):
                    try:
                        label = labels.nth(index)
                        if not label.is_visible():
                            continue
                        if self._normalize_label(label.inner_text()) not in normalized_aliases:
                            continue
                    except PlaywrightError:
                        continue
                    checkbox = label.locator('input[type="checkbox"]').first
                    if checkbox.count() == 0:
                        continue
                    if checkbox.is_checked() == checked:
                        return
                    visible_control = label.locator(
                        ".el-checkbox__input:visible"
                    ).first
                    if visible_control.count() == 0:
                        visible_control = label
                    self._click_with_pacing(page, visible_control)
                    if checkbox.is_checked() != checked:
                        raise CutoverReportRpaError(
                            f"骨干线路确认项勾选未生效：{aliases[0]}"
                        )
                    return
            page.wait_for_timeout(200)
        raise CutoverReportRpaError(f"骨干线路表单未找到确认项：{aliases[0]}")

    def _upload_backbone_attachments(
        self,
        page: Page,
        attachment_paths: tuple[Path, ...],
    ) -> tuple[str, ...]:
        if not attachment_paths:
            return ()
        try:
            attachment_item = self._find_form_item(page, ("割接方案",))
            file_input = attachment_item.locator('input[type="file"]').first
            if file_input.count() == 0:
                raise CutoverReportRpaError("骨干线路表单未找到附件上传控件")
        except CutoverReportRpaError:
            file_input = self._find_attached(
                page,
                self._settings.report_backbone_attachment_selector,
            )
        file_input.set_input_files([str(path) for path in attachment_paths])
        self._wait_for_page_settled(page)
        return tuple(path.name for path in attachment_paths)

    def _submit_backbone_form(self, page: Page) -> str:
        self._pace_before_action(page)
        submit = self._find_visible(
            page,
            self._settings.report_backbone_submit_selector,
        )
        submit.click()
        deadline = monotonic() + self._settings.timeout_ms / 1000
        while monotonic() < deadline:
            if self._first_visible(page, (
                self._settings.username_selector,
                self._settings.mobile_phone_selector,
            )) is not None:
                raise PortalSessionError(
                    "RPA_SESSION_REQUIRED",
                    "综调会话已失效，请前往综调会话重新登录",
                )
            success = self._backbone_success_text(page)
            if success is not None:
                task_number = re.search(
                    r"(?:任务号|工单号)\s*[:：]\s*([A-Za-z0-9_-]+)",
                    success,
                )
                self._wait_for_page_settled(page)
                return task_number.group(1) if task_number else ""
            validation_error = self._first_visible(page, (
                ".el-form-item__error:visible",
                ".el-message--error:visible",
            ))
            if validation_error is not None:
                raise CutoverReportRpaError(
                    f"骨干线路表单校验未通过：{validation_error.inner_text().strip()}"
                )
            dialog = self._first_visible(page, (
                '.el-dialog:visible',
                '[role="dialog"]:visible',
            ))
            if dialog is not None:
                raise CutoverReportManualInterventionError(
                    "骨干线路提交后出现未识别弹窗，已停止自动上报，请转人工处理"
                )
            page.wait_for_timeout(200)
        raise CutoverReportRpaError("骨干线路提交后未检测到成功结果")

    def _backbone_success_text(self, page: Page) -> str | None:
        configured = self._settings.report_backbone_success_selector
        if configured:
            success = self._find_locator_once(
                page,
                configured,
                require_visible=True,
            )
            if success is not None:
                return success.inner_text()
        success_pattern = re.compile(r"(?:提交|创建|上报|操作)成功")
        for frame in page.frames:
            try:
                text = frame.locator("body").inner_text(timeout=500)
            except PlaywrightError:
                continue
            match = success_pattern.search(text)
            if match:
                return text
        return None

    def _wait_for_report_page(self, page: Page) -> Locator:
        deadline = monotonic() + self._settings.timeout_ms / 1000
        while monotonic() < deadline:
            for selector in (
                self._settings.username_selector,
                self._settings.mobile_phone_selector,
            ):
                if self._find_locator_once(
                    page,
                    selector,
                    require_visible=True,
                ) is not None:
                    raise PortalSessionError(
                        "RPA_SESSION_REQUIRED",
                        "综调会话已失效，请前往综调会话重新登录",
                    )
            report_entry = self._find_locator_once(
                page,
                self._settings.report_excel_import_selector,
                require_visible=True,
            )
            if report_entry is not None:
                return report_entry
            page.wait_for_timeout(200)
        raise CutoverReportRpaError("综调系统未加载割接影响填报页面")

    def _find_visible(self, page: Page, selector: str) -> Locator:
        return self._find_locator(page, selector, require_visible=True)

    def _find_attached(self, page: Page, selector: str) -> Locator:
        return self._find_locator(page, selector, require_visible=False)

    def _find_locator(
        self,
        page: Page,
        selector: str,
        *,
        require_visible: bool,
    ) -> Locator:
        deadline = monotonic() + self._settings.timeout_ms / 1000
        while monotonic() < deadline:
            for frame in page.frames:
                try:
                    locator = frame.locator(selector).first
                    if locator.count() == 0:
                        continue
                    if require_visible and not locator.is_visible():
                        continue
                    return locator
                except PlaywrightError:
                    continue
            page.wait_for_timeout(200)
        state = "可见" if require_visible else "已挂载"
        raise CutoverReportRpaError(
            f"综调系统页面未找到{state}控件：{selector}"
        )

    def _complete_import_dialogs(
        self,
        page: Page,
        upload_dialog: Locator,
        screenshot_path: Path,
        operation_log: list[CutoverReportOperationStep],
    ) -> str:
        deadline = monotonic() + self._settings.timeout_ms / 1000
        warning_count = 0
        existing_task_confirmed = False
        temporary_circuits_confirmed = False
        while monotonic() < deadline:
            login_field = self._first_visible(page, (
                self._settings.username_selector,
                self._settings.mobile_phone_selector,
            ))
            if login_field is not None:
                raise PortalSessionError(
                    "RPA_SESSION_REQUIRED",
                    "综调会话已失效，请前往综调会话重新登录",
                )

            task_number = self._find_successful_import_task_number(page)
            if task_number is not None:
                return task_number

            missing_circuit = self._visible_dialog_containing(
                page,
                "电路编号系统中不存在",
            )
            if missing_circuit is not None:
                step = self._capture_operation_step(
                    page,
                    screenshot_path,
                    operation_log,
                    "manual_intervention_required",
                    "电路编号不存在，等待人工处理",
                )
                raise CutoverReportManualInterventionError(
                    "综调系统提示电路编号不存在，已停止自动上报，请转人工处理",
                    screenshot_path=step.screenshot_path,
                    operation_log=tuple(operation_log),
                )

            existing_task = self._visible_dialog_containing(
                page,
                "发现任务在数据库中已存在",
            )
            if existing_task is not None:
                if existing_task_confirmed:
                    page.wait_for_timeout(200)
                    continue
                self._capture_operation_step(
                    page,
                    screenshot_path,
                    operation_log,
                    "existing_task_confirmation",
                    "任务已存在，继续追加影响电路",
                )
                self._click_with_pacing(
                    page,
                    existing_task.locator('button:has-text("继续"):visible').last,
                )
                existing_task_confirmed = True
                continue

            temporary = self._visible_dialog_containing(page, "临时电路确认")
            if temporary is not None:
                if temporary_circuits_confirmed:
                    page.wait_for_timeout(200)
                    continue
                self._capture_operation_step(
                    page,
                    screenshot_path,
                    operation_log,
                    "temporary_circuits_detected",
                    "检测到临时电路，准备全选",
                )
                select_all_control = temporary.locator(
                    '.el-table__header-wrapper:visible '
                    '.el-checkbox__input:visible, '
                    'thead:visible .el-checkbox__input:visible'
                ).first
                if select_all_control.count() > 0:
                    select_all_input = select_all_control.locator(
                        'input[type="checkbox"]'
                    ).first
                    self._click_with_pacing(page, select_all_control)
                else:
                    select_all_input = temporary.locator(
                        'input[type="checkbox"]'
                    ).first
                    if select_all_input.count() == 0:
                        raise CutoverReportRpaError(
                            "临时电路确认弹窗中未找到全选复选框",
                            operation_log=tuple(operation_log),
                        )
                    self._pace_before_action(page)
                    select_all_input.check(force=True)
                if select_all_input.count() == 0:
                    raise CutoverReportRpaError(
                        "临时电路全选控件缺少状态输入框",
                        operation_log=tuple(operation_log),
                    )
                if not select_all_input.is_checked():
                    raise CutoverReportRpaError(
                        "临时电路全选操作未生效",
                        operation_log=tuple(operation_log),
                    )
                self._capture_operation_step(
                    page,
                    screenshot_path,
                    operation_log,
                    "temporary_circuits_selected",
                    "临时电路已全选",
                )
                self._click_with_pacing(
                    page,
                    temporary.locator('button:has-text("继续"):visible').last,
                )
                temporary_circuits_confirmed = True
                continue

            warning = self._visible_dialog_containing(
                page,
                "发现有电路没有填写客户名称",
            )
            if warning is not None:
                warning_count += 1
                if warning_count > 20:
                    raise CutoverReportRpaError(
                        "客户名称确认弹窗重复次数异常，已停止自动上报",
                        operation_log=tuple(operation_log),
                    )
                self._capture_operation_step(
                    page,
                    screenshot_path,
                    operation_log,
                    f"customer_name_warning_{warning_count}",
                    f"第 {warning_count} 次客户名称确认",
                )
                self._click_with_pacing(
                    page,
                    warning.locator('button:has-text("继续"):visible').last,
                )
                continue

            unknown = self._first_unknown_dialog(page, upload_dialog)
            if unknown is not None:
                step = self._capture_operation_step(
                    page,
                    screenshot_path,
                    operation_log,
                    "manual_intervention_required",
                    "出现未识别弹窗，等待人工处理",
                )
                raise CutoverReportManualInterventionError(
                    "综调系统出现未识别弹窗，已停止自动上报，请转人工处理",
                    screenshot_path=step.screenshot_path,
                    operation_log=tuple(operation_log),
                )
            page.wait_for_timeout(200)
        raise CutoverReportRpaError(
            "提交后未检测到导入日志或已知确认弹窗",
            operation_log=tuple(operation_log),
        )

    def _click_with_pacing(self, page: Page, locator: Locator) -> None:
        self._pace_before_action(page)
        locator.click()
        delay_ms = self._settings.report_action_delay_ms
        if delay_ms > 0:
            page.wait_for_timeout(delay_ms)
        self._wait_for_page_settled(page)

    def _pace_before_action(self, page: Page) -> None:
        self._wait_for_page_settled(page)
        delay_ms = self._settings.report_action_delay_ms
        if delay_ms > 0:
            page.wait_for_timeout(delay_ms)

    def _wait_for_page_settled(self, page: Page) -> None:
        deadline = monotonic() + self._settings.timeout_ms / 1000
        stable_since: float | None = None
        loading_selectors = (
            '.el-loading-mask:visible',
            '.el-loading-spinner:visible',
            '.el-message:visible',
        )
        while monotonic() < deadline:
            if self._first_visible(page, loading_selectors) is None:
                now = monotonic()
                if stable_since is None:
                    stable_since = now
                elif now - stable_since >= 0.3:
                    return
            else:
                stable_since = None
            page.wait_for_timeout(100)
        raise CutoverReportRpaError("综调系统页面长时间处于加载状态")

    def _find_successful_import_task_number(self, page: Page) -> str | None:
        for frame in page.frames:
            try:
                body = frame.locator("body")
                if body.count() == 0:
                    continue
                task_number = self._extract_successful_portal_task_number(
                    body.inner_text(timeout=500)
                )
                if task_number is not None:
                    return task_number
            except PlaywrightError:
                continue
        return None

    @staticmethod
    def _extract_successful_portal_task_number(text: str) -> str | None:
        successful_tasks = re.search(r"导入成功的任务\s*(\d+)\s*条", text)
        successful_circuits = re.search(r"导入成功的电路\s*(\d+)\s*条", text)
        failed_tasks = re.search(r"导入失败的任务\s*(\d+)\s*条", text)
        failed_circuits = re.search(r"导入失败的电路\s*(\d+)\s*条", text)
        task_number = re.search(
            r"导入涉及的任务号\s*[:：]\s*([A-Za-z0-9_-]+)",
            text,
        )
        if (
            successful_tasks is None
            or successful_circuits is None
            or failed_tasks is None
            or failed_circuits is None
            or task_number is None
        ):
            return None
        if (
            (int(successful_tasks.group(1)) < 1 and int(successful_circuits.group(1)) < 1)
            or int(failed_tasks.group(1)) != 0
            or int(failed_circuits.group(1)) != 0
        ):
            return None
        return task_number.group(1)

    def _visible_dialog_containing(self, page: Page, text: str) -> Locator | None:
        matched_dialog: Locator | None = None
        matched_text_length: int | None = None
        for frame in page.frames:
            for selector in ('.el-dialog:visible', '[role="dialog"]:visible'):
                try:
                    dialogs = frame.locator(selector)
                    for index in range(dialogs.count()):
                        dialog = dialogs.nth(index)
                        dialog_text = dialog.inner_text()
                        if text not in dialog_text:
                            continue
                        text_length = len(dialog_text)
                        if (
                            matched_text_length is None
                            or text_length <= matched_text_length
                        ):
                            matched_dialog = dialog
                            matched_text_length = text_length
                except PlaywrightError:
                    continue
        return matched_dialog

    def _first_unknown_dialog(
        self,
        page: Page,
        upload_dialog: Locator,
    ) -> Locator | None:
        known_texts = (
            "传输任务及影响电路导入",
            "发现任务在数据库中已存在",
            "发现有电路没有填写客户名称",
            "临时电路确认",
            "导入日志",
        )
        for frame in page.frames:
            for selector in ('.el-dialog:visible', '[role="dialog"]:visible'):
                try:
                    dialogs = frame.locator(selector)
                    for index in range(dialogs.count()):
                        candidate = dialogs.nth(index)
                        if candidate == upload_dialog:
                            continue
                        text = candidate.inner_text()
                        if not any(known in text for known in known_texts):
                            return candidate
                except PlaywrightError:
                    continue
        return None

    def _first_visible(
        self,
        page: Page,
        selectors: tuple[str, ...],
    ) -> Locator | None:
        for selector in selectors:
            found = self._find_locator_once(page, selector, require_visible=True)
            if found is not None:
                return found
        return None

    def _capture_operation_step(
        self,
        page: Page,
        final_path: Path,
        operation_log: list[CutoverReportOperationStep],
        step: str,
        label: str,
    ) -> CutoverReportOperationStep:
        self._wait_for_page_settled(page)
        step_path = final_path.with_name(
            f"{final_path.stem}-{len(operation_log) + 1:02d}-{step}{final_path.suffix}"
        )
        self._capture_screenshot(page, step_path)
        entry = CutoverReportOperationStep(
            step=step,
            label=label,
            screenshot_path=step_path,
            captured_at=datetime.now(UTC).isoformat(),
        )
        operation_log.append(entry)
        if self._operation_step_callback is not None:
            self._operation_step_callback(entry)
        return entry

    @staticmethod
    def _find_locator_once(
        page: Page,
        selector: str,
        *,
        require_visible: bool,
    ) -> Locator | None:
        for frame in page.frames:
            try:
                locator = frame.locator(selector).first
                if locator.count() == 0:
                    continue
                if require_visible and not locator.is_visible():
                    continue
                return locator
            except PlaywrightError:
                continue
        return None

    @staticmethod
    def _capture_screenshot(page: Page, screenshot_path: Path) -> None:
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path.touch(mode=0o600, exist_ok=True)
        os.chmod(screenshot_path, 0o600)
        page.screenshot(
            path=str(screenshot_path),
            full_page=True,
        )
        os.chmod(screenshot_path, 0o600)

    def _capture_failure_screenshot(
        self,
        page: Page | None,
        artifact_dir: Path,
    ) -> Path | None:
        if page is None:
            return None
        try:
            timestamp = int(monotonic() * 1000)
            path = artifact_dir / f"report-failure-{timestamp}.png"
            self._capture_screenshot(page, path)
            return path
        except PlaywrightError:
            return None

    def _append_failure_step(
        self,
        operation_log: list[CutoverReportOperationStep],
        screenshot_path: Path | None,
        reason: str,
    ) -> None:
        if screenshot_path is None:
            return
        entry = CutoverReportOperationStep(
            step="operation_failed",
            label=reason,
            screenshot_path=screenshot_path,
            captured_at=datetime.now(UTC).isoformat(),
        )
        operation_log.append(entry)
        if self._operation_step_callback is not None:
            self._operation_step_callback(entry)
