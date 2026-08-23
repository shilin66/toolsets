import unittest
import tempfile
from email import policy
from email.parser import BytesParser
from email.message import EmailMessage as RawEmailMessage
from pathlib import Path
from unittest.mock import patch

import email_attachments
from email_attachments import save_attachment
from email_client import EmailClient, build_reply_message
from mail_artifacts import mailbox_storage_key
from mail_accounts import MailAccountConfig
from models import EmailMessage


def _test_account():
    return MailAccountConfig(
        id=1,
        name="测试邮箱",
        email_address="receiver@example.com",
        email_password="password",
        imap_server="imap.example.com",
    )


class FakeIMAPClient:
    def __init__(self, messages):
        self.messages = messages
        self.added_flags = []
        self.removed_flags = []

    def fetch(self, uid, fields):
        return {uid: {(b"BODY[]" if "BODY.PEEK[]" in fields else b"RFC822"): self.messages[uid]}}

    def add_flags(self, uid, flags):
        self.added_flags.append((uid, flags))

    def remove_flags(self, uid, flags):
        self.removed_flags.append((uid, flags))


class EmailClientParsingTest(unittest.TestCase):
    def test_set_read_state_updates_seen_flag(self):
        # Given
        client = EmailClient(_test_account())
        imap_client = FakeIMAPClient({})
        client.client = imap_client
        client.connected = True

        # When
        marked_read = client.set_read_state(7, True)
        marked_unread = client.set_read_state(7, False)

        # Then
        self.assertTrue(marked_read)
        self.assertTrue(marked_unread)
        self.assertEqual(imap_client.added_flags, [(7, ["\\Seen"])])
        self.assertEqual(imap_client.removed_flags, [(7, ["\\Seen"])])

    def test_fetch_raw_message_returns_original_rfc822_bytes(self):
        raw_message = b"From: sender@example.com\r\nSubject: source\r\n\r\nbody"
        client = EmailClient(_test_account())
        client.client = FakeIMAPClient({2519: raw_message})
        client.connected = True

        self.assertEqual(client.fetch_raw_message(2519), raw_message)

    def test_parse_email_keeps_only_sender_email_address(self):
        raw_message = RawEmailMessage()
        raw_message["Subject"] = "Sender parsing"
        raw_message["From"] = '"Example Sender" <sender@example.com>'
        raw_message["To"] = "receiver@example.com"
        raw_message["Date"] = "Fri, 26 Jun 2026 10:00:00 +0800"
        raw_message.set_content("hello")

        client = EmailClient(_test_account())
        client.client = FakeIMAPClient({1: raw_message.as_bytes()})

        parsed = client._parse_email(1)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.sender, "sender@example.com")

    def test_parse_email_extracts_reply_headers(self):
        raw_message = RawEmailMessage()
        raw_message["Subject"] = "Reply headers"
        raw_message["From"] = '"Example Sender" <sender@example.com>'
        raw_message["Reply-To"] = '"Support Team" <support@example.com>'
        raw_message["To"] = "receiver@example.com"
        raw_message["Message-ID"] = "<message-1@example.com>"
        raw_message["References"] = "<root@example.com> <parent@example.com>"
        raw_message["In-Reply-To"] = "<parent@example.com>"
        raw_message["Date"] = "Fri, 26 Jun 2026 10:00:00 +0800"
        raw_message.set_content("hello")

        client = EmailClient(_test_account())
        client.client = FakeIMAPClient({1: raw_message.as_bytes()})

        parsed = client._parse_email(1)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.reply_to, "support@example.com")
        self.assertEqual(parsed.message_id, "<message-1@example.com>")
        self.assertEqual(parsed.references, "<root@example.com> <parent@example.com>")
        self.assertEqual(parsed.in_reply_to, "<parent@example.com>")

    def test_parse_email_saves_multiple_attachments_as_relative_paths(self):
        raw_message = RawEmailMessage()
        raw_message["Subject"] = "Attachments"
        raw_message["From"] = "sender@example.com"
        raw_message["To"] = "receiver@example.com"
        raw_message["Date"] = "Fri, 26 Jun 2026 10:00:00 +0800"
        raw_message.set_content("plain body")
        raw_message.add_attachment(
            b"first file",
            maintype="application",
            subtype="octet-stream",
            filename="notice.txt",
        )
        raw_message.add_attachment(
            b"second file",
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="../unsafe.xlsx",
        )

        client = EmailClient(_test_account())
        client.client = FakeIMAPClient({9: raw_message.as_bytes()})

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with patch.object(email_attachments, "DATA_DIR", data_dir), patch.object(
                email_attachments,
                "ATTACHMENT_DIR",
                data_dir / "email_attachments",
            ):
                parsed = client._parse_email(9)

            self.assertIsNotNone(parsed)
            self.assertEqual(len(parsed.attachments), 2)
            expected_prefix = (
                "mail_store/mailboxes/"
                f"{mailbox_storage_key('receiver@example.com')}/messages/9/attachments/"
            )
            self.assertTrue(parsed.attachments[0].startswith(expected_prefix))
            self.assertTrue(parsed.attachments[0].endswith("-notice.txt"))
            self.assertTrue(parsed.attachments[1].endswith("-unsafe.xlsx"))
            for relative_path in parsed.attachments:
                self.assertTrue((data_dir / relative_path).exists())

    def test_same_uid_in_different_mailboxes_keeps_attachments_separate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with patch.object(email_attachments, "DATA_DIR", data_dir):
                first = save_attachment(
                    "first@example.com",
                    2519,
                    "notice.txt",
                    b"first",
                )
                second = save_attachment(
                    "second@example.com",
                    2519,
                    "notice.txt",
                    b"second",
                )

            self.assertNotEqual(first, second)
            self.assertIn(mailbox_storage_key("first@example.com"), first)
            self.assertIn(mailbox_storage_key("second@example.com"), second)
            self.assertEqual((data_dir / first).read_bytes(), b"first")
            self.assertEqual((data_dir / second).read_bytes(), b"second")

    def test_build_reply_message_uses_reply_to_and_thread_headers(self):
        original = EmailMessage(
            uid=1,
            subject="Original subject",
            sender="sender@example.com",
            recipients=["receiver@example.com"],
            content="hello",
            message_id="<message-1@example.com>",
            reply_to="support@example.com",
            references="<root@example.com>",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )

        reply = build_reply_message(
            original,
            reply_content="收到",
            from_address="receiver@example.com",
        )

        self.assertEqual(reply["From"], "receiver@example.com")
        self.assertEqual(reply["To"], "support@example.com")
        self.assertEqual(reply["Subject"], "Re: Original subject")
        self.assertEqual(reply["In-Reply-To"], "<message-1@example.com>")
        self.assertEqual(reply["References"], "<root@example.com> <message-1@example.com>")
        self.assertIn("收到", reply.get_content())

    def test_build_reply_message_falls_back_to_sender(self):
        original = EmailMessage(
            uid=1,
            subject="Re: Existing subject",
            sender="sender@example.com",
            recipients=["receiver@example.com"],
            content="hello",
            message_id="<message-1@example.com>",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )

        reply = build_reply_message(
            original,
            reply_content="收到",
            from_address="receiver@example.com",
        )

        self.assertEqual(reply["To"], "sender@example.com")
        self.assertEqual(reply["Subject"], "Re: Existing subject")
        self.assertEqual(reply["References"], "<message-1@example.com>")

    def test_build_reply_message_overrides_recipients(self):
        """传入 recipients 时覆盖默认回复地址，支持多个收件人。"""
        original = EmailMessage(
            uid=1,
            subject="Original subject",
            sender="sender@example.com",
            recipients=["receiver@example.com"],
            content="hello",
            reply_to="support@example.com",
            message_id="<message-1@example.com>",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )

        reply = build_reply_message(
            original,
            reply_content="收到",
            from_address="receiver@example.com",
            recipients=["a@example.com", "b@example.com"],
        )

        self.assertEqual(reply["To"], "a@example.com, b@example.com")

    def test_build_reply_message_adds_configured_cc_recipients(self):
        # Given
        original = EmailMessage(
            uid=1,
            subject="Original subject",
            sender="sender@example.com",
            recipients=["receiver@example.com"],
            content="hello",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )

        # When
        reply = build_reply_message(
            original,
            reply_content="收到",
            from_address="receiver@example.com",
            recipients=["reply@supplier.example.com"],
            cc_recipients=["receiver@example.com"],
        )

        # Then
        self.assertEqual(reply["To"], "reply@supplier.example.com")
        self.assertEqual(reply["Cc"], "receiver@example.com")

    def test_build_reply_message_unfolds_thread_headers(self):
        original = EmailMessage(
            uid=1,
            subject="Original subject",
            sender="sender@example.com",
            recipients=["receiver@example.com"],
            content="hello",
            message_id="<message-1@example.com>\r\n",
            references="<root@example.com>\r\n <parent@example.com>",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )

        reply = build_reply_message(
            original,
            reply_content="收到",
            from_address="receiver@example.com",
        )

        self.assertEqual(reply["In-Reply-To"], "<message-1@example.com>")
        self.assertEqual(
            reply["References"],
            "<root@example.com> <parent@example.com> <message-1@example.com>",
        )

    def test_build_reply_message_html_part_contains_reply_and_quote(self):
        original = EmailMessage(
            uid=1,
            subject="Original subject",
            sender="sender@example.com",
            recipients=["receiver@example.com"],
            content="hello",
            message_id="<message-1@example.com>",
            received_date="2026-06-26T10:00:00+08:00",
            attachments=[],
        )

        reply = build_reply_message(
            original,
            reply_content="回复一下",
            from_address="receiver@example.com",
            html_content="<html><body><p>原始HTML内容</p></body></html>",
        )
        parsed = BytesParser(policy=policy.default).parsebytes(reply.as_bytes())
        html_body = parsed.get_body(preferencelist=("html",))
        plain_body = parsed.get_body(preferencelist=("plain",))

        self.assertIsNotNone(html_body)
        self.assertIsNotNone(plain_body)
        self.assertIn("回复一下", html_body.get_content())
        self.assertIn("原始HTML内容", html_body.get_content())
        self.assertIn("回复一下", plain_body.get_content())


if __name__ == "__main__":
    unittest.main()
