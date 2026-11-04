import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'audit_mail_storage.py'


def load_audit():
    spec = importlib.util.spec_from_file_location('audit_mail_storage', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MailStorageAuditTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'mail_store'
        self.root.mkdir()

    def put(self, relative, content, age_days=2):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        modified = time.time() - age_days * 86400
        os.utime(path, (modified, modified))
        return path

    def attachment(self, uid, filename, content, **kwargs):
        return self.put('mailboxes/mailbox-test-12345678/messages/{}/attachments/{}'.format(
            uid, filename), content, **kwargs)

    def run_audit(self, *args):
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--root', str(self.root),
                                 '--format', 'json', *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_metadata_only_accounts_for_hardlinks_symlinks_and_sparse_files(self):
        original = self.attachment(1, 'report.PDF', b'PDF bytes')
        os.link(original, original.with_name('hardlink.pdf'))
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'large.pdf').write_bytes(b'x' * 10000)
        (self.root / 'external').symlink_to(outside, target_is_directory=True)
        (self.root / 'link.pdf').symlink_to(original)
        sparse = self.attachment(2, 'sparse.csv', b'')
        with sparse.open('r+b') as stream:
            stream.truncate(8 * 1024 * 1024)
        self.put('mailboxes/mailbox-test-12345678/messages/1/source-email-1.eml', b'eml')
        self.put('mailboxes/mailbox-test-12345678/messages/1/cutover/reports/d/1/1_1/a.png', b'png')
        self.put('mailboxes/mailbox-test-12345678/messages/1/cutover/report-inputs/1/customer.xlsx', b'zip')
        before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                  for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}
        report = self.run_audit()
        self.assertEqual(report['totals']['regular_file_paths'], 6)
        self.assertEqual(report['totals']['unique_regular_files'], 5)
        self.assertEqual(report['totals']['hardlink_aliases'], 1)
        self.assertEqual(report['totals']['symlinks'], 2)
        self.assertEqual(report['extensions']['.pdf']['files'], 1)
        self.assertEqual(report['extensions']['.csv']['logical_bytes'], 8 * 1024 * 1024)
        self.assertEqual(report['extensions']['.csv']['allocated_bytes'], sparse.stat().st_blocks * 512)
        self.assertEqual(report['categories']['report_screenshots']['files'], 1)
        self.assertEqual(report['categories']['report_inputs']['files'], 1)
        self.assertEqual(report['categories']['source_eml']['files'], 1)
        self.assertEqual(report['hash_audit']['enabled'], False)
        after = {str(p): (p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                 for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}
        self.assertEqual(before, after)

    def test_hash_distinguishes_same_directory_from_mail_reply_copies(self):
        self.attachment(1, 'uuid1-plan.pdf', b'same content')
        self.attachment(1, 'uuid2-plan.pdf', b'same content')
        self.attachment(2, 'uuid3-plan.pdf', b'same content')
        self.attachment(3, 'uuid4-plan.pdf', b'new contents')
        self.attachment(4, 'recent.pdf', b'same content', age_days=0)
        # ctime cannot be backdated on Unix: use zero settling time here and
        # a future mtime to exercise the recent-file exclusion deterministically.
        recent = self.root / 'mailboxes/mailbox-test-12345678/messages/4/attachments/recent.pdf'
        os.utime(recent, (time.time() + 86400, time.time() + 86400))
        report = self.run_audit('--hash-attachments', '--settle-hours', '0')
        audit = report['hash_audit']
        self.assertEqual(audit['hashed_files'], 4)
        self.assertEqual(audit['recent_files_skipped'], 1)
        self.assertEqual(audit['duplicate_groups'], 1)
        self.assertEqual(audit['within_directory_extra_copies'], 1)
        self.assertEqual(audit['across_directory_extra_copies'], 1)
        self.assertEqual(audit['extra_copy_logical_bytes'], 2 * len(b'same content'))
        self.assertEqual(audit['top_groups'][0]['attachment_directories'], 2)

    def test_metadata_scan_does_not_open_file_contents(self):
        self.attachment(1, 'do-not-read.pdf', b'data')
        code = '''
import importlib.util, sys
spec = importlib.util.spec_from_file_location('audit', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = sys.argv[2]
def deny_content(event, args):
    if event == 'open' and isinstance(args[0], str) and args[0].endswith('.pdf'):
        raise AssertionError('metadata scan attempted a content read')
sys.addaudithook(deny_content)
module.main(['--root', root, '--format', 'json'])
'''
        result = subprocess.run([sys.executable, '-B', '-c', code, str(SCRIPT), str(self.root)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['totals']['unique_regular_files'], 1)

    def test_missing_root_is_error_and_never_created(self):
        missing = self.base / 'missing'
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--root', str(missing)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(missing.exists())

    def test_read_error_marks_report_incomplete(self):
        self.attachment(1, 'unreadable.pdf', b'pdf')
        audit = load_audit()
        original_stat = os.stat

        def fail_one(path, *args, **kwargs):
            if path == 'unreadable.pdf':
                raise PermissionError('unreadable.pdf')
            return original_stat(path, *args, **kwargs)

        with patch.object(audit.os, 'stat', side_effect=fail_one):
            report = audit.inventory(self.root)
        self.assertFalse(report['complete'])
        self.assertEqual(report['errors']['count'], 1)
        self.assertEqual(report['totals']['unique_regular_files'], 0)

    def test_hash_does_not_trust_a_changed_or_symlink_replaced_file(self):
        path = self.attachment(1, 'changing.pdf', b'before')
        audit = load_audit()
        expected = path.stat()
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            path.write_bytes(b'after!')
            self.assertIsNone(audit.content_hash(directory_fd, path.name, expected))
            path.unlink()
            path.symlink_to(self.base / 'outside.pdf')
            with self.assertRaises(OSError):
                audit.content_hash(directory_fd, path.name, expected)
        finally:
            os.close(directory_fd)

    def test_default_hash_settling_checks_ctime_even_when_mtime_is_old(self):
        self.attachment(1, 'backdated.pdf', b'pdf', age_days=30)
        report = self.run_audit('--hash-attachments')
        self.assertEqual(report['hash_audit']['hashed_files'], 0)
        self.assertEqual(report['hash_audit']['recent_files_skipped'], 1)

    def test_top_limits_and_legacy_layout(self):
        for uid in range(5):
            self.attachment(uid, 'tiny.ics', b'calendar')
        report = self.run_audit('--top', '2')
        self.assertEqual(len(report['top_messages_by_allocated_bytes']), 2)
        self.assertEqual(len(report['top_files']), 2)
        self.assertEqual(report['message_directories'], 5)
        data_root = self.base / 'data'
        legacy = data_root / 'email_attachments' / '42'
        legacy.mkdir(parents=True)
        (legacy / 'old.csv').write_bytes(b'a,b')
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--root', str(data_root),
                                 '--format', 'json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['categories']['legacy_attachments']['files'], 1)


if __name__ == '__main__':
    unittest.main()
