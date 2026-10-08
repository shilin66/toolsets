import tempfile
import unittest
from pathlib import Path
import sys
from typing import final

# pyright: reportImplicitRelativeImport=false

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mail_artifacts import (
    SourceEmailArchiveError,
    customer_excel_path,
    email_attachment_directory,
    mailbox_storage_key,
    read_source_email_archive,
    report_artifact_directory,
    save_source_email_archive,
    source_email_archive_path,
)


@final
class SourceEmailArchiveTest(unittest.TestCase):
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.data_dir = Path(self.tmpdir.name)

    def test_saves_original_message_in_deterministic_private_path(self):
        raw_message = b"From: noc@example.com\r\n\r\nsource"

        path = save_source_email_archive(
            self.data_dir,
            mailbox_address="noc@example.com",
            email_uid=2519,
            raw_message=raw_message,
        )

        self.assertEqual(
            path,
            self.data_dir
            / "mail_store"
            / "mailboxes"
            / mailbox_storage_key("noc@example.com")
            / "messages"
            / "2519"
            / "source-email-2519.eml",
        )
        self.assertEqual(path.read_bytes(), raw_message)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_mailbox_directory_key_is_readable_normalized_and_unique(self):
        key = mailbox_storage_key("  NOC@Example.COM  ")

        self.assertRegex(key, r"^mailbox-noc@example\.com-[0-9a-f]{8}$")
        self.assertEqual(key, mailbox_storage_key("noc@example.com"))
        self.assertNotEqual(key, mailbox_storage_key("noc@other.example.com"))

    def test_reads_archived_message(self):
        raw_message = b"Subject: maintenance\r\n\r\nbody"
        _ = save_source_email_archive(
            self.data_dir,
            mailbox_address="noc@example.com",
            email_uid=99,
            raw_message=raw_message,
        )

        self.assertEqual(
            read_source_email_archive(
                self.data_dir,
                mailbox_address="noc@example.com",
                email_uid=99,
            ),
            raw_message,
        )

    def test_rejects_invalid_identifiers_and_empty_message(self):
        for uid in (0, "1"):
            with self.subTest(uid=uid):
                with self.assertRaises(SourceEmailArchiveError):
                    _ = source_email_archive_path(
                        self.data_dir,
                        mailbox_address="noc@example.com",
                        email_uid=uid,
                    )

        with self.assertRaises(SourceEmailArchiveError):
            _ = save_source_email_archive(
                self.data_dir,
                mailbox_address="noc@example.com",
                email_uid=1,
                raw_message=b"",
            )

    def test_same_uid_in_different_mailboxes_uses_different_paths(self):
        first = save_source_email_archive(
            self.data_dir,
            mailbox_address="first@example.com",
            email_uid=2519,
            raw_message=b"first",
        )
        second = save_source_email_archive(
            self.data_dir,
            mailbox_address="second@example.com",
            email_uid=2519,
            raw_message=b"second",
        )

        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), b"first")
        self.assertEqual(second.read_bytes(), b"second")

    def test_all_cutover_artifacts_share_the_message_root(self):
        mailbox = "noc@example.com"
        source = source_email_archive_path(
            self.data_dir,
            mailbox_address=mailbox,
            email_uid=2519,
        )
        attachments = email_attachment_directory(
            self.data_dir,
            mailbox_address=mailbox,
            email_uid=2519,
        )
        excel = customer_excel_path(
            self.data_dir,
            mailbox_address=mailbox,
            email_uid=2519,
            filename="RT00_26012495.xlsx",
        )
        report = report_artifact_directory(
            self.data_dir,
            mailbox_address=mailbox,
            email_uid=2519,
            report_date="2026-09-07",
            email_record_id=135,
            task_id=10,
            report_id=19,
        )

        message_root = source.parent
        self.assertEqual(attachments, message_root / "attachments")
        self.assertEqual(
            excel,
            message_root / "cutover" / "customer" / "RT00_26012495.xlsx",
        )
        self.assertEqual(
            report,
            message_root
            / "cutover"
            / "reports"
            / "2026-09-07"
            / "135"
            / "10_19",
        )


if __name__ == "__main__":
    _ = unittest.main()
