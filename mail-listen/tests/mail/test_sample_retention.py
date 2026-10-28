import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.mail import test_unconfigured_combined as combined, test_unconfigured_flow as flow
from unconfigured_mail import ANALYSIS
from unconfigured_mail_repository import SAMPLE_MAIL_TYPES


class SampleRetentionTest(unittest.TestCase):
    setUp = flow.UnconfiguredFlowTest.setUp
    mail = flow.UnconfiguredFlowTest.mail
    complete = flow.UnconfiguredFlowTest.complete
    classify = flow.UnconfiguredFlowTest.classify
    response = combined.CombinedMailTest.response
    run_mail = combined.CombinedMailTest.run_mail

    def seed_limit(self, category='割接通知'):
        for uid in range(1, 4):
            self.mail(uid)
            self.run_mail(category)

    def attach(self, record_id, filename='sample.csv'):
        root = Path(self.tmp.name)
        path = root / 'email_attachments' / str(record_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('ID,Order\n0001,002\n')
        with self.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET attachments=?, html_content=? WHERE id=?',
                         (json.dumps([path.relative_to(root).as_posix()]), '<p>原邮件</p>', record_id))
            conn.commit()
        return path

    def test_three_per_category_with_time_and_reply_continuing(self):
        with patch('email_attachments.DATA_DIR', Path(self.tmp.name)):
            for category_index, category in enumerate(SAMPLE_MAIL_TYPES):
                ids = []
                for index in range(5):
                    record_id = self.mail(category_index*10+index+1)
                    ids.append(record_id)
                    path = self.attach(record_id)
                    content = self.run_mail(category)
                    record = self.db.get_email_record_by_id(record_id)
                    self.assertEqual(bool(record['content']), index < 3)
                    self.assertEqual(bool(record['html_content']), index < 3)
                    self.assertEqual(path.exists(), index < 3)
                    if category == '割接通知':
                        self.assertEqual(record['pending_reply_scene'], 'emergency')
                        self.assertTrue(record['pending_reply_content'])
                        self.assertEqual(len(self.repo.projection(record_id)['ai_tasks']), 3 if index == 0 else 2)
                        self.assertEqual(content['should_generate_supplier_draft'], index == 0)
                    else:
                        self.assertEqual(len(self.repo.projection(record_id)['ai_tasks']), 1)
                with self.db.get_connection() as conn:
                    actual = [row[0] for row in conn.execute('''SELECT s.email_records_id FROM supplier_draft_samples s
                        JOIN email_records e ON e.id=s.email_records_id WHERE e.mail_type=? ORDER BY e.id''', (category,))]
                    self.assertEqual(actual, ids[:3])
                    self.assertEqual(conn.execute('SELECT count(*) FROM unconfigured_sample_cleanup').fetchone()[0], 0)
                self.assertEqual(self.mail(category_index*10+5), ids[-1])
            with self.db.get_connection() as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM supplier_draft_samples').fetchone()[0], 12)

    def test_failed_time_branch_keeps_source_until_successful_independent_retry(self):
        self.seed_limit()
        record_id = self.mail(4)
        path = self.attach(record_id)
        job = self.repo.claim(combined=True)
        envelope = self.response({**job, **job['workflow_context'], 'task_type':'unconfigured_mail_process', 'schema_version':1}).json()
        envelope = json.loads(envelope['choices'][0]['message']['content'])
        envelope['result']['time_analysis'] = {'status':'failed', 'error':'retry time'}
        with patch('email_attachments.DATA_DIR', Path(self.tmp.name)):
            self.repo.complete_combined(envelope)
            self.assertTrue(path.exists())
            self.assertTrue(self.db.get_email_record_by_id(record_id)['content'])
            self.assertIsNone(self.repo.projection(record_id)['supplier_draft_id'])
            self.repo.retry(record_id, 'cutover_time_extract')
            retry = self.repo.claim()
            from tests.mail.test_unconfigured_runtime import UnconfiguredRuntimeTest
            self.complete(retry, UnconfiguredRuntimeTest.time_result())
            self.assertFalse(path.exists())
            record = self.db.get_email_record_by_id(record_id)
            self.assertEqual(record['content'], '')
            self.assertTrue(record['pending_reply_content'])

    def test_missing_and_shared_attachments_and_cleanup_retry(self):
        self.seed_limit('割接取消')
        overflow = self.mail(4)
        path = self.attach(overflow)
        with self.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET attachments=(SELECT attachments FROM email_records WHERE id=?) WHERE id=1', (overflow,))
            conn.commit()
        with patch('email_attachments.DATA_DIR', Path(self.tmp.name)):
            self.run_mail('割接取消')
            self.assertTrue(path.exists())
            overflow = self.mail(5)
            path = self.attach(overflow)
            with patch.object(Path, 'unlink', side_effect=PermissionError):
                self.run_mail('割接取消')
            self.assertTrue(self.db.get_email_record_by_id(overflow)['content'])
            path.unlink()
            self.repo.cleanup_excess_samples()
            self.assertEqual(self.db.get_email_record_by_id(overflow)['content'], '')

    def test_no_sample_association_before_classification_and_no_other_sample(self):
        record_id = self.mail()
        job = self.repo.claim(combined=True)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM supplier_draft_samples').fetchone()[0], 0)
        envelope = self.response({**job, **job['workflow_context'], 'task_type':'unconfigured_mail_process', 'schema_version':1}, '其它').json()
        self.repo.complete_combined(json.loads(envelope['choices'][0]['message']['content']))
        self.assertIsNone(self.repo.projection(record_id)['supplier_draft_id'])
        self.assertEqual(self.db.get_email_record_by_id(record_id)['content'], '')

    def test_overflow_without_time_analysis_releases_immediately(self):
        self.seed_limit()
        self.db.set_system_settings({}, {ANALYSIS:False})
        record_id = self.mail(4)
        self.run_mail()
        self.assertEqual(self.db.get_email_record_by_id(record_id)['content'], '')

    def test_concurrent_classifications_cannot_exceed_cap(self):
        from concurrent.futures import ThreadPoolExecutor
        for uid in (1, 2):
            self.mail(uid)
            self.classify('割接取消')
        self.mail(3)
        self.mail(4)
        jobs = [self.repo.claim(), self.repo.claim()]
        result = {'mail_type':'割接取消','classification_reason':'当前正文','needs_review':False}
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda job:self.complete(job, result), jobs))
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM supplier_draft_samples').fetchone()[0], 3)
            self.assertEqual(conn.execute("SELECT count(*) FROM email_records WHERE content='' ").fetchone()[0], 1)
        self.mail(5, sender='another@example.com')
        self.classify('割接取消')
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM supplier_draft_samples').fetchone()[0], 4)

    def test_archive_removed_and_reply_thread_metadata_retained(self):
        from mail_artifacts import source_email_archive_path
        self.seed_limit()
        record_id = self.mail(4)
        archive = source_email_archive_path(Path(self.tmp.name), mailbox_address='inbox@example.com', email_uid=4)
        archive.parent.mkdir(parents=True)
        archive.write_text('raw MIME message')
        with self.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET message_id=?, reply_to=?, "references"=? WHERE id=?',
                         ('<mail@sender>', 'reply@example.com', '<parent@sender>', record_id))
            conn.commit()
        with patch('email_attachments.DATA_DIR', Path(self.tmp.name)):
            self.run_mail()
        self.assertFalse(archive.exists())
        record = self.db.get_email_record_by_id(record_id)
        self.assertEqual(record['message_id'], '<mail@sender>')
        self.assertEqual(record['reply_to'], 'reply@example.com')
        self.assertEqual(record['references'], '<parent@sender>')
        self.assertTrue(record['subject'])

    def test_shared_file_between_two_excess_records_removed_after_both_release(self):
        self.seed_limit('割接取消')
        first = self.mail(4)
        second = self.mail(5)
        path = self.attach(first)
        with self.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET attachments=(SELECT attachments FROM email_records WHERE id=?) WHERE id=?', (first, second))
            conn.commit()
        with patch.object(self.repo, 'cleanup_excess_samples'):
            self.classify('割接取消')
            self.classify('割接取消')
        with patch('email_attachments.DATA_DIR', Path(self.tmp.name)):
            self.repo.cleanup_excess_samples()
        self.assertFalse(path.exists())
