import json
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from supplier_drafts import SupplierDraftRepository
from tests.mail import test_unconfigured_flow as fixture, test_unconfigured_runtime as runtime
from unconfigured_mail import DISCOVERY, ANALYSIS
from unconfigured_mail_worker import MailAIWorker


class CombinedMailTest(fixture.UnconfiguredFlowTest):
    def test_in_window_workflow_result_creates_queryable_pending_reply(self):
        self.assert_started_window_reply('2026-10-13T08:00:00+08:00')

    def test_ended_window_still_creates_same_pending_reply(self):
        self.assert_started_window_reply('2026-10-14T08:00:00+08:00')

    def assert_started_window_reply(self, assessed_at):
        from record_query import RecordQueryRepository

        self.db.set_system_settings({}, {DISCOVERY: False, ANALYSIS: True})
        record_id = self.mail()
        job = self.repo.claim(combined=True)
        workflow = json.loads((Path(__file__).resolve().parents[2] /
            'workflows/ctg_mail.unconfigured.template.json').read_text())
        nodes = {node['nodeId']: node for node in workflow['nodes']}
        code = next(item['value'] for item in nodes['new_unconfigured_finish']['inputs'] if item['key'] == 'code')
        content = {**job['workflow_context'], **{key: job[key] for key in (
            'request_id', 'attempt_id', 'email_records_id')}, 'schema_version': 1,
            'task_type': 'unconfigured_mail_process', 'securityTime': '', 'attachments': []}
        args = {'originMail': json.dumps(content),
            'now': int(datetime.fromisoformat(assessed_at).timestamp() * 1000),
            'state': {'classification': {'status': 'succeeded', 'result': {
                'mail_type': '割接通知', 'needs_review': False, 'classification_reason': '维护通知'}}},
            'timeAnswer': json.dumps({'windows': [{'start': '2026-10-13T07:00:00+08:00',
                'end': '2026-10-13T10:00:00+08:00'}], 'source_timezone': 'Asia/Shanghai',
                'source_time_text': '2026年10月13日北京时间07:00至10:00', 'needs_review': False})}
        result = subprocess.run(['node', '-e', "const p=JSON.parse(require('fs').readFileSync(0,'utf8'));"
            "const run=new Function(p.code+'; return main;')(); console.log(JSON.stringify(run(p.args).envelope));"],
            input=json.dumps({'code': code, 'args': args}), text=True, capture_output=True, check=True)
        envelope = json.loads(result.stdout)
        self.assertEqual(envelope['result']['time_analysis']['result']['scene'], 'in_window')
        updates = next(i['value'] for i in nodes['tzwoYLCKW41mAMDh']['inputs'] if i['key'] == 'updateList')
        expected_reply = next(i['value'][1] for i in updates if i['variable'][1] == 'adxERFBe').replace('\\n', '\n')
        self.assertEqual(envelope['result']['time_analysis']['result']['reply']['content'], expected_reply)
        self.repo.complete_combined(envelope)
        queries = RecordQueryRepository(self.db)
        detail = queries.get_cutover_email_detail(record_id)
        self.assertEqual(detail['unconfigured_analysis']['scene'], 'in_window')
        self.assertEqual(detail['reply_status'], 'pending')
        self.assertEqual(detail['pending_reply_scene_label'], '已在割接窗口内')
        self.assertEqual(detail['pending_reply_content'], expected_reply)
        filtered = queries.list_cutover_task_emails(
            {'page': 1, 'page_size': 20, 'offset': 0}, status='reply_pending', supplier=None, tag='in_window')
        self.assertEqual([row['id'] for row in filtered['items']], [record_id])

    def response(self, content, mail_type='割接通知', draft_error=None):
        result = {
            'classification': {'status': 'succeeded', 'result': {
                'mail_type': mail_type, 'needs_review': False, 'classification_reason': '当前通知'}},
            'time_analysis': {'status': 'skipped'},
            'supplier_draft': {'status': 'skipped'},
        }
        if mail_type == '割接通知':
            if content['should_analyze_cutover_time']:
                result['time_analysis'] = {'status': 'succeeded', 'result': runtime.UnconfiguredRuntimeTest.time_result()}
            if content['should_generate_supplier_draft']:
                result['supplier_draft'] = {'status': 'failed', 'error': draft_error} if draft_error else {
                    'status': 'succeeded', 'result': {'config': {'name': 'Test supplier',
                        'reply_email': 'maintenance@example.net',
                        'fixed_field_rules': {'carrier_ticket_no': '从当前通知 Maintenance Reference 提取单号'},
                        'email_type_samples': {'割接通知': {'subject': '维护通知', 'content': '维护正文'}}},
                        'evidence': ['当前通知'], 'unresolved_questions': []}}
        envelope = {key: content[key] for key in ('schema_version', 'task_type', 'request_id', 'attempt_id', 'email_records_id')}
        envelope['result'] = result
        return Mock(ok=True, json=lambda: {'choices': [{'message': {'content': json.dumps(envelope)}}]})

    def run_mail(self, mail_type='割接通知', draft_error=None, before_response=None):
        sent = []
        def answer(_url, **kwargs):
            content = json.loads(kwargs['json']['messages'][0]['content'])
            self.assertEqual(content['task_type'], 'unconfigured_mail_process')
            self.assertNotIn('variables', kwargs['json'])
            sent.append(content)
            if before_response:
                before_response(content)
            return self.response(content, mail_type, draft_error)
        with patch('unconfigured_mail_worker.requests.post', side_effect=answer) as post:
            self.assertTrue(MailAIWorker(self.db).run_once())
        self.assertEqual(post.call_count, 1)
        return sent[0]

    def test_first_notice_is_one_request_and_saves_all_branches(self):
        record_id = self.mail()
        content = self.run_mail()
        self.assertTrue(content['should_generate_supplier_draft'])
        self.assertTrue(content['should_analyze_cutover_time'])
        self.assertIn('fixed_field_defaults', content)
        view = self.repo.projection(record_id)
        self.assertEqual(len(view['ai_tasks']), 3)
        self.assertTrue(all(t['status'] == 'succeeded' for t in view['ai_tasks']))
        self.assertEqual(view['unconfigured_analysis']['scene'], 'emergency')
        draft = SupplierDraftRepository(self.db).get(view['supplier_draft_id'])
        self.assertEqual(draft['draft']['config']['name'], '')
        self.assertEqual(draft['draft']['config']['reply_email'], 'maintenance@example.net')
        self.assertEqual(self.db.get_email_record_by_id(record_id)['reply_status'], 'pending')
        self.assertIsNone(self.repo.claim())

    def test_combined_draft_uses_complete_original_sample_instead_of_model_summary(self):
        record_id = self.mail()
        html = '<p>原始通知<br>第二行</p>' + '<p>维护</p>' * 80 + '<table><tr><td>COMPLETE-4992</td></tr></table>'
        with self.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET html_content=? WHERE id=?', (html, record_id))
            conn.commit()
        self.run_mail()
        draft = SupplierDraftRepository(self.db).get(self.repo.projection(record_id)['supplier_draft_id'])
        self.assertEqual(draft['draft']['config']['email_type_samples']['割接通知']['content'], html)

    def test_existing_draft_is_not_regenerated_but_new_mail_still_classified(self):
        self.mail()
        self.run_mail()
        before = SupplierDraftRepository(self.db).list()['items'][0]
        second = self.mail(2)
        content = self.run_mail()
        self.assertFalse(content['should_generate_supplier_draft'])
        self.assertNotIn('fixed_field_defaults', content)
        self.assertEqual(len(self.repo.projection(second)['ai_tasks']), 2)
        self.assertEqual(SupplierDraftRepository(self.db).get(before['id'])['draft'], before['draft'])

    def test_other_mail_only_classifies_then_next_notice_can_generate(self):
        first = self.mail()
        self.run_mail('割接取消')
        self.assertEqual(len(self.repo.projection(first)['ai_tasks']), 1)
        self.assertIsNone(self.repo.projection(first)['unconfigured_analysis'])
        draft = SupplierDraftRepository(self.db).list()['items'][0]
        self.assertEqual(draft['status'], 'collecting')
        self.mail(2)
        self.assertTrue(self.run_mail()['should_generate_supplier_draft'])

    def test_draft_failure_keeps_classification_and_time_and_retries_only_draft(self):
        record_id = self.mail()
        self.run_mail(draft_error='模型服务暂时不可用')
        view = self.repo.projection(record_id)
        states = {t['task_type']: t['status'] for t in view['ai_tasks']}
        self.assertEqual(states, {'unconfigured_mail_analyze':'succeeded', 'cutover_time_extract':'succeeded', 'supplier_config_draft':'failed'})
        self.assertEqual(SupplierDraftRepository(self.db).get(view['supplier_draft_id'])['status'], 'generation_failed')
        self.repo.retry(record_id, 'supplier_config_draft')
        def answer(_url, **kwargs):
            content = json.loads(kwargs['json']['messages'][0]['content'])
            self.assertEqual(content['task_type'], 'supplier_config_draft')
            return runtime.UnconfiguredRuntimeTest.fastgpt_response(content, {'config': {'name':'Retried'}, 'evidence':[], 'unresolved_questions':[]})
        with patch('unconfigured_mail_worker.requests.post', side_effect=answer) as post:
            self.assertTrue(MailAIWorker(self.db).run_once())
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.repo.projection(record_id)['unconfigured_analysis'], view['unconfigured_analysis'])
        draft = SupplierDraftRepository(self.db).get(view['supplier_draft_id'])
        self.assertEqual(draft['draft']['config']['name'], '')

    def test_deleting_candidate_during_request_does_not_recreate_it(self):
        record_id = self.mail()
        def delete(content):
            SupplierDraftRepository(self.db).delete(content['draft_id'], content['draft_revision'])
        self.run_mail(before_response=delete)
        self.assertEqual(SupplierDraftRepository(self.db).list()['total'], 0)
        self.assertEqual(self.repo.projection(record_id)['unconfigured_analysis']['scene'], 'emergency')

    def test_same_sender_is_serialized_but_other_sender_can_run(self):
        self.mail()
        self.mail(2)
        third = self.mail(3, sender='other@example.net')
        first = self.repo.claim(combined=True)
        second = self.repo.claim(combined=True)
        self.assertEqual(second['email_records_id'], third)
        self.assertIsNone(self.repo.claim(combined=True))

    def test_switches_control_each_branch(self):
        self.db.set_system_settings({}, {DISCOVERY:False, ANALYSIS:True})
        self.mail()
        content = self.run_mail()
        self.assertFalse(content['should_generate_supplier_draft'])
        self.assertTrue(content['should_analyze_cutover_time'])
        self.assertEqual(SupplierDraftRepository(self.db).list()['total'], 0)

    def claimed_response(self, **options):
        job = self.repo.claim(combined=True)
        content = {**job, **job['workflow_context'], 'schema_version':1, 'task_type':'unconfigured_mail_process'}
        envelope = json.loads(self.response(content, **options).json()['choices'][0]['message']['content'])
        return job, envelope

    def test_invalid_time_keeps_draft_and_can_retry_time_only(self):
        record_id = self.mail()
        job, envelope = self.claimed_response()
        envelope['result']['time_analysis']['result']['hours_until_start'] = 'invalid'
        self.repo.complete_combined(envelope)
        view = self.repo.projection(record_id)
        self.assertIsNone(view['unconfigured_analysis'])
        self.assertEqual(SupplierDraftRepository(self.db).get(view['supplier_draft_id'])['status'],'review')
        self.repo.retry(record_id,'cutover_time_extract')
        self.assertEqual(self.repo.claim(combined=True)['task_type'], 'cutover_time_extract')

    def test_classification_failure_and_old_attempt_cannot_save_children(self):
        record_id = self.mail()
        job, envelope = self.claimed_response()
        original = json.loads(json.dumps(envelope))
        envelope['result']['classification'] = {'status':'failed','error':'classification failed'}
        with self.assertRaises(ValueError):
            self.repo.complete_combined(envelope)
        self.assertEqual(len(self.repo.projection(record_id)['ai_tasks']),1)
        self.repo.fail(job,'failed')
        self.repo.retry(record_id,'unconfigured_mail_analyze')
        self.repo.claim(combined=True)
        with self.assertRaisesRegex(ValueError,'attempt_id'):
            self.repo.complete_combined(original)

    def test_duplicate_result_cannot_restore_cancelled_reply_or_edited_draft(self):
        record_id = self.mail()
        job, envelope = self.claimed_response()
        self.repo.complete_combined(envelope)
        view = self.repo.projection(record_id)
        drafts = SupplierDraftRepository(self.db)
        draft = drafts.get(view['supplier_draft_id'])
        drafts.edit(draft['id'],draft['revision'],{**draft['draft']['config'],'name':'Human edited'})
        with self.db.get_connection() as conn:
            conn.execute("UPDATE email_records SET reply_status='cancelled' WHERE id=?",(record_id,))
            conn.commit()
        self.repo.complete_combined(envelope)
        self.assertEqual(self.db.get_email_record_by_id(record_id)['reply_status'],'cancelled')
        self.assertEqual(drafts.get(draft['id'])['draft']['config']['name'],'Human edited')

    def test_disabled_switches_at_completion_drop_late_branch_results(self):
        record_id = self.mail()
        job, envelope = self.claimed_response()
        self.db.set_system_settings({}, {DISCOVERY:False, ANALYSIS:False})
        self.repo.complete_combined(envelope)
        self.assertEqual(len(self.repo.projection(record_id)['ai_tasks']),1)
        self.assertIsNone(self.repo.projection(record_id)['unconfigured_analysis'])

    def test_deleted_mail_does_not_return_from_late_result(self):
        from cutover_deletion import delete_cutover_email
        record_id = self.mail()
        job, envelope = self.claimed_response()
        self.repo.fail(job, '网络请求失败')
        delete_cutover_email(self.db,self.tmp.name,record_id)
        with self.assertRaises(ValueError):
            self.repo.complete_combined(envelope)
        self.assertIsNone(self.db.get_email_record_by_id(record_id))
        draft = SupplierDraftRepository(self.db).list()['items'][0]
        self.assertIsNone(draft['draft'])
        self.assertEqual(draft['sample_count'],0)

    def test_candidate_deleted_before_transport_retry_stays_deleted(self):
        record_id = self.mail()
        job, envelope = self.claimed_response()
        context = job['workflow_context']
        SupplierDraftRepository(self.db).delete(context['draft_id'],context['draft_revision'])
        self.repo.fail(job,'timeout')
        self.repo.retry(record_id,'unconfigured_mail_analyze')
        retried = self.repo.claim(combined=True)
        self.assertFalse(retried['workflow_context']['should_generate_supplier_draft'])
        self.assertEqual(SupplierDraftRepository(self.db).list()['total'],0)

