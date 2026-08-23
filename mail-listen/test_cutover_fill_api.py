import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault('IMAP_SERVER', 'imap.example.com')
os.environ.setdefault('EMAIL_ADDRESS', 'test@example.com')
os.environ.setdefault('EMAIL_PASSWORD', 'password')
os.environ.setdefault('API_URL', 'https://api.example.com')
os.environ.setdefault('API_TOKEN', 'token')
os.environ.setdefault('API_KEY', 'test-key')

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_server
import cutover_task
from database import EmailDatabase


class CutoverFillPayloadTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = EmailDatabase(os.path.join(self.tmpdir.name, "mail_listener.db"))
        self.db_patch = patch.object(api_server, "email_db", self.db)
        self.db_patch.start()
        self.task_db_patch = patch.object(cutover_task, "email_db", self.db)
        self.task_db_patch.start()
        self.source_email_patch = patch.object(
            api_server,
            "ensure_source_email_archived",
        )
        self.source_email_patch.start()
        self.client = api_server.app.test_client()
        self.headers = {"Authorization": "Bearer test-key"}
        self.email_records_id = self.insert_email_record()

    def tearDown(self):
        self.source_email_patch.stop()
        self.task_db_patch.stop()
        self.db_patch.stop()
        self.tmpdir.cleanup()

    def insert_email_record(self, email_id=None):
        if email_id is None:
            email_id = 1000 + (self.db.get_statistics().get('email_records', {}).get('total', 0))
        self.db.add_email_record(
            email_id=email_id,
            sender="noc@supplier.example.com",
            receiver="noc@example.com",
            subject="割接通知",
            content="割接邮件正文",
        )
        record = self.db.get_email_record(email_id)
        return record["id"]

    def test_cutover_fill_api_accepts_line_array_and_configured_query_keywords(self):
        payload = {
            "email_records_id": self.email_records_id,
            "carrier_ticket_no": "CR202606060001",
            "cutover_time": "2026-06-06 16:00:00/2026-06-06 22:00:00",
            "cutover_timezone": "UTC",
            "cutover_reason": "设备版本升级维护",
            "location": "Singapore POP ",
            "line_query_keywords": ["OrderNumber"],
            "line_array": [
                {
                    "CircuitID": "CID-001",
                    "OrderNumber": "SO-123456",
                    "InternationalId": "INTL-8899",
                    "CircuitIDRT": "RT-7788",
                    "ImpactType": "Service interruption",
                    "ImpactDateTime": "2026-06-07 00:00:00/2026-06-07 06:00:00",
                    "ImpactDuration": "6 hours",
                    "InteruptionsCounts": "1",
                }
            ],
        }
        captured_queries = []

        def fake_query(supplier, keywords):
            captured_queries.append((supplier, keywords))
            if keywords == ["SO-123456"]:
                return [{
                    "supplier": "RT",
                    "supplier_circuit_id": "SO-123456",
                    "circuit_id": "EU202606000001",
                    "line_type": "客户",
                    "line_status": "正常",
                    "remark": "",
                }]
            return []

        with patch.object(api_server, "query_supplier_circuits", side_effect=fake_query), patch.object(
            api_server,
            "build_template_workbook",
            return_value=object(),
        ), patch.object(
            api_server,
            "save_workbook_output",
            return_value=Path("/tmp/cutoverCR202606060001.xlsx"),
        ):
            response = self.client.post(
                "/api/cutover/tasks/generate",
                headers=self.headers,
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(captured_queries, [(None, ["SO-123456"])])
        self.assertEqual(data["customer_excel"]["filename"], "cutoverCR202606060001.xlsx")
        self.assertEqual(data["backbone_circuits"], [])
        self.assertEqual(data["validation_messages"], [])

    def test_legacy_fill_path_still_works(self):
        """旧路径 /api/cutover/fill 作为兼容别名仍可用（与新路径同一处理逻辑）。"""
        missing = self.client.post("/api/cutover/fill", headers=self.headers, json={})
        self.assertEqual(missing.status_code, 200)
        self.assertIn("email_records_id", missing.get_json()["data"]["msg"])
        self.assertFalse(missing.get_json()["success"])

        not_found = self.client.post(
            "/api/cutover/fill", headers=self.headers, json={"email_records_id": 999999}
        )
        self.assertEqual(not_found.status_code, 200)

    def test_builds_customer_workbook_payload_and_backbone_fields(self):
        payload = {
            "supplier": "RT",
            "carrier_ticket_no": "00/26012495",
            "cutover_time": "2026-06-12 14:00:00/2026-06-12 20:00:00",
            "cutover_timezone": "UTC",
            "cutover_reason": "Scheduled maintenance.",
            "location": "Odense - Aabenraa (Denmark)",
            "line_array_info": {
                "data": [
                    {
                        "CircuitID": "Customer circuit",
                        "OrderNumber": "24-162081",
                        "InternationalId": "International customer",
                        "CircuitIDRT": "1940952",
                        "ImpactType": "Outage",
                        "ImpactDateTime": "2026-06-12 14:00:00/2026-06-12 20:00:00",
                        "ImpactDuration": "4h",
                        "InteruptionsCounts": "1",
                    },
                    {
                        "CircuitID": "Backbone circuit",
                        "OrderNumber": "24-162082",
                        "InternationalId": "International backbone",
                        "CircuitIDRT": "1940953",
                        "ImpactType": "Outage",
                        "ImpactDateTime": "2026-06-12 15:00:00/2026-06-12 16:30:00",
                        "ImpactDuration": "20m",
                        "InteruptionsCounts": "2",
                    },
                ]
            },
        }

        def fake_query(supplier, keywords):
            if "1940952" in keywords:
                return [{
                    "supplier": supplier,
                    "supplier_circuit_id": "1940952",
                    "circuit_id": "EU202510000941",
                    "line_type": "客户",
                    "line_status": "正常",
                    "remark": "",
                }]
            return [{
                "supplier": supplier,
                "supplier_circuit_id": "1940953",
                "circuit_id": "Backbone-System-001",
                "line_type": "骨干",
                "line_status": "正常",
                "remark": "",
            }]

        with patch.object(api_server, "query_supplier_circuits", side_effect=fake_query):
            result = api_server.build_cutover_fill_response(
                payload,
                sender_email="noc@supplier.example.com",
            )

        self.assertNotIn("body", result)
        self.assertNotIn("unmatched_lines", result)
        self.assertNotIn("unsupported_lines", result)
        self.assertEqual(result["filename"], "RT00_26012495.xlsx")
        self.assertEqual(result["cutStartTime"], "2026-06-12 22:00:00")
        self.assertEqual(result["cutEndTime"], "2026-06-13 04:00:00")
        self.assertEqual(len(result["circuits"]), 1)
        self.assertEqual(result["circuits"][0]["电路代号"], "EU202510000941")
        self.assertEqual(result["circuits"][0]["客户电路在割接段是否有保护"], "无保护")
        self.assertEqual(result["circuits"][0]["预计影响客户业务时长"], "中断:240分钟")
        self.assertEqual(len(result["reasons"]), 1)
        self.assertEqual(len(result["backbone_circuits"]), 1)
        self.assertEqual(result["backbone_interruption_minutes"], [40])
        self.assertEqual(
            result["backbone_circuits"][0]["割接对象"]["系统名称"],
            ["Backbone-System-001"],
        )
        self.assertEqual(
            result["backbone_circuits"][0]["割接对象"]["割接开始时间"],
            "2026-06-12 23:00:00",
        )
        self.assertEqual(
            result["backbone_circuits"][0]["基本信息"]["中断类型"],
            "中断",
        )
        self.assertEqual(
            result["backbone_circuits"][0]["基本信息"]["中断时间 (分钟)"],
            40,
        )
        self.assertEqual(
            result["backbone_circuits"][0]["基本信息"]["变更操作等级"],
            "四级",
        )
        self.assertNotIn(
            "割接名称",
            result["backbone_circuits"][0]["割接对象"],
        )

        backbone = result["backbone_circuits"][0]
        self.assertEqual(backbone["基本信息"]["涉及系统（网络）"], "涉及系统（网络）")
        self.assertEqual(backbone["基本信息"]["操作厂家"], "无")
        self.assertEqual(backbone["基本信息"]["设备名称"], "无")
        self.assertEqual(backbone["基本信息"]["调度方式"], "不调度")
        self.assertEqual(backbone["基本信息"]["需要配合的省"], "")
        self.assertEqual(
            backbone["基本信息"]["中断原因"],
            "Location: Odense - Aabenraa (Denmark) Reason: Scheduled maintenance.",
        )
        self.assertEqual(
            backbone["基本信息"]["是否涉及集团维护设备或业务影响超出本省范围"],
            "是",
        )
        self.assertEqual(backbone["基本信息"]["割接地点"], "")
        self.assertEqual(
            backbone["其他"]["风险操作影响范围"],
            "割接影响传输通道及其承载的客户电路，IP中继等",
        )
        self.assertEqual(
            backbone["其他"][
                "是否为境外运营商割接或联通割接(跳过变更操作方案校验)"
            ],
            "否",
        )
        self.assertEqual(
            backbone["人员信息"],
            {
                "现场指挥人员名称": "RT",
                "现场指挥人电话": "noc@supplier.example.com",
                "现场指挥人单位": "国际公司",
                "支撑人员": "NOC",
                "支撑人电话": "+85231000000",
                "支撑人单位": "国际公司",
                "省公司审核人姓名": "Andrew",
                "省公司审核人电话": "+85291089855",
                "省公司审核人单位": "国际公司",
                "业务测试人员": "NOC",
                "业务测试人员电话": "+85231000000",
                "业务测试人单位": "国际公司",
                "操作审核人姓名": "RT NOC",
                "操作审核人电话": "noc@supplier.example.com",
                "操作审核人单位": "国际公司",
                "业务复核人姓名": "NOC",
                "业务复核人电话": "+85231000000",
                "业务复核人单位": "国际公司",
            },
        )
        self.assertTrue(all(backbone["确认项"].values()))

    def test_backbone_personnel_uses_configured_values(self):
        self.db.set_system_setting('backbone_noc_phone', '+85232223333')
        self.db.set_system_setting('backbone_province_reviewer_name', 'Chris')
        self.db.set_system_setting(
            'backbone_province_reviewer_phone',
            '+85294445555',
        )
        payload = {
            "supplier": "TTK",
            "carrier_ticket_no": "00/26012495",
            "cutover_time": "2026-06-12 14:00:00/2026-06-12 20:00:00",
            "cutover_timezone": "UTC",
            "cutover_reason": "Scheduled maintenance.",
            "location": "Romania",
            "line_array": [{
                "CircuitIDRT": "1940953",
                "ImpactType": "protected",
                "ImpactDateTime": "2026-06-12 15:00:00/2026-06-12 16:30:00",
            }],
        }

        with patch.object(
            api_server,
            "query_supplier_circuits",
            return_value=[{
                "supplier": "TTK",
                "supplier_circuit_id": "1940953",
                "circuit_id": "Backbone-System-001",
                "line_type": "骨干",
                "line_status": "正常",
                "remark": "",
            }],
        ):
            result = api_server.build_cutover_fill_response(
                payload,
                sender_email="cutover@ttk.example.com",
            )

        personnel = result['backbone_circuits'][0]['人员信息']
        self.assertEqual(personnel['现场指挥人员名称'], 'TTK')
        self.assertEqual(personnel['支撑人员'], 'NOC')
        self.assertEqual(personnel['支撑人电话'], '+85232223333')
        self.assertEqual(personnel['省公司审核人姓名'], 'Chris')
        self.assertEqual(personnel['省公司审核人电话'], '+85294445555')
        self.assertEqual(personnel['业务测试人员'], 'NOC')
        self.assertEqual(personnel['业务测试人员电话'], '+85232223333')
        self.assertEqual(personnel['操作审核人姓名'], 'TTK NOC')
        self.assertEqual(personnel['现场指挥人电话'], 'cutover@ttk.example.com')
        self.assertEqual(personnel['操作审核人电话'], 'cutover@ttk.example.com')
        self.assertEqual(personnel['业务复核人姓名'], 'NOC')
        self.assertEqual(personnel['业务复核人电话'], '+85232223333')

    def test_backbone_interruption_is_protected_when_impact_type_is_protected(self):
        # Given: 邮件线路明确标记为 protected，即使时长很长也不中断
        line = {
            "ImpactType": "protected",
            "ImpactDateTime": "2026-06-12 15:00:00/2026-06-12 16:30:00",
            "ImpactDuration": "247m",
            "InteruptionsCounts": "1",
        }

        # When: 生成骨干线路预填卡片
        backbone = api_server.build_backbone_circuit(
            line,
            {"circuit_id": "Backbone-System-001"},
            "测试割接",
            "UTC",
            "measurement",
            "Romania",
            "RT",
            api_server.get_backbone_personnel_settings(),
        )

        # Then: 中断类型为不中断，且不生成中断时间字段
        self.assertEqual(backbone["基本信息"]["中断类型"], "不中断")
        self.assertNotIn("中断时间 (分钟)", backbone["基本信息"])
        self.assertNotIn("中断原因", backbone["基本信息"])

    def test_backbone_interruption_is_instant_when_duration_is_three_minutes(self):
        # Given: 非 protected 线路的总中断时长恰好为 3 分钟
        line = {
            "ImpactType": "Outage",
            "ImpactDateTime": "2026-06-12 15:00:00/2026-06-12 16:30:00",
            "ImpactDuration": "3m",
            "InteruptionsCounts": "1",
        }

        # When: 生成骨干线路预填卡片
        backbone = api_server.build_backbone_circuit(
            line,
            {"circuit_id": "Backbone-System-001"},
            "测试割接",
            "UTC",
            "measurement",
            "Romania",
            "RT",
            api_server.get_backbone_personnel_settings(),
        )

        # Then: 三分钟边界归类为瞬断，且无需填写中断时间
        self.assertEqual(backbone["基本信息"]["中断类型"], "瞬断")
        self.assertNotIn("中断时间 (分钟)", backbone["基本信息"])

    def test_backbone_four_minute_interruption_is_instant(self):
        # Given
        line = {
            "ImpactType": "momentary_interrupted",
            "ImpactDateTime": "2026-06-12 15:00:00/2026-06-12 15:04:00",
            "ImpactDuration": "4m",
            "InteruptionsCounts": "1",
        }

        # When
        backbone = api_server.build_backbone_circuit(
            line,
            {"circuit_id": "Backbone-System-004"},
            "测试割接",
            "UTC",
            "measurement",
            "Romania",
            "RT",
            api_server.get_backbone_personnel_settings(),
        )

        # Then
        self.assertEqual(backbone["基本信息"]["中断类型"], "瞬断")
        self.assertNotIn("中断时间 (分钟)", backbone["基本信息"])
        self.assertNotIn("中断原因", backbone["基本信息"])

    def test_customer_interruption_uses_protection_and_total_minutes(self):
        # Given: 一条有保护线路和一条非保护线路，非保护线路需按时长乘次数
        protected_line = {
            "ImpactType": "protected",
            "ImpactDuration": "20m",
            "InteruptionsCounts": "2",
        }
        interrupted_line = {
            "ImpactType": "Outage",
            "ImpactDuration": "4m",
            "InteruptionsCounts": "2",
        }

        # When: 生成客户线路预填行
        protected = api_server.build_customer_circuit(
            protected_line, {"circuit_id": "C-1"}, "线路一", "2026-01-01", "UTC"
        )
        interrupted = api_server.build_customer_circuit(
            interrupted_line, {"circuit_id": "C-2"}, "线路二", "2026-01-01", "UTC"
        )

        # Then: 有保护线路不中断，非保护线路显示计算后的分钟数
        self.assertEqual(protected["客户电路在割接段是否有保护"], "有保护")
        self.assertEqual(protected["预计影响客户业务时长"], "不中断")
        self.assertEqual(interrupted["客户电路在割接段是否有保护"], "无保护")
        self.assertEqual(interrupted["预计影响客户业务时长"], "中断:8分钟")

    def test_customer_three_minute_boundary_is_instant(self):
        # Given: 非保护线路的总影响时长恰好为三分钟
        line = {
            "ImpactType": "Outage",
            "ImpactDuration": "1m",
            "InteruptionsCounts": "3",
        }

        # When: 生成客户线路预填行
        customer = api_server.build_customer_circuit(
            line, {"circuit_id": "C-3"}, "线路三", "2026-01-01", "UTC"
        )

        # Then: 三分钟边界归类为瞬断
        self.assertEqual(customer["客户电路在割接段是否有保护"], "无保护")
        self.assertEqual(customer["预计影响客户业务时长"], "瞬断")

    def test_customer_four_minute_interruption_is_instant(self):
        # Given
        line = {
            "ImpactType": "momentary_interrupted",
            "ImpactDuration": "4m",
            "InteruptionsCounts": "1",
        }

        # When
        customer = api_server.build_customer_circuit(
            line, {"circuit_id": "C-4"}, "线路四", "2026-01-01", "UTC"
        )

        # Then
        self.assertEqual(customer["预计影响客户业务时长"], "瞬断")

    def test_customer_five_minute_interruption_is_interrupted(self):
        # Given
        line = {
            "ImpactType": "interrupted",
            "ImpactDuration": "5m",
            "InteruptionsCounts": "1",
        }

        # When
        customer = api_server.build_customer_circuit(
            line, {"circuit_id": "C-5"}, "线路五", "2026-01-01", "UTC"
        )

        # Then
        self.assertEqual(customer["预计影响客户业务时长"], "中断:5分钟")

    def test_merges_backbone_systems_with_the_same_cutover_window(self):
        # Given: 两条骨干线路的割接起止时间完全相同
        payload = {
            "supplier": "RT",
            "carrier_ticket_no": "wt 271326133720",
            "cutover_time": "2026-11-10 21:00:00/2026-12-10 04:00:00",
            "cutover_timezone": "UTC",
            "cutover_reason": "measurement",
            "location": "Romania",
            "line_array_info": {
                "data": [
                    {
                        "CircuitIDRT": "1940953",
                        "ImpactDateTime": "2026-11-10 21:00:00/2026-12-10 04:00:00",
                        "ImpactDuration": "20m",
                        "InteruptionsCounts": "1",
                    },
                    {
                        "CircuitIDRT": "1940954",
                        "ImpactDateTime": "2026-11-10 21:00:00/2026-12-10 04:00:00",
                        "ImpactDuration": "20m",
                        "InteruptionsCounts": "1",
                    },
                ]
            },
        }

        def fake_query(supplier, keywords):
            circuit_suffix = "A" if "1940953" in keywords else "B"
            return [{
                "supplier": supplier,
                "supplier_circuit_id": keywords[-1],
                "circuit_id": f"Backbone-System-{circuit_suffix}",
                "line_type": "骨干",
                "line_status": "正常",
                "remark": "",
            }]

        # When: 生成工作台骨干线路预填数据
        with patch.object(api_server, "query_supplier_circuits", side_effect=fake_query):
            result = api_server.build_cutover_fill_response(payload)

        # Then: 同一时间窗口只生成一张卡片，并保留两个系统名称
        self.assertEqual(len(result["backbone_circuits"]), 1)
        self.assertEqual(
            result["backbone_circuits"][0]["割接对象"]["系统名称"],
            ["Backbone-System-A", "Backbone-System-B"],
        )

    def test_cutover_fill_api_generates_customer_excel_metadata(self):
        payload = {
            "email_records_id": self.email_records_id,
            "supplier": "RT",
            "carrier_ticket_no": "00/26012495",
            "cutover_time": "2026-06-12 14:00:00/2026-06-12 20:00:00",
            "cutover_timezone": "UTC",
            "cutover_reason": "Scheduled maintenance.",
            "location": "Odense - Aabenraa (Denmark)",
            "line_array_info": {
                "data": [{
                    "CircuitID": "Customer circuit",
                    "OrderNumber": "24-162081",
                    "InternationalId": "International customer",
                    "CircuitIDRT": "1940952",
                    "ImpactDateTime": "2026-06-12 14:00:00/2026-06-12 20:00:00",
                    "ImpactDuration": "4h",
                    "InteruptionsCounts": "1",
                }]
            },
        }

        with patch.object(api_server, "query_supplier_circuits", return_value=[{
            "supplier": "RT",
            "supplier_circuit_id": "1940952",
            "circuit_id": "EU202510000941",
            "line_type": "客户",
            "line_status": "正常",
            "remark": "",
        }]), patch.object(api_server, "build_template_workbook", return_value=object()) as build_workbook, patch.object(
            api_server,
            "save_workbook_output",
            return_value=Path("/tmp/RT00_26012495.xlsx"),
        ) as save_workbook:
            response = self.client.post(
                "/api/cutover/tasks/generate",
                headers=self.headers,
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertNotIn("body", data)
        self.assertNotIn("unmatched_lines", data)
        self.assertNotIn("unsupported_lines", data)
        self.assertNotIn("filename", data)
        self.assertNotIn("circuits", data)
        self.assertNotIn("reasons", data)
        build_workbook.assert_called_once()
        save_workbook.assert_called_once()
        self.assertEqual(set(data["customer_excel"].keys()), {"filename", "download_url"})
        self.assertEqual(data["customer_excel"]["filename"], "RT00_26012495.xlsx")
        self.assertEqual(data["backbone_circuits"], [])

    def test_reports_multiple_lookup_results_without_generating_fields(self):
        payload = {
            "supplier": "RT",
            "carrier_ticket_no": "00/26012495",
            "cutover_time": "2026-06-12 14:00:00/2026-06-12 20:00:00",
            "cutover_timezone": "UTC",
            "cutover_reason": "Scheduled maintenance.",
            "location": "Odense - Aabenraa (Denmark)",
            "line_array_info": {"data": [{
                "CircuitID": "Customer circuit",
                "OrderNumber": "24-162081",
                "InternationalId": "International customer",
                "CircuitIDRT": "1940952",
                "ImpactDateTime": "2026-06-12 14:00:00/2026-06-12 20:00:00",
                "ImpactDuration": "4h",
                "InteruptionsCounts": "1",
            }]},
        }

        with patch.object(api_server, "query_supplier_circuits", return_value=[
            {
                "supplier": "RT",
                "supplier_circuit_id": "1940952",
                "circuit_id": "EU202510000941",
                "line_type": "客户",
                "line_status": "正常",
                "remark": "",
            },
            {
                "supplier": "RT",
                "supplier_circuit_id": "24-162081",
                "circuit_id": "EU202510000942",
                "line_type": "客户",
                "line_status": "正常",
                "remark": "",
            },
        ]):
            result = api_server.build_cutover_fill_response(payload)

        self.assertNotIn("body", result)
        self.assertNotIn("unmatched_lines", result)
        self.assertNotIn("unsupported_lines", result)
        self.assertEqual(result["circuits"], [])
        self.assertEqual(result["backbone_circuits"], [])
        self.assertEqual(len(result["validation_messages"]), 1)
        self.assertEqual(result["validation_messages"][0]["type"], "multiple_matches")
        self.assertIn("查询到多条线路", result["validation_messages"][0]["message"])

    def test_cutover_fill_api_hides_customer_payload_fields_without_excel(self):
        payload = {
            "email_records_id": self.email_records_id,
            "supplier": "RT",
            "carrier_ticket_no": "00/26012495",
            "cutover_time": "2026-06-12 14:00:00/2026-06-12 20:00:00",
            "cutover_timezone": "UTC",
            "cutover_reason": "Scheduled maintenance.",
            "location": "Odense - Aabenraa (Denmark)",
            "line_array_info": {"data": [{
                "CircuitID": "Backbone circuit",
                "OrderNumber": "24-162082",
                "InternationalId": "International backbone",
                "CircuitIDRT": "1940953",
                "ImpactDateTime": "2026-06-12 15:00:00/2026-06-12 16:30:00",
                "ImpactDuration": "20m",
                "InteruptionsCounts": "2",
            }]},
        }

        with patch.object(api_server, "query_supplier_circuits", return_value=[{
            "supplier": "RT",
            "supplier_circuit_id": "1940953",
            "circuit_id": "Backbone-System-001",
            "line_type": "骨干",
            "line_status": "正常",
            "remark": "",
        }]):
            response = self.client.post(
                "/api/cutover/tasks/generate",
                headers=self.headers,
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertNotIn("filename", data)
        self.assertNotIn("circuits", data)
        self.assertNotIn("reasons", data)
        self.assertIsNone(data["customer_excel"])
        self.assertEqual(len(data["backbone_circuits"]), 1)
        personnel = data["backbone_circuits"][0]["人员信息"]
        self.assertEqual(
            personnel["现场指挥人电话"],
            "noc@supplier.example.com",
        )
        self.assertEqual(
            personnel["操作审核人电话"],
            "noc@supplier.example.com",
        )
        self.assertEqual(
            data["backbone_circuits"][0]["其他"][
                "是否为境外运营商割接或联通割接(跳过变更操作方案校验)"
            ],
            "否",
        )
        # msg 只含摘要与任务详情链接，不展示具体填报字段
        self.assertIn("割接填报摘要", data["msg"])
        self.assertIn(f"任务 #{data['tasks'][0]['id']}", data["msg"])
        self.assertIn(f"/admin/cutover-emails/{self.email_records_id}?taskId={data['tasks'][0]['id']}", data["msg"])
        self.assertNotIn("Backbone-System-001", data["msg"])

    def test_cutover_fill_api_returns_readable_msg_for_excel_backbone_and_validation(self):
        payload = {
            "email_records_id": self.email_records_id,
            "supplier": "RT",
            "carrier_ticket_no": "00/26012495",
            "cutover_time": "2026-06-12 14:00:00/2026-06-12 20:00:00",
            "cutover_timezone": "UTC",
            "cutover_reason": "Scheduled maintenance.",
            "location": "Odense - Aabenraa (Denmark)",
            "line_array_info": {"data": [
                {
                    "CircuitID": "Customer circuit",
                    "OrderNumber": "24-162081",
                    "InternationalId": "International customer",
                    "CircuitIDRT": "1940952",
                    "ImpactDateTime": "2026-06-12 14:00:00/2026-06-12 20:00:00",
                    "ImpactDuration": "4h",
                    "InteruptionsCounts": "1",
                },
                {
                    "CircuitID": "Backbone circuit",
                    "OrderNumber": "24-162082",
                    "InternationalId": "International backbone",
                    "CircuitIDRT": "1940953",
                    "ImpactDateTime": "2026-06-12 15:00:00/2026-06-12 16:30:00",
                    "ImpactDuration": "20m",
                    "InteruptionsCounts": "2",
                },
                {
                    "CircuitID": "Missing circuit",
                    "OrderNumber": "24-162099",
                    "InternationalId": "Missing international",
                    "CircuitIDRT": "1999999",
                    "ImpactDateTime": "2026-06-12 14:00:00/2026-06-12 20:00:00",
                    "ImpactDuration": "4h",
                    "InteruptionsCounts": "1",
                },
            ]},
        }

        def fake_query(supplier, keywords):
            if "1940952" in keywords:
                return [{
                    "supplier": supplier,
                    "supplier_circuit_id": "1940952",
                    "circuit_id": "EU202510000941",
                    "line_type": "客户",
                    "line_status": "正常",
                    "remark": "",
                }]
            if "1940953" in keywords:
                return [{
                    "supplier": supplier,
                    "supplier_circuit_id": "1940953",
                    "circuit_id": "Backbone-System-001",
                    "line_type": "骨干",
                    "line_status": "正常",
                    "remark": "",
                }]
            return []

        with patch.object(api_server, "query_supplier_circuits", side_effect=fake_query), patch.object(
            api_server,
            "build_template_workbook",
            return_value=object(),
        ), patch.object(
            api_server,
            "save_workbook_output",
            return_value=Path("/tmp/RT00_26012495.xlsx"),
        ):
            response = self.client.post(
                "/api/cutover/tasks/generate",
                headers=self.headers,
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        # msg 只含摘要信息与任务详情链接，不体现具体填报结果
        self.assertIn("割接填报摘要", data["msg"])
        self.assertIn("(EUR)RT网内割接00/26012495", data["msg"])
        self.assertIn("割接窗口(北京时间)", data["msg"])
        self.assertIn("生成任务: 2 个", data["msg"])
        self.assertIn("校验提示: 1 条", data["msg"])
        for task in data["tasks"]:
            self.assertIn(
                f"/admin/cutover-emails/{self.email_records_id}?taskId={task['id']}",
                data["msg"],
            )
        # 摘要不展示具体填报内容
        self.assertNotIn(data["customer_excel"]["download_url"], data["msg"])
        self.assertIn("线路表未查询到匹配线路", data["msg"])
        self.assertNotIn("Backbone-System-001", data["msg"])
        self.assertNotIn("现场指挥人员名称", data["msg"])

    def test_reports_empty_or_unsupported_lookup_fields(self):
        payload = {
            "supplier": "RT",
            "carrier_ticket_no": "00/26012495",
            "cutover_time": "2026-06-12 14:00:00/2026-06-12 20:00:00",
            "cutover_timezone": "UTC",
            "cutover_reason": "Scheduled maintenance.",
            "location": "Odense - Aabenraa (Denmark)",
            "line_array_info": {"data": [
                {
                    "CircuitID": "Empty circuit id",
                    "OrderNumber": "24-162081",
                    "InternationalId": "International customer",
                    "CircuitIDRT": "1940952",
                    "ImpactDateTime": "2026-06-12 14:00:00/2026-06-12 20:00:00",
                    "ImpactDuration": "4h",
                    "InteruptionsCounts": "1",
                },
                {
                    "CircuitID": "Empty line type",
                    "OrderNumber": "24-162082",
                    "InternationalId": "International customer",
                    "CircuitIDRT": "1940953",
                    "ImpactDateTime": "2026-06-12 14:00:00/2026-06-12 20:00:00",
                    "ImpactDuration": "4h",
                    "InteruptionsCounts": "1",
                },
                {
                    "CircuitID": "Unsupported line type",
                    "OrderNumber": "24-162083",
                    "InternationalId": "International customer",
                    "CircuitIDRT": "1940954",
                    "ImpactDateTime": "2026-06-12 14:00:00/2026-06-12 20:00:00",
                    "ImpactDuration": "4h",
                    "InteruptionsCounts": "1",
                },
            ]},
        }

        def fake_query(supplier, keywords):
            if "1940952" in keywords:
                return [{
                    "supplier": supplier,
                    "supplier_circuit_id": "1940952",
                    "circuit_id": "",
                    "line_type": "客户",
                    "line_status": "正常",
                    "remark": "",
                }]
            if "1940953" in keywords:
                return [{
                    "supplier": supplier,
                    "supplier_circuit_id": "1940953",
                    "circuit_id": "EU202510000943",
                    "line_type": "",
                    "line_status": "正常",
                    "remark": "",
                }]
            return [{
                "supplier": supplier,
                "supplier_circuit_id": "1940954",
                "circuit_id": "EU202510000944",
                "line_type": "未知",
                "line_status": "正常",
                "remark": "",
            }]

        with patch.object(api_server, "query_supplier_circuits", side_effect=fake_query):
            result = api_server.build_cutover_fill_response(payload)

        self.assertNotIn("body", result)
        self.assertNotIn("unmatched_lines", result)
        self.assertNotIn("unsupported_lines", result)
        self.assertEqual(result["circuits"], [])
        self.assertEqual(result["backbone_circuits"], [])
        self.assertEqual(
            [message["type"] for message in result["validation_messages"]],
            ["empty_circuit_id", "empty_line_type", "unsupported_line_type"],
        )

    def test_reports_unmatched_line_in_validation_messages(self):
        payload = {
            "supplier": "RT",
            "carrier_ticket_no": "00/26012495",
            "cutover_time": "2026-06-12 14:00:00/2026-06-12 20:00:00",
            "cutover_timezone": "UTC",
            "cutover_reason": "Scheduled maintenance.",
            "location": "Odense - Aabenraa (Denmark)",
            "line_array_info": {"data": [{
                "CircuitID": "Missing circuit",
                "OrderNumber": "24-162099",
                "InternationalId": "Missing international",
                "CircuitIDRT": "1999999",
                "ImpactDateTime": "2026-06-12 14:00:00/2026-06-12 20:00:00",
                "ImpactDuration": "4h",
                "InteruptionsCounts": "1",
            }]},
        }

        with patch.object(api_server, "query_supplier_circuits", return_value=[]):
            result = api_server.build_cutover_fill_response(payload)

        self.assertNotIn("unmatched_lines", result)
        self.assertNotIn("unsupported_lines", result)
        self.assertEqual(result["circuits"], [])
        self.assertEqual(result["backbone_circuits"], [])
        self.assertEqual(len(result["validation_messages"]), 1)
        self.assertEqual(result["validation_messages"][0]["type"], "unmatched_line")
        self.assertIn("未查询到匹配线路", result["validation_messages"][0]["message"])


class CutoverSceneWritebackTest(unittest.TestCase):
    """割接场景回写：FastGPT 判定命中供应商特殊规则后回写场景与说明。"""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = EmailDatabase(os.path.join(self.tmpdir.name, "mail_listener.db"))
        self.db_patch = patch.object(api_server, "email_db", self.db)
        self.db_patch.start()
        self.client = api_server.app.test_client()
        self.headers = {"Authorization": "Bearer test-key"}
        self.db.add_email_record(
            email_id=2001,
            sender="noc@supplier.example.com",
            receiver="noc@example.com",
            subject="割接通知",
            content="割接邮件正文",
        )
        self.email_records_id = self.db.get_email_record(2001)["id"]

    def tearDown(self):
        self.db_patch.stop()
        self.tmpdir.cleanup()

    def test_scene_writeback_rule_skipped_with_remark(self):
        response = self.client.post("/api/cutover/scene", headers=self.headers, json={
            "email_records_id": self.email_records_id,
            "cutover_scene": "rule_skipped",
            "scene_remark": "Carrier 为 China Telecom Europe Limited，命中 RT 特殊规则，不上报",
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["cutover_scene"], "rule_skipped")
        self.assertEqual(data["cutover_scene_label"], "命中特殊规则")
        self.assertIn("China Telecom Europe Limited", data["scene_remark"])

        record = self.db.get_email_record_by_id(self.email_records_id)
        self.assertEqual(record["cutover_scene"], "rule_skipped")
        self.assertIn("China Telecom Europe Limited", record["cutover_scene_remark"])

    def test_scene_writeback_validation(self):
        missing = self.client.post("/api/cutover/scene", headers=self.headers, json={
            "cutover_scene": "rule_skipped",
        })
        self.assertEqual(missing.status_code, 400)

        invalid = self.client.post("/api/cutover/scene", headers=self.headers, json={
            "email_records_id": self.email_records_id,
            "cutover_scene": "not_a_scene",
        })
        self.assertEqual(invalid.status_code, 400)

        not_found = self.client.post("/api/cutover/scene", headers=self.headers, json={
            "email_records_id": 999999,
            "cutover_scene": "rule_skipped",
        })
        self.assertEqual(not_found.status_code, 404)

    def test_reply_endpoint_rejects_rule_skipped_scene(self):
        """rule_skipped 只能经 /api/cutover/scene 回写，回复接口不可携带。"""
        response = self.client.post("/api/cutover/reply", headers=self.headers, json={
            "email_records_id": self.email_records_id,
            "reply_content": "拒绝割接",
            "cutover_scene": "rule_skipped",
        })
        self.assertEqual(response.status_code, 400)


class CutoverReplyConfirmTest(unittest.TestCase):
    """回复人工确认流程：登记草稿 → 确认发送/放弃，场景仅在确认发送后写入。"""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = EmailDatabase(os.path.join(self.tmpdir.name, "mail_listener.db"))
        self.db_patch = patch.object(api_server, "email_db", self.db)
        self.db_patch.start()
        self.client = api_server.app.test_client()
        self.headers = {"Authorization": "Bearer test-key"}
        self.db.add_email_record(
            email_id=3001,
            sender="noc@supplier.example.com",
            receiver="noc@example.com",
            subject="割接通知",
            content="割接邮件正文",
            reply_to="reply@supplier.example.com",
        )
        self.email_records_id = self.db.get_email_record(3001)["id"]

    def tearDown(self):
        self.db_patch.stop()
        self.tmpdir.cleanup()

    def register_pending_reply(self, scene="major_event"):
        with patch.object(api_server.EmailClient, "reply_email", return_value=True) as reply_email:
            response = self.client.post("/api/cutover/reply", headers=self.headers, json={
                "email_records_id": self.email_records_id,
                "reply_content": "拒绝割接",
                "cutover_scene": scene,
            })
        return response, reply_email

    def test_reply_registers_pending_without_sending(self):
        response, reply_email = self.register_pending_reply()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["reply_status"], "pending")
        reply_email.assert_not_called()

        record = self.db.get_email_record_by_id(self.email_records_id)
        self.assertEqual(record["reply_status"], "pending")
        self.assertEqual(record["pending_reply_content"], "拒绝割接")
        self.assertEqual(record["pending_reply_scene"], "major_event")
        # 登记阶段不写入割接场景，避免未发送就展示已拒绝
        self.assertEqual(record["cutover_scene"], "normal")

        detail = self.client.get(f"/api/cutover/emails/{self.email_records_id}", headers=self.headers)
        self.assertEqual(detail.status_code, 200)
        detail_data = detail.get_json()["data"]
        self.assertEqual(detail_data["reply_status"], "pending")
        self.assertEqual(detail_data["pending_reply_content"], "拒绝割接")
        self.assertEqual(detail_data["pending_reply_scene_label"], "重保期割接")
        self.assertEqual(detail_data["reply_to"], "reply@supplier.example.com")

        listing = self.client.get("/api/cutover/emails", headers=self.headers)
        item = listing.get_json()["data"]["items"][0]
        self.assertEqual(item["reply_status"], "pending")
        self.assertEqual(item["pending_reply_scene"], "major_event")
        self.assertEqual(item["pending_reply_scene_label"], "重保期割接")

    def test_pending_reply_scene_tags_are_filterable_before_confirmation(self):
        for scene, expected_label in (
            ("emergency", "紧急割接"),
            ("major_event", "重保期割接"),
            ("in_window", "已在割接窗口内"),
        ):
            with self.subTest(scene=scene):
                response, reply_email = self.register_pending_reply(scene=scene)
                self.assertEqual(response.status_code, 200)
                reply_email.assert_not_called()

                listing = self.client.get(
                    f"/api/cutover/emails?tag={scene}",
                    headers=self.headers,
                )
                self.assertEqual(listing.status_code, 200)
                data = listing.get_json()["data"]
                self.assertEqual(data["total"], 1)
                item = data["items"][0]
                self.assertEqual(item["cutover_scene"], "normal")
                self.assertEqual(item["pending_reply_scene"], scene)
                self.assertEqual(item["pending_reply_scene_label"], expected_label)

    def test_confirm_sends_and_writes_scene(self):
        self.register_pending_reply()

        with patch.object(api_server, "build_reply_email_client") as build_client:
            build_client.return_value.reply_email.return_value = True
            response = self.client.post("/api/cutover/reply/confirm", headers=self.headers, json={
                "email_records_id": self.email_records_id,
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(build_client.return_value.reply_email.call_args.args[1], "拒绝割接")
        record = self.db.get_email_record_by_id(self.email_records_id)
        self.assertEqual(record["reply_status"], "sent")
        self.assertTrue(record["reply_time"])
        self.assertEqual(record["cutover_scene"], "major_event")

    def test_confirm_allows_edited_content(self):
        self.register_pending_reply(scene="normal")

        with patch.object(api_server, "build_reply_email_client") as build_client:
            build_client.return_value.reply_email.return_value = True
            response = self.client.post("/api/cutover/reply/confirm", headers=self.headers, json={
                "email_records_id": self.email_records_id,
                "reply_content": "人工修改后的回复",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(build_client.return_value.reply_email.call_args.args[1], "人工修改后的回复")
        record = self.db.get_email_record_by_id(self.email_records_id)
        self.assertEqual(record["reply_status"], "sent")
        # normal 场景不回写场景字段，保持默认值
        self.assertEqual(record["cutover_scene"], "normal")

    def test_confirm_with_custom_recipients(self):
        """人工确认时可修改收件人，支持多个地址；不传时沿用原回复地址。"""
        self.register_pending_reply()

        with patch.object(api_server, "build_reply_email_client") as build_client:
            build_client.return_value.reply_email.return_value = True
            custom = self.client.post("/api/cutover/reply/confirm", headers=self.headers, json={
                "email_records_id": self.email_records_id,
                "recipients": ["noc@supplier.example.com", "leader@example.com"],
            })

        self.assertEqual(custom.status_code, 200)
        data = custom.get_json()["data"]
        self.assertEqual(data["recipients"], ["noc@supplier.example.com", "leader@example.com"])
        self.assertEqual(data["recipient"], "noc@supplier.example.com, leader@example.com")
        self.assertEqual(
            build_client.return_value.reply_email.call_args.kwargs["recipients"],
            ["noc@supplier.example.com", "leader@example.com"],
        )

        # 非法收件人直接 400（收件人校验先于状态检查执行）
        invalid = self.client.post("/api/cutover/reply/confirm", headers=self.headers, json={
            "email_records_id": self.email_records_id,
            "recipients": ["bad-address"],
        })
        self.assertEqual(invalid.status_code, 400)

    def test_confirm_rejected_when_not_pending(self):
        response = self.client.post("/api/cutover/reply/confirm", headers=self.headers, json={
            "email_records_id": self.email_records_id,
        })
        self.assertEqual(response.status_code, 400)

    def test_cancel_discards_pending_reply(self):
        self.register_pending_reply()

        response = self.client.post("/api/cutover/reply/cancel", headers=self.headers, json={
            "email_records_id": self.email_records_id,
        })

        self.assertEqual(response.status_code, 200)
        record = self.db.get_email_record_by_id(self.email_records_id)
        self.assertEqual(record["reply_status"], "cancelled")
        self.assertEqual(record["pending_reply_content"], "")
        self.assertEqual(record["pending_reply_scene"], "")
        self.assertEqual(record["cutover_scene"], "normal")

        # 取消后不可再确认发送
        confirm = self.client.post("/api/cutover/reply/confirm", headers=self.headers, json={
            "email_records_id": self.email_records_id,
        })
        self.assertEqual(confirm.status_code, 400)


if __name__ == '__main__':
    unittest.main()
