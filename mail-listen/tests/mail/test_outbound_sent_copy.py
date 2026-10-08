from __future__ import annotations

# pyright: reportImplicitRelativeImport=false

import smtplib
import unittest
from datetime import datetime
from email import policy
from email.message import EmailMessage as RawEmailMessage
from email.parser import BytesParser
from types import TracebackType
from unittest.mock import patch

import imapclient
from imapclient.exceptions import IMAPClientError

from email_client import EmailClient
from mail_accounts import MailAccountConfig
from models import EmailMessage


class FakeSmtpClient:
    def __enter__(self) -> FakeSmtpClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def login(self, user: str, password: str) -> tuple[int, bytes]:
        return 235, b"authenticated"

    def send_message(self, message: RawEmailMessage) -> dict[str, tuple[int, bytes]]:
        return {}


class FakeImapClient:
    def __init__(self) -> None:
        self.appended: tuple[str, bytes, list[bytes]] | None = None

    def __enter__(self) -> FakeImapClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def login(self, user: str, password: str) -> bytes:
        return b"authenticated"

    def append(self, folder: str, message: bytes, flags: list[bytes]) -> None:
        self.appended = folder, message, flags


class FailingImapClient(FakeImapClient):
    def append(self, folder: str, message: bytes, flags: list[bytes]) -> None:
        raise IMAPClientError("temporary append failure")


class OutboundSentCopyTests(unittest.TestCase):
    def test_reply_from_21cn_service_is_appended_to_sent_folder(self) -> None:
        # Given
        account = MailAccountConfig(
            id=1,
            name="21CN企业邮箱",
            email_address="sender@chinatelecomglobal.com",
            email_password="secret",
            imap_server="imap-ent.21cn.com",
            smtp_server="smtp-ent.21cn.com",
        )
        original = EmailMessage(
            uid=1,
            subject="割接通知",
            sender="recipient@example.com",
            recipients=[account.email_address],
            content="original",
            received_date=datetime.fromisoformat("2026-09-24T10:00:00+08:00"),
            attachments=[],
        )
        smtp_client = FakeSmtpClient()
        imap_client = FakeImapClient()

        # When
        with (
            patch.object(smtplib, "SMTP_SSL", return_value=smtp_client),
            patch.object(imapclient, "IMAPClient", return_value=imap_client),
        ):
            sent = EmailClient(account).reply_email(original, "已收到")

        # Then
        self.assertTrue(sent)
        appended = imap_client.appended
        assert appended is not None
        folder, payload, flags = appended
        archived = BytesParser(policy=policy.default).parsebytes(payload)
        self.assertEqual(folder, "已发送")
        self.assertEqual(flags, [br"\Seen"])
        self.assertEqual(archived["Subject"], "Re: 割接通知")

    def test_reply_stays_successful_when_21cn_sent_copy_fails(self) -> None:
        # Given
        account = MailAccountConfig(
            id=1,
            name="21CN企业邮箱",
            email_address="sender@chinatelecomglobal.com",
            email_password="secret",
            imap_server="imap-ent.21cn.com",
            smtp_server="smtp-ent.21cn.com",
        )
        original = EmailMessage(
            uid=1,
            subject="割接通知",
            sender="recipient@example.com",
            recipients=[account.email_address],
            content="original",
            received_date=datetime.fromisoformat("2026-09-24T10:00:00+08:00"),
            attachments=[],
        )

        # When
        with (
            patch.object(smtplib, "SMTP_SSL", return_value=FakeSmtpClient()),
            patch.object(
                imapclient,
                "IMAPClient",
                return_value=FailingImapClient(),
            ),
        ):
            sent = EmailClient(account).reply_email(original, "已收到")

        # Then
        self.assertTrue(sent)

    def test_non_21cn_reply_does_not_open_sent_folder_connection(self) -> None:
        # Given
        account = MailAccountConfig(
            id=2,
            name="其他邮箱",
            email_address="sender@example.com",
            email_password="secret",
            imap_server="imap.example.com",
            smtp_server="smtp.example.com",
        )
        original = EmailMessage(
            uid=2,
            subject="普通通知",
            sender="recipient@example.com",
            recipients=[account.email_address],
            content="original",
            received_date=datetime.fromisoformat("2026-09-24T10:00:00+08:00"),
            attachments=[],
        )

        # When
        with (
            patch.object(smtplib, "SMTP_SSL", return_value=FakeSmtpClient()),
            patch.object(imapclient, "IMAPClient") as imap_factory,
        ):
            sent = EmailClient(account).reply_email(original, "已收到")

        # Then
        self.assertTrue(sent)
        imap_factory.assert_not_called()


if __name__ == "__main__":
    _ = unittest.main()
