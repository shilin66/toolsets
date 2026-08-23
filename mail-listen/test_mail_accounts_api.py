import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

# 测试用加密密钥（必须在导入 api_server 前设置，避免生成真实密钥文件）
os.environ['MAIL_SECRET_KEY'] = Fernet.generate_key().decode('utf-8')

os.environ.setdefault('IMAP_SERVER', 'imap.example.com')
os.environ.setdefault('EMAIL_ADDRESS', 'test@example.com')
os.environ.setdefault('EMAIL_PASSWORD', 'password')
os.environ.setdefault('API_URL', 'https://api.example.com')
os.environ.setdefault('API_TOKEN', 'token')
os.environ.setdefault('API_KEY', 'test-key')

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_server
import mail_accounts
from database import EmailDatabase


class MailAccountsApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = EmailDatabase(os.path.join(self.tmpdir.name, 'mail_listener.db'))
        self.db_patch = patch.object(api_server, 'email_db', self.db)
        self.db_patch.start()
        # 监听管理器替换为桩，避免测试中真实连接 IMAP/启动线程
        self.manager_patch = patch.object(api_server, 'listener_manager', MagicMock())
        self.manager_patch.start()
        self.client = api_server.app.test_client()
        self.headers = {'Authorization': 'Bearer test-key'}

    def tearDown(self):
        self.manager_patch.stop()
        self.db_patch.stop()
        self.tmpdir.cleanup()

    def _create_account(self, address='noc@example.com', **overrides):
        payload = {
            'name': '值班邮箱',
            'email_address': address,
            'email_password': 'secret-auth-code',
            'imap_server': 'imap.example.com',
            'imap_port': 993,
            'imap_use_ssl': True,
            'smtp_server': 'smtp.example.com',
            'smtp_port': 465,
            'smtp_use_ssl': True,
            'smtp_use_tls': False,
        }
        payload.update(overrides)
        return self.client.post('/api/system/mail-accounts', headers=self.headers, json=payload)

    def test_requires_api_key(self):
        response = self.client.get('/api/system/mail-accounts')
        self.assertEqual(response.status_code, 401)

    def test_list_empty(self):
        response = self.client.get('/api/system/mail-accounts', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data'], [])

    def test_create_success_and_password_masked(self):
        response = self._create_account()
        self.assertEqual(response.status_code, 201)
        data = response.get_json()['data']
        self.assertEqual(data['email_address'], 'noc@example.com')
        self.assertTrue(data['password_set'])
        # 密码绝不回传
        self.assertNotIn('email_password', data)
        self.assertNotIn('password_enc', data)
        # 数据库中为加密密文，解密后等于原密码
        row = self.db.get_mail_account(data['id'])
        self.assertNotEqual(row['password_enc'], 'secret-auth-code')
        self.assertEqual(mail_accounts.decrypt_password(row['password_enc']), 'secret-auth-code')
        # 保存成功后热同步监听
        api_server.listener_manager.sync.assert_called()

    def test_create_requires_password(self):
        response = self._create_account(email_password='')
        self.assertEqual(response.status_code, 400)

    def test_create_duplicate_address_rejected(self):
        self.assertEqual(self._create_account().status_code, 201)
        response = self._create_account(address='NOC@example.com')  # 大小写不同也视为重复
        self.assertEqual(response.status_code, 400)

    def test_update_empty_password_keeps_existing(self):
        account_id = self._create_account().get_json()['data']['id']
        old_enc = self.db.get_mail_account(account_id)['password_enc']

        response = self.client.put(
            f'/api/system/mail-accounts/{account_id}',
            headers=self.headers,
            json={'name': '新名称', 'email_password': ''},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['data']['name'], '新名称')
        self.assertEqual(self.db.get_mail_account(account_id)['password_enc'], old_enc)

    def test_update_new_password_replaces(self):
        account_id = self._create_account().get_json()['data']['id']
        response = self.client.put(
            f'/api/system/mail-accounts/{account_id}',
            headers=self.headers,
            json={'email_password': 'new-code'},
        )
        self.assertEqual(response.status_code, 200)
        row = self.db.get_mail_account(account_id)
        self.assertEqual(mail_accounts.decrypt_password(row['password_enc']), 'new-code')

    def test_update_toggle_enabled(self):
        account_id = self._create_account().get_json()['data']['id']
        response = self.client.put(
            f'/api/system/mail-accounts/{account_id}',
            headers=self.headers,
            json={'enabled': False},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()['data']['enabled'])
        self.assertEqual(self.db.get_mail_account(account_id)['enabled'], 0)

    def test_update_conflicting_address_rejected(self):
        self._create_account(address='a@example.com')
        account_id = self._create_account(address='b@example.com').get_json()['data']['id']
        response = self.client.put(
            f'/api/system/mail-accounts/{account_id}',
            headers=self.headers,
            json={'email_address': 'a@example.com'},
        )
        self.assertEqual(response.status_code, 400)

    def test_update_missing_account(self):
        response = self.client.put(
            '/api/system/mail-accounts/99999',
            headers=self.headers,
            json={'name': 'x'},
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_account(self):
        account_id = self._create_account().get_json()['data']['id']
        response = self.client.delete(
            f'/api/system/mail-accounts/{account_id}', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.db.get_mail_account(account_id))
        api_server.listener_manager.sync.assert_called()

        response = self.client.delete(
            f'/api/system/mail-accounts/{account_id}', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_connection_invalid_server_fails(self):
        # 无效域名 DNS 解析失败，connect 返回 False → 400
        account_id = self._create_account(imap_server='invalid.invalid').get_json()['data']['id']
        response = self.client.post(
            f'/api/system/mail-accounts/{account_id}/test', headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_connection_missing_account(self):
        response = self.client.post(
            '/api/system/mail-accounts/99999/test', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_status_returns_running_flag_and_db_fallback(self):
        """状态端点：监听未运行时最后收件时间回退历史记录。"""
        account_id = self._create_account().get_json()['data']['id']
        self.db.add_email_record(
            email_id=1, sender='s@example.com', receiver='noc@example.com',
            subject='历史邮件', content='c')

        response = self.client.get('/api/system/mail-accounts/status', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()['data']
        item = data[str(account_id)]
        self.assertFalse(item['running'])
        self.assertIsNone(item['error'])
        self.assertIsNotNone(item['last_email_at'])

    def test_status_uses_listener_manager_snapshot(self):
        """状态端点：监听器实时状态优先于历史记录。"""
        account_id = self._create_account().get_json()['data']['id']
        api_server.listener_manager.get_status.return_value = {
            account_id: {'running': True, 'error': None, 'last_email_at': '2026-08-22 10:00:00'},
        }

        response = self.client.get('/api/system/mail-accounts/status', headers=self.headers)
        data = response.get_json()['data']
        self.assertTrue(data[str(account_id)]['running'])
        self.assertEqual(data[str(account_id)]['last_email_at'], '2026-08-22 10:00:00')

    def test_test_preview_invalid_server_fails(self):
        """保存前连接测试：无效域名连接失败返回 400，且不写入数据库。"""
        response = self.client.post('/api/system/mail-accounts/test-preview', headers=self.headers, json={
            'name': '预览邮箱',
            'email_address': 'preview@example.com',
            'email_password': 'secret',
            'imap_server': 'invalid.invalid',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])
        self.assertEqual(len(self.db.list_mail_accounts()), 0)

    def test_test_preview_requires_password(self):
        response = self.client.post('/api/system/mail-accounts/test-preview', headers=self.headers, json={
            'email_address': 'preview@example.com',
            'email_password': '',
            'imap_server': 'imap.example.com',
        })
        self.assertEqual(response.status_code, 400)


class ReplyClientResolutionTest(unittest.TestCase):
    """回复邮件按邮件记录 receiver 匹配账号，缺失时回退第一个启用账号。"""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = EmailDatabase(os.path.join(self.tmpdir.name, 'mail_listener.db'))
        self.db_patch = patch.object(api_server, 'email_db', self.db)
        self.db_patch.start()
        self.account_id = self.db.add_mail_account({
            'name': '值班邮箱',
            'email_address': 'noc@example.com',
            'password_enc': mail_accounts.encrypt_password('secret'),
            'imap_server': 'imap.example.com',
            'imap_port': 993,
            'imap_use_ssl': 1,
            'enabled': 1,
        })

    def tearDown(self):
        self.db_patch.stop()
        self.tmpdir.cleanup()

    def test_match_by_receiver(self):
        # build_reply_email_client 回退路径读 mail_accounts.email_db，需同步替换
        with patch.object(mail_accounts, 'email_db', self.db):
            client = api_server.build_reply_email_client({'receiver': 'noc@example.com'})
        self.assertIsNotNone(client)
        self.assertEqual(client.account.email_address, 'noc@example.com')

    def test_fallback_to_first_enabled(self):
        with patch.object(mail_accounts, 'email_db', self.db):
            client = api_server.build_reply_email_client({'receiver': 'unknown@example.com'})
        self.assertIsNotNone(client)
        self.assertEqual(client.account.id, self.account_id)

    def test_no_account_returns_none(self):
        empty_db = EmailDatabase(os.path.join(self.tmpdir.name, 'empty.db'))
        with patch.object(api_server, 'email_db', empty_db), \
             patch.object(mail_accounts, 'email_db', empty_db):
            client = api_server.build_reply_email_client({'receiver': 'noc@example.com'})
        self.assertIsNone(client)


if __name__ == '__main__':
    unittest.main()
