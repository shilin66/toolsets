import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('API_KEY', 'test-key')

import api_server
from database import EmailDatabase
from user_access import UserAccessRepository


class UserAccessApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = EmailDatabase(str(Path(self.temp.name) / 'test.db'))
        for name, value in [('email_db', self.db), ('API_KEY', 'test-key')]:
            replacement = patch.object(api_server, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.repo = UserAccessRepository(self.db)
        self.user = self.repo.create_user('alice', 'a-secure-password', '张三')
        self.accounts, self.emails, self.tasks = [], [], []
        for address in ('one@example.com', 'two@example.com'):
            self.accounts.append(self.db.add_mail_account({'email_address': address, 'imap_server': 'example.com'}))
            self.db.add_email_record(123, receiver=address, subject=address, content='test')
            email = self.db.get_email_record(123, receiver=address)
            self.emails.append(email['id'])
            self.tasks.append(self.db.upsert_cutover_task(email_records_id=email['id'], fill_result={'circuits': []}))
        self.repo.set_grants(self.user['id'], [{'account_id': self.accounts[0], 'can_operate': True}])
        self.client = api_server.app.test_client()
        self.admin_headers = {'Authorization': 'Bearer test-key'}

    def login(self):
        response = self.client.post('/api/auth/login', json={'username': 'alice', 'password': 'a-secure-password'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        return {'X-CSRF-Token': response.get_json()['data']['csrf_token']}

    def test_api_key_admin_cannot_use_personal_portal_or_submit_reports(self):
        paths = [
            ('GET', '/api/rpa/session', None), ('HEAD', '/api/rpa/session?environment=production', None),
            ('DELETE', '/api/rpa/session', None),
            ('POST', '/api/rpa/session/attempts', {'mode': 'password'}),
            ('POST', '/api/rpa/session/attempts/old/captcha', {}),
            ('POST', '/api/rpa/session/attempts/old/password', {'username': 'portal', 'password': 'secret', 'captcha': '42'}),
            ('POST', '/api/rpa/session/attempts/old/sms', {'phone': '123', 'password': 'secret', 'captcha': '42'}),
            ('POST', '/api/rpa/session/attempts/old/sms/verify', {'sms_code': '42'}),
            ('POST', f'/api/cutover/tasks/{self.tasks[0]}/report', {'environment': 'production'}),
        ]
        response = self.client.post('/api/auth/login', json={'mode': 'admin', 'api_key': 'test-key'})
        cookie_headers = {'X-CSRF-Token': response.get_json()['data']['csrf_token']}
        with patch.object(api_server, 'get_portal_session_service') as portal, patch.object(api_server, 'submit_cutover_report_job') as submit:
            for headers in (self.admin_headers, cookie_headers):
                for method, path, body in paths:
                    with self.subTest(method=method, path=path, bearer=bool(headers.get('Authorization'))):
                        result = self.client.open(path, method=method, headers=headers, json=body)
                        self.assertEqual(result.status_code, 403)
                        if method != 'HEAD':
                            self.assertIn('普通用户', result.get_json()['message'])
            portal.assert_not_called()
            submit.assert_not_called()
        self.assertEqual(self.db.get_cutover_reports(self.tasks[0]), [])
        self.assertEqual(self.client.get('/api/users').status_code, 200)
        self.assertEqual(self.client.get('/api/system/mail-accounts').status_code, 200)

    def test_cookie_login_filters_history_counts_and_tasks(self):
        self.login()
        mails = self.client.get('/api/email-records').get_json()['data']
        self.assertEqual(mails['total'], 1)
        self.assertEqual(mails['items'][0]['id'], self.emails[0])
        tasks = self.client.get('/api/cutover/tasks').get_json()['data']
        self.assertEqual(tasks['total'], 1)
        self.assertEqual(tasks['items'][0]['id'], self.tasks[0])
        summary = self.client.get('/api/dashboard/summary').get_json()['data']
        self.assertEqual(summary['pending_tasks'], 1)
        self.assertEqual(summary['today_emails'], 1)
        filtered = self.client.get('/api/email-records?receiver=two@example.com').get_json()['data']
        self.assertEqual(filtered['total'], 0)

    def test_direct_ids_and_user_management_endpoints_are_denied(self):
        headers = self.login()
        for path in (f'/api/cutover/tasks/{self.tasks[1]}', f'/api/cutover/tasks/{self.tasks[1]}/excel',
                     f'/api/cutover/emails/{self.emails[1]}', f'/api/emails/{self.emails[1]}/source',
                     '/api/users', f'/api/users/{self.user["id"]}/mailboxes'):
            with self.subTest(path=path):
                self.assertIn(self.client.get(path).status_code, (403, 404))
        response = self.client.post('/api/cutover/reply/cancel', json={'email_id': 123}, headers=headers)
        self.assertEqual(response.status_code, 400)
        for method, path, body in (
            ('post', '/api/users', {'username': 'escalated', 'password': 'new-password'}),
            ('patch', f'/api/users/{self.user["id"]}', {'enabled': False}),
            ('put', f'/api/users/{self.user["id"]}/mailboxes', {'grants': []}),
            ('delete', f'/api/users/{self.user["id"]}/portal-session', {}),
        ):
            with self.subTest(path=path, method=method):
                self.assertEqual(getattr(self.client, method)(path, json=body, headers=headers).status_code, 403)

    def test_regular_user_can_manage_shared_business_configuration(self):
        headers = self.login()
        preview = self.client.post('/api/suppliers/sample-preview', headers=headers,
                                   json={'content':'<p>Caller-provided sample</p>'})
        self.assertEqual(preview.status_code, 200)
        self.assertIn('Caller-provided sample', preview.get_json()['data']['preview_html'])
        for path in ('/api/system/settings', '/api/suppliers',
                     '/api/suppliers/mail-types', '/api/suppliers/field-defaults', '/api/circuits',
                     '/api/circuits/export', '/api/supplier-drafts'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.get_json(silent=True))
                response.close()
        response = self.client.post('/api/circuits', headers=headers, json={
            'supplier': 'Shared', 'supplier_circuit_id': 'shared-1', 'circuit_id': 'C-1', 'line_type': '骨干'})
        self.assertEqual(response.status_code, 201)
        circuit_id = response.get_json()['data']['id']
        self.assertEqual(self.client.patch(f'/api/circuits/{circuit_id}', headers=headers,
                                          json={'remark': '普通用户编辑'}).status_code, 200)
        self.assertEqual(self.client.delete(f'/api/circuits/{circuit_id}', headers=headers).status_code, 200)
        response = self.client.post('/api/suppliers', headers=headers, json={
            'name': '共享供应商', 'email': 'supplier@example.com', 'prompt_mode': 'auto',
            'email_type_samples': {'割接通知': {'subject': '维护', 'content': '维护通知'}}})
        self.assertEqual(response.status_code, 201, response.get_json())
        supplier_id = response.get_json()['data']['id']
        self.assertEqual(self.client.patch(f'/api/suppliers/{supplier_id}', headers=headers,
                                          json={'name': '修改共享供应商'}).status_code, 200)
        self.assertEqual(self.client.delete(f'/api/suppliers/{supplier_id}', headers=headers).status_code, 200)
        from unconfigured_mail import DISCOVERY
        self.assertEqual(self.client.put('/api/system/settings', headers=headers, json={DISCOVERY: True}).status_code, 200)

    def make_access_draft(self, name, samples, source=None):
        config = {'name': name, 'prompt_mode': 'auto',
                  'email_type_samples': {'割接通知': {'subject': '共享配置样本', 'content': '维护规则'}}}
        with self.db.get_connection() as conn:
            draft_id = conn.execute("""INSERT INTO supplier_drafts
                (candidate_key,sender,status,draft_json,revision,source_email_records_id,create_time,update_time)
                VALUES (?,?,'review',?,1,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
                (name, name + '@example.com', json.dumps({'config': config}), source)).lastrowid
            conn.executemany('INSERT INTO supplier_draft_samples VALUES (?,?)', [(draft_id, item) for item in samples])
            conn.commit()
        return draft_id, config

    def test_any_authorized_source_grants_draft_access_but_original_mails_stay_scoped(self):
        own, _ = self.make_access_draft('own', [self.emails[0]])
        mixed, _ = self.make_access_draft('mixed', self.emails, self.emails[1])
        private, _ = self.make_access_draft('private', [self.emails[1]])
        empty, _ = self.make_access_draft('empty', [])
        headers = self.login()
        pages = [self.client.get(f'/api/supplier-drafts?pageSize=1&page={page}').get_json()['data'] for page in (1, 2)]
        self.assertEqual([page['total'] for page in pages], [2, 2])
        self.assertEqual({item['id'] for page in pages for item in page['items']}, {own, mixed})
        self.assertTrue(all(item['sample_count'] == 1 for page in pages for item in page['items']))
        detail = self.client.get(f'/api/supplier-drafts/{mixed}?pageSize=1').get_json()['data']
        self.assertEqual([mail['id'] for mail in detail['samples']], [self.emails[0]])
        self.assertEqual(detail['sample_count'], 1)
        self.assertEqual(sum(detail['sample_counts'].values()), 1)
        self.assertEqual(self.client.get(f'/api/supplier-drafts/{mixed}?pageSize=1&page=2').get_json()['data']['samples'], [])
        self.assertEqual(detail['draft']['config']['name'], 'mixed')
        for draft in (private, empty):
            self.assertEqual(self.client.get(f'/api/supplier-drafts/{draft}').status_code, 404)
        self.assertEqual(self.client.get(f'/api/emails/{self.emails[1]}/source').status_code, 404)
        self.assertEqual(self.client.post('/api/suppliers/sample-attachment-source', headers=headers,
                         json={'source_email_records_id': self.emails[1]}).status_code, 404)
        admin = self.client.get(f'/api/supplier-drafts/{mixed}', headers=self.admin_headers).get_json()['data']
        self.assertEqual(admin['sample_count'], 2)
        self.assertEqual({mail['id'] for mail in admin['samples']}, set(self.emails))

    def test_received_mail_grants_access_even_when_not_selected_as_draft_sample(self):
        draft, _ = self.make_access_draft('capped', [self.emails[1]], self.emails[1])
        with self.db.get_connection() as conn:
            conn.execute("UPDATE email_records SET sender='CAPPED@example.com' WHERE id=?", (self.emails[0],))
            conn.commit()
        self.login()
        detail = self.client.get(f'/api/supplier-drafts/{draft}').get_json()['data']
        self.assertEqual(detail['id'], draft)
        self.assertEqual(detail['samples'], [])
        self.assertEqual(detail['sample_count'], 0)
        self.repo.set_grants(self.user['id'], [])
        self.assertEqual(self.client.get(f'/api/supplier-drafts/{draft}').status_code, 404)
        self.assertEqual(self.client.get('/api/supplier-drafts').get_json()['data']['total'], 0)

    def test_any_operable_source_allows_edit_publish_delete_and_retry_shared_drafts(self):
        from unconfigured_mail_repository import UnconfiguredMailRepository
        draft, config = self.make_access_draft('shared', self.emails, self.emails[1])
        headers = self.login()
        url = f'/api/supplier-drafts/{draft}'
        response = self.client.put(url, headers=headers, json={'revision': 1, 'config': {'name': '共享草稿可管理', 'prompt_mode': 'auto'}})
        self.assertEqual(response.status_code, 200, response.get_json())
        revision = response.get_json()['data']['revision']
        published = self.client.post(url + '/publish', headers=headers, json={'revision': revision})
        self.assertEqual(published.status_code, 200, published.get_json())
        self.assertEqual(self.client.get('/api/supplier-drafts?status=published').get_json()['data']['total'], 1)
        self.assertEqual(self.client.delete(url, headers=headers, json={'revision': revision}).status_code, 200)
        self.assertTrue(all(self.db.get_email_record_by_id(email_id) for email_id in self.emails))
        failed, _ = self.make_access_draft('failed', self.emails, self.emails[1])
        with self.db.get_connection() as conn:
            conn.execute("UPDATE supplier_drafts SET status='generation_failed',draft_json=NULL WHERE id=?", (failed,))
            UnconfiguredMailRepository.enqueue(conn, 'supplier_config_draft', self.emails[1], {}, failed, 1)
            conn.execute("UPDATE mail_ai_jobs SET status='failed' WHERE draft_id=?", (failed,))
            conn.commit()
        response = self.client.post(f'/api/supplier-drafts/{failed}/retry', headers=headers, json={})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['data']['status'], 'generating')

    def test_shared_draft_hides_ungranted_source_copies_and_preserves_them_on_edit(self):
        draft, config = self.make_access_draft('private-copies', self.emails, self.emails[1])
        secret = 'B邮箱未授权的完整邮件正文'
        config['email_type_samples']['割接通知'].update(content=secret, source_email_records_id=self.emails[1])
        config['review_metadata'] = {'questions': [secret], 'confirmations': {}}
        stored = {'config': config, 'evidence': [secret], 'unresolved_questions': [secret]}
        with self.db.get_connection() as conn:
            conn.execute('UPDATE supplier_drafts SET draft_json=? WHERE id=?', (json.dumps(stored), draft))
            conn.commit()
        headers = self.login()
        for url in ('/api/supplier-drafts', f'/api/supplier-drafts/{draft}'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(secret, response.get_data(as_text=True))
        url = f'/api/supplier-drafts/{draft}'
        detail = self.client.get(url).get_json()['data']
        self.assertTrue(detail['draft']['config']['samples_restricted'])
        for field, value in (('email_type_samples', {}), ('review_metadata', {})):
            response = self.client.put(url, headers=headers, json={'revision': 1, 'config': {'name': '共享', field: value}})
            self.assertEqual(response.status_code, 403, response.get_json())
        response = self.client.put(url, headers=headers, json={'revision': 1, 'config': {'name': '可修改的规则', 'prompt_mode': 'auto'}})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertNotIn(secret, response.get_data(as_text=True))
        with self.db.get_connection() as conn:
            actual = json.loads(conn.execute('SELECT draft_json FROM supplier_drafts WHERE id=?', (draft,)).fetchone()[0])
        self.assertEqual(actual['config']['email_type_samples'], config['email_type_samples'])
        self.assertEqual(actual['config']['review_metadata'], config['review_metadata'])
        self.assertEqual(actual['evidence'], [secret])
        admin = self.client.get(url, headers=self.admin_headers).get_json()['data']
        self.assertEqual(admin['draft']['config']['email_type_samples']['割接通知']['content'], secret)
        published = self.client.post(url + '/publish', headers=headers, json={'revision': 2})
        self.assertEqual(published.status_code, 200, published.get_json())
        supplier_id = published.get_json()['data']['supplier_id']
        for path in (url, '/api/supplier-drafts?status=published', f'/api/suppliers/{supplier_id}'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(secret, response.get_data(as_text=True))

    def test_deleted_source_does_not_make_retained_html_sample_public(self):
        from cutover_deletion import _remove_database_records
        draft, config = self.make_access_draft('deleted-source', self.emails, self.emails[1])
        secret = '<p>B邮箱 HTML 私有样本</p>'
        config['email_type_samples']['割接通知'].update(
            subject='B来源', content=secret, source_email_records_id=self.emails[1])
        with self.db.get_connection() as conn:
            conn.execute("UPDATE email_records SET subject='B来源',content='不同的纯文本',html_content=? WHERE id=?", (secret, self.emails[1]))
            conn.execute('UPDATE supplier_drafts SET draft_json=? WHERE id=?', (json.dumps({'config': config}), draft))
            _remove_database_records(conn, self.emails[1])
            conn.commit()
        headers = self.login()
        url = f'/api/supplier-drafts/{draft}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(secret, response.get_data(as_text=True))
        self.assertTrue(response.get_json()['data']['draft']['config']['samples_restricted'])
        revision = response.get_json()['data']['revision']
        published = self.client.post(url + '/publish', headers=headers, json={'revision': revision})
        self.assertEqual(published.status_code, 200, published.get_json())
        supplier = self.client.get('/api/suppliers/' + str(published.get_json()['data']['supplier_id'])).get_json()['data']
        self.assertTrue(supplier['samples_restricted'])

    def test_all_source_grants_allow_editing_draft_samples(self):
        draft, config = self.make_access_draft('all-sources', self.emails, self.emails[1])
        self.repo.set_grants(self.user['id'], [{'account_id': account, 'can_operate': True} for account in self.accounts])
        headers = self.login()
        url = f'/api/supplier-drafts/{draft}'
        detail = self.client.get(url).get_json()['data']
        self.assertEqual(detail['draft']['config']['email_type_samples'], config['email_type_samples'])
        config['email_type_samples']['割接通知']['content'] = '已审核的样本'
        response = self.client.put(url, headers=headers, json={'revision': 1, 'config': config})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['data']['draft']['config']['email_type_samples'], config['email_type_samples'])

    def test_read_only_draft_access_does_not_grant_modification(self):
        draft, config = self.make_access_draft('readonly', self.emails, self.emails[1])
        self.repo.set_grants(self.user['id'], [{'account_id': self.accounts[0], 'can_operate': False}])
        headers = self.login()
        url = f'/api/supplier-drafts/{draft}'
        self.assertEqual(self.client.get(url).status_code, 200)
        for method, path, body in [('PUT', url, {'revision': 1, 'config': config}),
                                   ('DELETE', url, {'revision': 1}),
                                   ('POST', url + '/publish', {'revision': 1}),
                                   ('POST', url + '/retry', {})]:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.client.open(path, method=method, headers=headers, json=body).status_code, 404)

    def test_draft_retry_does_not_retry_another_draft_for_the_same_source(self):
        from unconfigured_mail_repository import UnconfiguredMailRepository
        target, _ = self.make_access_draft('target', self.emails, self.emails[1])
        other, _ = self.make_access_draft('other', [self.emails[1]], self.emails[1])
        with self.db.get_connection() as conn:
            conn.execute("UPDATE supplier_drafts SET status='generation_failed',draft_json=NULL")
            UnconfiguredMailRepository.enqueue(conn, 'supplier_config_draft', self.emails[1], {}, other, 1)
            conn.execute("UPDATE mail_ai_jobs SET status='failed'")
            conn.commit()
        response = self.client.post(f'/api/supplier-drafts/{target}/retry', headers=self.login(), json={})
        self.assertEqual(response.status_code, 409, response.get_json())
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT status FROM mail_ai_jobs').fetchone()[0], 'failed')
            self.assertEqual(conn.execute('SELECT status FROM supplier_drafts WHERE id=?', (other,)).fetchone()[0], 'generation_failed')

    def test_draft_retry_rechecks_revoked_operate_grant(self):
        from unconfigured_mail_repository import UnconfiguredMailRepository
        draft, _ = self.make_access_draft('revoked', self.emails, self.emails[1])
        principal = self.repo.get_principal(self.user['id'])
        with self.db.get_connection() as conn:
            conn.execute("UPDATE supplier_drafts SET status='generation_failed',draft_json=NULL WHERE id=?", (draft,))
            UnconfiguredMailRepository.enqueue(conn, 'supplier_config_draft', self.emails[1], {}, draft, 1)
            conn.execute("UPDATE mail_ai_jobs SET status='failed'")
            conn.commit()
        self.repo.set_grants(self.user['id'], [])
        with self.assertRaises(LookupError):
            UnconfiguredMailRepository(self.db).retry(self.emails[1], 'supplier_config_draft', draft_id=draft, principal=principal)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT status FROM mail_ai_jobs').fetchone()[0], 'failed')
            self.assertEqual(conn.execute('SELECT status FROM supplier_drafts WHERE id=?', (draft,)).fetchone()[0], 'generation_failed')

    def test_published_samples_remain_scoped_after_draft_deletion(self):
        from supplier_drafts import SupplierDraftRepository
        headers = self.login()
        secret = '仅第二个邮箱可见的原始邮件正文'
        config = {'name': '私有来源样本', 'prompt_mode': 'auto',
                  'email_type_samples': {'割接通知': {'subject': '维护', 'content': secret}}}
        with self.db.get_connection() as conn:
            cursor = conn.execute('''INSERT INTO supplier_drafts
                (candidate_key,sender,status,draft_json,revision,source_email_records_id,create_time,update_time)
                VALUES ('private','private@example.com','review',?,1,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)''',
                (json.dumps({'config': config}), self.emails[1]))
            draft_id = cursor.lastrowid
            conn.execute('INSERT INTO supplier_draft_samples VALUES (?,?)', (draft_id, self.emails[1]))
            conn.commit()
        drafts = SupplierDraftRepository(self.db)
        supplier_id = drafts.publish(draft_id, 1)['supplier_id']
        # Simulate an existing publication upgrading to the new provenance table.
        with self.db.get_connection() as conn:
            conn.execute('DELETE FROM supplier_sample_access WHERE supplier_id=?', (supplier_id,))
            conn.commit()
        self.db.init_database()
        drafts.delete(draft_id, 1)
        for url in ('/api/suppliers', f'/api/suppliers/{supplier_id}'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(secret, json.dumps(response.get_json(), ensure_ascii=False))
        response = self.client.patch(f'/api/suppliers/{supplier_id}', headers=headers, json={'name': '共享字段可修改'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['data']['email_type_samples'], {})
        self.assertEqual(response.get_json()['data']['supplier_mail_classify_prompt'], '')
        self.assertEqual(response.get_json()['data']['review_metadata'], {})
        self.assertEqual(self.client.patch(f'/api/suppliers/{supplier_id}', headers=headers,
                         json={'email_type_samples': config['email_type_samples']}).status_code, 403)
        self.repo.set_grants(self.user['id'], [{'account_id': self.accounts[1], 'can_operate': False}])
        record = self.client.get(f'/api/suppliers/{supplier_id}').get_json()['data']
        self.assertEqual(record['email_type_samples']['割接通知']['content'], secret)
        self.assertTrue(record['samples_read_only'])
        self.assertEqual(self.client.patch(f'/api/suppliers/{supplier_id}', headers=headers,
                         json={'review_metadata':{'questions':[], 'confirmations':{}}}).status_code, 403)
        self.repo.set_grants(self.user['id'], [])
        self.assertTrue(self.client.get(f'/api/suppliers/{supplier_id}').get_json()['data']['samples_restricted'])

    def test_regular_user_cannot_use_mail_configuration_even_for_authorized_mailbox(self):
        headers = self.login()
        before = self.db.list_mail_accounts()
        grants = self.repo.list_grants(self.user['id'])
        base = '/api/system/mail-accounts'
        body = {'name': '禁止保存', 'email_address': 'new@example.com',
                'email_password': 'mail-password', 'imap_server': 'imap.example.com'}
        routes = [('get', base), ('head', base), ('get', base + '/status'),
                  ('post', base), ('post', base + '/test-preview')]
        for account_id in self.accounts:
            routes.extend([('put', f'{base}/{account_id}'), ('delete', f'{base}/{account_id}'),
                           ('post', f'{base}/{account_id}/test')])
        with patch.object(api_server, 'listener_manager') as manager, \
                patch.object(api_server, 'EmailClient') as mail_client, \
                patch.object(api_server, 'encrypt_password', return_value='encrypted'):
            for method, path in routes:
                with self.subTest(method=method, path=path):
                    response = getattr(self.client, method)(path, headers=headers, json=body)
                    self.assertEqual(response.status_code, 403)
            manager.sync.assert_not_called()
            manager.get_status.assert_not_called()
            mail_client.assert_not_called()
        self.assertEqual(self.db.list_mail_accounts(), before)
        self.assertEqual(self.repo.list_grants(self.user['id']), grants)
        options = self.client.get('/api/me/mailboxes').get_json()['data']
        self.assertEqual([item['account_id'] for item in options], [self.accounts[0]])

    def test_read_only_grant_csrf_and_revocation_apply_immediately(self):
        headers = self.login()
        path = f'/api/cutover/emails/{self.emails[0]}/read-state'
        self.assertEqual(self.client.patch(path, json={'is_read': True}).status_code, 403)
        self.repo.set_grants(self.user['id'], [{'account_id': self.accounts[0], 'can_operate': False}])
        self.assertEqual(self.client.patch(path, json={'is_read': True}, headers=headers).status_code, 403)
        self.repo.set_grants(self.user['id'], [])
        self.assertEqual(self.client.get('/api/email-records').get_json()['data']['total'], 0)
        self.assertEqual(self.client.get(f'/api/cutover/tasks/{self.tasks[0]}').status_code, 404)

    def test_admin_has_all_data_and_can_create_and_grant_user(self):
        response = self.client.get('/api/email-records', headers=self.admin_headers)
        self.assertEqual(response.get_json()['data']['total'], 2)
        created = self.client.post('/api/users', headers=self.admin_headers,
                                   json={'username': 'bob', 'password': 'another-password', 'display_name': '李四'})
        self.assertEqual(created.status_code, 201)
        user_id = created.get_json()['data']['id']
        grant = self.client.put(f'/api/users/{user_id}/mailboxes', headers=self.admin_headers,
                               json={'grants': [{'account_id': self.accounts[1], 'can_operate': True}]})
        self.assertEqual(grant.status_code, 200)

    def test_logout_revokes_session_and_public_files_require_authentication(self):
        headers = self.login()
        self.assertEqual(self.client.post('/api/auth/logout', headers=headers).status_code, 200)
        self.assertEqual(self.client.get('/api/email-records').status_code, 401)
        for path in ('/api/email/images/email-123.png', '/api/email/attachments/old.txt',
                     f'/api/cutover/tasks/{self.tasks[0]}/excel', '/api/template-xlsx/download/old.xlsx'):
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_disabling_or_resetting_user_revokes_existing_login(self):
        self.login()
        result = self.client.patch(f'/api/users/{self.user["id"]}', headers=self.admin_headers, json={'enabled': False})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)
        self.assertEqual(self.client.post('/api/auth/login', json={'username': 'alice', 'password': 'a-secure-password'}).status_code, 401)

    def test_same_filename_never_grants_generic_legacy_excel_access(self):
        self.login()
        for task_id in self.tasks:
            self.db.update_cutover_task(task_id, customer_excel_filename='same.xlsx')
        root = Path(self.temp.name)
        (root / 'same.xlsx').write_bytes(b'other mailbox legacy content')
        with patch.object(api_server, 'DATA_DIR', root):
            self.assertEqual(self.client.get('/api/template-xlsx/download/same.xlsx').status_code, 404)
            self.assertEqual(self.client.get(f'/api/cutover/tasks/{self.tasks[0]}/excel').status_code, 404)
            for name in ('same', ' same.xlsx', 'same.xlsx '):
                path = f'/api/template-xlsx/download/users/user-{self.user["id"]}/templates/{name}'
                self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_regular_user_can_retry_authorized_mail_analysis(self):
        headers = self.login()
        response = self.client.post(f'/api/emails/{self.emails[0]}/analysis-retry', headers=headers,
                                    json={'task_type': 'supplier_config_draft'})
        self.assertEqual(response.status_code, 409, '允许操作，但当前邮件没有失败任务可重试')

    def test_regular_user_preview_attachments_are_private_and_cannot_sign_other_mail(self):
        import email_attachments
        headers = self.login()
        root = Path(self.temp.name)
        with patch.object(email_attachments, 'DATA_DIR', root), patch.object(api_server, 'DATA_DIR', root), \
                patch.object(email_attachments, 'ATTACHMENT_DIR', root / 'email_attachments'):
            response = self.client.post('/api/suppliers/preview-attachments', headers=headers,
                                        data={'file': (io.BytesIO(b'private preview'), 'sample.txt')})
            self.assertEqual(response.status_code, 201)
            relative = response.get_json()['data']['relative_path']
            response = self.client.get('/api/email/attachments/' + relative)
            self.assertEqual(response.status_code, 200)
            response.close()
            self.repo.create_user('bob', 'another-password')
            other_client = api_server.app.test_client()
            login = other_client.post('/api/auth/login', json={'username': 'bob', 'password': 'another-password'})
            other_headers = {'X-CSRF-Token': login.get_json()['data']['csrf_token']}
            self.assertEqual(other_client.get('/api/email/attachments/' + relative).status_code, 404)
            with patch.object(api_server.requests, 'post') as external:
                response = other_client.post('/api/suppliers/preview-extract', headers=other_headers,
                                              json={'attachments': [relative]})
                self.assertEqual(response.status_code, 404)
                external.assert_not_called()

    def test_regular_user_template_generation_cannot_overwrite_legacy_files(self):
        headers = self.login()
        root = Path(self.temp.name)
        (root / 'template.xlsx').write_bytes(b'legacy contents')
        with patch.object(api_server, 'DATA_DIR', root):
            response = self.client.post('/api/template-xlsx', headers=headers, json={'filename': 'template.xlsx'})
            self.assertEqual(response.status_code, 200, response.get_json())
            from urllib.parse import urlsplit
            url = urlsplit(response.get_json()['data']['download_url']).path
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            response.close()
            self.assertEqual((root / 'template.xlsx').read_bytes(), b'legacy contents')

    def test_signed_attachment_capability_cannot_be_reused_for_another_file(self):
        from artifact_access import sign_artifact_url
        root = Path(self.temp.name)
        folder = root / 'email_attachments' / '123'
        folder.mkdir(parents=True)
        (folder / 'one.txt').write_text('one')
        (folder / 'two.txt').write_text('two')
        signed = sign_artifact_url('/api/email/attachments/email_attachments/123/one.txt', 'test-key')
        with patch.object(api_server, 'attachment_path_from_relative', side_effect=lambda value: root / value):
            response = self.client.get(signed)
            self.assertEqual(response.status_code, 200)
            response.close()
            self.assertEqual(self.client.get(signed.replace('one.txt', 'two.txt')).status_code, 401)

    def test_running_report_blocks_shared_mail_regeneration_before_files_are_written(self):
        headers = self.login()
        self.db.update_cutover_task(self.tasks[0], status='reporting')
        with patch.object(api_server, 'save_workbook_output') as write:
            response = self.client.post('/api/cutover/tasks/generate', headers=headers,
                                       json={'email_records_id': self.emails[0]})
        self.assertEqual(response.status_code, 409)
        write.assert_not_called()

    def test_unicode_invalid_secrets_fail_as_auth_errors(self):
        response = self.client.post('/api/auth/login', json={'mode': 'admin', 'api_key': '无效密码'})
        self.assertEqual(response.status_code, 401)
        headers = self.login()
        headers['X-CSRF-Token'] = '错误令牌'
        self.assertEqual(self.client.post('/api/auth/logout', headers=headers).status_code, 403)

    def test_https_proxy_login_accepts_same_origin_and_rejects_other_origins(self):
        credentials = {'username': 'alice', 'password': 'a-secure-password'}
        with patch.dict(os.environ, {'NOC_COOKIE_SECURE': 'true'}):
            response = self.client.post('/api/auth/login', base_url='http://noc.example.com',
                                        headers={'Origin': 'https://noc.example.com'}, json=credentials)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Secure;', response.headers['Set-Cookie'])
            for origin in ('https://other.example.com', 'http://noc.example.com', 'null'):
                with self.subTest(origin=origin):
                    response = self.client.post('/api/auth/login', base_url='http://noc.example.com',
                                                headers={'Origin': origin}, json=credentials)
                    self.assertEqual(response.status_code, 403)
