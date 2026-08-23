import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from email.message import EmailMessage as RawEmailMessage
from unittest.mock import patch


os.environ.setdefault('IMAP_SERVER', 'imap.example.com')
os.environ.setdefault('EMAIL_ADDRESS', 'test@example.com')
os.environ.setdefault('EMAIL_PASSWORD', 'password')
os.environ.setdefault('API_URL', 'https://api.example.com')
os.environ.setdefault('API_TOKEN', 'token')
os.environ.setdefault('API_KEY', 'test-key')
os.environ.setdefault('API_PUBLIC_BASE_URL', 'http://mail-listen.example.com')

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_server
import email_client
import html_image
from actions import APIForwardAction
from database import EmailDatabase
from email_client import EmailClient
from mail_accounts import MailAccountConfig
from models import EmailMessage
from supplier_config import SupplierConfigCreate, SupplierConfigRepository


def _test_account():
    return MailAccountConfig(
        id=1,
        name="测试邮箱",
        email_address="receiver@example.com",
        email_password="password",
        imap_server="imap.example.com",
    )


class FakeIMAPClient:
    def __init__(self, messages, internal_dates=None):
        self.messages = messages
        self.internal_dates = internal_dates or {}
        self.flags = []
        self.fetched_fields = []

    def fetch(self, uid, fields):
        self.fetched_fields.append((uid, list(fields)))
        result = {}
        if 'RFC822' in fields:
            result[b'RFC822'] = self.messages[uid]
        if 'INTERNALDATE' in fields and uid in self.internal_dates:
            result[b'INTERNALDATE'] = self.internal_dates[uid]
        return {uid: result}

    def add_flags(self, uid, flags):
        self.flags.append((uid, flags))


class FakeResponse:
    status_code = 200

    @staticmethod
    def json():
        return {"ok": True}


