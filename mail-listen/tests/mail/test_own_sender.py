from datetime import datetime
import unittest
from unittest.mock import Mock, patch

import mail_listener
from mail_accounts import MailAccountConfig
from models import EmailMessage
from supplier_config import SupplierConfigCreate, SupplierConfigRepository
from tests.mail import test_unconfigured_flow as fixture


class OwnSenderTest(unittest.TestCase):
    setUp = fixture.UnconfiguredFlowTest.setUp

    def listener(self, address='inbox@example.com'):
        account = MailAccountConfig(id=1, name='NOC', email_address=address,
            email_password='test', imap_server='imap.example.com')
        listener = mail_listener.MailListener(account, on_email_received=Mock())
        if listener.executor:
            self.addCleanup(listener.executor.shutdown)
        return listener

    @staticmethod
    def message(uid, sender):
        return EmailMessage(uid=uid, sender=sender, recipients=['inbox@example.com'],
            subject='Maintenance', content='maintenance window', received_date=datetime.now())

    def test_incremental_skips_self_mail_but_accepts_other_account_mail(self):
        self.db.add_mail_account({'email_address':'Other@Example.com',
            'imap_server':'imap.example.com', 'enabled':False})
        self.repo.cursor('inbox@example.com', 'INBOX', 1, 100)
        imap = Mock()
        imap.folder_status.return_value = {b'UIDVALIDITY':1, b'UIDNEXT':104}
        imap.search.return_value = [100,101,102,103]
        imap.fetch.return_value = {}
        senders = {100:'My NOC < INBOX@EXAMPLE.COM >',101:'Other <other@example.com>',
            102:'supplier@example.com',103:'inbox@example.com.evil.net'}
        with patch.object(mail_listener, 'email_db', self.db), \
                patch.object(mail_listener.settings, 'mark_as_read', False):
            listener = self.listener()
            listener.email_client = Mock(connected=True, client=imap)
            listener.email_client._parse_email.side_effect = lambda uid: self.message(uid, senders[uid])
            listener._check_incremental_emails()
            self.assertIsNone(self.db.get_email_record(100, 'inbox@example.com'))
            for uid in (101,102,103):
                self.assertIsNotNone(self.db.get_email_record(uid, 'inbox@example.com'))
            self.assertEqual(listener.on_email_received.call_count, 3)
            self.assertEqual(self.repo.cursor('inbox@example.com','INBOX',1,999),104)
            # Rechecking must not fetch the skipped messages again via the cursor.
            listener._check_incremental_emails()
            self.assertEqual(imap.search.call_count, 1)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM mail_ai_jobs').fetchone()[0],3)
            self.assertEqual(conn.execute('SELECT count(*) FROM supplier_drafts').fetchone()[0],0)
        imap.add_flags.assert_not_called()

    def test_direct_processing_skips_own_sender_even_with_supplier_rule(self):
        SupplierConfigRepository(self.db).create(SupplierConfigCreate(name='Own mailbox',
            email='inbox@example.com', prompt_mode='auto',
            email_type_samples={'割接通知':{'subject':'Maintenance','content':'maintenance'}}))
        with patch.object(mail_listener, 'email_db', self.db):
            listener = self.listener()
            listener.action_manager = Mock()
            listener.email_filter = Mock()
            listener._process_email(self.message(1,'inbox@example.com'))
        self.assertIsNone(self.db.get_email_record(1,'inbox@example.com'))
        listener.email_filter.filter_email.assert_not_called()
        listener.action_manager.execute_action.assert_not_called()
        listener.on_email_received.assert_not_called()

    def test_all_own_mail_only_logs_and_is_not_marked_read(self):
        self.repo.cursor('inbox@example.com', 'INBOX', 1, 100)
        imap = Mock()
        imap.folder_status.return_value = {b'UIDVALIDITY':1, b'UIDNEXT':101}
        imap.search.return_value = [100]
        with patch.object(mail_listener, 'email_db', self.db), \
                patch.object(mail_listener.settings, 'mark_as_read', True), \
                patch.object(mail_listener, 'logger') as log:
            listener = self.listener()
            listener.email_client = Mock(connected=True, client=imap)
            listener.email_client._parse_email.return_value = self.message(100, 'inbox@example.com')
            listener._check_incremental_emails()
            self.assertTrue(any('reason_code=own_sender' in call.args[0]
                                for call in log.info.call_args_list))
            log.error.assert_not_called()
        imap.add_flags.assert_not_called()
        listener.on_email_received.assert_not_called()
        self.assertEqual(self.repo.cursor('inbox@example.com','INBOX',1,999),101)
        with self.db.get_connection() as conn:
            for table in ('email_records', 'mail_ai_jobs', 'supplier_drafts'):
                self.assertEqual(conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0],0)

    def test_other_account_registration_does_not_change_sender_filter(self):
        with patch.object(mail_listener, 'email_db', self.db):
            listener = self.listener()
            email = self.message(1, 'new-own@example.net')
            self.assertFalse(listener._skip_own_sender(email))
            account_id = self.db.add_mail_account({'email_address':email.sender,
                'imap_server':'imap.example.net'})
            self.assertFalse(listener._skip_own_sender(email))
            self.db.delete_mail_account(account_id)
            self.assertFalse(listener._skip_own_sender(email))

    def test_same_message_is_skipped_only_in_senders_own_inbox(self):
        self.db.add_mail_account({'email_address':'inbox@example.com',
            'imap_server':'imap.example.com'})
        email = self.message(1, 'NOC < INBOX@EXAMPLE.COM >')
        email.recipients = ['inbox@example.com', 'other@example.com']
        with patch.object(mail_listener, 'email_db', self.db):
            self.assertTrue(self.listener()._skip_own_sender(email))
            self.assertFalse(self.listener('other@example.com')._skip_own_sender(email))
