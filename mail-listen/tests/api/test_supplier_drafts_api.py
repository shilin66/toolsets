import json
from datetime import datetime
from unittest.mock import Mock, patch

import api_server
from actions import APIForwardAction, email_message_from_record
from cutover_prompt import get_fixed_field_definitions
from models import EmailMessage
from supplier_config import SupplierConfigRepository
from tests.mail import test_unconfigured_flow as fixture
from unconfigured_mail_worker import MailAIWorker


class SupplierDraftApiTest(fixture.UnconfiguredFlowTest):
    def setUp(self):
        super().setUp()
        patcher = patch.object(api_server, 'email_db', self.db)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = api_server.app.test_client()
        self.headers = {'Authorization': 'Bearer test-key'}

    def make_draft(self):
        self.mail()
        self.classify()
        job = self.repo.claim()
        self.complete(job, {'config': {'name': 'New supplier', 'prompt_mode': 'auto',
            'email_type_samples': {'割接通知': {'subject': '维护', 'content': '维护时间'}}},
            'evidence': ['邮件正文'], 'unresolved_questions': []})
        return job['draft_id']

    def review_supplier_name(self, draft):
        self.assertEqual(draft['draft']['config']['name'], '')
        response = self.client.put(f"/api/supplier-drafts/{draft['id']}", headers=self.headers,
            json={'revision': draft['revision'], 'config': {
                **draft['draft']['config'], 'name': f"Reviewed supplier {draft['id']}"}})
        self.assertEqual(response.status_code, 200)
        return response.get_json()['data']

    def test_list_defaults_to_unpublished_and_filters_before_pagination(self):
        draft_id = self.make_draft()
        url = f'/api/supplier-drafts/{draft_id}'
        draft = self.review_supplier_name(self.client.get(url, headers=self.headers).get_json()['data'])
        response = self.client.post(url + '/publish', headers=self.headers, json={'revision': draft['revision']})
        self.assertEqual(response.status_code, 200)
        statuses = ['collecting', 'generating', 'generation_failed', 'review']
        with self.db.get_connection() as conn:
            for index, status in enumerate(statuses):
                sender = f'pending-{index}@example.com'
                conn.execute('''INSERT INTO supplier_drafts (candidate_key,sender,status,create_time,update_time)
                             VALUES (?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)''',
                             (sender, sender, status))
            conn.commit()
        for suffix in ('', '?status=unpublished'):
            result = self.client.get('/api/supplier-drafts' + suffix, headers=self.headers).get_json()['data']
            self.assertEqual(result['total'], 4)
            self.assertEqual({item['status'] for item in result['items']}, set(statuses))
        pages = [self.client.get(f'/api/supplier-drafts?status=unpublished&pageSize=2&page={page}',
                 headers=self.headers).get_json()['data'] for page in (1, 2)]
        self.assertEqual([page['total'] for page in pages], [4, 4])
        self.assertEqual(len({item['id'] for page in pages for item in page['items']}), 4)
        history = self.client.get('/api/supplier-drafts?status=published&pageSize=1', headers=self.headers).get_json()['data']
        self.assertEqual(history['total'], 1)
        self.assertEqual([item['id'] for item in history['items']], [draft_id])
        self.assertEqual(history['items'][0]['sample_count'], 1)
        detail = self.client.get(url, headers=self.headers).get_json()['data']
        self.assertEqual(detail['samples'], draft['samples'])
        self.assertEqual(detail['draft'], draft['draft'])
        self.assertEqual(self.client.get('/api/supplier-drafts?status=invalid', headers=self.headers).status_code, 400)
        self.assertEqual(self.client.get('/api/supplier-drafts?status=published').status_code, 401)

    def test_ai_supplier_name_is_blank_until_human_review(self):
        draft_id = self.make_draft()
        url = f'/api/supplier-drafts/{draft_id}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        self.assertEqual(draft['draft']['config']['name'], '')
        response = self.client.post(url + '/publish', headers=self.headers,
            json={'revision': draft['revision']})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['message'], '启用前请填写供应商名称')
        self.assertEqual(SupplierConfigRepository(self.db).list(), [])
        saved = self.client.put(url, headers=self.headers, json={'revision': draft['revision'],
            'config': {**draft['draft']['config'], 'name': '人工填写供应商'}}).get_json()['data']
        self.assertEqual(saved['draft']['config']['name'], '人工填写供应商')
        response = self.client.post(url + '/publish', headers=self.headers,
            json={'revision': saved['revision']})
        self.assertEqual(response.status_code, 200)
        supplier = SupplierConfigRepository(self.db).get(response.get_json()['data']['supplier_id'])
        self.assertEqual(supplier['name'], '人工填写供应商')

    def test_blank_name_can_be_saved_but_cannot_be_published(self):
        url = f'/api/supplier-drafts/{self.make_draft()}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        for name in ('', ' \t\n\u3000'):
            with self.subTest(name=repr(name)):
                response = self.client.put(url, headers=self.headers, json={
                    'revision': draft['revision'], 'config': {**draft['draft']['config'], 'name': name}})
                self.assertEqual(response.status_code, 200)
                draft = response.get_json()['data']
                response = self.client.post(url + '/publish', headers=self.headers,
                    json={'revision': draft['revision']})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()['message'], '启用前请填写供应商名称')
                self.assertEqual(self.client.get(url, headers=self.headers).get_json()['data'], draft)
                self.assertEqual(SupplierConfigRepository(self.db).list(), [])

    def test_publish_validation_errors_are_actionable_and_leave_draft_intact(self):
        url = f'/api/supplier-drafts/{self.make_draft()}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        base = {**draft['draft']['config'], 'name': '人工确认供应商'}
        cases = [
            ({'reply_email': 'invalid-address'}, '回复邮箱格式不正确'),
            ({'email_type_samples': {'割接通知': {'subject': '', 'content': '维护'}}}, '主题样本不能为空'),
            ({'email_type_samples': {'割接通知': {'subject': '维护', 'content': ''}}}, '正文样本不能为空'),
            ({'line_custom_fields': [{'name': '', 'description': '规则'}]}, '线路自定义字段第 1 项的字段名不能为空'),
            ({'line_custom_fields': [{'name': 'Circuit ID', 'description': '规则'}]}, '字段名只能包含字母'),
            ({'line_query_keywords': ['MissingId']}, '线路查询关键字 MissingId 必须是'),
            ({'custom_fields': [{'name': 'line_array'}]}, '与内置字段或保留键冲突'),
            ({'custom_fields': [{'name': 'Ref'}, {'name': 'Ref'}]}, '自定义字段 Ref 重复'),
            ({'prompt_mode': 'manual', 'cutover_extract_prompt': ''}, '手工提示词模式下请填写'),
        ]
        for changes, message in cases:
            with self.subTest(changes=changes):
                saved = self.client.put(url, headers=self.headers, json={
                    'revision': draft['revision'], 'config': {**base, **changes}})
                self.assertEqual(saved.status_code, 200)
                draft = saved.get_json()['data']
                response = self.client.post(url + '/publish', headers=self.headers,
                    json={'revision': draft['revision']})
                self.assertEqual(response.status_code, 400)
                error = response.get_json()['message']
                self.assertIn(message, error)
                for technical in ('validation error', 'pydantic.dev', 'input_value=', 'Value error,'):
                    self.assertNotIn(technical, error)
                self.assertEqual(self.client.get(url, headers=self.headers).get_json()['data'], draft)
                self.assertEqual(SupplierConfigRepository(self.db).list(), [])

    def test_publish_blank_reply_address_uses_sender(self):
        url = f'/api/supplier-drafts/{self.make_draft()}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        saved = self.client.put(url, headers=self.headers, json={
            'revision': draft['revision'], 'config': {**draft['draft']['config'],
                'name': '人工确认供应商', 'reply_email': '  '}}).get_json()['data']
        response = self.client.post(url + '/publish', headers=self.headers, json={'revision': saved['revision']})
        self.assertEqual(response.status_code, 200)
        supplier = SupplierConfigRepository(self.db).get(response.get_json()['data']['supplier_id'])
        self.assertEqual(supplier['reply_email'], draft['sender'])

    def test_original_sample_returns_complete_plain_and_html_bodies(self):
        draft_id = self.make_draft()
        draft = self.client.get(f'/api/supplier-drafts/{draft_id}', headers=self.headers).get_json()['data']
        email_id = draft['samples'][0]['id']
        text = 'Dear NOC,\n\n' + 'Maintenance details. ' * 40 + '\nCircuit ID: FULL-CIRCUIT-4821\nEnd of notice.'
        html = '<p>Dear NOC,<br>Maintenance details.</p><table><tr><th>Circuit ID</th></tr><tr><td>FULL-CIRCUIT-4821</td></tr></table><p>End of notice.</p>'
        with self.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET content=?, html_content=? WHERE id=?', (text, html, email_id))
            conn.commit()
        response = self.client.get(f'/api/emails/{email_id}/source', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        source = response.get_json()['data']
        self.assertEqual(source['content'], text)
        self.assertEqual(source['html_content'], html)
        self.assertIn('FULL-CIRCUIT-4821', source['preview_html'])
        self.assertIn('<table>', source['preview_html'])
        self.assertIn('Content-Security-Policy', source['preview_html'])
        with self.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET content=? WHERE id=?', ('', email_id))
            conn.commit()
        html_only = self.client.get(f'/api/emails/{email_id}/source', headers=self.headers).get_json()['data']
        self.assertEqual(html_only['content'], '')
        self.assertIn('FULL-CIRCUIT-4821', html_only['preview_html'])
        self.assertEqual(self.client.get(f'/api/emails/{email_id}/source').status_code, 401)
        self.assertEqual(self.client.get('/api/emails/999999/source', headers=self.headers).status_code, 404)

    def test_generated_notice_sample_keeps_original_in_classification_after_publish(self):
        html = '<p>通知第一段<br>下一行</p>' + '<p>维护说明</p>' * 80 + '<table><tr><td>LAST-LINE-7921</td></tr></table>'
        email = EmailMessage(uid=1, sender='noc@example.com', recipients=['inbox@example.com'],
            subject='完整维护通知', content='纯文本版本缺少表格', html_content=html, received_date=datetime.now())
        email_id = self.repo.ingest(email, 'inbox@example.com')
        self.classify()
        job = self.repo.claim()
        self.complete(job, {'config': {'name': 'Original sample supplier', 'email_type_samples': {
            '割接通知': {'subject': '模型缩写主题', 'content': '模型缩写正文', 'content_in_attachment': True}}},
            'evidence': [], 'unresolved_questions': []})
        url = f"/api/supplier-drafts/{job['draft_id']}"
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        draft = self.review_supplier_name(draft)
        sample = draft['draft']['config']['email_type_samples']['割接通知']
        self.assertEqual(sample, {'subject': email.subject, 'content': html, 'content_in_attachment': True, 'source_email_records_id': email_id})
        sample['content'] += '\n人工确认保留的备注'
        saved = self.client.put(url, headers=self.headers, json={'revision': draft['revision'],
            'config': draft['draft']['config']}).get_json()['data']
        published = self.client.post(url + '/publish', headers=self.headers, json={'revision': saved['revision']})
        self.assertEqual(published.status_code, 200)
        record = self.db.get_email_record_by_id(email_id)
        outgoing = json.loads(APIForwardAction(self.db)._build_content(email_message_from_record(record), {}))
        self.assertEqual(outgoing['content'], html)
        self.assertIn(sample['content'], outgoing['supplier_mail_classify_prompt'])

    def test_ai_designated_reply_address_survives_review_publish_and_later_reply(self):
        reply_address = 'maintenance-replies@example.net'
        body = f'Planned maintenance. Please reply to {reply_address} about this maintenance.'
        email = EmailMessage(uid=1, sender='noc@example.com', recipients=['inbox@example.com'],
            subject='Maintenance notification', content=body, received_date=datetime.now())
        email_id = self.repo.ingest(email, 'inbox@example.com')
        self.classify()
        def answer(_url, **kwargs):
            content = json.loads(kwargs['json']['messages'][0]['content'])
            self.assertEqual(content['content'], body)
            self.assertEqual(content['task_type'], 'supplier_config_draft')
            envelope = {key:content[key] for key in
                ('schema_version','task_type','request_id','attempt_id','email_records_id')}
            envelope['result'] = {'config':{'name':'Maintenance supplier',
                # The model cannot choose the sender used for same-address comparison.
                'email':reply_address, 'reply_email':reply_address,
                'email_type_samples':{'割接通知':{'subject':email.subject,'content':body}}},
                'evidence':[f'正文明确要求维护相关回复发送至 {reply_address}。'], 'unresolved_questions':[]}
            return Mock(ok=True, json=lambda:{'choices':[{'message':{
                'content':json.dumps(envelope, ensure_ascii=False)}}]})
        with patch('unconfigured_mail_worker.requests.post', side_effect=answer):
            self.assertTrue(MailAIWorker(self.db).run_once())
        draft_id = self.repo.projection(email_id)['supplier_draft_id']
        url = f'/api/supplier-drafts/{draft_id}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        self.assertEqual(draft['draft']['config']['email'], 'noc@example.com')
        self.assertEqual(draft['draft']['config']['reply_email'], reply_address)
        response = self.client.put(url, headers=self.headers, json={'revision':draft['revision'],
            'config':{**draft['draft']['config'], 'name':'Reviewed maintenance supplier'}})
        self.assertEqual(response.status_code, 200)
        reviewed = response.get_json()['data']
        self.assertEqual(reviewed['draft']['config']['reply_email'], reply_address)
        published = self.client.post(url + '/publish', headers=self.headers,
            json={'revision':reviewed['revision']})
        self.assertEqual(published.status_code, 200)
        supplier = SupplierConfigRepository(self.db).get(published.get_json()['data']['supplier_id'])
        self.assertEqual(supplier['reply_email'], reply_address)
        self.assertTrue(self.db.add_email_record(2, sender='noc@example.com', receiver='inbox@example.com',
            subject='Later maintenance', content='Another maintenance notification', reply_to='header-reply@example.org'))
        later = self.db.get_email_record(2, 'inbox@example.com')
        self.db.save_pending_reply(later['id'], '请调整维护窗口', 'emergency')
        smtp = Mock()
        smtp.reply_email.return_value = True
        with patch.object(api_server, 'build_reply_email_client', return_value=smtp):
            response = self.client.post('/api/cutover/reply/confirm', headers=self.headers,
                json={'email_records_id':later['id']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['data']['recipients'], [reply_address])
        self.assertEqual(smtp.reply_email.call_args.kwargs['recipients'], [reply_address])

    def test_ai_same_sender_or_unspecified_reply_address_falls_back_after_publish(self):
        cases = ({'reply_email':'  NoC@EXAMPLE.COM  '}, {'reply_email':None}, {})
        for index, reply_config in enumerate(cases):
            with self.subTest(reply_config=reply_config):
                sender = f'noc{index}@example.com'
                config = dict(reply_config)
                if config.get('reply_email'):
                    config['reply_email'] = f'  NoC{index}@EXAMPLE.COM  '
                email = EmailMessage(uid=index + 1, sender=f'Supplier <{sender}>',
                    recipients=['inbox@example.com'], subject='维护通知', content='维护正文', received_date=datetime.now())
                email_id = self.repo.ingest(email, 'inbox@example.com')
                self.classify()
                job = self.repo.claim()
                self.complete(job, {'config':{'name':f'Supplier {index}', 'email':'model-value@example.net',
                    **config, 'email_type_samples':{'割接通知':{'subject':'维护通知','content':'维护正文'}}},
                    'evidence':[], 'unresolved_questions':[]})
                self.repo.claim()  # Keep the independent time-analysis job out of the next iteration.
                url = f"/api/supplier-drafts/{job['draft_id']}"
                draft = self.client.get(url, headers=self.headers).get_json()['data']
                draft = self.review_supplier_name(draft)
                self.assertIsNone(draft['draft']['config']['reply_email'])
                response = self.client.post(url + '/publish', headers=self.headers, json={'revision':draft['revision']})
                self.assertEqual(response.status_code, 200)
                supplier = SupplierConfigRepository(self.db).get(response.get_json()['data']['supplier_id'])
                self.assertEqual(supplier['reply_email'], sender)
                _, recipients, _ = api_server.resolve_reply_routing(self.db.get_email_record_by_id(email_id))
                self.assertEqual(recipients, [sender])

    def test_ai_invalid_or_multiple_reply_addresses_do_not_complete_draft(self):
        self.mail()
        self.classify()
        job = self.repo.claim()
        url = f"/api/supplier-drafts/{job['draft_id']}"
        original = self.client.get(url, headers=self.headers).get_json()['data']
        invalid = ('', 'not-an-address', 'a@example.com,b@example.com', 'a@example.com; b@example.com',
            'a@example.com\nb@example.com', 'a@example.com\r\nBcc: b@example.com',
            ['a@example.com'], 42)
        for address in invalid:
            with self.subTest(address=address):
                with self.assertRaisesRegex(ValueError, 'reply_email'):
                    self.complete(job, {'config':{'name':'Supplier', 'reply_email':address},
                        'evidence':[], 'unresolved_questions':[]})
                saved = self.client.get(url, headers=self.headers).get_json()['data']
                self.assertEqual(saved['revision'], original['revision'])
                self.assertEqual(saved['draft'], original['draft'])
                self.assertEqual(saved['status'], 'generating')
                with self.db.get_connection() as conn:
                    state = conn.execute('SELECT status,result_json FROM mail_ai_jobs WHERE id=?', (job['id'],)).fetchone()
                self.assertEqual(state['status'], 'running')
                self.assertIsNone(state['result_json'])

    def test_manual_reply_address_edit_does_not_apply_ai_same_sender_normalization(self):
        draft_id = self.make_draft()
        url = f'/api/supplier-drafts/{draft_id}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        response = self.client.put(url, headers=self.headers, json={'revision':draft['revision'],
            'config':{**draft['draft']['config'], 'reply_email':'noc@example.com'}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['data']['draft']['config']['reply_email'], 'noc@example.com')

    def test_draft_edit_publish_idempotency_and_conflict(self):
        draft_id = self.make_draft()
        url = f'/api/supplier-drafts/{draft_id}'
        self.assertEqual(self.client.get(url).status_code, 401)
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        config = draft['draft']['config']
        config['name'] = '人工确认名称'
        result = self.client.put(url, headers=self.headers, json={'revision': draft['revision'], 'config': config})
        self.assertEqual(result.status_code, 200)
        revised = result.get_json()['data']['revision']
        self.assertEqual(self.client.post(url + '/publish', headers=self.headers,
                                         json={'revision': draft['revision']}).status_code, 409)
        first = self.client.post(url + '/publish', headers=self.headers, json={'revision': revised})
        second = self.client.post(url + '/publish', headers=self.headers, json={'revision': revised})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json(), second.get_json())
        self.assertEqual(len(SupplierConfigRepository(self.db).list()), 1)
        self.assertEqual(self.client.put(url, headers=self.headers,
            json={'revision': revised, 'config': config}).status_code, 409)

    def test_delete_running_draft_preserves_mail_analysis_and_rejects_late_result(self):
        email_id = self.mail()
        self.classify()
        draft_job = self.repo.claim()
        time_job = self.repo.claim()
        analysis = {'analysis_status':'ready', 'scene':'emergency',
            'cutover_start':'2030-10-14T02:00:00+08:00', 'cutover_end':'2030-10-14T04:00:00+08:00',
            'assessed_at':'2030-10-13T10:00:00+08:00', 'source_timezone':'Asia/Shanghai',
            'source_time_text':'北京时间14日2至4点', 'hours_until_start':16,
            'reason':'紧急通知', 'reply':{'content':'请调整维护窗口'}}
        self.complete(time_job, analysis)
        original_mail = self.db.get_email_record_by_id(email_id)
        url = f"/api/supplier-drafts/{draft_job['draft_id']}"
        payload = {'revision':draft_job['draft_revision']}
        self.assertEqual(self.client.delete(url, json=payload).status_code, 401)
        response = self.client.delete(url, headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['data'], {'draft_id':draft_job['draft_id'], 'deleted':True})
        self.assertEqual(self.client.get(url, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.delete(url, headers=self.headers, json=payload).status_code, 404)
        self.assertEqual(self.client.get('/api/supplier-drafts', headers=self.headers).get_json()['data']['total'], 0)
        self.assertEqual(self.db.get_email_record_by_id(email_id), original_mail)
        projection = self.repo.projection(email_id)
        self.assertIsNone(projection['supplier_draft_id'])
        self.assertEqual(projection['unconfigured_analysis'], analysis)
        self.assertEqual({job['task_type'] for job in projection['ai_tasks']},
            {'unconfigured_mail_analyze', 'cutover_time_extract'})
        with self.assertRaisesRegex(ValueError, '未知任务'):
            self.complete(draft_job, {'config':{'name':'迟到草稿'}, 'evidence':[], 'unresolved_questions':[]})
        self.repo.fail(draft_job, 'late failure', transient=True)
        with self.assertRaises(ValueError):
            self.repo.retry(email_id, 'supplier_config_draft')
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM supplier_draft_samples').fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT count(*) FROM mail_ai_jobs WHERE task_type='supplier_config_draft'").fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM supplier_drafts').fetchone()[0], 0)

    def test_delete_requires_current_integer_revision(self):
        draft_id = self.make_draft()
        url = f'/api/supplier-drafts/{draft_id}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        for payload in ({}, {'revision':True}, {'revision':'1'}, {'revision':None}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.delete(url, headers=self.headers, json=payload).status_code, 400)
        edited = self.client.put(url, headers=self.headers, json={
            'revision':draft['revision'], 'config':{**draft['draft']['config'], 'name':'人工更新'}}).get_json()['data']
        self.assertEqual(self.client.delete(url, headers=self.headers,
            json={'revision':draft['revision']}).status_code, 409)
        self.assertEqual(self.client.get(url, headers=self.headers).get_json()['data'], edited)
        self.assertEqual(self.client.delete(url, headers=self.headers,
            json={'revision':edited['revision']}).status_code, 200)

    def test_delete_published_draft_keeps_active_supplier(self):
        draft_id = self.make_draft()
        url = f'/api/supplier-drafts/{draft_id}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        draft = self.review_supplier_name(draft)
        publish = self.client.post(url + '/publish', headers=self.headers, json={'revision':draft['revision']})
        self.assertEqual(publish.status_code, 200)
        supplier_id = publish.get_json()['data']['supplier_id']
        before = SupplierConfigRepository(self.db).get(supplier_id)
        self.assertEqual(self.client.delete(url, headers=self.headers,
            json={'revision':draft['revision']}).status_code, 200)
        self.assertEqual(SupplierConfigRepository(self.db).get(supplier_id), before)

    def test_deleted_draft_can_be_discovered_again_only_from_a_new_sample(self):
        draft_id = self.make_draft()
        self.repo.claim()  # Leave the independent time-analysis job running.
        url = f'/api/supplier-drafts/{draft_id}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        self.assertEqual(self.client.delete(url, headers=self.headers,
            json={'revision':draft['revision']}).status_code, 200)
        self.assertIsNone(self.repo.claim())
        new_email = self.mail(2)
        self.classify()
        new_job = self.repo.claim()
        self.assertEqual(new_job['task_type'], 'supplier_config_draft')
        self.assertNotEqual(new_job['draft_id'], draft_id)
        self.assertEqual(new_job['email_records_id'], new_email)
        new_draft = self.client.get(f"/api/supplier-drafts/{new_job['draft_id']}", headers=self.headers).get_json()['data']
        self.assertEqual([mail['id'] for mail in new_draft['samples']], [new_email])

    def test_delete_collecting_candidate_and_failed_generation(self):
        self.mail()
        self.classify('其它')
        collecting = self.client.get('/api/supplier-drafts', headers=self.headers).get_json()['data']['items'][0]
        self.assertEqual(collecting['status'], 'collecting')
        self.assertEqual(self.client.delete(f"/api/supplier-drafts/{collecting['id']}", headers=self.headers,
            json={'revision':collecting['revision']}).status_code, 200)
        self.mail(2)
        self.classify()
        job = self.repo.claim()
        self.repo.fail(job, 'Invalid model output')
        failed = self.client.get(f"/api/supplier-drafts/{job['draft_id']}", headers=self.headers).get_json()['data']
        self.assertEqual(failed['status'], 'generation_failed')
        self.assertEqual(self.client.delete(f"/api/supplier-drafts/{job['draft_id']}", headers=self.headers,
            json={'revision':failed['revision']}).status_code, 200)
        with self.assertRaises(ValueError):
            self.repo.retry(job['email_records_id'], 'supplier_config_draft')

    def test_missing_notice_sample_cannot_publish(self):
        draft_id = self.make_draft()
        url = f'/api/supplier-drafts/{draft_id}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        draft['draft']['config']['email_type_samples'] = {}
        updated = self.client.put(url, headers=self.headers,
            json={'revision': draft['revision'], 'config': draft['draft']['config']}).get_json()['data']
        response = self.client.post(url + '/publish', headers=self.headers, json={'revision': updated['revision']})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SupplierConfigRepository(self.db).list(), [])

    def test_custom_categories_can_be_added_to_draft_and_published(self):
        draft_id = self.make_draft()
        url = f'/api/supplier-drafts/{draft_id}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        draft = self.review_supplier_name(draft)
        config = draft['draft']['config']
        config['email_type_samples']['维护进展'] = {'subject': '维护进度', 'content': '已经完成一半'}
        config['email_type_samples']['故障邮件'] = {'subject': '故障通告', 'content': '人工添加的故障样本'}
        edited = self.client.put(url, headers=self.headers, json={'revision': draft['revision'], 'config': config})
        self.assertEqual(edited.status_code, 200)
        saved = edited.get_json()['data']
        self.assertIn('维护进展', saved['draft']['config']['email_type_samples'])
        response = self.client.post(url + '/publish', headers=self.headers, json={'revision': saved['revision']})
        self.assertEqual(response.status_code, 200)
        supplier = SupplierConfigRepository(self.db).get(response.get_json()['data']['supplier_id'])
        self.assertIn('维护进展', supplier['email_type_samples'])
        self.assertIn('故障邮件', supplier['email_type_samples'])
        self.assertIn('样本主题：维护进度', supplier['supplier_mail_classify_prompt'])

    def test_invalid_draft_category_names_leave_revision_and_content_unchanged(self):
        draft_id = self.make_draft()
        url = f'/api/supplier-drafts/{draft_id}'
        original = self.client.get(url, headers=self.headers).get_json()['data']
        for name in ('', '其它', ' 割接通知 ', '维护\n进展', '维护\x00进展', '类' * 33):
            with self.subTest(name=repr(name)):
                config = {**original['draft']['config'], 'email_type_samples': {
                    **original['draft']['config']['email_type_samples'], name: {'subject': '', 'content': ''}}}
                response = self.client.put(url, headers=self.headers,
                    json={'revision': original['revision'], 'config': config})
                self.assertEqual(response.status_code, 400)
                saved = self.client.get(url, headers=self.headers).get_json()['data']
                self.assertEqual(saved['revision'], original['revision'])
                self.assertEqual(saved['draft'], original['draft'])

    def test_model_generated_draft_rejects_fault_and_custom_category_samples(self):
        self.mail()
        self.classify()
        job = self.repo.claim()
        for name in ('故障邮件', '维护进展'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, '自动生成.*分类'):
                self.complete(job, {'config': {'name': 'Supplier', 'prompt_mode': 'auto',
                    'email_type_samples': {name: {'subject': '主题', 'content': '正文'}}},
                    'evidence': [], 'unresolved_questions': []})
        draft = self.client.get(f"/api/supplier-drafts/{job['draft_id']}", headers=self.headers).get_json()['data']
        self.assertEqual(draft['status'], 'generating')
        self.assertIsNone(draft['draft'])
        self.complete(job, {'config': {'name': 'Supplier', 'prompt_mode': 'auto',
            'email_type_samples': {'割接通知': {'subject': '维护通知', 'content': ''}}},
            'evidence': [], 'unresolved_questions': ['补充割接通知正文样本']})
        draft = self.client.get(f"/api/supplier-drafts/{job['draft_id']}", headers=self.headers).get_json()['data']
        self.assertEqual(draft['status'], 'review')
        self.assertEqual(draft['draft']['config']['email_type_samples']['割接通知']['subject'], '维护')
        self.assertEqual(draft['draft']['config']['email_type_samples']['割接通知']['content'], '维护正文')

    def test_model_generated_draft_rejects_unknown_fixed_fields_without_mutation(self):
        self.mail()
        self.classify()
        job = self.repo.claim()
        url = f"/api/supplier-drafts/{job['draft_id']}"
        original = self.client.get(url, headers=self.headers).get_json()['data']
        for field in ('unknown_field', '__proto__', 'constructor'):
            with self.subTest(field=field):
                result = {'config': {'name':'Supplier', 'prompt_mode':'auto',
                    'fixed_field_rules':{field:'不应接受的规则'},
                    'email_type_samples':{'割接通知':{'subject':'维护通知','content':'维护正文'}}},
                    'evidence':[], 'unresolved_questions':[]}
                with self.assertRaisesRegex(ValueError, '未知的固定字段'):
                    self.complete(job, result)
                saved = self.client.get(url, headers=self.headers).get_json()['data']
                self.assertEqual(saved['revision'], original['revision'])
                self.assertEqual(saved['draft'], original['draft'])
                self.assertEqual(saved['status'], 'generating')
                with self.db.get_connection() as conn:
                    state = conn.execute('SELECT status,result_json FROM mail_ai_jobs WHERE id=?',
                        (job['id'],)).fetchone()
                    self.assertEqual(state['status'], 'running')
                    self.assertFalse(state['result_json'])

    def test_manual_unknown_fixed_fields_leave_draft_revision_and_content_unchanged(self):
        draft_id = self.make_draft()
        url = f'/api/supplier-drafts/{draft_id}'
        for field in ('unknown_field', '__proto__', 'constructor'):
            with self.subTest(field=field):
                original = self.client.get(url, headers=self.headers).get_json()['data']
                config = {**original['draft']['config'], 'fixed_field_rules':{field:'不应接受的规则'}}
                response = self.client.put(url, headers=self.headers,
                    json={'revision':original['revision'], 'config':config})
                self.assertEqual(response.status_code, 400)
                self.assertIn('未知的固定字段', response.get_json()['message'])
                saved = self.client.get(url, headers=self.headers).get_json()['data']
                self.assertEqual(saved['revision'], original['revision'])
                self.assertEqual(saved['draft'], original['draft'])
                self.assertEqual(saved['status'], original['status'])

    def test_fixed_field_rules_survive_draft_edit_and_publish_with_defaults(self):
        definitions = get_fixed_field_definitions()
        defaults = {field['name']:field['description']
            for group in definitions.values() for field in group}
        rules = {
            'carrier_ticket_no':defaults['carrier_ticket_no'] + '\n\n供应商补充：优先读取邮件标题中的 Maintenance ID。',
            'ImpactDuration':defaults['ImpactDuration'] + '\n\n供应商补充：本供应商的每次中断窗口位于 Service Outage 表格。',
        }
        self.mail()
        self.classify()
        job = self.repo.claim()
        self.complete(job, {'config':{'name':'Supplier with field rules', 'prompt_mode':'auto',
            'fixed_field_rules':rules,
            'email_type_samples':{'割接通知':{'subject':'维护通知','content':'维护正文'}}},
            'evidence':['原文存在 Maintenance ID 和 Service Outage 字段'], 'unresolved_questions':[]})
        url = f"/api/supplier-drafts/{job['draft_id']}"
        original = self.client.get(url, headers=self.headers).get_json()['data']
        original = self.review_supplier_name(original)
        self.assertEqual(original['draft']['config']['fixed_field_rules'], rules)
        edited_rules = {**rules, 'carrier_ticket_no':rules['carrier_ticket_no'] + '\n人工确认：没有 Maintenance ID 时使用正文 No 字段。'}
        config = {**original['draft']['config'], 'fixed_field_rules':edited_rules}
        response = self.client.put(url, headers=self.headers,
            json={'revision':original['revision'], 'config':config})
        self.assertEqual(response.status_code, 200)
        edited = self.client.get(url, headers=self.headers).get_json()['data']
        self.assertEqual(edited['draft']['config']['fixed_field_rules'], edited_rules)
        self.assertEqual(edited['revision'], original['revision'] + 1)
        response = self.client.post(url + '/publish', headers=self.headers, json={'revision':edited['revision']})
        self.assertEqual(response.status_code, 200)
        supplier = SupplierConfigRepository(self.db).get(response.get_json()['data']['supplier_id'])
        self.assertEqual(supplier['fixed_field_rules'], edited_rules)
        for rule in edited_rules.values():
            self.assertIn(rule, supplier['cutover_extract_prompt'])
        self.assertNotIn('cutover_timezone', supplier['fixed_field_rules'])
        self.assertIn(defaults['cutover_timezone'], supplier['cutover_extract_prompt'])
        self.assertIn(defaults['ImpactType'], supplier['cutover_extract_prompt'])

    def test_direct_ai_rules_replace_inapplicable_defaults_through_review_publish_and_forward(self):
        subject = 'Planned Maintenance Notification'
        body = ('Maintenance Reference: MR-2030-001\nService ID: CCT-1001\n'
            'Impact: service interruption\nDuration: 15 minutes\n'
            'Maintenance Reason: Router software upgrade\nLocation: Hong Kong')
        email = EmailMessage(uid=1, sender='noc@example.com', recipients=['inbox@example.com'],
            subject=subject, content=body, received_date=datetime.now())
        email_id = self.repo.ingest(email, 'inbox@example.com')
        defaults = get_fixed_field_definitions()
        default_rules = {field['name']:field['description']
            for fields in defaults.values() for field in fields}
        rules = {
            'carrier_ticket_no':'从 Maintenance Reference 标签后的值提取运营商单号；不得使用 Service ID 电路编号，未提供时返回空字符串。',
            'ImpactDuration':'从描述实际业务中断的 Duration 字段读取时长，按原文单位换算为分钟并输出整数加 m。'
                '明确时长不依赖中断起止时间；只有起止时间时才计算差值，不得把维护窗口视为中断。'
                '明确有保护时返回 0m；多次等长中断输出单次时长；两种时长证据均缺失时返回空字符串。',
            'ImpactType':'明确有保护或不会中断时返回 protected；否则使用明确 Duration 或实际中断起止时间得到的单次分钟数乘以次数。'
                '总分钟数小于 5 返回 momentary_interrupted，大于等于 5 返回 interrupted；不能确定时返回空字符串。',
            'cutover_timezone':'',
        }
        evidence = [
            'carrier_ticket_no：Maintenance Reference 与默认 No 标签不匹配，改为完整的标签提取规则。',
            'cutover_time：未提供时间，默认规则的无法确定则留空分支适用。',
            'cutover_backup_time：未提供备用时间，默认留空分支适用。',
            'cutover_timezone：未提供时区，默认无法转换则留空分支适用。',
            'cutover_reason：Maintenance Reason 已被默认关键词覆盖。',
            'location：Location 已被默认关键词覆盖。',
            'ImpactType：有明确 Duration 但没有起止时间，完整重写时长来源并保留枚举与 5 分钟阈值。',
            'ImpactDateTime：没有影响窗口，沿用默认引用 cutover_time 的规则。',
            'ImpactDuration：Duration 为明确业务中断时长，替换缺少起止即留空的默认规则。',
            'InteruptionsCounts：原文没有多次中断，默认次数 1 适用。',
        ]
        draft_result = {'config':{'name':'Reference supplier', 'fixed_field_rules':rules,
            'email_type_samples':{'割接通知':{'subject':subject, 'content':body}}},
            'evidence':evidence, 'unresolved_questions':['需补充实际割接时间与来源时区。']}
        tasks = []
        def answer(_url, **kwargs):
            content = json.loads(kwargs['json']['messages'][0]['content'])
            self.assertEqual(content['content'], body)
            self.assertEqual(content['email_records_id'], email_id)
            tasks.append(content['task_type'])
            self.assertEqual(content['task_type'], 'unconfigured_mail_process')
            self.assertEqual(content['fixed_field_defaults']['top_fields'], defaults['top_fields'])
            self.assertEqual(content['fixed_field_defaults']['line_fields'], defaults['line_fields'])
            result = {'classification': {'status':'succeeded', 'result': {
                'mail_type':'割接通知', 'classification_reason':'首次维护通知', 'needs_review':False}},
                'supplier_draft': {'status':'succeeded', 'result':draft_result},
                'time_analysis': {'status':'failed', 'error':'样本缺少时间'}}
            envelope = {key:content[key] for key in
                ('schema_version','task_type','request_id','attempt_id','email_records_id')}
            envelope['result'] = result
            return Mock(ok=True, json=lambda:{'choices':[{'message':{'role':'assistant',
                'content':json.dumps(envelope, ensure_ascii=False)}}]})
        worker = MailAIWorker(self.db)
        with patch('unconfigured_mail_worker.requests.post', side_effect=answer):
            self.assertTrue(worker.run_once())
            self.assertFalse(worker.run_once())
        self.assertEqual(tasks, ['unconfigured_mail_process'])
        draft_id = self.repo.projection(email_id)['supplier_draft_id']
        url = f'/api/supplier-drafts/{draft_id}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        draft = self.review_supplier_name(draft)
        self.assertEqual(draft['status'], 'review')
        self.assertEqual(draft['draft']['config']['fixed_field_rules'], rules)
        self.assertEqual(draft['draft']['config']['prompt_mode'], 'auto')
        self.assertEqual(draft['draft']['evidence'], evidence)
        self.assertNotIn('fixed_field_supplements', draft['draft'])
        edited_rules = {**rules, 'ImpactDuration':rules['ImpactDuration'] + '人工确认：Duration 属于当前 Service ID 对应线路。'}
        response = self.client.put(url, headers=self.headers, json={'revision':draft['revision'],
            'config':{**draft['draft']['config'], 'fixed_field_rules':edited_rules}})
        self.assertEqual(response.status_code, 200)
        edited = self.client.get(url, headers=self.headers).get_json()['data']
        self.assertEqual(edited['draft']['config']['fixed_field_rules'], edited_rules)
        self.assertEqual(edited['draft']['evidence'], evidence)
        self.assertEqual(edited['revision'], draft['revision'] + 1)
        response = self.client.post(url + '/publish', headers=self.headers, json={'revision':edited['revision']})
        self.assertEqual(response.status_code, 200)
        supplier = SupplierConfigRepository(self.db).get(response.get_json()['data']['supplier_id'])
        self.assertEqual(supplier['prompt_mode'], 'auto')
        self.assertEqual(supplier['fixed_field_rules'], edited_rules)
        prompt = supplier['cutover_extract_prompt']
        for name, rule in edited_rules.items():
            if rule:
                self.assertIn(rule, prompt)
                self.assertNotIn(default_rules[name], prompt)
        for name in set(default_rules) - {'carrier_ticket_no','ImpactDuration','ImpactType'}:
            self.assertIn(default_rules[name], prompt)
        self.assertNotIn('* No:', prompt)
        self.assertNotIn('缺少可计算的中断起止时间时返回空字符串', prompt)
        self.assertNotIn('供应商补充提取规则', prompt)
        record = self.db.get_email_record_by_id(email_id)
        forwarded = json.loads(APIForwardAction(self.db)._build_content(
            email_message_from_record(record), {'_email_records_id':email_id}))
        self.assertEqual(forwarded['supplier_cutover_extract_prompt'], prompt)

    def test_invalid_direct_ai_rule_types_do_not_change_generating_draft(self):
        self.mail()
        self.classify()
        job = self.repo.claim()
        url = f"/api/supplier-drafts/{job['draft_id']}"
        original = self.client.get(url, headers=self.headers).get_json()['data']
        invalid = (None, [], '完整规则', {'carrier_ticket_no':None},
            {'ImpactDuration':15}, {'ImpactType':True}, {'carrier_ticket_no':{'rule':'嵌套规则'}})
        for rules in invalid:
            with self.subTest(rules=rules):
                with self.assertRaisesRegex(ValueError, 'fixed_field_rules'):
                    self.complete(job, {'config':{'name':'Supplier', 'fixed_field_rules':rules},
                        'evidence':[], 'unresolved_questions':[]})
                saved = self.client.get(url, headers=self.headers).get_json()['data']
                self.assertEqual(saved['revision'], original['revision'])
                self.assertEqual(saved['draft'], original['draft'])
                self.assertEqual(saved['status'], original['status'])

    def test_legacy_fixed_field_supplements_merge_defaults_before_publish(self):
        definitions = get_fixed_field_definitions()
        defaults = {field['name']:field['description']
            for group in definitions.values() for field in group}
        additions = {'carrier_ticket_no':'优先读取邮件标题中的 Maintenance ID。',
            'ImpactDuration':'该供应商的实际中断起止时间位于 Service Outage 表格。'}
        self.mail()
        self.classify()
        job = self.repo.claim()
        self.complete(job, {'config':{'name':'Supplier with supplemental rules', 'prompt_mode':'auto',
            'fixed_field_rules':{},
            'email_type_samples':{'割接通知':{'subject':'维护通知','content':'维护正文'}}},
            'fixed_field_supplements':{**additions, 'cutover_timezone':'', 'location':defaults['location']},
            'evidence':['标题单号及独立线路影响表格'], 'unresolved_questions':[]})
        url = f"/api/supplier-drafts/{job['draft_id']}"
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        draft = self.review_supplier_name(draft)
        merged_rules = draft['draft']['config']['fixed_field_rules']
        self.assertEqual(set(merged_rules), set(additions))
        for name, rule in merged_rules.items():
            self.assertIn(defaults[name], rule)
            self.assertIn(additions[name], rule)
            self.assertIn('明确列出的来源或条件优先适用', rule)
            self.assertIn('未涉及部分沿用默认规则', rule)
            self.assertIn('不得改变输出结构', rule)
            self.assertIn('UTC 转换', rule)
            self.assertIn('判定阈值及无证据不推断', rule)
        self.assertNotIn('fixed_field_supplements', draft['draft'])
        self.assertNotIn('fixed_field_supplements', draft['draft']['config'])
        response = self.client.post(url + '/publish', headers=self.headers, json={'revision':draft['revision']})
        self.assertEqual(response.status_code, 200)
        supplier = SupplierConfigRepository(self.db).get(response.get_json()['data']['supplier_id'])
        self.assertEqual(supplier['fixed_field_rules'], merged_rules)
        for rule in merged_rules.values():
            self.assertIn(rule, supplier['cutover_extract_prompt'])
        self.assertIn(defaults['cutover_timezone'], supplier['cutover_extract_prompt'])
        self.assertIn(defaults['location'], supplier['cutover_extract_prompt'])

    def test_legacy_fixed_supplement_protocol_rejects_manual_prompt_mode(self):
        self.mail()
        self.classify()
        job = self.repo.claim()
        url = f"/api/supplier-drafts/{job['draft_id']}"
        original = self.client.get(url, headers=self.headers).get_json()['data']
        with self.assertRaises(ValueError):
            self.complete(job, {'config':{'name':'Supplier', 'prompt_mode':'manual',
                'cutover_extract_prompt':'自定义提示词将绕过固定字段规则。', 'fixed_field_rules':{}},
                'fixed_field_supplements':{'carrier_ticket_no':'优先读取 Maintenance Reference。'},
                'evidence':[], 'unresolved_questions':[]})
        saved = self.client.get(url, headers=self.headers).get_json()['data']
        self.assertEqual(saved['revision'], original['revision'])
        self.assertEqual(saved['draft'], original['draft'])
        self.assertEqual(saved['status'], original['status'])

    def test_legacy_fixed_supplement_protocol_defaults_to_publishable_auto_mode(self):
        self.mail()
        self.classify()
        job = self.repo.claim()
        self.complete(job, {'config':{'name':'Supplier with implicit auto mode', 'fixed_field_rules':{},
            'email_type_samples':{'割接通知':{'subject':'维护通知','content':'维护正文'}}},
            'fixed_field_supplements':{'carrier_ticket_no':'优先读取 Maintenance Reference。'},
            'evidence':[], 'unresolved_questions':[]})
        url = f"/api/supplier-drafts/{job['draft_id']}"
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        draft = self.review_supplier_name(draft)
        self.assertEqual(draft['draft']['config']['prompt_mode'], 'auto')
        response = self.client.post(url + '/publish', headers=self.headers, json={'revision':draft['revision']})
        self.assertEqual(response.status_code, 200)
        supplier = SupplierConfigRepository(self.db).get(response.get_json()['data']['supplier_id'])
        self.assertEqual(supplier['prompt_mode'], 'auto')
        self.assertIn('优先读取 Maintenance Reference。', supplier['cutover_extract_prompt'])

    def test_legacy_manual_draft_result_and_human_edit_remain_publishable(self):
        self.mail()
        self.classify()
        job = self.repo.claim()
        manual_prompt = '按人工配置提取维护邮件字段，无法识别时留空。'
        self.complete(job, {'config':{'name':'Legacy manual supplier', 'prompt_mode':'manual',
            'cutover_extract_prompt':manual_prompt,
            'email_type_samples':{'割接通知':{'subject':'维护通知','content':'维护正文'}}},
            'evidence':[], 'unresolved_questions':[]})
        url = f"/api/supplier-drafts/{job['draft_id']}"
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        draft = self.review_supplier_name(draft)
        self.assertEqual(draft['draft']['config']['cutover_extract_prompt'], manual_prompt)
        edited_prompt = manual_prompt + '\n工单号使用 Maintenance ID 标签。'
        config = {**draft['draft']['config'], 'cutover_extract_prompt':edited_prompt}
        response = self.client.put(url, headers=self.headers,
            json={'revision':draft['revision'], 'config':config})
        self.assertEqual(response.status_code, 200)
        edited = response.get_json()['data']
        response = self.client.post(url + '/publish', headers=self.headers, json={'revision':edited['revision']})
        self.assertEqual(response.status_code, 200)
        supplier = SupplierConfigRepository(self.db).get(response.get_json()['data']['supplier_id'])
        self.assertEqual(supplier['prompt_mode'], 'manual')
        self.assertEqual(supplier['cutover_extract_prompt'], edited_prompt)

    def test_unknown_fixed_field_supplements_cannot_change_draft(self):
        self.mail()
        self.classify()
        job = self.repo.claim()
        url = f"/api/supplier-drafts/{job['draft_id']}"
        original = self.client.get(url, headers=self.headers).get_json()['data']
        for field in ('unknown_field', '__proto__', 'constructor'):
            with self.subTest(field=field):
                result = {'config':{'name':'Supplier', 'prompt_mode':'auto', 'fixed_field_rules':{}},
                    'fixed_field_supplements':{field:'不能接受的补充'},
                    'evidence':[], 'unresolved_questions':[]}
                with self.assertRaisesRegex(ValueError, '未知的固定字段'):
                    self.complete(job, result)
                saved = self.client.get(url, headers=self.headers).get_json()['data']
                self.assertEqual(saved['revision'], original['revision'])
                self.assertEqual(saved['draft'], original['draft'])
                self.assertEqual(saved['status'], original['status'])

    def test_generated_draft_cannot_mix_complete_rules_with_supplements(self):
        self.mail()
        self.classify()
        job = self.repo.claim()
        url = f"/api/supplier-drafts/{job['draft_id']}"
        original = self.client.get(url, headers=self.headers).get_json()['data']
        with self.assertRaises(ValueError):
            self.complete(job, {'config':{'name':'Supplier', 'prompt_mode':'auto',
                'fixed_field_rules':{'carrier_ticket_no':'完整替换规则'}},
                'fixed_field_supplements':{'ImpactDuration':'供应商补充规则'},
                'evidence':[], 'unresolved_questions':[]})
        saved = self.client.get(url, headers=self.headers).get_json()['data']
        self.assertEqual(saved['revision'], original['revision'])
        self.assertEqual(saved['draft'], original['draft'])
        self.assertEqual(saved['status'], original['status'])

    def test_invalid_fixed_supplement_types_do_not_change_generated_draft(self):
        self.mail()
        self.classify()
        job = self.repo.claim()
        url = f"/api/supplier-drafts/{job['draft_id']}"
        original = self.client.get(url, headers=self.headers).get_json()['data']
        invalid = (None, [], '补充规则', {'carrier_ticket_no':None},
            {'ImpactDuration':15}, {'carrier_ticket_no':{'rule':'嵌套规则'}})
        for supplements in invalid:
            with self.subTest(supplements=supplements):
                with self.assertRaisesRegex(ValueError, 'fixed_field_supplements'):
                    self.complete(job, {'config':{'name':'Supplier', 'prompt_mode':'auto', 'fixed_field_rules':{}},
                        'fixed_field_supplements':supplements, 'evidence':[], 'unresolved_questions':[]})
                saved = self.client.get(url, headers=self.headers).get_json()['data']
                self.assertEqual(saved['revision'], original['revision'])
                self.assertEqual(saved['draft'], original['draft'])
                self.assertEqual(saved['status'], original['status'])

    def test_invalid_manual_fixed_rule_types_do_not_change_review_draft(self):
        draft_id = self.make_draft()
        url = f'/api/supplier-drafts/{draft_id}'
        original = self.client.get(url, headers=self.headers).get_json()['data']
        invalid = (None, [], '完整规则', {'carrier_ticket_no':None},
            {'ImpactDuration':15}, {'carrier_ticket_no':{'rule':'嵌套规则'}})
        for rules in invalid:
            with self.subTest(rules=rules):
                config = {**original['draft']['config'], 'fixed_field_rules':rules}
                response = self.client.put(url, headers=self.headers,
                    json={'revision':original['revision'], 'config':config})
                self.assertEqual(response.status_code, 400)
                self.assertIn('fixed_field_rules', response.get_json()['message'])
                saved = self.client.get(url, headers=self.headers).get_json()['data']
                self.assertEqual(saved['revision'], original['revision'])
                self.assertEqual(saved['draft'], original['draft'])
                self.assertEqual(saved['status'], original['status'])

    def test_time_callback_survives_reply_cancel_and_repeated_delivery(self):
        record_id = self.mail()
        self.classify()
        self.repo.claim()  # Configuration and analysis are independent jobs.
        job = self.repo.claim()
        result = {'analysis_status': 'ready', 'scene': 'emergency',
            'cutover_start': '2026-10-14T02:00:00+08:00', 'cutover_end': '2026-10-14T04:00:00+08:00',
            'assessed_at': '2026-10-13T10:00:00+08:00', 'source_timezone': 'Asia/Shanghai',
            'source_time_text': '北京时间 14 日 2 点至 4 点', 'hours_until_start': 16,
            'reason': '工作流紧急阈值', 'reply': {'content': '请调整维护窗口'}}
        envelope = {key: job[key] for key in ('task_type', 'request_id', 'attempt_id', 'email_records_id')}
        envelope.update(schema_version=1, result=result)
        self.assertEqual(self.client.post('/api/unconfigured-mail/results', json=envelope).status_code, 401)
        response = self.client.post('/api/unconfigured-mail/results', headers=self.headers, json=envelope)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.get_email_record_by_id(record_id)['reply_status'], 'pending')
        self.db.cancel_pending_reply(record_id)
        self.client.post('/api/unconfigured-mail/results', headers=self.headers, json=envelope)
        saved = self.db.get_email_record_by_id(record_id)
        self.assertEqual(saved['reply_status'], 'cancelled')
        self.assertEqual(json.loads(saved['unconfigured_analysis_json'])['scene'], 'emergency')
        self.repo.fail(job, 'outer request timed out', transient=True)
        self.assertEqual(self.repo.projection(record_id)['ai_tasks'][-1]['status'], 'succeeded')

    def test_non_notice_stays_out_of_cutover_list_after_publish(self):
        other_id = self.mail(2)
        self.classify('故障邮件')
        draft_id = self.make_draft()
        url = f'/api/supplier-drafts/{draft_id}'
        draft = self.client.get(url, headers=self.headers).get_json()['data']
        revision = self.review_supplier_name(draft)['revision']
        self.assertEqual(self.client.post(url + '/publish', headers=self.headers,
                                         json={'revision':revision}).status_code, 200)
        result = self.client.get('/api/cutover/emails', headers=self.headers).get_json()['data']
        self.assertEqual(result['total'], 1)
        self.assertNotIn(other_id, [row['id'] for row in result['items']])
        self.assertEqual(self.client.get(f'/api/cutover/emails/{other_id}', headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get(f'/api/emails/{other_id}/source', headers=self.headers).status_code, 200)

    def test_failed_classification_is_accessible_and_retryable_from_raw_mail(self):
        record_id = self.mail()
        self.repo.fail(self.repo.claim(), '结果结构无效')
        result = self.client.get('/api/email-records', headers=self.headers).get_json()['data']
        row = next(row for row in result['items'] if row['id'] == record_id)
        self.assertEqual(row['ai_tasks'][0]['status'], 'failed')
        self.assertEqual(self.client.post(f'/api/emails/{record_id}/analysis-retry', headers=self.headers,
            json={'task_type':'unconfigured_mail_analyze'}).status_code, 200)
        self.assertEqual(self.repo.claim()['attempts'], 1)

    def test_wrong_email_and_attempt_callback_leave_reply_untouched(self):
        record_id = self.mail()
        self.classify()
        self.repo.claim()
        job = self.repo.claim()
        envelope = {key:job[key] for key in ('task_type','request_id','attempt_id','email_records_id')}
        envelope.update(schema_version=1, result={'analysis_status':'needs_review','scene':None,'reply':None,
            'reason':'时区不明','assessed_at':'2026-10-13T00:00:00Z'})
        for field, value in [('email_records_id', record_id + 1), ('attempt_id', 'old-attempt')]:
            response = self.client.post('/api/unconfigured-mail/results', headers=self.headers,
                                        json={**envelope, field:value})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.get_email_record_by_id(record_id)['reply_status'], '')
        self.assertEqual(self.repo.projection(record_id)['ai_tasks'][-1]['status'], 'running')

    def test_uncertain_smtp_result_cannot_be_resent_by_repeated_confirmation(self):
        record_id = self.mail()
        self.db.save_pending_reply(record_id, '请调整维护窗口', 'emergency')
        client = Mock()
        client.reply_email.side_effect = TimeoutError('smtp timeout')
        body = {'email_records_id':record_id, 'recipients':['noc@example.com']}
        with patch.object(api_server, 'build_reply_email_client', return_value=client):
            first = self.client.post('/api/cutover/reply/confirm', headers=self.headers, json=body)
            second = self.client.post('/api/cutover/reply/confirm', headers=self.headers, json=body)
        self.assertEqual(first.status_code, 500)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(client.reply_email.call_count, 1)
        self.assertEqual(self.db.get_email_record_by_id(record_id)['reply_status'], 'send_uncertain')
