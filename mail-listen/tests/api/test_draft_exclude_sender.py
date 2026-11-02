import json
from pathlib import Path
from unittest.mock import patch
import api_server
import unittest
from concurrent.futures import ThreadPoolExecutor

from tests.api import test_supplier_drafts_api as fixture, test_user_access_api as access
from supplier_drafts import SupplierDraftRepository
from unconfigured_mail import read_settings, accepts_sender, DISCOVERY, ANALYSIS
from unconfigured_mail_repository import ResultConflict


class DraftExcludeSenderTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.SupplierDraftApiTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db = self.fixture.db
        self.repo = self.fixture.repo
        self.client = self.fixture.client
        self.headers = self.fixture.headers
        self.root = Path(self.fixture.tmp.name)
        for target in ('api_server.DATA_DIR', 'email_attachments.DATA_DIR'):
            replacement = patch(target, self.root)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.draft_id = self.fixture.make_draft()

    def exclude(self, revision=None):
        draft = SupplierDraftRepository(self.db).get(self.draft_id)
        return self.client.post(f'/api/supplier-drafts/{self.draft_id}/exclude-sender', headers=self.headers,
                                json={'revision':draft['revision'] if revision is None else revision})

    def test_excludes_and_deletes_historical_mail_and_results(self):
        self.db.set_system_settings({'unrelated_setting':'keep'}, {'unconfigured_sender_filter_list':['inactive@example.com']})
        self.fixture.mail(2)
        other = self.fixture.mail(3, sender='other@example.com')
        attachment = self.root / 'email_attachments' / '1' / 'sample.txt'
        attachment.parent.mkdir(parents=True)
        attachment.write_text('old attachment')
        with self.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET attachments=?,unconfigured_analysis_json=?,reply_history=? WHERE id=1',
                (json.dumps(['email_attachments/1/sample.txt']), json.dumps({'old':'analysis'}), json.dumps([{'content':'old reply'}])))
            conn.commit()
        response = self.exclude()
        self.assertEqual(response.status_code, 200, response.get_json())
        policy = read_settings(self.db)
        self.assertEqual(policy['unconfigured_sender_filter_mode'], 'blocklist')
        self.assertEqual(policy['unconfigured_sender_filter_list'], ['noc@example.com'])
        self.assertTrue(policy[DISCOVERY] and policy[ANALYSIS])
        self.assertEqual(self.db.get_system_settings()['unrelated_setting'], 'keep')
        self.assertIsNone(self.db.get_email_record_by_id(1))
        self.assertIsNone(self.db.get_email_record_by_id(2))
        self.assertIsNotNone(self.db.get_email_record_by_id(other))
        self.assertFalse(attachment.exists())
        self.assertEqual(SupplierDraftRepository(self.db).list()['total'], 0)
        future = self.fixture.mail(4)
        self.assertEqual(self.repo.projection(future)['ai_tasks'], [])
        self.assertIsNone(self.fixture.mail(1))
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM supplier_draft_samples').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM mail_ai_jobs WHERE email_records_id IN (1,2)').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM excluded_sender_mail_cleanup').fetchone()[0], 0)

    def test_existing_exclusions_preserved_and_addresses_deduplicated(self):
        self.db.set_system_settings({}, {'unconfigured_sender_filter_mode':'blocklist',
            'unconfigured_sender_filter_list':['*@other.example.com','NOC@EXAMPLE.COM']})
        self.assertEqual(self.exclude().status_code, 200)
        self.assertEqual(read_settings(self.db)['unconfigured_sender_filter_list'], ['*@other.example.com','noc@example.com'])
        self.assertFalse(accepts_sender(read_settings(self.db), 'NOC <NOC@example.com>'))
        self.assertTrue(accepts_sender(read_settings(self.db), 'another@example.com'))

    def test_allowlist_and_stale_revision_do_not_change_settings_or_draft(self):
        self.assertEqual(self.exclude(revision=999).status_code, 409)
        self.db.set_system_settings({}, {'unconfigured_sender_filter_mode':'allowlist',
                                        'unconfigured_sender_filter_list':['*@example.com']})
        before = self.db.get_system_settings()
        self.assertEqual(self.exclude().status_code, 409)
        self.assertEqual(self.db.get_system_settings(), before)
        self.assertEqual(SupplierDraftRepository(self.db).get(self.draft_id)['status'], 'review')

    def test_published_draft_cannot_exclude_formal_supplier(self):
        repository = SupplierDraftRepository(self.db)
        draft = repository.get(self.draft_id)
        draft = repository.edit(self.draft_id, draft['revision'], {**draft['draft']['config'], 'name':'Supplier'})
        repository.publish(self.draft_id, draft['revision'])
        self.assertEqual(self.exclude().status_code, 409)
        self.assertEqual(read_settings(self.db)['unconfigured_sender_filter_mode'], 'all')
        self.assertEqual(repository.get(self.draft_id)['status'], 'published')

    def test_running_time_result_is_rejected_after_exclusion(self):
        job = self.repo.claim()
        self.assertEqual(job['task_type'], 'cutover_time_extract')
        self.assertEqual(self.exclude().status_code, 200)
        from tests.mail.test_unconfigured_runtime import UnconfiguredRuntimeTest
        with self.assertRaises(ResultConflict):
            self.fixture.complete(job, UnconfiguredRuntimeTest.time_result())
        self.assertIsNone(self.db.get_email_record_by_id(job['email_records_id']))

    def test_running_combined_result_cannot_recreate_excluded_draft(self):
        self.db.set_system_settings({}, {ANALYSIS:False})
        # Drain old time job under the changed policy, then claim another mail from the same sender.
        self.assertIsNone(self.repo.claim())
        self.fixture.mail(2)
        job = self.repo.claim(combined=True)
        self.assertEqual(self.exclude().status_code, 200)
        envelope = {key:job[key] for key in ('request_id','attempt_id','email_records_id')}
        envelope.update(schema_version=1, task_type='unconfigured_mail_process', result={'classification':{
            'status':'succeeded','result':{'mail_type':'割接通知','classification_reason':'当前通知','needs_review':False}}})
        with self.assertRaises(ResultConflict):
            self.repo.complete_combined(envelope)
        self.assertEqual(SupplierDraftRepository(self.db).list()['total'], 0)

    def test_concurrent_actions_preserve_both_addresses(self):
        self.db.set_system_settings({}, {ANALYSIS:False})
        self.repo.claim()
        self.fixture.mail(2, sender='second@example.com')
        self.fixture.classify('割接取消')
        repository = SupplierDraftRepository(self.db)
        drafts = repository.list()['items']
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda draft:repository.exclude_sender(draft['id'], draft['revision']), drafts))
        self.assertEqual(set(read_settings(self.db)['unconfigured_sender_filter_list']), {'noc@example.com','second@example.com'})

    def test_cleanup_failure_retries_without_reaccepting_late_results(self):
        from excluded_sender_cleanup import cleanup_excluded_sender_mail
        with patch('cutover_deletion.delete_cutover_email', side_effect=PermissionError('busy file')):
            self.assertEqual(self.exclude().status_code, 200)
        self.assertIsNotNone(self.db.get_email_record_by_id(1))
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT status FROM mail_deletions WHERE email_records_id=1').fetchone()[0], 'pending_cleanup')
            conn.execute('UPDATE excluded_sender_mail_cleanup SET next_run_at=0')
            conn.commit()
        cleanup_excluded_sender_mail(self.db, data_dir=self.root)
        self.assertIsNone(self.db.get_email_record_by_id(1))
        self.assertEqual(SupplierDraftRepository(self.db).list()['total'], 0)

    def test_sending_reply_rejects_exclusion_without_changing_any_data(self):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE email_records SET reply_status='sending' WHERE id=1")
            conn.commit()
        self.assertEqual(self.exclude().status_code, 409)
        self.assertEqual(read_settings(self.db)['unconfigured_sender_filter_mode'], 'all')
        self.assertIsNotNone(self.db.get_email_record_by_id(1))
        self.assertEqual(SupplierDraftRepository(self.db).get(self.draft_id)['status'], 'review')


