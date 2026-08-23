import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
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


class RecordsQueryApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = EmailDatabase(os.path.join(self.tmpdir.name, "mail_listener.db"))
        self.db_patch = patch.object(api_server, "email_db", self.db)
        self.db_patch.start()
        self.api_key_patch = patch.object(api_server, "API_KEY", "test-key")
        self.api_key_patch.start()
        self.client = api_server.app.test_client()
        self.headers = {"Authorization": "Bearer test-key"}

    def tearDown(self):
        self.api_key_patch.stop()
        self.db_patch.stop()
        self.tmpdir.cleanup()

    def test_email_records_can_be_queried_by_sender(self):
        self.db.add_email_record(
            email_id=101,
            sender="noc@supplier-a.example.com",
            receiver="noc@example.com",
            subject="Supplier A cutover",
            content="cutover body",
            html_content="<p>cutover body</p>",
            attachments=["email_attachments/101/notice.txt"],
        )
        self.db.add_email_record(
            email_id=102,
            sender="noc@supplier-b.example.com",
            receiver="noc@example.com",
            subject="Supplier B cutover",
            content="cutover body",
        )

        response = self.client.get(
            "/api/email-records?sender=supplier-a&pageSize=20",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["email_id"], 101)
        self.assertEqual(data["items"][0]["sender"], "noc@supplier-a.example.com")
        self.assertEqual(data["items"][0]["html_content"], "<p>cutover body</p>")
        self.assertEqual(data["items"][0]["attachments"], ["email_attachments/101/notice.txt"])
        self.assertTrue(data["items"][0]["attachment_urls"][0].endswith(
            "/api/email/attachments/email_attachments/101/notice.txt"
        ))

    def test_email_records_can_be_queried_by_receiver(self):
        """多邮箱场景：按接收邮箱（监听账号）过滤邮件记录。"""
        self.db.add_email_record(
            email_id=401, sender="noc@supplier.example.com",
            receiver="noc@example.com", subject="Mail A", content="body",
        )
        self.db.add_email_record(
            email_id=402, sender="noc@supplier.example.com",
            receiver="backup@example.com", subject="Mail B", content="body",
        )

        response = self.client.get(
            "/api/email-records?receiver=backup@example.com&pageSize=20",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["email_id"], 402)
        self.assertEqual(data["items"][0]["receiver"], "backup@example.com")

    def test_ticket_records_can_be_listed(self):
        self.db.add_email_record(
            email_id=201,
            sender="noc@supplier.example.com",
            receiver="noc@example.com",
            subject="Ticket source",
            content="ticket body",
        )
        email_record = self.db.get_email_record(201)
        ticket_id = self.db.add_ticket_record(
            email_records_id=email_record["id"],
            carrier_ticket_no="CUT-001",
            cut_start_time=datetime(2026, 7, 8, 10, 0, 0),
            cut_end_time=datetime(2026, 7, 8, 12, 0, 0),
            status="created",
            cut_task_id="TASK-001",
        )

        response = self.client.get("/api/tickets?pageSize=20", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["id"], ticket_id)
        self.assertEqual(data["items"][0]["carrier_ticket_no"], "CUT-001")
        self.assertEqual(data["items"][0]["sender"], "noc@supplier.example.com")
        self.assertEqual(data["items"][0]["receiver"], "noc@example.com")

    def test_operations_summary_prioritizes_actionable_work(self):
        today = datetime.now().replace(hour=12, minute=30, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)

        for email_id, received_at in ((301, today), (302, today), (303, yesterday)):
            self.db.add_email_record(
                email_id=email_id,
                sender="noc@supplier.example.com",
                receiver="noc@example.com",
                subject=f"Cutover {email_id}",
                content="cutover body",
            )
            with self.db.get_connection() as connection:
                connection.execute(
                    "UPDATE email_records SET create_time = ? WHERE email_id = ?",
                    (received_at, email_id),
                )
                connection.commit()

        task_statuses = ("draft", "report_failed", "reported")
        for email_id, task_status in zip((301, 302, 303), task_statuses):
            email_record = self.db.get_email_record(email_id)
            if email_record is None:
                self.fail(f"email record {email_id} was not created")
            task_id = self.db.upsert_cutover_task(
                email_records_id=email_record["id"],
                carrier_ticket_no=f"CUT-{email_id}",
                fill_result={"circuits": []},
            )
            if task_id is None:
                self.fail(f"cutover task for email {email_id} was not created")
            self.db.update_cutover_task(task_id, status=task_status)

        response = self.client.get("/api/dashboard/summary", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"], {
            "pending_tasks": 1,
            "failed_tasks": 1,
            "today_emails": 2,
            "last_email_at": today.strftime("%Y-%m-%d %H:%M:%S"),
        })


if __name__ == "__main__":
    unittest.main()
