import codecs
import csv
import io
import os
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('API_KEY', 'test-key')

import email_attachments
from email_client import EmailClient
from tests.mail.test_email_client import _test_account


class AttachmentNormalizationTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name, value in (('DATA_DIR', self.root), ('ATTACHMENT_DIR', self.root / 'email_attachments')):
            p = patch.object(email_attachments, name, value)
            p.start()
            self.addCleanup(p.stop)

    def save(self, filename, content, *, preview=False, **kwargs):
        relative = (email_attachments.save_preview_attachment(filename, content, **kwargs) if preview else
                    email_attachments.save_attachment('receiver@example.com', 123, filename, content, **kwargs))
        return (self.root / relative).read_bytes()

    def test_utf16_tsv_csv_keeps_all_cells_in_both_save_paths(self):
        rows = [['Circuit ID', '城市', 'Notes', ''],
                ['00123', '北京', 'comma, quote " and\nsecond line', ''],
                ['MRS/FRA/LE-306115', 'FRANKFURT', 'literal\ttab', '']]
        source = io.StringIO(newline='')
        csv.writer(source, delimiter='\t').writerows(rows)
        for preview in (False, True):
            with self.subTest(preview=preview):
                saved = self.save('线路.CSV', source.getvalue().encode('utf-16'), preview=preview)
                self.assertEqual(list(csv.reader(io.StringIO(saved.decode('utf-8'), newline=''))), rows)
                self.assertNotIn(b'\x00', saved)
                self.assertFalse(saved.startswith(codecs.BOM_UTF8))

    def test_unicode_boms_txt_are_converted_without_changing_text(self):
        text = '维护通知\r\n线路 00123\tParis — 北京\r\n'
        for encoding in ('utf-8-sig', 'utf-16', 'utf-32'):
            with self.subTest(encoding=encoding):
                self.assertEqual(self.save('notice.TXT', text.encode(encoding)), text.encode('utf-8'))
        for bom, encoding in ((codecs.BOM_UTF16_BE, 'utf-16-be'), (codecs.BOM_UTF32_BE, 'utf-32-be')):
            with self.subTest(encoding=encoding):
                self.assertEqual(self.save('notice.txt', bom + text.encode(encoding)), text.encode('utf-8'))

    def test_valid_utf8_txt_and_standard_csv_keep_values(self):
        text = '你好\tWorld\r\n原有换行\n'.encode('utf-8')
        self.assertEqual(self.save('notice.txt', text), text)
        raw = 'id,remark,empty\r\n00123,"a,b and ""quote""",\r\n'.encode('utf-8')
        saved = self.save('lines.csv', raw)
        self.assertEqual(list(csv.reader(io.StringIO(saved.decode('utf-8')))),
                         list(csv.reader(io.StringIO(raw.decode('utf-8')))))
        self.assertEqual(self.save('lines.csv', saved), saved)

    def test_preview_upload_and_download_return_normalized_csv(self):
        import api_server

        with patch.object(api_server, 'API_KEY', 'normalization-test-key'):
            client = api_server.app.test_client()
            response = client.post('/api/suppliers/preview-attachments',
                data={'file': (io.BytesIO('Circuit ID\tCity\r\n00123\t北京\r\n'.encode('utf-16')),
                               'lines.csv', 'application/octet-stream')},
                headers={'Authorization': 'Bearer normalization-test-key'})
            self.assertEqual(response.status_code, 201)
            path = response.get_json()['data']['relative_path']
            download = client.get('/api/email/attachments/' + path,
                                  headers={'Authorization': 'Bearer normalization-test-key'})
            try:
                self.assertEqual(download.status_code, 200)
                self.assertEqual(list(csv.reader(io.StringIO(download.get_data().decode('utf-8')))),
                                 [['Circuit ID', 'City'], ['00123', '北京']])
            finally:
                download.close()

    def test_declared_gb18030_charset_is_used_by_email_attachment_parser(self):
        text = '割接通知\r\n线路编号：00123\r\n地点：北京\r\n'
        message = EmailMessage()
        message.set_content('body')
        message.add_attachment(text.encode('gb18030'), maintype='text', subtype='plain',
                               filename='notice.txt', params={'charset': 'gb18030'})
        paths = EmailClient(_test_account())._extract_attachments(message, 123)
        self.assertEqual(len(paths), 1)
        self.assertEqual((self.root / paths[0]).read_bytes(), text.encode('utf-8'))

    def test_ambiguous_or_damaged_text_keeps_original_and_logs_failure(self):
        for raw in (b'\xff\xfe\x41', b'PK\x00\x01\x02',
                    '割接通知\r\n线路编号：00123\r\n地点：北京\r\n'.encode('gb18030')):
            with self.subTest(raw=raw), patch('email_attachments.logger') as log:
                self.assertEqual(self.save('notice.txt', raw), raw)
                self.assertTrue(log.warning.called)
                self.assertIn('attachment_normalization_failed', str(log.warning.call_args))

    def test_non_text_formats_are_byte_identical(self):
        raw = b'\xff\xfe\x00\x01\x02binary'
        for extension in ('doc', 'docx', 'xls', 'xlsx', 'pdf', 'png'):
            with self.subTest(extension=extension):
                self.assertEqual(self.save('notice.' + extension, raw), raw)

    def test_empty_and_single_column_csv_remain_usable(self):
        self.assertEqual(self.save('empty.txt', b''), b'')
        self.assertEqual(self.save('empty.csv', b''), b'')
        saved = self.save('single.csv', 'Circuit ID\n00123\n'.encode('utf-16'))
        self.assertEqual(list(csv.reader(io.StringIO(saved.decode('utf-8')))), [['Circuit ID'], ['00123']])
