from datetime import datetime
import unittest
from unittest.mock import Mock, patch

import mail_listener
from mail_accounts import MailAccountConfig
from models import EmailMessage
from tests.mail import test_unconfigured_flow as fixture


class IncrementalMailStatusTest(unittest.TestCase):
    def setUp(self):
        fixture.UnconfiguredFlowTest.setUp(self)
        self.account = MailAccountConfig(id=1, name='NOC', email_address='inbox@example.com',
            email_password='test', imap_server='imap.example.com')
        for patcher in (
            patch.object(mail_listener, 'email_db', self.db),
            patch.object(mail_listener.settings, 'mark_as_read', False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.listener = mail_listener.MailListener(self.account)
        if self.listener.executor:
            self.addCleanup(self.listener.executor.shutdown)
        self.imap = Mock()
        self.imap.folder_status.return_value = {b'UIDVALIDITY': 1}
        self.imap.select_folder.return_value = {b'UIDVALIDITY': 1, b'UIDNEXT': 102}
        self.imap.search.return_value = [100, 101]
        self.imap.fetch.return_value = {100: {b'FLAGS': (b'\\Seen',)}}
        self.listener.email_client = Mock(connected=True, client=self.imap)
        self.listener.email_client._parse_email.side_effect = lambda uid: EmailMessage(
            uid=uid, sender='new@example.com', recipients=[self.account.email_address],
            subject='通知', content='正文', received_date=datetime.now())

    def seed_cursor(self):
        self.repo.cursor(self.account.email_address, 'INBOX', 1, 100)

    def saved_cursor(self):
        with self.db.get_connection() as conn:
            row = conn.execute('SELECT uidvalidity, next_uid FROM mail_intake_cursors').fetchone()
            return tuple(row) if row else None

    def test_missing_uidnext_recovers_and_ingests_seen_mail(self):
        self.seed_cursor()
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 102))
        self.assertTrue(self.db.get_email_record(100, self.account.email_address)['is_read'])
        self.assertIsNotNone(self.db.get_email_record(101, self.account.email_address))
        self.imap.search.assert_called_once_with(['UID', '100:101'])

    def test_missing_uidvalidity_recovers_initial_boundary_without_backfill(self):
        self.imap.folder_status.return_value = {b'UIDNEXT': 99}
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 102))
        self.imap.search.assert_not_called()

    def test_complete_status_needs_no_fallback(self):
        self.imap.folder_status.return_value = {b'UIDVALIDITY': 1, b'UIDNEXT': 102}
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 102))
        self.imap.select_folder.assert_not_called()

    def test_missing_uidvalidity_keeps_cursor_and_names_missing_field(self):
        self.seed_cursor()
        self.imap.select_folder.return_value = {b'UIDNEXT': 102}
        with patch.object(mail_listener, 'logger') as log:
            self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 100))
        self.imap.search.assert_not_called()
        self.assertIn('SELECT', log.error.call_args.args[1])
        self.assertIn('UIDVALIDITY', log.error.call_args.args[1])

    def test_fallback_does_not_mix_uidvalidity_from_older_status(self):
        self.seed_cursor()
        self.imap.select_folder.return_value = {b'UIDVALIDITY': 2, b'UIDNEXT': 102}
        with patch.object(mail_listener, 'logger') as log:
            self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 100))
        self.assertIn('UIDVALIDITY 已变化', log.error.call_args.args[1])
        self.imap.search.assert_not_called()

    def test_fallback_failure_keeps_cursor_and_next_check_recovers(self):
        self.seed_cursor()
        self.imap.select_folder.side_effect = OSError('connection lost')
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 100))
        self.imap.search.assert_not_called()
        self.imap.select_folder.side_effect = None
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 102))

    def test_invalid_status_never_creates_initial_cursor(self):
        for invalid in (0, -1, None, 'invalid'):
            with self.subTest(uidnext=invalid):
                self.imap.folder_status.return_value = {b'UIDVALIDITY': 1, b'UIDNEXT': invalid}
                self.listener._check_incremental_emails()
                self.assertIsNone(self.saved_cursor())
        self.imap.search.assert_not_called()

    def use_uid_search_boundary(self, uids):
        self.imap.select_folder.return_value = {b'UIDVALIDITY': 1}
        def search(query):
            if query == ['UID', '*']:
                return [max(uids)] if uids else []
            self.assertEqual(query[0], 'UID')
            lower, upper = map(int, query[1].split(':'))
            self.assertLessEqual(lower, upper)
            return [uid for uid in uids if lower <= uid <= upper]
        self.imap.search.side_effect = search

    def test_missing_uidnext_in_status_and_select_ingests_seen_mail_and_uid_gaps(self):
        self.seed_cursor()
        self.use_uid_search_boundary([90, 100, 105])
        with patch.object(mail_listener, 'logger') as log:
            self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 106))
        self.assertIsNone(self.db.get_email_record(90, self.account.email_address))
        self.assertTrue(self.db.get_email_record(100, self.account.email_address)['is_read'])
        self.assertIsNotNone(self.db.get_email_record(105, self.account.email_address))
        log.error.assert_not_called()

    def test_uid_search_initial_boundary_skips_history_and_receives_later_mail(self):
        uids = [90, 105]
        self.use_uid_search_boundary(uids)
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 106))
        self.listener.email_client._parse_email.assert_not_called()
        uids.append(110)
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 111))
        self.listener.email_client._parse_email.assert_called_once_with(110)

    def test_uid_search_empty_initial_mailbox_receives_first_mail(self):
        uids = []
        self.use_uid_search_boundary(uids)
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 1))
        uids.append(500)
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 501))
        self.assertIsNotNone(self.db.get_email_record(500, self.account.email_address))

    def test_deleted_latest_mail_or_empty_mailbox_never_rewinds_cursor(self):
        self.seed_cursor()
        for uids in ([90], []):
            with self.subTest(uids=uids):
                self.use_uid_search_boundary(uids)
                self.listener._check_incremental_emails()
                self.assertEqual(self.saved_cursor(), (1, 100))
        self.listener.email_client._parse_email.assert_not_called()

    def test_uid_search_failure_does_not_initialize_or_advance_cursor(self):
        self.use_uid_search_boundary([])
        self.imap.search.side_effect = OSError('search failed')
        self.listener._check_incremental_emails()
        self.assertIsNone(self.saved_cursor())
        self.seed_cursor()
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 100))
        self.imap.search.side_effect = [[105], OSError('range search failed')]
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 100))
        self.listener.email_client._parse_email.assert_not_called()

    def test_uid_search_boundary_respects_batch_limit(self):
        self.seed_cursor()
        self.use_uid_search_boundary([100, 105])
        with patch.object(mail_listener.settings, 'max_emails_per_batch', 1):
            self.listener._check_incremental_emails()
            self.assertEqual(self.saved_cursor(), (1, 101))
            self.assertIsNone(self.db.get_email_record(105, self.account.email_address))
            self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 106))
        self.assertIsNotNone(self.db.get_email_record(105, self.account.email_address))

    def test_uid_search_boundary_retries_from_failed_message(self):
        self.seed_cursor()
        self.use_uid_search_boundary([100, 105, 110])
        parse = self.listener.email_client._parse_email.side_effect
        self.listener.email_client._parse_email.side_effect = lambda uid: None if uid == 105 else parse(uid)
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 101))
        self.assertIsNone(self.db.get_email_record(110, self.account.email_address))
        self.listener.email_client._parse_email.side_effect = parse
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 111))
        self.assertIsNotNone(self.db.get_email_record(105, self.account.email_address))
        self.assertIsNotNone(self.db.get_email_record(110, self.account.email_address))

    def test_uid_search_does_not_accept_changed_uidvalidity(self):
        self.seed_cursor()
        self.use_uid_search_boundary([100, 105])
        self.imap.select_folder.return_value[b'UIDVALIDITY'] = 2
        with patch.object(mail_listener, 'logger') as log:
            self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 100))
        self.assertIn('UIDVALIDITY 已变化', log.error.call_args.args[1])
        self.listener.email_client._parse_email.assert_not_called()

    def test_mail_arriving_after_uid_search_boundary_is_received_next_check(self):
        self.seed_cursor()
        self.use_uid_search_boundary([100])
        search = self.imap.search.side_effect
        def receive_after_boundary(query):
            result = search(query)
            if query == ['UID', '*']:
                self.use_uid_search_boundary([100, 105])
            return result
        self.imap.search.side_effect = receive_after_boundary
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 101))
        self.assertIsNone(self.db.get_email_record(105, self.account.email_address))
        self.listener._check_incremental_emails()
        self.assertEqual(self.saved_cursor(), (1, 106))
        self.assertIsNotNone(self.db.get_email_record(105, self.account.email_address))
