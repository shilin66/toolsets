import json
import os
import sqlite3
import tempfile
import time
import unittest
from datetime import date, datetime, timezone
from email.header import Header
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from scripts.diagnose_mail_intake import DiagnosticTimeout, deadline, diagnose


class FakeIMAP:
    def __init__(self, **kwargs):
        self.normalise_times = True
        self.selected = []
        self.searches = []
        self.fetches = []
        self.folder = None
        self.messages = {'INBOX': {}, 'Archive': {}}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def shutdown(self):
        self.closed = True

    def login(self, address, password):
        self.credentials = address, password

    def list_folders(self):
        return [((), '/', 'INBOX'), ((), '/', 'Archive'), ((b'\\Noselect',), '/', 'Root')]

    def select_folder(self, folder, readonly=False):
        if not readonly:
            raise AssertionError('诊断必须使用只读文件夹')
        self.folder = folder
        self.selected.append(folder)
        return {b'UIDVALIDITY': 1, b'UIDNEXT': 1000}

    def search(self, criteria):
        self.searches.append(criteria)
        if 'UNSEEN' in criteria or 'FROM' in criteria:
            raise AssertionError('诊断不能排除已读或带异常 From 的邮件')
        return list(self.messages[self.folder])

    def fetch(self, uids, fields):
        self.fetches.append((uids, fields))
        return {uid: self.messages[self.folder][uid] for uid in uids}


class DiagnoseMailIntakeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'mail.db'
        key = Fernet.generate_key()
        (self.path.parent / 'mail_secret.key').write_bytes(key)
        encrypted = Fernet(key).encrypt(b'diagnostic-password').decode()
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute('CREATE TABLE mail_accounts (email_address TEXT, password_enc TEXT, imap_server TEXT, imap_port INTEGER, imap_use_ssl INTEGER)')
            conn.execute('INSERT INTO mail_accounts VALUES (?, ?, ?, ?, ?)',
                         ('inbox@example.com', encrypted, 'imap.example.com', 993, 1))
            conn.execute('CREATE TABLE email_records (id INTEGER, email_id INTEGER, receiver TEXT, subject TEXT, create_time TEXT)')
        self.imap = FakeIMAP()
        self.checked_at = datetime.fromisoformat('2026-10-14T15:09:48+08:00')

    def mail(self, ticket='26014176', flags=(b'\\Seen',)):
        return {
            b'FLAGS': flags,
            b'INTERNALDATE': datetime(2026, 10, 14, 7, 9, tzinfo=timezone.utc),
            b'BODY[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)]': (
                'From: Supr.notification@rt.ru\r\n'
                f'Subject: Emergency maintenance 15/{ticket}\r\n'
                ' for HONG KONG CHINA TELECOM GLOBALLIMITED\r\n'
                'Date: Wed, 14 Oct 2026 07:00:00 +0300\r\n'
                'Message-ID: <target@example.com>\r\n\r\n'
            ).encode(),
        }

    def run_diagnosis(self, **kwargs):
        with patch.dict(os.environ, {'MAIL_SECRET_KEY': ''}):
            return diagnose(self.path, 'inbox@example.com', '26014176', self.checked_at,
                            client_factory=lambda **options: self.imap, **kwargs)

    def test_finds_seen_mail_beyond_twenty_and_reports_old_date_without_writes(self):
        self.imap.messages['INBOX'] = {uid: self.mail(str(uid)) for uid in range(1, 26)}
        self.imap.messages['INBOX'][1] = self.mail()
        original = self.path.read_bytes()
        result = self.run_diagnosis()
        self.assertEqual(len(result['matches']), 1)
        match = result['matches'][0]
        self.assertEqual(match['uid'], 1)
        self.assertTrue(match['is_read_now'])
        self.assertTrue(match['date_header_before_cutoff'])
        self.assertFalse(match['internaldate_before_cutoff'])
        self.assertEqual(match['database_record_ids'], [])
        self.assertEqual(self.imap.selected, ['INBOX'])
        self.assertFalse(self.imap.normalise_times)
        self.assertEqual(self.imap.searches[0], ['SUBJECT', '26014176'])
        self.assertEqual(self.path.read_bytes(), original)
        self.assertNotIn('diagnostic-password', json.dumps(result))
        for _, fields in self.imap.fetches:
            self.assertIn('BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)]', fields)
            self.assertNotIn('BODY[]', fields)

    def test_all_folders_finds_archive_and_does_not_confuse_folder_uids(self):
        self.imap.messages['Archive'][7] = self.mail()
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute('INSERT INTO email_records VALUES (1, 7, ?, ?, ?)',
                         ('inbox@example.com', 'different INBOX email', '2026-10-14'))
        result = self.run_diagnosis(all_folders=True)
        self.assertEqual(result['matches'][0]['folder'], 'Archive')
        self.assertIsNone(result['matches'][0]['database_record_ids'])
        self.assertEqual(self.imap.selected, ['INBOX', 'Archive'])

    def test_missing_database_or_key_is_not_created(self):
        missing = self.path.parent / 'missing.db'
        with self.assertRaises(ValueError):
            diagnose(missing, 'inbox@example.com', '26014176', self.checked_at)
        self.assertFalse(missing.exists())
        (self.path.parent / 'mail_secret.key').unlink()
        with self.assertRaises(ValueError):
            self.run_diagnosis()
        self.assertFalse((self.path.parent / 'mail_secret.key').exists())

    def test_missing_headers_fail_instead_of_reporting_no_match(self):
        self.imap.messages['INBOX'][1] = {b'FLAGS': (), b'INTERNALDATE': datetime.now(timezone.utc)}
        with self.assertRaises(RuntimeError):
            self.run_diagnosis()

    def test_scans_every_batch_and_decodes_encoded_subject(self):
        self.imap.messages['INBOX'] = {uid: self.mail(str(uid)) for uid in range(1, 206)}
        target = self.mail()
        encoded = Header('Emergency maintenance\u00a015/26014176\u00a0for HONG KONG', 'utf-8').encode()
        target[b'BODY[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)]'] = (
            f'Subject: {encoded}\r\nFrom: supr.notification@rt.ru\r\n'
            'Date: Wed, 14 Oct 2026 10:09:07 +0300\r\n\r\n'
        ).encode()
        self.imap.messages['INBOX'][205] = target
        result = self.run_diagnosis()
        self.assertEqual([match['uid'] for match in result['matches']], [205])
        self.assertFalse(result['matches'][0]['date_header_before_cutoff'])
        self.assertEqual(len(self.imap.fetches), 3)

    def test_reports_folder_access_failure_instead_of_complete_no_match(self):
        from imapclient.exceptions import IMAPClientError

        select = self.imap.select_folder
        def select_folder(folder, readonly=False):
            if folder == 'Archive':
                raise IMAPClientError('restricted')
            return select(folder, readonly)
        self.imap.select_folder = select_folder
        result = self.run_diagnosis(all_folders=True)
        self.assertEqual(result['matches'], [])
        self.assertEqual(result['folder_errors'], [{'folder': 'Archive', 'error_type': 'IMAPClientError'}])

    def test_progress_is_visible_before_search_and_date_scope_is_explicit(self):
        events = []
        search = self.imap.search
        def observed_search(criteria):
            self.assertTrue(any('INBOX' in event and '搜索' in event for event in events))
            return search(criteria)
        self.imap.search = observed_search
        result = self.run_diagnosis(progress=events.append, received_date=date(2026, 10, 14))
        self.assertEqual(self.imap.searches[0], [
            'SUBJECT', '26014176', 'SINCE', date(2026, 10, 13), 'BEFORE', date(2026, 10, 16),
        ])
        self.assertEqual(result['search_received_date'], '2026-10-14')
        self.assertTrue(any('登录' in event for event in events))

    def test_total_deadline_stops_stalled_command_and_closes_diagnostic_connection(self):
        def stalled_search(criteria):
            time.sleep(2)
            return []
        self.imap.search = stalled_search
        started = time.monotonic()
        with self.assertRaises(DiagnosticTimeout), deadline(0.05):
            self.run_diagnosis()
        self.assertLess(time.monotonic() - started, 1)
        self.assertTrue(self.imap.closed)


if __name__ == '__main__':
    unittest.main()
