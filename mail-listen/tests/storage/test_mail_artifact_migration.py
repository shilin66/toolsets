import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mail_artifact_migration import apply_migration, build_migration_plan
from mail_artifacts import (
    customer_excel_path,
    email_attachment_directory,
    report_artifact_directory,
    source_email_archive_path,
)


class MailArtifactMigrationTest(unittest.TestCase):
    def test_migrates_business_files_and_database_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary)
            data_dir = project_dir / "data"
            data_dir.mkdir()
            database_path = data_dir / "mail_listener.db"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                "CREATE TABLE email_records ("
                "id INTEGER PRIMARY KEY,"
                "email_id INTEGER NOT NULL,"
                "receiver TEXT NOT NULL,"
                "attachments TEXT);"
                "CREATE TABLE cutover_tasks ("
                "id INTEGER PRIMARY KEY,"
                "email_records_id INTEGER NOT NULL,"
                "customer_excel_filename TEXT);"
                "CREATE TABLE cutover_reports ("
                "id INTEGER PRIMARY KEY,"
                "task_id INTEGER NOT NULL,"
                "result TEXT,"
                "create_time TEXT NOT NULL);"
            )
            legacy_attachment = "email_attachments/2519/notice.pdf"
            connection.execute(
                "INSERT INTO email_records VALUES (?, ?, ?, ?)",
                (135, 2519, "noc@example.com", json.dumps([legacy_attachment])),
            )
            connection.execute(
                "INSERT INTO cutover_tasks VALUES (?, ?, ?)",
                (10, 135, "RT00_2519.xlsx"),
            )
            report_result = {
                "screenshot_path": (
                    "data/rpa/artifacts/2026-09-04/135/10_19/report-success.png"
                ),
                "operation_log": [{
                    "step": "excel_selected",
                    "screenshot_filename": (
                        "2026-09-04/135/10_19/report-step.png"
                    ),
                }],
            }
            connection.execute(
                "INSERT INTO cutover_reports VALUES (?, ?, ?, ?)",
                (19, 10, json.dumps(report_result), "2026-09-04 12:00:00"),
            )
            connection.commit()
            connection.close()

            source_files = {
                data_dir / legacy_attachment: b"pdf",
                data_dir / "RT00_2519.xlsx": b"xlsx",
                data_dir
                / "rpa/artifacts/2026-09-04/135/10_19/report-step.png": b"step",
                data_dir
                / "rpa/artifacts/2026-09-04/135/10_19/report-success.png": b"success",
                data_dir / "rpa/backbone-attachments/UID-2519.eml": b"eml",
            }
            for source, content in source_files.items():
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(content)

            plan = build_migration_plan(project_dir)
            self.assertEqual(len(plan.files), 5)
            self.assertEqual(len(plan.updates), 2)

            result = apply_migration(plan, backup_label="test-migration")

            attachment_target = email_attachment_directory(
                data_dir,
                mailbox_address="noc@example.com",
                email_uid=2519,
            ) / "notice.pdf"
            excel_target = customer_excel_path(
                data_dir,
                mailbox_address="noc@example.com",
                email_uid=2519,
                filename="RT00_2519.xlsx",
            )
            report_dir = report_artifact_directory(
                data_dir,
                mailbox_address="noc@example.com",
                email_uid=2519,
                report_date="2026-09-04",
                email_record_id=135,
                task_id=10,
                report_id=19,
            )
            eml_target = source_email_archive_path(
                data_dir,
                mailbox_address="noc@example.com",
                email_uid=2519,
            )
            expected_contents = {
                attachment_target: b"pdf",
                excel_target: b"xlsx",
                report_dir / "report-step.png": b"step",
                report_dir / "report-success.png": b"success",
                eml_target: b"eml",
            }
            for target, content in expected_contents.items():
                self.assertEqual(target.read_bytes(), content)
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)

            migrated = sqlite3.connect(database_path)
            attachments = json.loads(
                migrated.execute(
                    "SELECT attachments FROM email_records WHERE id = 135"
                ).fetchone()[0]
            )
            stored_result = json.loads(
                migrated.execute(
                    "SELECT result FROM cutover_reports WHERE id = 19"
                ).fetchone()[0]
            )
            migrated.close()
            self.assertEqual(
                attachments,
                [attachment_target.relative_to(data_dir).as_posix()],
            )
            self.assertEqual(
                stored_result["operation_log"][0]["screenshot_filename"],
                (report_dir / "report-step.png")
                .relative_to(data_dir)
                .as_posix(),
            )
            self.assertEqual(
                stored_result["screenshot_path"],
                (report_dir / "report-success.png")
                .relative_to(data_dir)
                .as_posix(),
            )
            self.assertTrue(result.manifest_path.is_file())
            self.assertTrue((result.backup_dir / "mail_listener.db").is_file())
            for source in source_files:
                self.assertFalse(source.exists())
                self.assertTrue(
                    (result.backup_dir / "legacy" / source.relative_to(data_dir))
                    .is_file()
                )

            second_plan = build_migration_plan(project_dir)
            self.assertEqual(second_plan.files, ())
            self.assertEqual(second_plan.updates, ())


if __name__ == "__main__":
    unittest.main()
