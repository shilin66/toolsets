import os
import sys
import json
import tempfile
import unittest
from io import BytesIO
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
from database import EmailDatabase


class SupplierConfigApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = EmailDatabase(os.path.join(self.tmpdir.name, "mail_listener.db"))
        self.db_patch = patch.object(api_server, "email_db", self.db)
        self.db_patch.start()
        self.client = api_server.app.test_client()
        self.headers = {"Authorization": "Bearer test-key"}

    def tearDown(self):
        self.db_patch.stop()
        self.tmpdir.cleanup()

    def test_supplier_config_can_be_created_fetched_and_updated(self):
        create_payload = {
            "name": "RT",
            "email": "noc@rt.example.com",
            "can_reply_directly": True,
            "cutover_extract_prompt": "提取割接开始时间、结束时间、影响线路和割接原因。",
        }

        create_response = self.client.post(
            "/api/suppliers",
            json=create_payload,
            headers=self.headers,
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.get_json()["data"]
        self.assertEqual(created["name"], "RT")
        self.assertEqual(created["email"], "noc@rt.example.com")
        self.assertTrue(created["can_reply_directly"])
        self.assertEqual(created["cutover_extract_prompt"], create_payload["cutover_extract_prompt"])
        self.assertIsNotNone(created["create_time"])
        self.assertIsNotNone(created["update_time"])

        fetch_response = self.client.get(f"/api/suppliers/{created['id']}", headers=self.headers)

        self.assertEqual(fetch_response.status_code, 200)
        fetched = fetch_response.get_json()["data"]
        self.assertEqual(fetched["id"], created["id"])
        self.assertEqual(fetched["email"], "noc@rt.example.com")

        update_response = self.client.patch(
            f"/api/suppliers/{created['id']}",
            json={
                "email": "new-noc@rt.example.com",
                "can_reply_directly": False,
            },
            headers=self.headers,
        )

        self.assertEqual(update_response.status_code, 200)
        updated = update_response.get_json()["data"]
        self.assertEqual(updated["email"], "new-noc@rt.example.com")
        self.assertFalse(updated["can_reply_directly"])
        self.assertEqual(updated["name"], "RT")

    def test_supplier_config_rejects_missing_required_fields(self):
        response = self.client.post(
            "/api/suppliers",
            json={
                "name": "RT",
                "email": "noc@rt.example.com",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("参数校验失败", data["message"])

    def test_supplier_config_with_line_custom_fields_generates_prompt(self):
        create_payload = {
            "name": "RT",
            "email": "noc@rt.example.com",
            "can_reply_directly": False,
            "prompt_mode": "auto",
            "line_custom_fields": [
                {
                    "name": "CircuitTitle",
                    "description": "对应表格中的 Circuit Title 列",
                },
            ],
            "line_query_keywords": ["CircuitTitle"],
            "extra_instructions": "该供应商时间均为 UTC+7。",
        }

        create_response = self.client.post(
            "/api/suppliers", json=create_payload, headers=self.headers
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.get_json()["data"]
        self.assertEqual(created["prompt_mode"], "auto")
        self.assertEqual(len(created["line_custom_fields"]), 1)
        self.assertEqual(created["line_query_keywords"], ["CircuitTitle"])
        prompt = created["cutover_extract_prompt"]
        self.assertIn("carrier_ticket_no", prompt)
        self.assertIn("cutover_backup_time", prompt)
        self.assertIn("CircuitTitle", prompt)
        self.assertIn('固定输出 `["CircuitTitle"]`', prompt)
        self.assertIn("该供应商时间均为 UTC+7。", prompt)

    def test_supplier_config_rejects_unknown_query_keyword(self):
        create_payload = {
            "name": "RT",
            "email": "noc@rt.example.com",
            "prompt_mode": "auto",
            "line_custom_fields": [{"name": "CircuitTitle"}],
            "line_query_keywords": ["NotConfigured"],
        }

        response = self.client.post(
            "/api/suppliers", json=create_payload, headers=self.headers
        )

        self.assertEqual(response.status_code, 400)

    def test_supplier_prompt_preview_endpoint(self):
        response = self.client.post(
            "/api/suppliers/preview-prompt",
            json={
                "line_custom_fields": [
                    {"name": "CircuitTitle", "description": "Circuit Title 列"},
                ],
                "line_query_keywords": ["CircuitTitle"],
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        prompt = response.get_json()["data"]["cutover_extract_prompt"]
        self.assertIn("CircuitTitle", prompt)
        self.assertIn("carrier_ticket_no", prompt)

        invalid_response = self.client.post(
            "/api/suppliers/preview-prompt",
            json={
                "line_custom_fields": [],
                "line_query_keywords": ["CircuitTitle"],
            },
            headers=self.headers,
        )
        self.assertEqual(invalid_response.status_code, 400)

    def test_supplier_config_with_top_custom_fields(self):
        create_payload = {
            "name": "RT",
            "email": "noc@rt.example.com",
            "prompt_mode": "auto",
            "line_custom_fields": [
                {"name": "CircuitID", "description": "电路号列"},
            ],
            "line_query_keywords": ["CircuitID"],
            "custom_fields": [
                {"name": "carrier", "description": "提取邮件正文中的 Carrier（承运方）"},
            ],
        }

        create_response = self.client.post(
            "/api/suppliers", json=create_payload, headers=self.headers
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.get_json()["data"]
        self.assertEqual(created["custom_fields"], create_payload["custom_fields"])
        prompt = created["cutover_extract_prompt"]
        self.assertIn('"carrier": ""', prompt)
        self.assertIn("Carrier（承运方）", prompt)

        clear_response = self.client.patch(
            f"/api/suppliers/{created['id']}",
            json={"custom_fields": []},
            headers=self.headers,
        )
        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(clear_response.get_json()["data"]["custom_fields"], [])

    def test_supplier_config_rejects_reserved_top_custom_field_name(self):
        for bad_name in ("line_array", "carrier_ticket_no"):
            response = self.client.post(
                "/api/suppliers",
                json={
                    "name": "RT",
                    "email": "noc@rt.example.com",
                    "prompt_mode": "auto",
                    "line_custom_fields": [{"name": "CircuitID"}],
                    "line_query_keywords": ["CircuitID"],
                    "custom_fields": [{"name": bad_name}],
                },
                headers=self.headers,
            )
            self.assertEqual(response.status_code, 400)

    def test_supplier_prompt_preview_supports_top_custom_fields(self):
        response = self.client.post(
            "/api/suppliers/preview-prompt",
            json={
                "line_custom_fields": [
                    {"name": "CircuitID", "description": "电路号列"},
                ],
                "line_query_keywords": ["CircuitID"],
                "custom_fields": [
                    {"name": "carrier", "description": "提取邮件正文中的 Carrier"},
                ],
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        prompt = response.get_json()["data"]["cutover_extract_prompt"]
        self.assertIn('"carrier": ""', prompt)

    def test_supplier_field_defaults_endpoint(self):
        response = self.client.get("/api/suppliers/field-defaults", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        top_names = [field["name"] for field in data["top_fields"]]
        line_names = [field["name"] for field in data["line_fields"]]
        self.assertIn("carrier_ticket_no", top_names)
        self.assertIn("ImpactType", line_names)

    def test_supplier_config_with_fixed_field_rules_override(self):
        create_payload = {
            "name": "RT",
            "email": "noc@rt.example.com",
            "prompt_mode": "auto",
            "line_custom_fields": [{"name": "CircuitTitle"}],
            "line_query_keywords": ["CircuitTitle"],
            "fixed_field_rules": {
                "carrier_ticket_no": "从邮件标题中提取单号。",
            },
        }

        create_response = self.client.post(
            "/api/suppliers", json=create_payload, headers=self.headers
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.get_json()["data"]
        self.assertEqual(
            created["fixed_field_rules"],
            {"carrier_ticket_no": "从邮件标题中提取单号。"},
        )
        self.assertIn("从邮件标题中提取单号。", created["cutover_extract_prompt"])

        invalid_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "RT2",
                "email": "noc2@rt.example.com",
                "prompt_mode": "auto",
                "fixed_field_rules": {"unknown_field": "规则"},
            },
            headers=self.headers,
        )
        self.assertEqual(invalid_response.status_code, 400)

    def test_supplier_config_rejects_duplicate_name_and_email(self):
        create_payload = {
            "name": "RT",
            "email": "noc@rt.example.com",
            "can_reply_directly": True,
            "cutover_extract_prompt": "提取割接字段。",
        }
        self.client.post("/api/suppliers", json=create_payload, headers=self.headers)

        duplicate_name_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "RT",
                "email": "noc-other@rt.example.com",
                "can_reply_directly": False,
                "cutover_extract_prompt": "提取割接字段。",
            },
            headers=self.headers,
        )

        self.assertEqual(duplicate_name_response.status_code, 409)
        self.assertIn("供应商名称已存在", duplicate_name_response.get_json()["message"])

        duplicate_email_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "RT Other",
                "email": "noc@rt.example.com",
                "can_reply_directly": False,
                "cutover_extract_prompt": "提取割接字段。",
            },
            headers=self.headers,
        )

        self.assertEqual(duplicate_email_response.status_code, 409)
        self.assertIn("供应商邮箱已存在", duplicate_email_response.get_json()["message"])

    def test_supplier_config_rejects_duplicate_name_and_email_on_update(self):
        first_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "RT",
                "email": "noc@rt.example.com",
                "can_reply_directly": False,
                "cutover_extract_prompt": "提取割接字段。",
            },
            headers=self.headers,
        )
        second_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "Level3",
                "email": "noc@level3.example.com",
                "can_reply_directly": False,
                "cutover_extract_prompt": "提取割接字段。",
            },
            headers=self.headers,
        )
        first = first_response.get_json()["data"]
        second = second_response.get_json()["data"]

        duplicate_name_response = self.client.patch(
            f"/api/suppliers/{second['id']}",
            json={"name": first["name"]},
            headers=self.headers,
        )

        self.assertEqual(duplicate_name_response.status_code, 409)
        self.assertIn("供应商名称已存在", duplicate_name_response.get_json()["message"])

        duplicate_email_response = self.client.patch(
            f"/api/suppliers/{second['id']}",
            json={"email": first["email"]},
            headers=self.headers,
        )

        self.assertEqual(duplicate_email_response.status_code, 409)
        self.assertIn("供应商邮箱已存在", duplicate_email_response.get_json()["message"])

    def test_supplier_config_can_be_listed_and_deleted(self):
        create_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "Level3",
                "email": "noc@level3.example.com",
                "can_reply_directly": False,
                "cutover_extract_prompt": "提取割接字段。",
            },
            headers=self.headers,
        )
        created = create_response.get_json()["data"]

        list_response = self.client.get("/api/suppliers", headers=self.headers)

        self.assertEqual(list_response.status_code, 200)
        records = list_response.get_json()["data"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], created["id"])

        delete_response = self.client.delete(f"/api/suppliers/{created['id']}", headers=self.headers)

        self.assertEqual(delete_response.status_code, 200)
        fetch_response = self.client.get(f"/api/suppliers/{created['id']}", headers=self.headers)
        self.assertEqual(fetch_response.status_code, 404)

    def test_mail_type_options_can_be_listed(self):
        response = self.client.get("/api/suppliers/mail-types", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        options = response.get_json()["data"]
        self.assertEqual(
            options,
            ["割接通知", "割接改期", "割接取消", "割接提醒", "故障邮件"],
        )

    def test_email_type_samples_can_be_created_and_updated(self):
        samples = {
            "割接通知": {
                "subject": "【割接通知】XX线路割接",
                "content": "割接时间：2026-08-20 00:00-06:00",
                "content_in_attachment": False,
            },
            "割接改期": {
                "subject": "【割接改期】XX线路割接改期",
                "content": "割接时间调整为 2026-08-21",
                "content_in_attachment": False,
            },
        }
        create_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "TT",
                "email": "noc@tt.example.com",
                "cutover_extract_prompt": "提取割接字段。",
                "email_type_samples": samples,
            },
            headers=self.headers,
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.get_json()["data"]
        self.assertEqual(created["email_type_samples"], samples)

        classify_prompt = created["supplier_mail_classify_prompt"]
        self.assertIn("邮件分类助手", classify_prompt)
        # 分类兜底类型始终存在，且不带样本段
        self.assertIn("* 其它：", classify_prompt)
        self.assertNotIn("类型：其它", classify_prompt)
        # 已配置的样本以 few-shot 形式写入提示词
        self.assertIn("样本主题：【割接通知】XX线路割接", classify_prompt)
        self.assertIn("割接时间：2026-08-20 00:00-06:00", classify_prompt)
        self.assertIn("样本主题：【割接改期】XX线路割接改期", classify_prompt)
        # 未配置样本的类型只有类型说明，没有样本段
        self.assertNotIn("类型：割接取消\n\n样本", classify_prompt)

        fetch_response = self.client.get(f"/api/suppliers/{created['id']}", headers=self.headers)
        self.assertEqual(fetch_response.get_json()["data"]["email_type_samples"], samples)

        updated_samples = dict(
            samples,
            故障邮件={"subject": "故障通告", "content": "线路中断", "content_in_attachment": False},
        )
        update_response = self.client.patch(
            f"/api/suppliers/{created['id']}",
            json={"email_type_samples": updated_samples},
            headers=self.headers,
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.get_json()["data"]["email_type_samples"], updated_samples)

    def test_email_type_samples_only_require_cutover_notice(self):
        # 只填割接通知，其余类型可缺省
        create_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "TT",
                "email": "noc@tt.example.com",
                "cutover_extract_prompt": "提取割接字段。",
                "email_type_samples": {
                    "割接通知": {"subject": "割接通知", "content": "正文样本"},
                },
            },
            headers=self.headers,
        )
        self.assertEqual(create_response.status_code, 201)

        # 割接通知主题缺失
        missing_subject_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "TT2",
                "email": "noc2@tt.example.com",
                "cutover_extract_prompt": "提取割接字段。",
                "email_type_samples": {
                    "割接通知": {"subject": "", "content": "正文样本"},
                },
            },
            headers=self.headers,
        )
        self.assertEqual(missing_subject_response.status_code, 400)
        self.assertIn("参数校验失败", missing_subject_response.get_json()["message"])

        # 割接通知正文缺失且未勾选正文在附件中
        missing_content_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "TT3",
                "email": "noc3@tt.example.com",
                "cutover_extract_prompt": "提取割接字段。",
                "email_type_samples": {
                    "割接通知": {"subject": "割接通知", "content": ""},
                },
            },
            headers=self.headers,
        )
        self.assertEqual(missing_content_response.status_code, 400)
        self.assertIn("参数校验失败", missing_content_response.get_json()["message"])

        # 正文在附件中时邮件正文本身仍需提供
        attachment_empty_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "TT4",
                "email": "noc4@tt.example.com",
                "cutover_extract_prompt": "提取割接字段。",
                "email_type_samples": {
                    "割接通知": {
                        "subject": "割接通知",
                        "content": "",
                        "content_in_attachment": True,
                    },
                },
            },
            headers=self.headers,
        )
        self.assertEqual(attachment_empty_response.status_code, 400)

        # 勾选正文在附件中且提供了正文
        attachment_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "TT4",
                "email": "noc4@tt.example.com",
                "cutover_extract_prompt": "提取割接字段。",
                "email_type_samples": {
                    "割接通知": {
                        "subject": "割接通知",
                        "content": "详见附件",
                        "content_in_attachment": True,
                    },
                },
            },
            headers=self.headers,
        )
        self.assertEqual(attachment_response.status_code, 201)
        created = attachment_response.get_json()["data"]
        self.assertTrue(created["email_type_samples"]["割接通知"]["content_in_attachment"])

    def test_email_type_samples_reject_unknown_type(self):
        unknown_response = self.client.post(
            "/api/suppliers",
            json={
                "name": "TT",
                "email": "noc@tt.example.com",
                "cutover_extract_prompt": "提取割接字段。",
                "email_type_samples": {"未知类型": {"subject": "主题", "content": "正文"}},
            },
            headers=self.headers,
        )
        self.assertEqual(unknown_response.status_code, 400)
        self.assertIn("参数校验失败", unknown_response.get_json()["message"])

    def test_preview_extract_calls_fastgpt_with_extract_preview_flag(self):
        captured = {}

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": "提取结果 JSON"}}]}

        def fake_post(url, json=None, headers=None, timeout=None, verify=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

        with patch.object(api_server.requests, "post", side_effect=fake_post):
            response = self.client.post(
                "/api/suppliers/preview-extract",
                json={
                    "subject": "【割接通知】XX线路",
                    "content": "割接正文样本",
                    "sender": "noc@tt.example.com",
                    "supplier_name": "TT",
                    "email_type_samples": {
                        "割接通知": {
                            "subject": "【割接通知】XX线路",
                            "content": "割接正文样本",
                        },
                    },
                    "cutover_extract_prompt": "提取割接字段。",
                },
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["extract_result"], "提取结果 JSON")

        content = json.loads(captured["json"]["messages"][0]["content"])
        self.assertTrue(content["extract_preview"])
        self.assertEqual(content["subject"], "【割接通知】XX线路")
        self.assertEqual(content["supplier_name"], "TT")
        self.assertEqual(content["supplier_cutover_extract_prompt"], "提取割接字段。")
        classify_prompt = content["supplier_mail_classify_prompt"]
        self.assertIn("邮件分类助手", classify_prompt)
        self.assertIn("样本主题：【割接通知】XX线路", classify_prompt)

    def test_preview_extract_uploads_and_forwards_attachments(self):
        upload_response = self.client.post(
            "/api/suppliers/preview-attachments",
            data={"file": (BytesIO(b"pdf-bytes"), "cutover.pdf")},
            content_type="multipart/form-data",
            headers=self.headers,
        )

        self.assertEqual(upload_response.status_code, 201)
        uploaded = upload_response.get_json()["data"]
        self.assertTrue(uploaded["relative_path"].startswith("email_attachments/preview-extract/"))
        self.assertTrue(uploaded["url"].endswith(uploaded["relative_path"]))

        captured = {}

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": "提取结果"}}]}

        def fake_post(url, json=None, headers=None, timeout=None, verify=None):
            captured["json"] = json
            return FakeResponse()

        with patch.object(api_server.requests, "post", side_effect=fake_post):
            response = self.client.post(
                "/api/suppliers/preview-extract",
                json={
                    "subject": "【割接通知】XX线路",
                    "content": "详见附件",
                    "content_in_attachment": True,
                    "attachments": [uploaded["relative_path"]],
                    "cutover_extract_prompt": "提取割接字段。",
                },
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        content = json.loads(captured["json"]["messages"][0]["content"])
        self.assertEqual(content["attachments"], [uploaded["relative_path"]])
        self.assertEqual(len(content["attachment_urls"]), 1)
        self.assertTrue(content["content_in_attachment"])

        # 非法附件路径被拒绝
        invalid_response = self.client.post(
            "/api/suppliers/preview-extract",
            json={
                "subject": "主题",
                "content": "正文",
                "attachments": ["../secrets.txt"],
                "cutover_extract_prompt": "提取割接字段。",
            },
            headers=self.headers,
        )
        self.assertEqual(invalid_response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
