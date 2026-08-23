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
import email_attachments


class EmailReplyApiTest(unittest.TestCase):
    def setUp(self):
        self.api_key_patch = patch.object(api_server, "API_KEY", "test-key")
        self.api_key_patch.start()

    def tearDown(self):
        self.api_key_patch.stop()

    def make_record(self, reply_status="", pending_reply_content="", pending_reply_scene=""):
        return {
            "id": 5,
            "email_id": 123,
            "sender": "sender@example.com",
            "receiver": "receiver@example.com",
            "subject": "Original subject",
            "content": "原始内容",
            "html_content": "<p>原始内容</p>",
            "message_id": "<message-1@example.com>",
            "reply_to": "reply@example.com",
            "references": "<root@example.com>",
            "in_reply_to": None,
            "create_time": "2026-06-26 10:00:00",
            "reply_status": reply_status,
            "pending_reply_content": pending_reply_content,
            "pending_reply_scene": pending_reply_scene,
        }

    def test_reply_email_api_registers_pending_instead_of_sending(self):
        """/api/cutover/reply 只登记待确认草稿，不直接发送邮件。"""
        record = self.make_record()

        with patch.object(api_server.email_db, "get_email_record", return_value=record), patch.object(
            api_server.email_db, "save_pending_reply", return_value=True
        ) as save_pending, patch.object(
            api_server.EmailClient, "reply_email", return_value=True
        ) as reply_email:
            response = api_server.app.test_client().post(
                "/api/cutover/reply",
                headers={"Authorization": "Bearer test-key"},
                json={"email_id": 123, "reply_content": "回复一下"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["email_records_id"], 5)
        self.assertEqual(data["data"]["email_id"], 123)
        self.assertEqual(data["data"]["reply_status"], "pending")
        save_pending.assert_called_once_with(5, "回复一下", "")
        reply_email.assert_not_called()

    def test_reply_email_api_missing_params_returns_400(self):
        response = api_server.app.test_client().post(
            "/api/cutover/reply",
            headers={"Authorization": "Bearer test-key"},
            json={},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email_records_id", response.get_json()["message"])

    def test_download_email_attachment_returns_saved_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            attachment_path = data_dir / "email_attachments" / "123" / "notice.txt"
            attachment_path.parent.mkdir(parents=True)
            attachment_path.write_bytes(b"attachment body")

            with patch.object(email_attachments, "DATA_DIR", data_dir), patch.object(
                email_attachments,
                "ATTACHMENT_DIR",
                data_dir / "email_attachments",
            ), patch.object(
                api_server,
                "attachment_path_from_relative",
                email_attachments.attachment_path_from_relative,
            ):
                response = api_server.app.test_client().get(
                    "/api/email/attachments/email_attachments/123/notice.txt"
                )
                response.get_data()
                response.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"attachment body")

    def test_download_email_attachment_rejects_other_data_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            other_file = data_dir / "private.txt"
            other_file.write_bytes(b"secret")

            with patch.object(email_attachments, "DATA_DIR", data_dir), patch.object(
                email_attachments,
                "ATTACHMENT_DIR",
                data_dir / "email_attachments",
            ), patch.object(
                api_server,
                "attachment_path_from_relative",
                email_attachments.attachment_path_from_relative,
            ):
                response = api_server.app.test_client().get(
                    "/api/email/attachments/private.txt"
                )

        self.assertEqual(response.status_code, 404)

    def test_download_email_attachment_rejects_path_traversal(self):
        response = api_server.app.test_client().get(
            "/api/email/attachments/../../etc/passwd"
        )

        self.assertEqual(response.status_code, 404)

    def test_reply_email_api_returns_404_for_missing_record(self):
        with patch.object(api_server.email_db, "get_email_record", return_value=None):
            response = api_server.app.test_client().post(
                "/api/cutover/reply",
                headers={"Authorization": "Bearer test-key"},
                json={"email_id": 999, "reply_content": "回复一下"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.get_json()["success"])

    def test_reply_email_api_stores_scene_with_pending_draft(self):
        """携带场景时随草稿暂存，登记阶段不写入邮件记录。"""
        record = self.make_record()

        with patch.object(api_server.email_db, "get_email_record_by_id", return_value=record), patch.object(
            api_server.email_db, "save_pending_reply", return_value=True
        ) as save_pending, patch.object(
            api_server.email_db, "update_email_record_cutover_scene", return_value=True
        ) as update_scene:
            response = api_server.app.test_client().post(
                "/api/cutover/reply",
                headers={"Authorization": "Bearer test-key"},
                json={"email_records_id": 5, "reply_content": "拒绝割接", "cutover_scene": "emergency"},
            )

        self.assertEqual(response.status_code, 200)
        save_pending.assert_called_once_with(5, "拒绝割接", "emergency")
        update_scene.assert_not_called()
        data = response.get_json()["data"]
        self.assertEqual(data["reply_status"], "pending")
        self.assertEqual(data["cutover_scene"], "emergency")
        self.assertEqual(data["cutover_scene_label"], "紧急割接")

    def test_reply_email_api_rejects_invalid_cutover_scene(self):
        response = api_server.app.test_client().post(
            "/api/cutover/reply",
            headers={"Authorization": "Bearer test-key"},
            json={"email_id": 123, "reply_content": "拒绝割接", "cutover_scene": "bogus"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("cutover_scene", response.get_json()["message"])

    def test_legacy_reply_path_still_registers_pending(self):
        """旧路径 /api/email/reply 与旧参数 email_id 作为兼容别名仍可用。"""
        record = self.make_record()

        with patch.object(api_server.email_db, "get_email_record", return_value=record), patch.object(
            api_server.email_db, "save_pending_reply", return_value=True
        ) as save_pending, patch.object(
            api_server.email_db, "update_email_record_cutover_scene", return_value=True
        ) as update_scene:
            response = api_server.app.test_client().post(
                "/api/email/reply",
                headers={"Authorization": "Bearer test-key"},
                json={"email_id": 123, "reply_content": "拒绝割接", "cutover_scene": "in_window"},
            )

        self.assertEqual(response.status_code, 200)
        save_pending.assert_called_once_with(5, "拒绝割接", "in_window")
        update_scene.assert_not_called()

    def test_reply_email_api_without_scene_defaults_normal(self):
        record = self.make_record()

        with patch.object(api_server.email_db, "get_email_record", return_value=record), patch.object(
            api_server.email_db, "save_pending_reply", return_value=True
        ) as save_pending:
            response = api_server.app.test_client().post(
                "/api/cutover/reply",
                headers={"Authorization": "Bearer test-key"},
                json={"email_id": 123, "reply_content": "回复一下"},
            )

        self.assertEqual(response.status_code, 200)
        save_pending.assert_called_once_with(5, "回复一下", "")
        self.assertEqual(response.get_json()["data"]["cutover_scene"], "normal")

    def test_confirm_reply_sends_and_writes_scene(self):
        """人工确认后发送草稿，成功后写入割接场景与发送状态。"""
        record = self.make_record(
            reply_status="pending",
            pending_reply_content="拒绝割接",
            pending_reply_scene="emergency",
        )

        with patch.object(api_server.email_db, "get_email_record_by_id", return_value=record), patch.object(
            api_server, "build_reply_email_client"
        ) as build_client, patch.object(
            api_server.email_db, "mark_reply_sent", return_value=True
        ) as mark_sent, patch.object(
            api_server.email_db, "update_email_record_cutover_scene", return_value=True
        ) as update_scene:
            build_client.return_value.reply_email.return_value = True
            response = api_server.app.test_client().post(
                "/api/cutover/reply/confirm",
                headers={"Authorization": "Bearer test-key"},
                json={"email_records_id": 5},
            )

        self.assertEqual(response.status_code, 200)
        sent_email = build_client.return_value.reply_email.call_args.args[0]
        self.assertEqual(sent_email.uid, 123)
        self.assertEqual(build_client.return_value.reply_email.call_args.args[1], "拒绝割接")
        self.assertEqual(build_client.return_value.reply_email.call_args.kwargs["html_content"], "<p>原始内容</p>")
        self.assertEqual(mark_sent.call_args.args[0], 5)
        update_scene.assert_called_once_with(5, "emergency")
        data = response.get_json()["data"]
        self.assertEqual(data["cutover_scene"], "emergency")
        self.assertEqual(data["recipient"], "reply@example.com")

    def test_confirm_reply_uses_override_content(self):
        record = self.make_record(reply_status="pending", pending_reply_content="草稿内容")

        with patch.object(api_server.email_db, "get_email_record_by_id", return_value=record), patch.object(
            api_server, "build_reply_email_client"
        ) as build_client, patch.object(
            api_server.email_db, "mark_reply_sent", return_value=True
        ), patch.object(
            api_server.email_db, "update_email_record_cutover_scene", return_value=True
        ) as update_scene:
            build_client.return_value.reply_email.return_value = True
            response = api_server.app.test_client().post(
                "/api/cutover/reply/confirm",
                headers={"Authorization": "Bearer test-key"},
                json={"email_records_id": 5, "reply_content": "人工修改后的内容"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(build_client.return_value.reply_email.call_args.args[1], "人工修改后的内容")
        update_scene.assert_not_called()

    def test_confirm_reply_overrides_recipients(self):
        """传入 recipients 时覆盖默认收件人，支持多个地址并随响应返回。"""
        record = self.make_record(reply_status="pending", pending_reply_content="拒绝割接")

        with patch.object(api_server.email_db, "get_email_record_by_id", return_value=record), patch.object(
            api_server, "build_reply_email_client"
        ) as build_client, patch.object(
            api_server.email_db, "mark_reply_sent", return_value=True
        ):
            build_client.return_value.reply_email.return_value = True
            response = api_server.app.test_client().post(
                "/api/cutover/reply/confirm",
                headers={"Authorization": "Bearer test-key"},
                json={
                    "email_records_id": 5,
                    "recipients": ["a@example.com", "b@example.com"],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            build_client.return_value.reply_email.call_args.kwargs["recipients"],
            ["a@example.com", "b@example.com"],
        )
        data = response.get_json()["data"]
        self.assertEqual(data["recipients"], ["a@example.com", "b@example.com"])
        self.assertEqual(data["recipient"], "a@example.com, b@example.com")

    def test_confirm_reply_accepts_recipients_string(self):
        record = self.make_record(reply_status="pending", pending_reply_content="拒绝割接")

        with patch.object(api_server.email_db, "get_email_record_by_id", return_value=record), patch.object(
            api_server, "build_reply_email_client"
        ) as build_client, patch.object(
            api_server.email_db, "mark_reply_sent", return_value=True
        ):
            build_client.return_value.reply_email.return_value = True
            response = api_server.app.test_client().post(
                "/api/cutover/reply/confirm",
                headers={"Authorization": "Bearer test-key"},
                json={"email_records_id": 5, "recipients": "a@example.com, b@example.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            build_client.return_value.reply_email.call_args.kwargs["recipients"],
            ["a@example.com", "b@example.com"],
        )

    def test_confirm_reply_rejects_invalid_recipient(self):
        record = self.make_record(reply_status="pending", pending_reply_content="拒绝割接")

        with patch.object(api_server.email_db, "get_email_record_by_id", return_value=record), patch.object(
            api_server.EmailClient, "reply_email", return_value=True
        ) as reply_email:
            response = api_server.app.test_client().post(
                "/api/cutover/reply/confirm",
                headers={"Authorization": "Bearer test-key"},
                json={"email_records_id": 5, "recipients": ["not-an-email"]},
            )

        self.assertEqual(response.status_code, 400)
        reply_email.assert_not_called()

    def test_confirm_reply_rejects_when_no_pending(self):
        record = self.make_record(reply_status="sent")

        with patch.object(api_server.email_db, "get_email_record_by_id", return_value=record), patch.object(
            api_server.EmailClient, "reply_email", return_value=True
        ) as reply_email:
            response = api_server.app.test_client().post(
                "/api/cutover/reply/confirm",
                headers={"Authorization": "Bearer test-key"},
                json={"email_records_id": 5},
            )

        self.assertEqual(response.status_code, 400)
        reply_email.assert_not_called()

    def test_confirm_reply_keeps_pending_when_send_fails(self):
        record = self.make_record(reply_status="pending", pending_reply_content="拒绝割接")

        with patch.object(api_server.email_db, "get_email_record_by_id", return_value=record), patch.object(
            api_server, "build_reply_email_client"
        ) as build_client, patch.object(
            api_server.email_db, "mark_reply_sent", return_value=True
        ) as mark_sent:
            build_client.return_value.reply_email.return_value = False
            response = api_server.app.test_client().post(
                "/api/cutover/reply/confirm",
                headers={"Authorization": "Bearer test-key"},
                json={"email_records_id": 5},
            )

        self.assertEqual(response.status_code, 500)
        mark_sent.assert_not_called()

    def test_cancel_reply_clears_pending(self):
        record = self.make_record(reply_status="pending", pending_reply_content="拒绝割接")

        with patch.object(api_server.email_db, "get_email_record_by_id", return_value=record), patch.object(
            api_server.email_db, "cancel_pending_reply", return_value=True
        ) as cancel_pending:
            response = api_server.app.test_client().post(
                "/api/cutover/reply/cancel",
                headers={"Authorization": "Bearer test-key"},
                json={"email_records_id": 5},
            )

        self.assertEqual(response.status_code, 200)
        cancel_pending.assert_called_once_with(5)

    def test_cancel_reply_rejects_when_no_pending(self):
        record = self.make_record()

        with patch.object(api_server.email_db, "get_email_record_by_id", return_value=record):
            response = api_server.app.test_client().post(
                "/api/cutover/reply/cancel",
                headers={"Authorization": "Bearer test-key"},
                json={"email_records_id": 5},
            )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
