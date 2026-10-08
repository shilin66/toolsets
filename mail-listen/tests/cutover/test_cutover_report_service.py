import importlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

cutover_report_service = importlib.import_module("cutover_report")
rpa_cutover_report_module = importlib.import_module("rpa.cutover_report")
session_models_module = importlib.import_module("rpa.session_models")
mail_artifacts_module = importlib.import_module("mail_artifacts")

CutoverReportOperationStep = rpa_cutover_report_module.CutoverReportOperationStep
CutoverReportResult = rpa_cutover_report_module.CutoverReportResult
BackboneReportResult = rpa_cutover_report_module.BackboneReportResult
PortalEnvironment = session_models_module.PortalEnvironment
customer_excel_path = mail_artifacts_module.customer_excel_path
email_attachment_directory = mail_artifacts_module.email_attachment_directory
report_artifact_directory = mail_artifacts_module.report_artifact_directory
save_source_email_archive = mail_artifacts_module.save_source_email_archive


class CutoverReportServiceTest(unittest.TestCase):
    def test_report_preparation_preserves_all_saved_backbone_values(self):
        form = {
            "基本信息": {
                "中断类型": "不中断", "中断原因": "人工保存的内容",
                "中断时间 (分钟)": None,
            },
            "割接对象": {"系统名称": [], "割接开始时间": "2026-10-10 01:00:00"},
            "人员信息": {"现场指挥人电话": "manual@example.com"},
        }
        forms = cutover_report_service._resolve_backbone_forms(
            {"fill_result": {"backbone_circuits": [form]}}
        )
        self.assertEqual(forms, [form])

    def test_customer_report_rejects_empty_saved_circuits_even_with_existing_excel(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "old.xlsx").write_bytes(b"old-workbook")
            task = {
                "customer_excel_filename": "old.xlsx",
                "fill_result": {"circuits": []},
                "source_mailbox_address": "noc@example.com", "source_email_uid": 2519,
            }
            with self.assertRaisesRegex(cutover_report_service.CutoverReportError, "至少保留一条电路"):
                cutover_report_service._resolve_customer_excel(task, data_dir=root)

    def test_preserves_saved_overseas_cutover_choice_for_rpa(self):
        field = "是否为境外运营商割接或联通割接(跳过变更操作方案校验)"
        for value in ("是", "否"):
            with self.subTest(value=value):
                form = {"其他": {field: value, "割接原因": "人工核对后的原因"}}
                task = {"fill_result": {"backbone_circuits": [form]}}

                forms = cutover_report_service._resolve_backbone_forms(task)

                self.assertEqual(forms[0]["其他"], form["其他"])
                self.assertEqual(form["其他"][field], value)

    def test_does_not_add_overseas_cutover_default_during_report(self):
        form = {"其他": {"割接原因": "历史任务数据"}}
        task = {"fill_result": {"backbone_circuits": [form]}}

        forms = cutover_report_service._resolve_backbone_forms(task)

        self.assertEqual(forms[0], form)

    def test_emits_each_captured_step_as_serialized_progress(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            excel_path = customer_excel_path(
                root,
                mailbox_address="noc@example.com",
                email_uid=2519,
                filename="RT00_26012495.xlsx",
            )
            excel_path.parent.mkdir(parents=True)
            excel_path.write_bytes(b"fake-xlsx")
            progress_updates = []

            def build_rpa(settings, *, operation_step_callback=None):
                rpa = Mock()

                def upload_customer_excel(
                    selected_excel_path,
                    *,
                    environment,
                    screenshot_path,
                ):
                    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                    screenshot_path.write_bytes(b"png")
                    step_path = screenshot_path.with_name(
                        "report-success-01-excel_selected.png"
                    )
                    step_path.write_bytes(b"png")
                    step = CutoverReportOperationStep(
                        step="excel_selected",
                        label="已选择上报 Excel",
                        screenshot_path=step_path,
                        captured_at="2026-09-07T08:00:00+00:00",
                    )
                    assert operation_step_callback is not None
                    operation_step_callback(step)
                    return CutoverReportResult(
                        final_url="https://portal.example/report",
                        uploaded_filename=selected_excel_path.name,
                        success_screenshot_path=screenshot_path,
                        portal_task_number="QT2026GJJJ000311",
                        operation_log=(step,),
                    )

                rpa.upload_customer_excel.side_effect = upload_customer_excel
                return rpa

            task = {
                "id": 10,
                "email_records_id": 135,
                "line_type": "customer",
                "fill_result": {"circuits": [{"电路代号": "manual-circuit"}]},
                "customer_excel_filename": excel_path.name,
                "source_mailbox_address": "noc@example.com",
                "source_email_uid": 2519,
            }

            with patch.object(
                cutover_report_service,
                "PortalSessionSettings",
                return_value=SimpleNamespace(artifact_dir=root / "artifacts"),
            ), patch.object(
                cutover_report_service,
                "PortalCutoverReportRpa",
                side_effect=build_rpa,
            ), patch.object(
                cutover_report_service,
                "_current_report_date",
                return_value="2026-09-07",
            ):
                cutover_report_service.report_cutover_task(
                    task,
                    environment=PortalEnvironment.TEST,
                    data_dir=root,
                    report_id=19,
                    progress_callback=progress_updates.append,
                )

            self.assertEqual(len(progress_updates), 1)
            self.assertEqual(progress_updates[0]["phase"], "running")
            self.assertEqual(
                progress_updates[0]["current_step_label"],
                "已选择上报 Excel",
            )
            self.assertEqual(
                progress_updates[0]["operation_log"][0]["step"],
                "excel_selected",
            )

    def test_saves_report_screenshots_under_business_identifiers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact_root = root / "artifacts"
            excel_path = customer_excel_path(
                root,
                mailbox_address="noc@example.com",
                email_uid=2519,
                filename="RT00_26012495.xlsx",
            )
            excel_path.parent.mkdir(parents=True)
            excel_path.write_bytes(b"fake-xlsx")
            rpa = Mock()

            def upload_customer_excel(
                selected_excel_path,
                *,
                environment,
                screenshot_path,
            ):
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                screenshot_path.write_bytes(b"png")
                step_path = screenshot_path.with_name(
                    "report-success-01-excel_selected.png"
                )
                step_path.write_bytes(b"png")
                return CutoverReportResult(
                    final_url="https://portal.example/report",
                    uploaded_filename=selected_excel_path.name,
                    success_screenshot_path=screenshot_path,
                    portal_task_number="QT2026GJJJ000311",
                    operation_log=(CutoverReportOperationStep(
                        step="excel_selected",
                        label="已选择上报 Excel",
                        screenshot_path=step_path,
                        captured_at="2026-09-04T08:00:00+00:00",
                    ),),
                )

            rpa.upload_customer_excel.side_effect = upload_customer_excel
            task = {
                "id": 10,
                "email_records_id": 135,
                "line_type": "customer",
                "fill_result": {"circuits": [{"电路代号": "manual-circuit"}]},
                "customer_excel_filename": excel_path.name,
                "source_mailbox_address": "noc@example.com",
                "source_email_uid": 2519,
            }

            with patch.object(
                cutover_report_service,
                "PortalSessionSettings",
                return_value=SimpleNamespace(artifact_dir=artifact_root),
            ), patch.object(
                cutover_report_service,
                "PortalCutoverReportRpa",
                return_value=rpa,
            ), patch.object(
                cutover_report_service,
                "_current_report_date",
                return_value="2026-09-04",
                create=True,
            ):
                result = cutover_report_service.report_cutover_task(
                    task,
                    environment=PortalEnvironment.TEST,
                    data_dir=root,
                    report_id=19,
                )

            expected_dir = report_artifact_directory(
                root,
                mailbox_address="noc@example.com",
                email_uid=2519,
                report_date="2026-09-04",
                email_record_id=135,
                task_id=10,
                report_id=19,
            )
            self.assertEqual(
                Path(result["screenshot_path"]),
                expected_dir / "report-success.png",
            )
            self.assertEqual(
                result["operation_log"][0]["screenshot_filename"],
                expected_dir.relative_to(root).as_posix()
                + "/report-success-01-excel_selected.png",
            )

    def test_reports_backbone_form_with_email_attachments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact_root = root / "artifacts"
            attachment_path = email_attachment_directory(
                root,
                mailbox_address="noc@example.com",
                email_uid=2519,
            ) / "方案.pdf"
            attachment_path.parent.mkdir(parents=True)
            attachment_path.write_bytes(b"fake-pdf")
            source_email_path = save_source_email_archive(
                root,
                mailbox_address="noc@example.com",
                email_uid=2519,
                raw_message=b"From: noc@example.com\r\n\r\nsource",
            )
            rpa = Mock()
            form_data = {
                "基本信息": {
                    "标题": "骨干割接测试",
                    "中断类型": "中断",
                    "中断原因": "Location: Romania Reason: measurement",
                },
                "其他": {
                    "割接原因": "历史任务数据",
                    "是否为境外运营商割接或联通割接(跳过变更操作方案校验)": "是",
                },
            }
            expected_form_data = {
                "基本信息": {
                    "标题": "骨干割接测试",
                    "中断类型": "中断",
                    "中断原因": "Location: Romania Reason: measurement",
                },
                "其他": {
                    "割接原因": "历史任务数据",
                    "是否为境外运营商割接或联通割接(跳过变更操作方案校验)": "是",
                },
            }

            def fill_backbone_form(
                selected_form_data,
                *,
                attachment_paths,
                environment,
                screenshot_path,
            ):
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                screenshot_path.write_bytes(b"png")
                return BackboneReportResult(
                    final_url="https://portal.example/backbone",
                    uploaded_filenames=tuple(path.name for path in attachment_paths),
                    success_screenshot_path=screenshot_path,
                    portal_task_number="QT2026GJJJ009999",
                    submitted=True,
                    operation_log=(),
                )

            rpa.fill_backbone_form.side_effect = fill_backbone_form
            task = {
                "id": 10,
                "email_records_id": 135,
                "line_type": "backbone",
                "fill_result": {"backbone_circuits": [form_data]},
                "email_attachments": [
                    attachment_path.relative_to(root).as_posix()
                ],
                "source_mailbox_address": "noc@example.com",
                "source_email_uid": 2519,
            }

            with patch.object(
                cutover_report_service,
                "PortalSessionSettings",
                return_value=SimpleNamespace(artifact_dir=artifact_root),
            ), patch.object(
                cutover_report_service,
                "PortalCutoverReportRpa",
                return_value=rpa,
            ), patch.object(
                cutover_report_service,
                "_current_report_date",
                return_value="2026-09-06",
                create=True,
            ):
                result = cutover_report_service.report_cutover_task(
                    task,
                    environment=PortalEnvironment.TEST,
                    data_dir=root,
                    report_id=21,
                )

            self.assertEqual(result["status"], "success")
            self.assertEqual(
                result["uploaded_filenames"],
                ["方案.pdf", "source-email-2519.eml"],
            )
            rpa.fill_backbone_form.assert_called_once()
            call = rpa.fill_backbone_form.call_args
            self.assertEqual(call.args[0], expected_form_data)
            self.assertEqual(
                call.kwargs["attachment_paths"],
                (
                    attachment_path.resolve(),
                    source_email_path.resolve(),
                ),
            )
            self.assertEqual(
                call.kwargs["attachment_paths"][1].read_bytes(),
                b"From: noc@example.com\r\n\r\nsource",
            )


if __name__ == "__main__":
    unittest.main()
