from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'find_repeated_pdf_attachments.py'
spec = importlib.util.spec_from_file_location('pdf_audit', SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class DirectoryCreationTimeTest(unittest.TestCase):
    def directory_stat(self, **extra):
        return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_dev=1, st_ino=42,
                               st_mtime=1800001000, st_ctime=1800002000, **extra)

    def test_native_birth_time_is_reported_in_china_time(self):
        with patch.object(audit.os, 'stat', return_value=self.directory_stat(st_birthtime=1800000000)):
            result = audit.directory_times(Path('/data/mail_store/example'))
        expected = datetime.fromtimestamp(1800000000, timezone(timedelta(hours=8))).isoformat(timespec='seconds')
        self.assertEqual(result['created_at'], expected)
        self.assertEqual(result['created_at_source'], 'os.stat.st_birthtime')
        self.assertEqual(result['created_at_status'], 'available')

    def test_linux_uses_gnu_stat_birth_not_ctime(self):
        completed = SimpleNamespace(returncode=0, stdout='1 42 1800000000\n')
        with patch.object(audit.os, 'stat', return_value=self.directory_stat()), \
                patch.object(audit.sys, 'platform', 'linux'), \
                patch.object(audit.subprocess, 'run', return_value=completed):
            result = audit.directory_times(Path('/data/mail_store/example'))
        self.assertEqual(result['created_at_source'], 'GNU stat %W')
        self.assertNotEqual(result['created_at'], result['modified_at'])
        self.assertEqual(datetime.fromisoformat(result['created_at']).timestamp(), 1800000000)

    def test_unknown_birth_does_not_fall_back_to_ctime_or_epoch(self):
        with patch.object(audit.os, 'stat', return_value=self.directory_stat()), \
                patch.object(audit.sys, 'platform', 'linux'), \
                patch.object(audit.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='1 42 0\n')):
            result = audit.directory_times(Path('/data/mail_store/example'))
        self.assertIsNone(result['created_at'])
        self.assertEqual(result['created_at_status'], 'unavailable')
        self.assertIsNotNone(result['modified_at'])

    def test_replaced_directory_is_not_given_another_inode_birth_time(self):
        with patch.object(audit.os, 'stat', return_value=self.directory_stat()), \
                patch.object(audit.sys, 'platform', 'linux'), \
                patch.object(audit.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='1 99 1800000000')):
            result = audit.directory_times(Path('/data/mail_store/example'))
        self.assertIsNone(result['created_at'])
        self.assertEqual(result['created_at_status'], 'directory_changed')

    def test_missing_stat_command_and_timeout_leave_explicit_unavailable_time(self):
        for error in (FileNotFoundError('stat'), subprocess.TimeoutExpired('stat', 3)):
            with self.subTest(error=type(error).__name__), \
                    patch.object(audit.os, 'stat', return_value=self.directory_stat()), \
                    patch.object(audit.sys, 'platform', 'linux'), \
                    patch.object(audit.subprocess, 'run', side_effect=error):
                result = audit.directory_times(Path('/data/mail_store/example'))
                self.assertIsNone(result['created_at'])
                self.assertEqual(result['created_at_status'], 'query_failed')

    def test_missing_directory_is_explicit(self):
        with patch.object(audit.os, 'stat', side_effect=FileNotFoundError('missing')):
            result = audit.directory_times(Path('/data/mail_store/missing'))
        self.assertIsNone(result['created_at'])
        self.assertIsNone(result['modified_at'])
        self.assertEqual(result['created_at_status'], 'query_failed')

    def test_scan_adds_times_for_both_directories_without_changing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / 'mailboxes' / 'box' / 'messages' / '123' / 'attachments'
            directory.mkdir(parents=True)
            for prefix in ('a', 'b'):
                (directory / (prefix * 32 + '-plan.pdf')).write_bytes(b'pdf')
            before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                      for p in root.rglob('*')}
            report = audit.scan(root)
            group = report['top_groups'][0]
            self.assertEqual(group['copies'], 2)
            self.assertEqual(group['message_directory']['path'], str(directory.parent))
            self.assertEqual(group['attachment_directory']['path'], str(directory))
            self.assertIn('created_at_status', group['attachment_directory'])
            after = {str(p): (p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                     for p in root.rglob('*')}
            self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
