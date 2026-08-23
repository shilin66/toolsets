import unittest
from collections.abc import Mapping, Sequence
from email.message import EmailMessage as RawEmailMessage
from unittest.mock import patch

from email_client import EmailClient
from mail_accounts import MailAccountConfig


class StatefulIMAPClient:
    def __init__(self, messages: Mapping[int, bytes]) -> None:
        self.messages = messages
        self.unread = set(messages)

    def search(self, _criteria: Sequence[str]) -> list[int]:
        return sorted(self.unread)

    def fetch(
        self,
        uid: int,
        fields: Sequence[str],
    ) -> Mapping[int, Mapping[bytes, bytes]]:
        if "BODY.PEEK[]" in fields:
            return {uid: {b"BODY[]": self.messages[uid]}}
        self.unread.discard(uid)
        return {uid: {b"RFC822": self.messages[uid]}}

    def add_flags(self, uid: int, flags: Sequence[str]) -> None:
        if "\\Seen" in flags:
            self.unread.discard(uid)


class EmailPollingUnreadStateTest(unittest.TestCase):
    def test_polling_keeps_message_unread_when_mark_as_read_is_disabled(self) -> None:
        raw_message = RawEmailMessage()
        raw_message["Subject"] = "Polling unread state"
        raw_message["From"] = "sender@example.com"
        raw_message["To"] = "receiver@example.com"
        raw_message["Date"] = "Fri, 11 Sep 2026 10:00:00 +0800"
        raw_message.set_content("body")
        imap_client = StatefulIMAPClient({7: raw_message.as_bytes()})
        client = EmailClient(
            MailAccountConfig(
                id=1,
                name="测试邮箱",
                email_address="receiver@example.com",
                email_password="password",
                imap_server="imap.example.com",
            )
        )

        with patch.object(client, "client", imap_client), patch.object(
            client,
            "connected",
            True,
        ), patch("email_client.email_db.email_exists", return_value=False), patch(
            "email_client.settings.email_hours_filter",
            0,
        ), patch("email_client.settings.mark_as_read", False):
            messages = client.get_unread_messages()

        self.assertEqual(len(messages), 1)
        self.assertEqual(imap_client.unread, {7})

    def test_polling_does_not_override_manually_unread_existing_message(self) -> None:
        # Given
        raw_message = RawEmailMessage()
        raw_message["Subject"] = "Manual unread state"
        raw_message["From"] = "sender@example.com"
        raw_message["To"] = "receiver@example.com"
        raw_message["Date"] = "Fri, 11 Sep 2026 10:00:00 +0800"
        raw_message.set_content("body")
        imap_client = StatefulIMAPClient({7: raw_message.as_bytes()})
        client = EmailClient(
            MailAccountConfig(
                id=1,
                name="测试邮箱",
                email_address="receiver@example.com",
                email_password="password",
                imap_server="imap.example.com",
            )
        )

        # When
        with patch.object(client, "client", imap_client), patch.object(
            client,
            "connected",
            True,
        ), patch("email_client.email_db.email_exists", return_value=True), patch(
            "email_client.settings.email_hours_filter",
            0,
        ), patch("email_client.settings.mark_as_read", True):
            messages = client.get_unread_messages()

        # Then
        self.assertEqual(messages, [])
        self.assertEqual(imap_client.unread, {7})



if __name__ == "__main__":
    unittest.main()