class EmailImageForwardTest(unittest.TestCase):
    def test_build_content_includes_image_url(self):
        email = EmailMessage(
            uid=123,
            subject="HTML mail",
            sender="sender@example.com",
            recipients=["receiver@example.com"],
            content="Hello",
            html_content="<p>Hello</p>",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=["email_attachments/123/notice.txt"],
            image_url="http://mail-listen.example.com/api/email/images/email-123.png",
        )

        with patch.object(api_server.email_db, "get_email_record", return_value={"id": 7}), patch(
            "actions.email_db.get_email_record",
            return_value={"id": 7},
        ):
            content = APIForwardAction()._build_content(email, {})

        payload = json.loads(content)
        self.assertEqual(payload["email_records_id"], 7)
        self.assertEqual(payload["content"], "<p>Hello</p>")
        self.assertNotIn("html_content", payload)
        self.assertEqual(payload["attachments"], ["email_attachments/123/notice.txt"])
        self.assertTrue(payload["attachment_urls"][0].endswith(
            "/api/email/attachments/email_attachments/123/notice.txt"
        ))
        self.assertEqual(payload["image_url"], "http://mail-listen.example.com/api/email/images/email-123.png")

    def test_build_content_includes_supplier_config_when_sender_matches(self):
        email = EmailMessage(
            uid=123,
            subject="Cutover mail",
            sender="noc@supplier.example.com",
            recipients=["receiver@example.com"],
            content="割接通知",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(str(Path(tmpdir) / "mail_listener.db"))
            SupplierConfigRepository(db).create(
                SupplierConfigCreate(
                    name="RT",
                    email="noc@supplier.example.com",
                    can_reply_directly=True,
                    cutover_extract_prompt="提取割接开始时间、结束时间、影响线路。",
                )
            )

            with patch("actions.email_db", db):
                content = APIForwardAction()._build_content(email, {})

        payload = json.loads(content)
        self.assertEqual(payload["supplier_name"], "RT")
        self.assertTrue(payload["supplier_can_reply_directly"])
        self.assertEqual(
            payload["supplier_cutover_extract_prompt"],
            "提取割接开始时间、结束时间、影响线路。",
        )

    def test_api_forward_sends_supplier_config_in_message_content(self):
        email = EmailMessage(
            uid=123,
            subject="Cutover mail",
            sender="noc@supplier.example.com",
            recipients=["receiver@example.com"],
            content="割接通知",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(str(Path(tmpdir) / "mail_listener.db"))
            SupplierConfigRepository(db).create(
                SupplierConfigCreate(
                    name="RT",
                    email="noc@supplier.example.com",
                    can_reply_directly=False,
                    cutover_extract_prompt="提取割接字段。",
                )
            )

            with patch("actions.email_db", db), patch("actions.requests.post", return_value=FakeResponse()) as post:
                result = APIForwardAction().execute(email, {})

        self.assertTrue(result.success)
        sent_json = post.call_args.kwargs["json"]
        payload = json.loads(sent_json["messages"][0]["content"])
        self.assertEqual(payload["supplier_name"], "RT")
        self.assertFalse(payload["supplier_can_reply_directly"])
        self.assertEqual(payload["supplier_cutover_extract_prompt"], "提取割接字段。")
        classify_prompt = payload["supplier_mail_classify_prompt"]
        self.assertIn("邮件分类助手", classify_prompt)
        self.assertIn("割接通知", classify_prompt)
        self.assertIn("* 其它：", classify_prompt)

    def test_parse_mail_type_from_ai_reply(self):
        from actions import parse_mail_type_from_ai_reply
        reply = (
            "```json\n"
            '{"mail_type": "割接通知"}\n'
            "```\n"
            "---\n"
            '{"carrier_ticket_no": "00/123", "line_array": []}'
        )
        self.assertEqual(parse_mail_type_from_ai_reply(reply), "割接通知")
        self.assertEqual(parse_mail_type_from_ai_reply('{"carrier_ticket_no": "x"}'), "")
        self.assertEqual(parse_mail_type_from_ai_reply(""), "")
        self.assertEqual(parse_mail_type_from_ai_reply(None), "")

    def test_api_forward_saves_mail_type_from_reply(self):
        email = EmailMessage(
            uid=456,
            subject="Cutover mail",
            sender="noc@supplier.example.com",
            recipients=["receiver@example.com"],
            content="割接通知",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )
        reply_text = '{"mail_type": "割接通知"}\n---\n{"carrier_ticket_no": "00/123"}'

        class ClassifyResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": reply_text}}]}

        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(str(Path(tmpdir) / "mail_listener.db"))
            db.add_email_record(
                email_id=456, sender=email.sender,
                subject=email.subject, content=email.content,
            )
            with patch("actions.email_db", db), patch(
                "actions.requests.post", return_value=ClassifyResponse()
            ):
                result = APIForwardAction().execute(email, {})
            record = db.get_email_record(456)

        self.assertTrue(result.success)
        self.assertEqual(result.data["mail_type"], "割接通知")
        self.assertEqual(record["mail_type"], "割接通知")
        # 提取解析结果存 FastGPT 返回原文，供详情页展示
        self.assertEqual(record["extract_result"], reply_text)

    def test_api_forward_without_mail_type_keeps_success(self):
        """FastGPT 返回无分类结果时转发仍成功，mail_type 保持为空。"""
        email = EmailMessage(
            uid=789,
            subject="Cutover mail",
            sender="noc@supplier.example.com",
            recipients=["receiver@example.com"],
            content="割接通知",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(str(Path(tmpdir) / "mail_listener.db"))
            db.add_email_record(
                email_id=789, sender=email.sender,
                subject=email.subject, content=email.content,
            )
            with patch("actions.email_db", db), patch(
                "actions.requests.post", return_value=FakeResponse()
            ):
                result = APIForwardAction().execute(email, {})
            record = db.get_email_record(789)

        self.assertTrue(result.success)
        self.assertEqual(result.data["mail_type"], "")
        self.assertEqual(record["mail_type"], "")
        self.assertIn("ok", record["extract_result"])

    def test_view_email_image_serves_temp_png(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(html_image, "IMAGE_DIR", Path(tmpdir)):
            image_path = Path(tmpdir) / "email-123-test.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

            response = api_server.app.test_client().get("/api/email/images/email-123-test.png")
            response.get_data()
            response.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")

    def test_parse_email_does_not_render_image_anymore(self):
        raw_message = RawEmailMessage()
        raw_message["Subject"] = "Plain mail"
        raw_message["From"] = "sender@example.com"
        raw_message["To"] = "receiver@example.com"
        raw_message["Date"] = "Fri, 26 Jun 2026 10:00:00 +0800"
        raw_message.set_content("plain mail body")

        with tempfile.TemporaryDirectory() as tmpdir:
            # 即使发件人是配置供应商，解析阶段也不再渲染（渲染后移至 API 转发时）
            db = EmailDatabase(str(Path(tmpdir) / "mail_listener.db"))
            SupplierConfigRepository(db).create(
                SupplierConfigCreate(
                    name="RT",
                    email="sender@example.com",
                    cutover_extract_prompt="提取割接字段。",
                )
            )

            with patch(
                "actions.render_email_body_to_image_url",
                return_value="http://mail-listen.example.com/api/email/images/email-123.png",
            ) as render_image, patch("email_client.email_db", db):
                client = EmailClient(_test_account())
                client.client = FakeIMAPClient({123: raw_message.as_bytes()})
                parsed = client._parse_email(123)

        self.assertIsNotNone(parsed)
        self.assertIsNone(parsed.image_url)
        render_image.assert_not_called()

    def test_api_forward_renders_image_before_forwarding(self):
        email = EmailMessage(
            uid=123,
            subject="Cutover mail",
            sender="noc@supplier.example.com",
            recipients=["receiver@example.com"],
            content="割接通知正文",
            html_content="<p>割接通知正文</p>",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(str(Path(tmpdir) / "mail_listener.db"))

            with patch(
                "actions.render_email_body_to_image_url",
                return_value="http://mail-listen.example.com/api/email/images/email-123.png",
            ) as render_image, patch("actions.email_db", db), patch(
                "actions.requests.post", return_value=FakeResponse()
            ) as post:
                result = APIForwardAction().execute(email, {})

        # 确定转发时才渲染，且转发内容携带 image_url
        self.assertTrue(result.success)
        render_image.assert_called_once_with("<p>割接通知正文</p>", "割接通知正文", 123)
        sent_json = post.call_args.kwargs["json"]
        payload = json.loads(sent_json["messages"][0]["content"])
        self.assertEqual(payload["image_url"], "http://mail-listen.example.com/api/email/images/email-123.png")

    def test_out_of_range_email_skips_parse_and_render_by_internaldate(self):
        raw_message = RawEmailMessage()
        raw_message["Subject"] = "Old cutover mail"
        raw_message["From"] = "noc@supplier.example.com"
        raw_message["To"] = "receiver@example.com"
        raw_message["Date"] = "Fri, 26 Jun 2026 10:00:00 +0800"
        raw_message.set_content("old mail body")

        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(str(Path(tmpdir) / "mail_listener.db"))
            old_internal = datetime.now(timezone.utc) - timedelta(hours=5)
            fake_imap = FakeIMAPClient(
                {123: raw_message.as_bytes()}, internal_dates={123: old_internal}
            )

            with patch(
                "actions.render_email_body_to_image_url",
                return_value="http://mail-listen.example.com/x.png",
            ) as render_image, patch("email_client.email_db", db), patch.object(
                email_client.settings, "email_hours_filter", 2
            ):
                client = EmailClient(_test_account())
                client.connected = True
                client.client = fake_imap
                emails = client.get_emails_by_uids([123])

        # INTERNALDATE 超范围：不解析不转图，仅预检一次 INTERNALDATE，未拉取全文
        self.assertEqual(emails, [])
        render_image.assert_not_called()
        self.assertEqual(fake_imap.fetched_fields, [(123, ['INTERNALDATE'])])

    def test_build_content_includes_security_time_from_system_settings(self):
        email = EmailMessage(
            uid=123,
            subject="Cutover mail",
            sender="noc@supplier.example.com",
            recipients=["receiver@example.com"],
            content="割接通知",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(str(Path(tmpdir) / "mail_listener.db"))
            db.set_system_setting("guard_start_time", "2026-07-15 00:00:00")
            db.set_system_setting("guard_end_time", "2026-07-18 23:59:59")

            with patch("actions.email_db", db):
                content = APIForwardAction()._build_content(email, {})

        payload = json.loads(content)
        self.assertEqual(payload["securityTime"], "2026-07-15 00:00:00/2026-07-18 23:59:59")

    def test_build_content_security_time_empty_when_not_configured(self):
        email = EmailMessage(
            uid=123,
            subject="Cutover mail",
            sender="noc@supplier.example.com",
            recipients=["receiver@example.com"],
            content="割接通知",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(str(Path(tmpdir) / "mail_listener.db"))
            db.set_system_setting("guard_start_time", "2026-07-15 00:00:00")

            with patch("actions.email_db", db):
                content = APIForwardAction()._build_content(email, {})

        payload = json.loads(content)
        self.assertEqual(payload["securityTime"], "")

    def test_build_image_url_prefers_fe_domain(self):
        original_fe_domain = html_image.settings.fe_domain
        original_api_public_base_url = html_image.settings.api_public_base_url
        try:
            html_image.settings.fe_domain = "https://fe.example.com/"
            html_image.settings.api_public_base_url = "https://api.example.com"

            image_url = html_image.build_image_url("email-123.png")
        finally:
            html_image.settings.fe_domain = original_fe_domain
            html_image.settings.api_public_base_url = original_api_public_base_url

        self.assertEqual(image_url, "https://fe.example.com/api/email/images/email-123.png")

    def test_processed_uid_skips_parse_and_image_render(self):
        client = EmailClient(_test_account())
        client.connected = True
        client.client = FakeIMAPClient({123: b"not parsed"})

        with patch("email_client.email_db.email_exists", return_value=True), patch(
            "actions.render_email_body_to_image_url",
        ) as render_image:
            emails = client.get_emails_by_uids([123])

        self.assertEqual(emails, [])
        render_image.assert_not_called()


if __name__ == "__main__":
    unittest.main()
