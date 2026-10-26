import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import Mock, patch

import mail_listener
from requests import Timeout
from mail_accounts import MailAccountConfig
from models import EmailMessage
from scripts.reset_mail_intake_cursor import reset_cursor
from tests.mail import test_unconfigured_flow as fixture
from unconfigured_mail import DISCOVERY
from unconfigured_mail_worker import MailAIWorker
from cutover_prompt import get_fixed_field_definitions, TIME_CONVERSION_RULES


class UnconfiguredRuntimeTest(fixture.UnconfiguredFlowTest):
    @staticmethod
    def time_result():
        return {'analysis_status':'ready', 'scene':'emergency',
            'cutover_start':'2030-10-14T02:00:00+08:00', 'cutover_end':'2030-10-14T04:00:00+08:00',
            'assessed_at':'2030-10-13T10:00:00+08:00', 'source_timezone':'Asia/Shanghai',
            'source_time_text':'2030年10月14日北京时间02:00至04:00', 'hours_until_start':16,
            'security_window':None, 'reason':'距割接开始16小时，命中紧急阈值',
            'reply':{'content':'请调整维护窗口，并提前发送割接通知。'}}

    @staticmethod
    def fastgpt_response(content, result):
        envelope = {key:content[key] for key in
            ('schema_version','task_type','request_id','attempt_id','email_records_id')}
        envelope['result'] = result
        return Mock(ok=True, json=lambda: {'choices':[{'message':{
            'role':'assistant', 'content':json.dumps(envelope, ensure_ascii=False)}}]})

    def queue_time_analysis_via_response(self):
        self.db.set_system_settings({}, {DISCOVERY:False})
        record_id = self.mail()
        worker = MailAIWorker(self.db)
        # Retain coverage for old pending jobs and independent time-only retries.
        self.classify()
        return record_id, worker

    def time_job(self, record_id):
        with self.db.get_connection() as conn:
            return dict(conn.execute("SELECT * FROM mail_ai_jobs WHERE email_records_id=? AND task_type='cutover_time_extract'",
                (record_id,)).fetchone())

    def test_two_workers_cannot_claim_same_job(self):
        self.mail()
        with ThreadPoolExecutor(2) as executor:
            claimed = list(executor.map(lambda _: self.repo.claim(), range(2)))
        self.assertEqual(sum(job is not None for job in claimed), 1)

    def test_fastgpt_classification_uses_content_and_standard_response(self):
        record_id = self.mail()
        def answer(_url, **kwargs):
            self.assertNotIn('variables', kwargs['json'])
            content = json.loads(kwargs['json']['messages'][0]['content'])
            self.assertEqual(content['task_type'], 'unconfigured_mail_process')
            self.assertIn('fixed_field_defaults', content)
            self.assertEqual(content['email_records_id'], record_id)
            envelope = {key:content[key] for key in ('schema_version','task_type','request_id','attempt_id','email_records_id')}
            envelope['result'] = {'classification': {'status':'succeeded', 'result': {
                'mail_type':'其它', 'classification_reason':'测试', 'needs_review':False}},
                'time_analysis':{'status':'skipped'}, 'supplier_draft':{'status':'skipped'}}
            return Mock(ok=True, json=lambda: {'choices':[{'message':{'content':json.dumps(envelope)}}]})
        with patch('unconfigured_mail_worker.requests.post', side_effect=answer) as post:
            self.assertTrue(MailAIWorker(self.db).run_once())
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.db.get_email_record_by_id(record_id)['mail_type'], '其它')

    def test_legacy_draft_supplements_still_merge_current_defaults(self):
        self.mail()
        self.classify()
        defaults = get_fixed_field_definitions()
        rules = {field['name']: field['description'] for fields in defaults.values() for field in fields}
        supplement = '优先从 Maintenance Reference 标签提取工单号；不要使用电路编号。'
        def answer(_url, **kwargs):
            content = json.loads(kwargs['json']['messages'][0]['content'])
            self.assertEqual(content['task_type'], 'supplier_config_draft')
            self.assertEqual(content['fixed_field_defaults'], {
                **defaults, 'time_conversion_rules': TIME_CONVERSION_RULES})
            self.assertNotIn('variables', kwargs['json'])
            return self.fastgpt_response(content, {
                'config': {'name':'供应商', 'fixed_field_rules':{}},
                'fixed_field_supplements': {'carrier_ticket_no':supplement, 'cutover_timezone':''},
                'evidence':['工单号标签为 Maintenance Reference'], 'unresolved_questions':[]})
        with patch('unconfigured_mail_worker.requests.post', side_effect=answer) as post:
            self.assertTrue(MailAIWorker(self.db).run_once())
        self.assertEqual(post.call_count, 1)
        sent = json.loads(post.call_args.kwargs['json']['messages'][0]['content'])
        self.assertIn('fixed_field_defaults', sent)
        with self.db.get_connection() as conn:
            saved = json.loads(conn.execute('SELECT draft_json FROM supplier_drafts').fetchone()[0])
        self.assertNotIn('fixed_field_supplements', saved)
        self.assertTrue(saved['config']['fixed_field_rules']['carrier_ticket_no'].startswith(
            rules['carrier_ticket_no'] + '\n\n供应商补充提取规则：\n' + supplement))
        self.assertIn('仅对明确列出的来源或条件优先适用', saved['config']['fixed_field_rules']['carrier_ticket_no'])
        self.assertNotIn('cutover_timezone', saved['config']['fixed_field_rules'])

    def test_invalid_direct_rule_response_fails_generation_without_saving_partial_rules(self):
        self.mail()
        self.classify()
        def answer(_url, **kwargs):
            content = json.loads(kwargs['json']['messages'][0]['content'])
            self.assertEqual(content['task_type'], 'supplier_config_draft')
            return self.fastgpt_response(content, {
                'config': {'name':'供应商', 'fixed_field_rules':{
                    'carrier_ticket_no':'从 Maintenance Reference 提取单号。', 'ImpactDuration':15}},
                'evidence':['Duration 为 15 minutes'], 'unresolved_questions':[]})
        with patch('unconfigured_mail_worker.requests.post', side_effect=answer):
            self.assertTrue(MailAIWorker(self.db).run_once())
        with self.db.get_connection() as conn:
            draft = conn.execute('SELECT * FROM supplier_drafts').fetchone()
            job = conn.execute("SELECT * FROM mail_ai_jobs WHERE task_type='supplier_config_draft'").fetchone()
        self.assertEqual(draft['status'], 'generation_failed')
        self.assertIsNone(draft['draft_json'])
        self.assertEqual(draft['revision'], 0)
        self.assertEqual(job['status'], 'failed')
        self.assertIsNone(job['result_json'])
        self.assertIn('fixed_field_rules', job['last_error'])

    def test_multiple_ai_reply_addresses_fail_generation_without_saving_draft(self):
        self.mail()
        self.classify()
        def answer(_url, **kwargs):
            content = json.loads(kwargs['json']['messages'][0]['content'])
            self.assertEqual(content['task_type'], 'supplier_config_draft')
            return self.fastgpt_response(content, {'config':{'name':'Supplier',
                'reply_email':'first@example.com; second@example.com'},
                'evidence':[], 'unresolved_questions':['原文包含两个联系地址。']})
        with patch('unconfigured_mail_worker.requests.post', side_effect=answer):
            self.assertTrue(MailAIWorker(self.db).run_once())
        with self.db.get_connection() as conn:
            draft = conn.execute('SELECT * FROM supplier_drafts').fetchone()
            job = conn.execute("SELECT * FROM mail_ai_jobs WHERE task_type='supplier_config_draft'").fetchone()
        self.assertEqual(draft['status'], 'generation_failed')
        self.assertIsNone(draft['draft_json'])
        self.assertEqual(draft['revision'], 0)
        self.assertEqual(job['status'], 'failed')
        self.assertIsNone(job['result_json'])
        self.assertIn('reply_email', job['last_error'])

    def test_time_analysis_standard_response_saves_analysis_and_pending_reply(self):
        record_id, worker = self.queue_time_analysis_via_response()
        result = self.time_result()
        def answer(_url, **kwargs):
            payload = kwargs['json']
            self.assertNotIn('variables', payload)
            self.assertFalse(payload['stream'])
            self.assertFalse(payload['detail'])
            content = json.loads(payload['messages'][0]['content'])
            self.assertEqual(content['task_type'], 'cutover_time_extract')
            self.assertEqual(content['email_records_id'], record_id)
            self.assertIsNone(content['draft_id'])
            self.assertIsNone(content['draft_revision'])
            # The response alone completes the task; no callback calls complete().
            return self.fastgpt_response(content, result)
        with patch('unconfigured_mail_worker.requests.post', side_effect=answer) as post:
            self.assertTrue(worker.run_once())
            self.assertFalse(worker.run_once())
        self.assertEqual(post.call_count, 1)
        saved = self.db.get_email_record_by_id(record_id)
        self.assertEqual(json.loads(saved['unconfigured_analysis_json']), result)
        self.assertEqual(saved['reply_status'], 'pending')
        self.assertEqual(saved['pending_reply_content'], result['reply']['content'])
        self.assertEqual(saved['pending_reply_scene'], 'emergency')
        self.assertEqual(self.time_job(record_id)['status'], 'succeeded')

    def test_repeated_standard_response_cannot_restore_cancelled_reply(self):
        record_id, worker = self.queue_time_analysis_via_response()
        result = self.time_result()
        def answer(_url, **kwargs):
            return self.fastgpt_response(json.loads(kwargs['json']['messages'][0]['content']), result)
        with patch('unconfigured_mail_worker.requests.post', side_effect=answer):
            self.assertTrue(worker.run_once())
        self.assertTrue(self.db.cancel_pending_reply(record_id))
        job = self.time_job(record_id)
        duplicate = self.time_result()
        duplicate['reply']['content'] = '重复结果不得恢复已经取消的回复'
        def repeated_answer(_url, **kwargs):
            content = json.loads(kwargs['json']['messages'][0]['content'])
            self.assertEqual(content['attempt_id'], job['attempt_id'])
            return self.fastgpt_response(content, duplicate)
        # Simulate duplicate delivery of the same task; completion still happens only
        # after the worker parses the standard FastGPT HTTP response.
        with patch.object(worker.repo, 'claim', return_value=job), \
                patch.object(worker.repo, 'fail', wraps=worker.repo.fail) as fail, \
                patch('unconfigured_mail_worker.requests.post', side_effect=repeated_answer) as post:
            self.assertTrue(worker.run_once())
        self.assertEqual(post.call_count, 1)
        fail.assert_not_called()
        saved = self.db.get_email_record_by_id(record_id)
        self.assertEqual(saved['reply_status'], 'cancelled')
        self.assertEqual(saved['pending_reply_content'], '')
        self.assertEqual(saved['pending_reply_scene'], '')
        self.assertEqual(json.loads(saved['unconfigured_analysis_json']), result)
        self.assertEqual(json.loads(self.time_job(record_id)['result_json']), result)

    def test_time_response_rejects_stale_attempt_after_network_retry(self):
        record_id, worker = self.queue_time_analysis_via_response()
        requests = []
        def timeout(_url, **kwargs):
            requests.append(json.loads(kwargs['json']['messages'][0]['content']))
            raise Timeout('FastGPT response not received')
        with patch('unconfigured_mail_worker.requests.post', side_effect=timeout):
            self.assertTrue(worker.run_once())
        job = self.time_job(record_id)
        self.assertEqual(job['status'], 'pending')
        with self.db.get_connection() as conn:
            conn.execute('UPDATE mail_ai_jobs SET next_run_at=0 WHERE id=?', (job['id'],))
            conn.commit()
        def stale_answer(_url, **kwargs):
            requests.append(json.loads(kwargs['json']['messages'][0]['content']))
            self.assertEqual(requests[1]['request_id'], requests[0]['request_id'])
            self.assertNotEqual(requests[1]['attempt_id'], requests[0]['attempt_id'])
            return self.fastgpt_response(requests[0], self.time_result())
        with patch('unconfigured_mail_worker.requests.post', side_effect=stale_answer):
            self.assertTrue(worker.run_once())
        job = self.time_job(record_id)
        self.assertEqual(job['status'], 'failed')
        self.assertIn('attempt_id', job['last_error'])
        saved = self.db.get_email_record_by_id(record_id)
        self.assertFalse(saved['unconfigured_analysis_json'])
        self.assertEqual(saved['reply_status'], '')
        self.repo.retry(record_id, 'cutover_time_extract')
        def current_answer(_url, **kwargs):
            content = json.loads(kwargs['json']['messages'][0]['content'])
            self.assertEqual(content['request_id'], requests[0]['request_id'])
            self.assertNotIn(content['attempt_id'], [request['attempt_id'] for request in requests])
            return self.fastgpt_response(content, self.time_result())
        with patch('unconfigured_mail_worker.requests.post', side_effect=current_answer):
            self.assertTrue(worker.run_once())
        self.assertEqual(self.time_job(record_id)['status'], 'succeeded')
        self.assertEqual(self.db.get_email_record_by_id(record_id)['reply_status'], 'pending')

    def test_incremental_intake_reads_seen_mail_and_stops_before_failed_uid(self):
        account = MailAccountConfig(id=1, name='test', email_address='inbox@example.com',
                                    email_password='test', imap_server='imap.example.com')
        imap = Mock()
        imap.folder_status.return_value = {b'UIDVALIDITY':1, b'UIDNEXT':100}
        imap.search.side_effect = lambda query: [uid for uid in (100,101,102) if int(query[1].split(':')[0]) <= uid <= int(query[1].split(':')[1])]
        imap.fetch.return_value = {100:{b'FLAGS':(b'\\Seen',)}, 102:{b'FLAGS':()}}
        def parsed(uid):
            if uid == 101:
                return None
            return EmailMessage(uid=uid, sender='new@example.com', recipients=[account.email_address],
                                subject='通知', content='正文', received_date=datetime.now())
        with patch.object(mail_listener, 'email_db', self.db), patch.object(mail_listener.settings, 'mark_as_read', False):
            listener = mail_listener.MailListener(account)
            if listener.executor:
                self.addCleanup(listener.executor.shutdown)
            listener.email_client = Mock(connected=True, client=imap)
            listener.email_client._parse_email.side_effect = parsed
            listener._check_incremental_emails()
            imap.search.assert_not_called()
            imap.folder_status.return_value[b'UIDNEXT'] = 103
            listener._check_incremental_emails()
            self.assertTrue(self.db.get_email_record(100, account.email_address)['is_read'])
            self.assertIsNone(self.db.get_email_record(102, account.email_address))
            self.assertEqual(self.repo.cursor(account.email_address, 'INBOX', 1, 999), 101)
            imap.add_flags.assert_not_called()
            listener.email_client._parse_email.side_effect = lambda uid: EmailMessage(
                uid=uid, sender='new@example.com', recipients=[account.email_address],
                subject='通知', content='正文', received_date=datetime.now())
            listener._check_incremental_emails()
            self.assertIsNotNone(self.db.get_email_record(102, account.email_address))
            self.assertEqual(self.repo.cursor(account.email_address, 'INBOX', 1, 999), 103)

    def test_reply_send_claim_is_exclusive_and_cannot_be_cancelled_while_sending(self):
        record_id = self.mail()
        self.db.save_pending_reply(record_id, 'reply', 'emergency')
        self.assertTrue(self.db.claim_unconfigured_reply(record_id, 'edited reply'))
        self.assertFalse(self.db.claim_unconfigured_reply(record_id, 'again'))
        self.assertFalse(self.db.cancel_pending_reply(record_id))
        self.db.mark_reply_uncertain(record_id)
        self.assertEqual(self.db.get_email_record_by_id(record_id)['reply_status'], 'send_uncertain')

    def test_incremental_intake_advances_past_deleted_mail_including_ingest_race(self):
        from cutover_deletion import delete_cutover_email

        account = MailAccountConfig(id=1, name='test', email_address='inbox@example.com',
                                    email_password='test', imap_server='imap.example.com')
        def delete_uid(uid):
            record = self.db.get_email_record(uid, account.email_address)
            delete_cutover_email(self.db, Path(self.tmp.name) / 'data', record['id'],
                                 image_dir=Path(self.tmp.name) / 'images')

        self.mail(100)
        delete_uid(100)
        self.repo.cursor(account.email_address, 'INBOX', 1, 100)
        imap = Mock()
        imap.folder_status.return_value = {b'UIDVALIDITY': 1, b'UIDNEXT': 103}
        imap.search.return_value = [100, 101, 102]
        imap.fetch.return_value = {}
        def delete_after_ingest():
            if self.db.get_email_record(101, account.email_address):
                delete_uid(101)

        with patch.object(mail_listener, 'email_db', self.db), patch.object(mail_listener.settings, 'mark_as_read', False):
            listener = mail_listener.MailListener(account, on_email_received=delete_after_ingest)
            if listener.executor:
                self.addCleanup(listener.executor.shutdown)
            listener.email_client = Mock(connected=True, client=imap)
            listener.email_client._parse_email.side_effect = lambda uid: EmailMessage(
                uid=uid, sender='new@example.com', recipients=[account.email_address],
                subject='通知', content='正文', received_date=datetime.now())
            listener._check_incremental_emails()

        self.assertEqual([call.args[0] for call in listener.email_client._parse_email.call_args_list], [101, 102])
        self.assertIsNone(self.db.get_email_record(101, account.email_address))
        self.assertTrue(self.db.is_email_deleted(101, account.email_address))
        self.assertIsNotNone(self.db.get_email_record(102, account.email_address))
        self.assertEqual(self.repo.cursor(account.email_address, 'INBOX', 1, 999), 103)

    def test_configured_intake_deletion_does_not_forward_another_mailbox_same_uid(self):
        from actions import APIForwardAction
        from cutover_deletion import delete_cutover_email

        account = MailAccountConfig(id=1, name='test', email_address='inbox@example.com',
                                    email_password='test', imap_server='imap.example.com')
        for uid, stage in ((110, 'after_ingest'), (111, 'before_action')):
            with self.subTest(stage=stage):
                self.db.add_email_record(uid, receiver='other@example.com',
                                        subject=f'Other mail {uid}', content='Keep this mail')
                other = self.db.get_email_record(uid, 'other@example.com')
                email = EmailMessage(uid=uid, sender='noc@example.com', recipients=[account.email_address],
                                     subject=f'Cutover {uid}', content='New cutover notice', received_date=datetime.now())
                deleted_ids = []
                def delete_received_mail():
                    record = self.db.get_email_record(uid, account.email_address)
                    deleted_ids.append(record['id'])
                    delete_cutover_email(self.db, Path(self.tmp.name) / 'data', record['id'],
                                         image_dir=Path(self.tmp.name) / 'images')

                with patch.object(mail_listener, 'email_db', self.db), patch('actions.requests.post') as post:
                    listener = mail_listener.MailListener(account,
                        on_email_received=delete_received_mail if stage == 'after_ingest' else None)
                    if listener.executor:
                        self.addCleanup(listener.executor.shutdown)
                    listener.supplier_config_repository = Mock()
                    listener.email_filter = Mock()
                    rule = Mock(action='api_forward', action_params={})
                    rule.name = '供应商邮件转发'
                    def match_and_delete(message):
                        delete_received_mail()
                        return [rule]
                    listener.email_filter.filter_email.side_effect = match_and_delete
                    listener.action_manager = Mock()
                    listener.action_manager.execute_action.side_effect = lambda action, message, params: APIForwardAction(self.db).execute(message, params)
                    listener._process_email(email)
                    post.assert_not_called()
                    if stage == 'after_ingest':
                        listener.action_manager.execute_action.assert_not_called()
                    else:
                        self.assertEqual(listener.action_manager.execute_action.call_args.args[2]['_email_records_id'], deleted_ids[0])
                self.assertEqual(self.db.get_email_record_by_id(other['id']), other)
                self.assertIsNone(self.db.get_email_record(uid, account.email_address))

    def test_cancelled_generation_waits_for_a_new_notice(self):
        self.mail()
        self.classify()
        self.db.set_system_settings({}, {DISCOVERY:False})
        job = self.repo.claim()
        self.assertEqual(job['task_type'], 'cutover_time_extract')
        self.db.set_system_settings({}, {DISCOVERY:True})
        self.assertIsNone(self.repo.claim())
        self.mail(2)
        self.classify()
        self.assertEqual(self.repo.claim()['task_type'], 'supplier_config_draft')

    def test_expired_final_attempt_marks_draft_failed_without_requeue(self):
        self.mail()
        self.classify()
        draft_job = self.repo.claim()
        with self.db.get_connection() as conn:
            conn.execute("UPDATE mail_ai_jobs SET attempts=3, lease_until=0 WHERE id=?", (draft_job['id'],))
            conn.commit()
        self.assertEqual(self.repo.claim()['task_type'], 'cutover_time_extract')
        self.assertIsNone(self.repo.claim())
        with self.db.get_connection() as conn:
            draft = conn.execute('SELECT * FROM supplier_drafts WHERE id=?', (draft_job['draft_id'],)).fetchone()
            self.assertEqual(draft['status'], 'generation_failed')
        self.repo.retry(draft_job['email_records_id'], 'supplier_config_draft')
        self.assertEqual(self.repo.claim()['attempts'], 1)

    def test_boundary_recovery_is_dry_run_and_refuses_historical_uid_collision(self):
        self.mail(100)
        self.repo.cursor('inbox@example.com', 'INBOX', 1, 101)
        args = (self.db.db_path, 'inbox@example.com', 'INBOX', 1, 2)
        self.assertFalse(reset_cursor(*args, 201)['applied'])
        self.assertEqual(self.repo.cursor('inbox@example.com', 'INBOX', 1, 999), 101)
        with self.assertRaises(ValueError):
            reset_cursor(*args, 100, apply=True)
        self.assertTrue(reset_cursor(*args, 201, apply=True)['applied'])
        self.assertEqual(self.repo.cursor('inbox@example.com', 'INBOX', 2, 999), 201)

    def test_policy_skip_reason_stays_in_runtime_log_only(self):
        self.db.set_system_settings({}, {'supplier_auto_discovery_enabled':False,
                                        'unconfigured_cutover_analysis_enabled':False})
        with patch('unconfigured_mail_repository.logger') as logger:
            record_id = self.mail()
        self.assertEqual(logger.info.call_args.args[-1], 'features_disabled')
        self.assertIn('reason_code={}', logger.info.call_args.args[0])
        projection = json.dumps(self.repo.projection(record_id))
        self.assertNotIn('reason_code', projection)
        self.assertNotIn('features_disabled', projection)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM mail_ai_jobs').fetchone()[0], 0)
