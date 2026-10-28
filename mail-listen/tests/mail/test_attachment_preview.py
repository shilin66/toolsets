import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from openpyxl import Workbook
from PIL import Image

from attachment_preview import build_attachment_preview, PreviewError


class AttachmentPreviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, name, content):
        path = self.root / name
        path.write_bytes(content)
        return path

    def test_csv_encoding_quotes_and_identifiers_are_preserved(self):
        content = 'CircuitId\tOrderNumber\tRemark\r\n00123\t000456\t"line one\nline two"\r\n'
        path = self.file('a' * 32 + '-services.csv', content.encode('utf-16'))
        result = build_attachment_preview(path)
        self.assertEqual(result['name'], 'services.csv')
        self.assertEqual(result['sheets'][0]['columns'], ['CircuitId', 'OrderNumber', 'Remark'])
        self.assertEqual(result['sheets'][0]['rows'], [['00123', '000456', 'line one\nline two']])
        self.assertFalse(result['truncated'])
        self.assertEqual(path.read_bytes(), content.encode('utf-16'))

    def test_xlsx_multiple_sheets_formatted_identifiers_and_formula_as_text(self):
        path = self.root / 'services.xlsx'
        book = Workbook()
        sheet = book.active
        sheet.title = '线路'
        sheet.append(['CircuitId', 'Order', 'Formula', 'Start'])
        sheet.append(['00123', 456, '=HYPERLINK("https://example.invalid/", "do not open")', datetime(2026, 10, 28, 2)])
        sheet['B2'].number_format = '000000'
        book.create_sheet('备用').append(['000999'])
        book.save(path)
        result = build_attachment_preview(path)
        self.assertEqual([sheet['name'] for sheet in result['sheets']], ['线路', '备用'])
        self.assertEqual(result['sheets'][0]['rows'][1][:2], ['00123', '000456'])
        self.assertTrue(result['sheets'][0]['rows'][1][2].startswith('=HYPERLINK'))
        self.assertEqual(result['sheets'][0]['rows'][1][3], '2026-10-28 02:00:00')
        self.assertEqual(len(result['sheets'][0]['rows']), 2)
        self.assertFalse(result['truncated'])

    def test_word_text_and_tables_remain_data(self):
        path = self.root / 'notice.docx'
        with ZipFile(path, 'w') as archive:
            archive.writestr('word/document.xml', '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
              <w:p><w:r><w:t>&lt;script&gt;alert(1)&lt;/script&gt;</w:t></w:r></w:p>
              <w:tbl><w:tr><w:tc><w:p><w:r><w:t>000123</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
            </w:body></w:document>''')
        result = build_attachment_preview(path)
        self.assertEqual(result['blocks'], [{'kind':'text','text':'<script>alert(1)</script>'},
                                           {'kind':'table','rows':[['000123']]}])

    def test_document_entities_and_archive_expansion_are_rejected(self):
        path = self.root / 'bad.docx'
        with ZipFile(path, 'w') as archive:
            archive.writestr('word/document.xml', '<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>')
        with self.assertRaises(PreviewError):
            build_attachment_preview(path)
        with patch('attachment_preview.MAX_ZIP_BYTES', 10), self.assertRaises(PreviewError):
            build_attachment_preview(path)

    def test_row_and_size_limits_are_explicit(self):
        path = self.file('many.csv', ('id\n' + '00123\n' * 510).encode())
        result = build_attachment_preview(path)
        self.assertEqual(len(result['sheets'][0]['rows']), 500)
        self.assertTrue(result['truncated'])
        with patch('attachment_preview.MAX_FILE_BYTES', 10):
            self.assertEqual(build_attachment_preview(path)['kind'], 'unsupported')

    def test_binary_formats_are_validated_and_unsupported_formats_stay_downloadable(self):
        for extension in ('doc', 'xls', 'svg', 'html', 'zip'):
            self.assertEqual(build_attachment_preview(self.file('file.' + extension, b'content'))['kind'], 'unsupported')
        with self.assertRaises(PreviewError):
            build_attachment_preview(self.file('fake.pdf', b'<script>alert(1)</script>'))
        self.assertEqual(build_attachment_preview(self.file('file.pdf', b'%PDF-1.4\n'))['kind'], 'pdf')
        output = io.BytesIO()
        Image.new('RGB', (10, 10)).save(output, format='PNG')
        self.assertEqual(build_attachment_preview(self.file('image.png', output.getvalue()))['kind'], 'image')
