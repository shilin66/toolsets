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
        self.client = api_server.app.test_client()
        self.headers = {"Authorization": "Bearer test-key"}
        self.email_records_id = self.insert_email_record()

    def tearDown(self):
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
        self.assertEqual(missing.status_code, 400)
        self.assertIn("email_records_id", missing.get_json()["message"])

        not_found = self.client.post(
            "/api/cutover/fill", headers=self.headers, json={"email_records_id": 999999}
        )
        self.assertEqual(not_found.status_code, 404)

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
                    "remark": "",
                }]
            return [{
                "supplier": supplier,
                "supplier_circuit_id": "1940953",
                "circuit_id": "Backbone-System-001",
                "line_type": "骨干",
                "remark": "",
            }]

        with patch.object(api_server, "query_supplier_circuits", side_effect=fake_query):
            result = api_server.build_cutover_fill_response(payload)

        self.assertNotIn("body", result)
        self.assertNotIn("unmatched_lines", result)
        self.assertNotIn("unsupported_lines", result)
        self.assertEqual(result["filename"], "RT00_26012495.xlsx")
        self.assertEqual(result["cutStartTime"], "2026-06-12 22:00:00")
        self.assertEqual(result["cutEndTime"], "2026-06-13 04:00:00")
        self.assertEqual(len(result["circuits"]), 1)
        self.assertEqual(result["circuits"][0]["电路代号"], "EU202510000941")
        self.assertEqual(result["circuits"][0]["预计影响客户业务时长"], "中断：240分钟")
        self.assertEqual(len(result["reasons"]), 1)
        self.assertEqual(len(result["backbone_circuits"]), 1)
        self.assertEqual(
            result["backbone_circuits"][0]["割接对象"]["系统名称"],
            "Backbone-System-001",
        )
        self.assertEqual(
            result["backbone_circuits"][0]["割接对象"]["割接开始时间"],
            "2026-06-12 23:00:00",
        )
        self.assertEqual(
            result["backbone_circuits"][0]["基本信息"]["中断类型"],
            "中断：40分钟",
        )
        self.assertEqual(
            result["backbone_circuits"][0]["基本信息"]["变更操作等级"],
            "四级",
        )
        self.assertIn(
            "割接名称",
            result["backbone_circuits"][0]["割接对象"],
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
                "remark": "",
            },
            {
                "supplier": "RT",
                "supplier_circuit_id": "24-162081",
                "circuit_id": "EU202510000942",
                "line_type": "客户",
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
                    "remark": "",
                }]
            if "1940953" in keywords:
                return [{
                    "supplier": supplier,
                    "supplier_circuit_id": "1940953",
                    "circuit_id": "Backbone-System-001",
                    "line_type": "骨干",
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
        self.assertNotIn("线路表未查询到匹配线路", data["msg"])
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
                    "remark": "",
                }]
            if "1940953" in keywords:
                return [{
                    "supplier": supplier,
                    "supplier_circuit_id": "1940953",
                    "circuit_id": "EU202510000943",
                    "line_type": "",
                    "remark": "",
                }]
            return [{
                "supplier": supplier,
                "supplier_circuit_id": "1940954",
                "circuit_id": "EU202510000944",
                "line_type": "未知",
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
