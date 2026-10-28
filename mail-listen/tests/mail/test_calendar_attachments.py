import json
import os
import tempfile
import unittest
from datetime import datetime
from email.header import Header
from email.message import EmailMessage as RawEmailMessage
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('API_KEY', 'test-key')

import api_server
import email_attachments
from actions import APIForwardAction
from database import EmailDatabase
from email_client import EmailClient
from models import EmailMessage
from supplier_config import SupplierConfigCreate, SupplierConfigRepository
from tests.mail.test_email_client import FakeIMAPClient, _test_account
from unconfigured_mail import ANALYSIS, DISCOVERY
from unconfigured_mail_repository import UnconfiguredMailRepository
from unconfigured_mail_worker import MailAIWorker


class CalendarAttachmentTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = self.root / 'data'
        self.db = EmailDatabase(str(self.root / 'mail.db'))
        SupplierConfigRepository(self.db)
        for target, name, value in (
            (email_attachments, 'DATA_DIR', self.data),
            (email_attachments, 'ATTACHMENT_DIR', self.data / 'email_attachments'),
            (api_server, 'email_db', self.db),
            (api_server, 'API_KEY', 'calendar-test-key'),
        ):
            p = patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)

    def parse_mail(self, include_documents):
        message = RawEmailMessage()
        message['Subject'] = 'Maintenance'
        message['From'] = 'noc@example.com'
        message['To'] = 'receiver@example.com'
        message['Date'] = 'Mon, 26 Oct 2026 10:00:00 +0800'
        message.set_content('Maintenance details in body')
        for filename, maintype, subtype in (
            ('calendar.ics', 'text', 'calendar'),
            ('日历.ICS', 'application', 'octet-stream'),
            (Header('割接.ics', 'utf-8').encode(), 'application', 'octet-stream'),
            ('event.txt', 'text', 'calendar'),
        ):
            message.add_attachment(b'BEGIN:VCALENDAR\r\nEND:VCALENDAR',
                                   maintype=maintype, subtype=subtype, filename=filename)
        if include_documents:
            for filename in ('lines.csv', 'notice.docx', 'window.txt', 'notice.pdf', 'image.png'):
                message.add_attachment(b'keep document', maintype='application',
                                       subtype='octet-stream', filename=filename)
        client = EmailClient(_test_account())
        client.client = FakeIMAPClient({9: message.as_bytes()})
        return client._parse_email(9)

    def test_mail_parse_does_not_save_calendars_but_keeps_documents_and_body(self):
        parsed = self.parse_mail(include_documents=True)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.content, 'Maintenance details in body')
        files = sorted(p for p in self.data.rglob('*') if p.is_file())
        self.assertEqual(len(files), 5)
        self.assertEqual(set(parsed.attachments), {p.relative_to(self.data).as_posix() for p in files})
        for filename in ('lines.csv', 'notice.docx', 'window.txt', 'notice.pdf', 'image.png'):
            self.assertTrue(any(p.name.endswith('-' + filename) for p in files))

    def test_calendar_only_mail_has_no_saved_attachments(self):
        parsed = self.parse_mail(include_documents=False)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.attachments, [])
        self.assertEqual(list(self.data.rglob('*')), [])

    def legacy_mail(self):
        return EmailMessage(uid=51, sender='noc@example.com', recipients=['receiver@example.com'],
                            subject='Maintenance', content='Maintenance body', received_date=datetime.now(),
                            attachments=['email_attachments/51/window.ics',
                                         'email_attachments/51/lines.csv',
                                         'email_attachments/51/日历.ICS'])

    def assert_filtered(self, content):
        self.assertEqual(content['attachments'], ['email_attachments/51/lines.csv'])
        self.assertEqual(len(content['attachment_urls']), 1)
        self.assertTrue(content['attachment_urls'][0].split('?')[0].endswith('/email_attachments/51/lines.csv'))
        self.assertIn('access_token=', content['attachment_urls'][0])

    def test_configured_supplier_forward_filters_legacy_calendars(self):
        SupplierConfigRepository(self.db).create(SupplierConfigCreate(
            name='Colt', email='noc@example.com', cutover_extract_prompt='Extract maintenance'))
        email = self.legacy_mail()
        response = Mock(status_code=200, json=lambda: {'choices': [{'message': {'content': 'ok'}}]})
        with patch('actions.render_email_body_to_image_url', return_value=None), patch(
            'actions.requests.post', return_value=response
        ) as post:
            result = APIForwardAction(self.db).execute(email, {})
        self.assertTrue(result.success)
        content = json.loads(post.call_args.kwargs['json']['messages'][0]['content'])
        self.assert_filtered(content)
        self.assertEqual(content['supplier_name'], 'Colt')
        self.assertEqual(len(email.attachments), 3)  # 历史记录本身不改写。

    def test_unconfigured_combined_request_filters_legacy_calendars(self):
        self.db.set_system_settings({}, {DISCOVERY: True, ANALYSIS: True})
        repo = UnconfiguredMailRepository(self.db)
        record_id = repo.ingest(self.legacy_mail(), 'receiver@example.com')
        sent = []

        def answer(_url, **kwargs):
            content = json.loads(kwargs['json']['messages'][0]['content'])
            sent.append(content)
            envelope = {key: content[key] for key in (
                'schema_version', 'task_type', 'request_id', 'attempt_id', 'email_records_id')}
            envelope['result'] = {
                'classification': {'status': 'succeeded', 'result': {
                    'mail_type': '其它', 'needs_review': False, 'classification_reason': 'test'}},
                'time_analysis': {'status': 'skipped'}, 'supplier_draft': {'status': 'skipped'}}
            return Mock(ok=True, json=lambda: {'choices': [{'message': {'content': json.dumps(envelope)}}]})

        with patch('unconfigured_mail_worker.requests.post', side_effect=answer):
            self.assertTrue(MailAIWorker(self.db).run_once())
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['task_type'], 'unconfigured_mail_process')
        self.assert_filtered(sent[0])
        self.assertEqual(self.db.get_email_record_by_id(record_id)['mail_type'], '其它')

    def test_preview_upload_rejects_calendar_without_saving(self):
        client = api_server.app.test_client()
        for filename, mime in (('日历.ICS', 'application/octet-stream'), ('event.txt', 'text/calendar')):
            with self.subTest(filename=filename):
                response = client.post('/api/suppliers/preview-attachments',
                    data={'file': (BytesIO(b'BEGIN:VCALENDAR'), filename, mime)},
                    headers={'Authorization': 'Bearer calendar-test-key'})
                self.assertEqual(response.status_code, 400)
        self.assertEqual(list(self.data.rglob('*')), [])

    def test_unconfigured_independent_jobs_filter_legacy_calendars(self):
        self.db.set_system_settings({}, {DISCOVERY: True, ANALYSIS: True})
        repo = UnconfiguredMailRepository(self.db)
        repo.ingest(self.legacy_mail(), 'receiver@example.com')
        job = repo.claim()
        envelope = {key: job[key] for key in (
            'task_type', 'request_id', 'attempt_id', 'email_records_id')}
        repo.complete({**envelope, 'schema_version': 1, 'result': {
            'mail_type': '割接通知', 'needs_review': False, 'classification_reason': 'test'}})
        # 独立任务与失败重试使用相同请求入口；模拟服务不可用，不触发真实 AI 调用。
        with patch('unconfigured_mail_worker.requests.post', return_value=Mock(ok=False, status_code=503)) as post:
            worker = MailAIWorker(self.db)
            self.assertTrue(worker.run_once())
            self.assertTrue(worker.run_once())
        contents = [json.loads(call.kwargs['json']['messages'][0]['content']) for call in post.call_args_list]
        self.assertEqual({content['task_type'] for content in contents},
                         {'supplier_config_draft', 'cutover_time_extract'})
        for content in contents:
            self.assert_filtered(content)

    def test_preview_extract_filters_legacy_calendars(self):
        response = Mock(status_code=200, json=lambda: {'choices': [{'message': {'content': 'ok'}}]})
        with patch('api_server.requests.post', return_value=response) as post:
            result = api_server.app.test_client().post('/api/suppliers/preview-extract',
                json={'content': 'Maintenance', 'attachments': self.legacy_mail().attachments},
                headers={'Authorization': 'Bearer calendar-test-key'})
        self.assertEqual(result.status_code, 200)
        self.assert_filtered(json.loads(post.call_args.kwargs['json']['messages'][0]['content']))
