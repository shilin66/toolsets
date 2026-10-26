import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import patch

from actions import APIForwardAction
from database import EmailDatabase
from models import EmailMessage
from supplier_config import SupplierConfigRepository
from unconfigured_mail import ANALYSIS, DISCOVERY
from unconfigured_mail_repository import ResultConflict, UnconfiguredMailRepository


class MailDeletionGuardsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = EmailDatabase(os.path.join(self.tmp.name, 'mail.db'))
        SupplierConfigRepository(self.db)
        self.db.set_system_settings({}, {DISCOVERY: True, ANALYSIS: True})
        self.repo = UnconfiguredMailRepository(self.db)
        self.email = EmailMessage(uid=31, sender='noc@example.com',
            recipients=['inbox@example.com'], subject='维护', content='维护正文',
            received_date=datetime.now())

    def configured_mail(self):
        self.assertTrue(self.db.add_email_record(self.email.uid,
            receiver='inbox@example.com', sender=self.email.sender,
            subject=self.email.subject, content=self.email.content))
        return self.db.get_email_record(self.email.uid, 'inbox@example.com')['id']

    def mark(self, record_id, status='pending_cleanup', remove=False):
        with self.db.get_connection() as conn:
            conn.execute('INSERT INTO mail_deletions (email_records_id, mailbox_address, email_uid, status) '
                         'VALUES (?, ?, ?, ?)', (record_id, 'inbox@example.com', self.email.uid, status))
            if remove:
                conn.execute('DELETE FROM email_records WHERE id=?', (record_id,))
            conn.commit()

    def test_tombstone_blocks_reingest_but_not_another_mailbox(self):
        record_id = self.configured_mail()
        self.mark(record_id, 'deleted', remove=True)
        self.assertTrue(self.db.email_exists(self.email.uid, 'inbox@example.com'))
        self.assertTrue(self.db.is_email_deleted(self.email.uid, 'inbox@example.com'))
        self.assertEqual(self.db.get_mail_deletion(record_id)['status'], 'deleted')
        self.assertFalse(self.db.add_email_record(self.email.uid, receiver='inbox@example.com'))
        self.assertIsNone(self.repo.ingest(self.email, 'inbox@example.com'))
        self.assertTrue(self.db.add_email_record(self.email.uid, receiver='other@example.com'))
        self.assertFalse(self.db.is_email_deleted(self.email.uid, 'other@example.com'))

    def test_tombstone_normalizes_mailbox_identity_for_every_intake_path(self):
        mailbox = 'NOC@Example.com'
        self.assertTrue(self.db.add_email_record(self.email.uid, receiver=mailbox))
        record_id = self.db.get_email_record(self.email.uid, mailbox)['id']
        with self.db.get_connection() as conn:
            conn.execute('INSERT INTO mail_deletions (email_records_id, mailbox_address, email_uid, status) '
                         "VALUES (?, ?, ?, 'deleted')", (record_id, mailbox.casefold(), self.email.uid))
            conn.execute('DELETE FROM email_records WHERE id=?', (record_id,))
            conn.commit()
        for receiver in (mailbox, mailbox.lower(), ' NOC@Example.com '):
            with self.subTest(receiver=receiver):
                self.assertTrue(self.db.email_exists(self.email.uid, receiver))
                self.assertTrue(self.db.is_email_deleted(self.email.uid, receiver))
                self.assertFalse(self.db.add_email_record(self.email.uid, receiver=receiver))
                self.assertIsNone(self.repo.ingest(self.email, receiver))
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM email_records').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM mail_ai_jobs').fetchone()[0], 0)

    def test_pending_cleanup_rejects_children_and_mail_mutations(self):
        record_id = self.configured_mail()
        task_id = self.db.upsert_cutover_task(record_id)
        report_id = self.db.add_cutover_report(task_id)
        self.assertTrue(self.db.save_pending_reply(record_id, '原回复'))
        self.mark(record_id)
        self.assertIsNone(self.db.add_ticket_record(record_id, 'T', datetime.now(), datetime.now()))
        self.assertIsNone(self.db.upsert_cutover_task(record_id, title='迟到任务'))
        self.assertIsNone(self.db.add_cutover_report(task_id))
        self.assertFalse(self.db.update_cutover_task(task_id, status='reporting'))
        self.assertFalse(self.db.update_cutover_report(report_id, status='running'))
        self.assertFalse(self.db.save_pending_reply(record_id, '迟到回复'))
        self.assertFalse(self.db.claim_pending_reply(record_id, '迟到发送'))
        self.assertFalse(self.db.claim_email_api_forward(record_id))
        self.assertFalse(self.db.update_email_api_forward_result(record_id, 'forwarding'))
        self.assertFalse(self.db.update_email_record_extract_result(record_id, '迟到 AI'))
        self.assertFalse(self.db.update_email_record_mail_type(record_id, '割接通知'))
        self.assertFalse(self.db.update_email_record_cutover_scene(record_id, 'emergency'))
        self.assertFalse(self.db.update_email_line_match_payload(record_id, {'late': True}))
        record = self.db.get_email_record_by_id(record_id)
        self.assertEqual(record['pending_reply_content'], '原回复')
        self.assertEqual(record['extract_result'], '')
        self.assertEqual(self.db.get_cutover_task(task_id)['status'], 'draft')
        self.assertIsNone(self.repo.ingest(self.email, 'inbox@example.com'))

    def test_orphan_task_cannot_receive_report(self):
        record_id = self.configured_mail()
        task_id = self.db.upsert_cutover_task(record_id)
        with self.db.get_connection() as conn:
            conn.execute('DELETE FROM email_records WHERE id=?', (record_id,))
            conn.commit()
        self.assertIsNone(self.db.add_cutover_report(task_id))
        self.assertFalse(self.db.update_cutover_task(task_id, status='reporting'))

    def test_claim_skips_pending_and_expired_marked_jobs(self):
        record_id = self.repo.ingest(self.email, 'inbox@example.com')
        self.mark(record_id)
        self.assertIsNone(self.repo.claim())
        with self.db.get_connection() as conn:
            conn.execute("UPDATE mail_ai_jobs SET status='running', lease_until=0, attempts=1")
            conn.commit()
        self.assertIsNone(self.repo.claim())

    def test_late_ai_result_and_retry_rejected_without_writes(self):
        record_id = self.repo.ingest(self.email, 'inbox@example.com')
        job = self.repo.claim()
        envelope = {key: job[key] for key in
            ('task_type', 'request_id', 'attempt_id', 'email_records_id')}
        envelope.update(schema_version=1, result={'mail_type':'割接通知',
            'classification_reason':'正文', 'needs_review':False})
        self.mark(record_id)
        with self.assertRaises(ResultConflict):
            self.repo.complete(envelope)
        self.repo.fail(job, '迟到失败', transient=True)
        with self.db.get_connection() as conn:
            row = conn.execute('SELECT * FROM mail_ai_jobs').fetchone()
            self.assertEqual(row['status'], 'running')
            self.assertIsNone(row['result_json'])
            self.assertEqual(conn.execute('SELECT count(*) FROM supplier_drafts').fetchone()[0], 0)
            conn.execute("UPDATE mail_ai_jobs SET status='failed'")
            conn.commit()
        with self.assertRaises(ResultConflict):
            self.repo.retry(record_id, 'unconfigured_mail_analyze')

    def test_forward_and_reply_claims_are_exclusive(self):
        record_id = self.configured_mail()
        self.assertTrue(self.db.save_pending_reply(record_id, '回复'))
        with ThreadPoolExecutor(2) as pool:
            replies = list(pool.map(lambda _: self.db.claim_pending_reply(record_id, '回复'), range(2)))
            forwards = list(pool.map(lambda _: self.db.claim_email_api_forward(record_id), range(2)))
        self.assertEqual(sum(replies), 1)
        self.assertEqual(sum(forwards), 1)
        self.assertEqual(self.db.get_email_record_by_id(record_id)['reply_status'], 'sending')

    def test_sending_claim_cannot_be_erased_by_reply_callback_or_cancel(self):
        record_id = self.configured_mail()
        self.assertTrue(self.db.save_pending_reply(record_id, '人工确认内容'))
        self.assertTrue(self.db.claim_pending_reply(record_id, '人工确认内容'))
        self.assertFalse(self.db.save_pending_reply(record_id, '迟到草稿'))
        self.assertFalse(self.db.cancel_pending_reply(record_id))
        self.assertEqual(self.db.get_email_record_by_id(record_id)['reply_status'], 'sending')
        self.assertTrue(self.db.release_pending_reply(record_id))
        self.assertTrue(self.db.claim_pending_reply(record_id, '人工确认内容'))
        self.mark(record_id)
        self.assertFalse(self.db.release_pending_reply(record_id))

    def test_children_wait_for_deletion_transaction_and_then_refuse(self):
        record_id = self.configured_mail()
        task_id = self.db.upsert_cutover_task(record_id)
        with self.db.get_connection() as conn, ThreadPoolExecutor(3) as pool:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('INSERT INTO mail_deletions (email_records_id, mailbox_address, email_uid) '
                         'VALUES (?, ?, ?)', (record_id, 'inbox@example.com', self.email.uid))
            futures = [
                pool.submit(self.db.add_ticket_record, record_id, 'T', datetime.now(), datetime.now()),
                pool.submit(self.db.upsert_cutover_task, record_id),
                pool.submit(self.db.add_cutover_report, task_id),
            ]
            conn.commit()
            self.assertEqual([future.result(timeout=5) for future in futures], [None, None, None])
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM ticket_records').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM cutover_reports').fetchone()[0], 0)

    def test_deletion_transaction_wins_before_new_insert(self):
        with self.db.get_connection() as conn, ThreadPoolExecutor(1) as pool:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('INSERT INTO mail_deletions (email_records_id, mailbox_address, email_uid, status) '
                         "VALUES (999, 'inbox@example.com', ?, 'deleted')", (self.email.uid,))
            future = pool.submit(self.db.add_email_record, self.email.uid, receiver='inbox@example.com')
            conn.commit()
            self.assertFalse(future.result(timeout=5))
        self.assertIsNone(self.db.get_email_record(self.email.uid, 'inbox@example.com'))

    def test_api_forward_does_not_render_or_send_marked_mail(self):
        record_id = self.configured_mail()
        self.mark(record_id)
        with patch('actions.requests.post') as post, patch('actions.render_email_body_to_image_url') as render:
            result = APIForwardAction(self.db).execute(self.email, {'_email_records_id': record_id})
        self.assertFalse(result.success)
        post.assert_not_called()
        render.assert_not_called()
        with self.db.get_connection() as conn:
            conn.execute('DELETE FROM email_records WHERE id=?', (record_id,))
            conn.commit()
        with patch('actions.requests.post') as post:
            result = APIForwardAction(self.db).execute(self.email, {})
        self.assertFalse(result.success)
        post.assert_not_called()

    def test_failed_forward_claim_cannot_release_another_running_request(self):
        record_id = self.configured_mail()
        self.assertTrue(self.db.claim_email_api_forward(record_id))
        with patch.object(self.db, 'claim_email_api_forward', side_effect=RuntimeError('claim failed')):
            with patch('actions.requests.post') as post:
                result = APIForwardAction(self.db).execute(self.email, {'_email_records_id': record_id})
        self.assertFalse(result.success)
        post.assert_not_called()
        self.assertEqual(self.db.get_email_record_by_id(record_id)['api_forward_status'], 'forwarding')


if __name__ == '__main__':
    unittest.main()
