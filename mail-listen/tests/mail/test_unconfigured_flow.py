import json
import os
import tempfile
import unittest
from datetime import datetime

from database import EmailDatabase
from models import EmailMessage
from supplier_config import SupplierConfigRepository
from unconfigured_mail import ANALYSIS, DISCOVERY
from unconfigured_mail_repository import UnconfiguredMailRepository, ResultConflict


class UnconfiguredFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = EmailDatabase(os.path.join(self.tmp.name, 'mail.db'))
        SupplierConfigRepository(self.db)
        self.repo = UnconfiguredMailRepository(self.db)
        self.db.set_system_settings({}, {DISCOVERY: True, ANALYSIS: True})

    def mail(self, uid=1, sender='noc@example.com', receiver='inbox@example.com'):
        email = EmailMessage(uid=uid, sender=sender, recipients=[receiver], subject='维护',
                             content='维护正文', received_date=datetime.now())
        return self.repo.ingest(email, receiver)

    def complete(self, job, result):
        envelope = {key: job[key] for key in ('task_type', 'request_id', 'attempt_id', 'email_records_id')}
        envelope.update(schema_version=1, result=result)
        return self.repo.complete(envelope)

    def classify(self, mail_type='割接通知'):
        job = self.repo.claim()
        self.assertEqual(job['task_type'], 'unconfigured_mail_analyze')
        self.complete(job, {'mail_type': mail_type, 'classification_reason': '最新正文', 'needs_review': False})
        return job

    def test_duplicate_receipt_and_other_then_notice(self):
        first = self.mail()
        self.assertEqual(first, self.mail())
        self.classify('其它')
        self.assertIsNone(self.repo.claim())
        second = self.mail(2)
        self.classify()
        draft = self.repo.claim()
        self.assertEqual(draft['task_type'], 'supplier_config_draft')
        self.complete(draft, {'config': {'name': '供应商', 'email': 'bad@example.com'},
                              'evidence': [], 'unresolved_questions': []})
        time_job = self.repo.claim()
        self.assertEqual(time_job['task_type'], 'cutover_time_extract')
        third = self.mail(3)
        self.classify()
        next_time = self.repo.claim()
        self.assertEqual(next_time['task_type'], 'cutover_time_extract')
        self.assertEqual(next_time['email_records_id'], third)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM supplier_drafts').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT count(*) FROM supplier_draft_samples').fetchone()[0], 2)
            saved = json.loads(conn.execute('SELECT draft_json FROM supplier_drafts').fetchone()[0])
            self.assertEqual(saved['config']['email'], 'noc@example.com')

    def test_new_toggle_does_not_backfill_old_classification(self):
        self.db.set_system_settings({}, {DISCOVERY: False})
        self.mail()
        self.db.set_system_settings({}, {DISCOVERY: True})
        self.classify('其它')
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM supplier_drafts').fetchone()[0], 0)

    def test_closed_policy_keeps_raw_mail_without_jobs_or_skip_fields(self):
        self.db.set_system_settings({}, {DISCOVERY: False, ANALYSIS: False})
        record_id = self.mail()
        self.assertEqual(self.db.get_email_record_by_id(record_id)['processing_origin'], 'unconfigured')
        self.assertEqual(self.repo.projection(record_id)['ai_tasks'], [])
        self.assertIsNone(self.repo.claim())

    def test_cursor_persists_boundary_and_rejects_uidvalidity_change(self):
        self.assertEqual(self.repo.cursor('box', 'INBOX', 1, 100), 100)
        self.assertEqual(self.repo.cursor('box', 'INBOX', 1, 200), 100)
        self.repo.advance_cursor('box', 'INBOX', 1, 103)
        self.assertEqual(self.repo.cursor('box', 'INBOX', 1, 200), 103)
        with self.assertRaises(ResultConflict):
            self.repo.cursor('box', 'INBOX', 2, 200)

    def test_stale_attempt_and_duplicate_result(self):
        self.mail()
        job = self.classify('其它')
        self.complete(job, {'mail_type': '其它', 'classification_reason': 'duplicate', 'needs_review': False})
        job['attempt_id'] = 'stale'
        with self.assertRaises(ValueError):
            self.complete(job, {'mail_type': '其它', 'classification_reason': '', 'needs_review': False})

    def test_unknown_type_rejected_and_retry_only_failed_job(self):
        record_id = self.mail()
        job = self.repo.claim()
        with self.assertRaises(ValueError):
            self.complete(job, {'mail_type': '正文提到割接通知', 'needs_review': False})
        self.repo.fail(job, 'invalid result')
        self.repo.retry(record_id, 'unconfigured_mail_analyze')
        self.assertEqual(self.repo.claim()['attempts'], 1)
        with self.assertRaises(ResultConflict):
            self.repo.retry(record_id, 'cutover_time_extract')

    def test_malformed_draft_cannot_break_review_form(self):
        self.mail()
        self.classify()
        job = self.repo.claim()
        for config in ({'name':None}, {'line_custom_fields':[None]}, {'email_type_samples':{'割接通知':'bad'}}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                self.complete(job, {'config':config, 'evidence':[], 'unresolved_questions':[]})
        self.complete(job, {'config':{}, 'evidence':[], 'unresolved_questions':['待人工补全']})
