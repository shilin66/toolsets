import base64
import os
import unittest
from email.message import EmailMessage

os.environ.setdefault('API_KEY', 'test-key')

from supplier_eml import MAX_EML_BYTES, parse_supplier_eml


def sample_eml():
    message = EmailMessage()
    message['From'] = '供应商 <notice@example.com>'
    message['Subject'] = '割接通知 CRQ-001'
    message.set_content('纯文本正文', charset='gb18030', cte='quoted-printable')
    message.add_alternative('<p>更换设备</p><table><tr><td>001234</td></tr></table>', subtype='html')
    message.add_attachment('编号\t位置\n001234\t上海\n'.encode('utf-16'), maintype='text', subtype='csv', filename='../线路.csv')
    message.add_attachment(b'BEGIN:VCALENDAR', maintype='text', subtype='calendar', filename='notice.ICS')
    return message.as_bytes()


class SupplierEmlTest(unittest.TestCase):
    def test_encoded_headers_html_and_attachments(self):
        result = parse_supplier_eml(sample_eml())
        self.assertEqual(result['subject'], '割接通知 CRQ-001')
        self.assertEqual(result['sender'], 'notice@example.com')
        self.assertIn('<td>001234</td>', result['content'])
        self.assertNotIn('纯文本正文', result['content'])
        self.assertEqual(result['skipped_attachments'], ['notice.ICS'])
        self.assertEqual(len(result['attachments']), 1)
        attachment = result['attachments'][0]
        self.assertEqual(attachment['name'], '线路.csv')
        self.assertIn('001234,上海', base64.b64decode(attachment['base64']).decode('utf-8'))

    def test_plain_text_charset_and_named_text_attachment_are_separate(self):
        message = EmailMessage()
        message['Subject'] = '维护'
        message.set_content('正文内容', charset='gb18030', cte='quoted-printable')
        message.add_attachment('附件内容', filename='data.txt')
        result = parse_supplier_eml(message.as_bytes())
        self.assertIn('正文内容', result['content'])
        self.assertNotIn('附件内容', result['content'])
        self.assertEqual(len(result['attachments']), 1)

    def test_invalid_size_and_attachment_limit(self):
        for raw in (b'', b'not an email', b'x' * (MAX_EML_BYTES + 1)):
            with self.assertRaises(ValueError):
                parse_supplier_eml(raw)
        message = EmailMessage()
        message['Subject'] = 'Too many files'
        for index in range(31):
            message.add_attachment(b'file', maintype='application', subtype='octet-stream', filename=f'{index}.txt')
        with self.assertRaisesRegex(ValueError, '30'):
            parse_supplier_eml(message.as_bytes())
