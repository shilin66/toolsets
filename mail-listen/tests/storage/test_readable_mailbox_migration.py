import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

# pyright: reportImplicitRelativeImport=false

from mail_artifact_migration import apply_migration, build_migration_plan
from mail_artifacts import (
    customer_excel_path,
    email_attachment_directory,
    report_artifact_directory,
    source_email_archive_path,
)


class ReadableMailboxMigrationTest(unittest.TestCase):
    def test_migrates_digest_only_mailbox_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            data_dir = project_dir / "data"
            data_dir.mkdir()
            database_path = data_dir / "mail_listener.db"
            mailbox = "noc@example.com"
            email_uid = 2519
            old_key = "mailbox-" + hashlib.sha256(
                mailbox.encode("utf-8")
            ).hexdigest()[:24]
            old_message_dir = (
                data_dir
                / "mail_store/mailboxes"
                / old_key
                / "messages"
                / str(email_uid)
            )
            old_attachment = old_message_dir / "attachments/notice.pdf"
            old_excel = old_message_dir / "cutover/customer/RT00_2519.xlsx"
            old_report_dir = (
                old_message_dir / "cutover/reports/2026-09-04/135/10_19"
            )
            old_step = old_report_dir / "report-step.png"
            old_success = old_report_dir / "report-success.png"
            old_eml = old_message_dir / "source-email-2519.eml"
            source_files = {
                old_attachment: b"pdf",
                old_excel: b"xlsx",
                old_step: b"step",
                old_success: b"success",
                old_eml: b"eml",
            }
            for source, content in source_files.items():
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(content)

            connection = sqlite3.connect(database_path)
            connection.executescript(
                "CREATE TABLE email_records ("
                "id INTEGER PRIMARY KEY, email_id INTEGER NOT NULL, "
                "receiver TEXT NOT NULL, attachments TEXT);"
                "CREATE TABLE cutover_tasks ("
                "id INTEGER PRIMARY KEY, email_records_id INTEGER NOT NULL, "
                "customer_excel_filename TEXT);"
                "CREATE TABLE cutover_reports ("
                "id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, "
                "result TEXT, create_time TEXT NOT NULL);"
            )
            old_attachment_ref = old_attachment.relative_to(data_dir).as_posix()
            connection.execute(
                "INSERT INTO email_records VALUES (?, ?, ?, ?)",
                (135, email_uid, mailbox, json.dumps([old_attachment_ref])),
            )
            connection.execute(
                "INSERT INTO cutover_tasks VALUES (?, ?, ?)",
                (10, 135, old_excel.name),
            )
            result = {
                "screenshot_path": old_success.relative_to(data_dir).as_posix(),
                "error": (
                    "失败截图："
                    + old_success.relative_to(data_dir).as_posix()
                ),
                "operation_log": [{
                    "step": "submitted",
                    "screenshot_filename": old_step.relative_to(data_dir).as_posix(),
                }],
            }
            connection.execute(
                "INSERT INTO cutover_reports VALUES (?, ?, ?, ?)",
                (19, 10, json.dumps(result), "2026-09-04 12:00:00"),
            )
            connection.commit()
            connection.close()

            plan = build_migration_plan(project_dir)

            self.assertEqual(len(plan.files), 5)
            self.assertEqual(len(plan.updates), 2)

            migration = apply_migration(plan, backup_label="readable-mailbox")
            attachment_target = email_attachment_directory(
                data_dir,
                mailbox_address=mailbox,
                email_uid=email_uid,
            ) / old_attachment.name
            excel_target = customer_excel_path(
                data_dir,
                mailbox_address=mailbox,
                email_uid=email_uid,
                filename=old_excel.name,
            )
            report_target = report_artifact_directory(
                data_dir,
                mailbox_address=mailbox,
                email_uid=email_uid,
                report_date="2026-09-04",
                email_record_id=135,
                task_id=10,
                report_id=19,
            )
            eml_target = source_email_archive_path(
                data_dir,
                mailbox_address=mailbox,
                email_uid=email_uid,
            )
            expected = {
                attachment_target: b"pdf",
                excel_target: b"xlsx",
                report_target / old_step.name: b"step",
                report_target / old_success.name: b"success",
                eml_target: b"eml",
            }
            for target, content in expected.items():
                self.assertEqual(target.read_bytes(), content)
            self.assertTrue(migration.manifest_path.is_file())

            migrated = sqlite3.connect(database_path)
            attachment_ref = json.loads(
                migrated.execute(
                    "SELECT attachments FROM email_records WHERE id=135"
                ).fetchone()[0]
            )[0]
            stored_result = json.loads(
                migrated.execute(
                    "SELECT result FROM cutover_reports WHERE id=19"
                ).fetchone()[0]
            )
            migrated.close()
            self.assertEqual(
                attachment_ref,
                attachment_target.relative_to(data_dir).as_posix(),
            )
            self.assertEqual(
                stored_result["screenshot_path"],
                (report_target / old_success.name).relative_to(data_dir).as_posix(),
            )
            self.assertIn(
                (report_target / old_success.name).relative_to(data_dir).as_posix(),
                stored_result["error"],
            )
            self.assertEqual(build_migration_plan(project_dir).files, ())


if __name__ == "__main__":
    unittest.main()
