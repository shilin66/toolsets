import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import EmailDatabase


class UserAccessTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = EmailDatabase(str(Path(self.temp.name) / 'test.db'))

    def repository(self):
        from user_access import UserAccessRepository
        return UserAccessRepository(self.db)

    def test_user_password_is_hashed_and_login_session_can_be_revoked(self):
        repo = self.repository()
        user = repo.create_user('alice', 'a-secure-password', '张三')
        self.assertNotIn('password_hash', user)
        with self.db.get_connection() as conn:
            saved = conn.execute('SELECT password_hash FROM app_users').fetchone()[0]
        self.assertNotEqual(saved, 'a-secure-password')
        self.assertIsNone(repo.verify_user('alice', 'wrong'))
        principal = repo.verify_user('ALICE', 'a-secure-password')
        self.assertEqual(principal.user_id, user['id'])
        token, csrf = repo.create_session(principal, 'admin-key')
        self.assertEqual(repo.resolve_session(token, 'admin-key')[0], principal)
        self.assertTrue(csrf)
        repo.revoke_session(token)
        self.assertIsNone(repo.resolve_session(token, 'admin-key'))

    def test_granting_existing_mailbox_preserves_history_and_supports_read_only(self):
        account = self.db.add_mail_account({'email_address': 'NOC@example.com', 'imap_server': 'example.com'})
        self.db.add_email_record(811, receiver='noc@example.com', subject='old mail', content='history')
        email = self.db.get_email_record(811)
        repo = self.repository()
        user = repo.create_user('alice', 'a-secure-password', '张三')
        principal = repo.verify_user('alice', 'a-secure-password')
        self.assertFalse(repo.can_access_email(principal, email['id']))
        repo.set_grants(user['id'], [{'account_id': account, 'can_operate': False}])
        self.assertTrue(repo.can_access_email(principal, email['id']))
        self.assertFalse(repo.can_access_email(principal, email['id'], operate=True))
        repo.set_grants(user['id'], [{'account_id': account, 'can_operate': True}])
        self.assertTrue(repo.can_access_email(principal, email['id'], operate=True))
        self.assertEqual(self.db.get_email_record(811)['id'], email['id'])
        repo.set_grants(user['id'], [])
        self.assertFalse(repo.can_access_email(principal, email['id']))

    def test_repeated_initialization_keeps_data_and_grants(self):
        repo = self.repository()
        user = repo.create_user('alice', 'a-secure-password', '张三')
        self.db.init_database()
        self.db.init_database()
        self.assertEqual(self.repository().list_users()[0]['id'], user['id'])
        with self.assertRaises(ValueError):
            repo.create_user('ALICE', 'another-password', 'duplicate')

    def test_admin_session_is_invalidated_when_api_key_changes(self):
        from user_access import Principal
        repo = self.repository()
        admin = Principal.admin()
        token, _ = repo.create_session(admin, 'old-key')
        self.assertIsNotNone(repo.resolve_session(token, 'old-key'))
        self.assertIsNone(repo.resolve_session(token, 'new-key'))

    def test_grants_update_is_atomic_on_invalid_account(self):
        repo = self.repository()
        user = repo.create_user('alice', 'a-secure-password', '张三')
        account = self.db.add_mail_account({'email_address': 'a@example.com', 'imap_server': 'example.com'})
        repo.set_grants(user['id'], [{'account_id': account, 'can_operate': True}])
        with self.assertRaises(ValueError):
            repo.set_grants(user['id'], [{'account_id': 999999, 'can_operate': True}])
        self.assertEqual(repo.list_grants(user['id'])[0]['account_id'], account)
