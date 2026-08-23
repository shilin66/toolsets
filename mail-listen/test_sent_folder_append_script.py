from __future__ import annotations

# pyright: reportImplicitRelativeImport=false

import unittest
from datetime import UTC, datetime
from types import TracebackType
from typing import Final
from unittest.mock import patch

from scripts import test_sent_folder_append

from scripts.sent_folder_append_core import (
    PreparedMessage,
    append_to_sent,
    build_test_message,
    deliver_message,
    has_sent_folder,
)

TEST_MESSAGE: Final = PreparedMessage(
    sender="sender@example.com",
    recipient="receiver@example.com",
    subject="test",
    message_id="<test@example.com>",
    payload=b"Message-ID: <test@example.com>\r\n\r\ntest\r\n",
)


class FakeSmtpSession:
    def __init__(self) -> None:
        self.delivered_payload: bytes | None = None

    def login(self, user: str, password: str) -> tuple[int, bytes]:
        return 235, b"authenticated"

    def sendmail(
        self,
        from_addr: str,
        to_addrs: str,
        msg: bytes,
    ) -> dict[str, tuple[int, bytes]]:
        self.delivered_payload = msg
        return {}


class FakeImapSession:
    def __init__(self) -> None:
        self.appended: tuple[str, bytes, list[bytes]] | None = None

    def append(self, folder: str, msg: bytes, flags: list[bytes]) -> None:
        self.appended = folder, msg, flags


class FakeLiveImapClient(FakeImapSession):
    def __enter__(self) -> FakeLiveImapClient:
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

    def list_folders(self) -> list[tuple[tuple[bytes, ...], str, str]]:
        return [((b"\\Marked",), "/", "已发送")]


class SentFolderAppendScriptTests(unittest.TestCase):
    def test_builds_serialized_message_with_same_message_id(self) -> None:
        # Given
        now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)

        # When
        message = build_test_message("sender@example.com", "receiver@example.com", now)

        # Then
        self.assertIn(message.message_id.encode(), message.payload)

    def test_delivers_the_exact_serialized_payload(self) -> None:
        # Given
        client = FakeSmtpSession()

        # When
        deliver_message(client, "secret", TEST_MESSAGE)

        # Then
        self.assertEqual(client.delivered_payload, TEST_MESSAGE.payload)

    def test_appends_seen_copy_to_sent_folder(self) -> None:
        # Given
        client = FakeImapSession()

        # When
        append_to_sent(client, "已发送", TEST_MESSAGE)

        # Then
        self.assertEqual(
            client.appended,
            ("已发送", TEST_MESSAGE.payload, [br"\Seen"]),
        )

    def test_live_flow_uses_only_archive_imap_connection(self) -> None:
        # Given
        settings = test_sent_folder_append.ConnectionSettings(
            username="sender@example.com",
            recipient="receiver@example.com",
            smtp_server="smtp.example.com",
            smtp_port=465,
            smtp_use_ssl=True,
            smtp_use_tls=False,
            imap_server="imap.example.com",
            imap_port=993,
            imap_use_ssl=True,
        )
        client = FakeLiveImapClient()

        # When
        with (
            patch.object(
                test_sent_folder_append,
                "IMAPClient",
                return_value=client,
            ) as imap_client,
            patch.object(test_sent_folder_append, "send_via_smtp"),
        ):
            test_sent_folder_append.run_live_test(settings, "secret", TEST_MESSAGE)

        # Then
        self.assertEqual(imap_client.call_count, 1)

    def test_accepts_exact_sent_folder_without_matching_archive_folder(self) -> None:
        # Given
        folders = [
            ((b"\\Marked",), "/", "发件归档"),
            ((b"\\Marked",), "/", "已发送"),
        ]

        # When
        found = has_sent_folder(folders)

        # Then
        self.assertTrue(found)


if __name__ == "__main__":
    _ = unittest.main()