class DraftExcludeAccessTest(unittest.TestCase):
    setUp = access.UserAccessApiTest.setUp
    login = access.UserAccessApiTest.login

    def test_requires_login_and_operate_access_to_draft_sources(self):
        with self.db.get_connection() as conn:
            draft = conn.execute("""INSERT INTO supplier_drafts(candidate_key,sender,create_time,update_time)
                VALUES ('noc@example.com','noc@example.com',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""").lastrowid
            conn.execute('INSERT INTO supplier_draft_samples VALUES (?,?)', (draft, self.emails[1]))
            conn.commit()
        url = f'/api/supplier-drafts/{draft}/exclude-sender'
        self.assertEqual(self.client.post(url, json={'revision':0}).status_code, 401)
        headers = self.login()
        self.assertEqual(self.client.post(url, headers=headers, json={'revision':0}).status_code, 404)
        with self.db.get_connection() as conn:
            conn.execute('UPDATE supplier_draft_samples SET email_records_id=? WHERE draft_id=?', (self.emails[0], draft))
            conn.commit()
        self.repo.set_grants(self.user['id'], [{'account_id':self.accounts[0], 'can_operate':False}])
        self.assertEqual(self.client.post(url, headers=headers, json={'revision':0}).status_code, 404)
        self.assertEqual(read_settings(self.db)['unconfigured_sender_filter_mode'], 'all')

    def test_cannot_delete_other_mailbox_history_even_when_draft_itself_is_accessible(self):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE email_records SET sender='noc@example.com',processing_origin='unconfigured'")
            draft = conn.execute("""INSERT INTO supplier_drafts(candidate_key,sender,create_time,update_time)
                VALUES ('noc@example.com','noc@example.com',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""").lastrowid
            conn.execute('INSERT INTO supplier_draft_samples VALUES (?,?)', (draft, self.emails[0]))
            conn.commit()
        headers = self.login()
        response = self.client.post(f'/api/supplier-drafts/{draft}/exclude-sender', headers=headers, json={'revision':0})
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual(read_settings(self.db)['unconfigured_sender_filter_mode'], 'all')
        self.assertTrue(all(self.db.get_email_record_by_id(email_id) for email_id in self.emails))
