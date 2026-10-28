import io
import json
from pathlib import Path
from unittest.mock import patch
import unittest

import api_server
from tests.api import test_user_access_api as access_fixture


class AttachmentPreviewApiTest(unittest.TestCase):
    setUp = access_fixture.UserAccessApiTest.setUp
    login = access_fixture.UserAccessApiTest.login

    def attach(self, index=0, filename='services.csv', content=b'CircuitId,OrderNumber\n00123,000456\n'):
        root = Path(self.temp.name)
        directory = root / 'email_attachments' / str(index)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        path.write_bytes(content)
        with self.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET attachments=? WHERE id=?',
                         (json.dumps([path.relative_to(root).as_posix()]), self.emails[index]))
            conn.commit()
        return root, path, f'/api/cutover/emails/{self.emails[index]}/attachments/0/preview'

    def test_preview_requires_login_and_respects_mailbox_even_when_read_only(self):
        root, path, url = self.attach()
        _, _, denied_url = self.attach(1)
        with patch.object(api_server, 'DATA_DIR', root):
            self.assertEqual(self.client.get(url).status_code, 401)
            self.login()
            self.assertEqual(self.client.get(denied_url).status_code, 404)
            self.repo.set_grants(self.user['id'], [{'account_id':self.accounts[0], 'can_operate':False}])
            result = self.client.get(url)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.get_json()['data']['sheets'][0]['rows'], [['00123', '000456']])
            self.assertIn('no-store', result.headers['Cache-Control'])
            self.assertEqual(path.read_bytes(), b'CircuitId,OrderNumber\n00123,000456\n')
            self.repo.set_grants(self.user['id'], [])
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_invalid_index_missing_file_and_unsafe_path_do_not_expose_files(self):
        root, path, url = self.attach()
        with patch.object(api_server, 'DATA_DIR', root):
            self.assertEqual(self.client.get(url.replace('/0/preview', '/20/preview'), headers=self.admin_headers).status_code, 404)
            path.unlink()
            self.assertEqual(self.client.get(url, headers=self.admin_headers).status_code, 404)
            outside = root / 'private.txt'
            outside.write_text('secret')
            with self.db.get_connection() as conn:
                conn.execute('UPDATE email_records SET attachments=? WHERE id=?',
                             (json.dumps(['email_attachments/../private.txt']), self.emails[0]))
                conn.commit()
            self.assertEqual(self.client.get(url, headers=self.admin_headers).status_code, 404)

    def test_corrupt_attachment_has_actionable_error_without_internal_path(self):
        root, _, url = self.attach(filename='bad.xlsx', content=b'not a workbook')
        with patch.object(api_server, 'DATA_DIR', root):
            result = self.client.get(url, headers=self.admin_headers)
            self.assertEqual(result.status_code, 422)
            self.assertIn('下载', result.get_json()['message'])
            self.assertNotIn(str(root), result.get_data(as_text=True))

    def test_preview_never_calls_fastgpt(self):
        root, _, url = self.attach()
        with patch.object(api_server, 'DATA_DIR', root), patch.object(api_server.requests, 'post') as external:
            self.assertEqual(self.client.get(url, headers=self.admin_headers).status_code, 200)
            external.assert_not_called()

    def test_local_sample_preview_is_ephemeral_authenticated_and_never_calls_ai(self):
        url = '/api/suppliers/preview-attachment-content'
        self.assertEqual(self.client.post(url).status_code, 401)
        headers = self.login()
        with patch.object(api_server.requests, 'post') as external:
            result = self.client.post(url, headers=headers, data={'file':(io.BytesIO('ID\t地点\n0001\t上海\n'.encode('utf-16')), '线路.csv')})
            self.assertEqual(result.status_code, 200, result.get_json())
            self.assertEqual(result.get_json()['data']['sheets'][0]['rows'], [['0001','上海']])
            self.assertIn('no-store', result.headers['Cache-Control'])
            external.assert_not_called()
        self.assertEqual(self.client.post(url, headers=headers, data={'file':(io.BytesIO(b'calendar'), 'event.ICS')}).status_code, 400)
        self.assertEqual(self.client.post(url, headers=headers, data={'file':(io.BytesIO(b'broken'), 'bad.xlsx')}).status_code, 422)

    def test_resolve_configured_sample_obeys_mailbox_scope_and_matches_legacy_body(self):
        url = '/api/suppliers/sample-attachment-source'
        root, _, _ = self.attach()
        self.assertEqual(self.client.post(url, json={}).status_code, 401)
        headers = self.login()
        record = self.db.get_email_record_by_id(self.emails[0])
        result = self.client.post(url, headers=headers, json={'subject':record['subject'], 'content':record['content']})
        self.assertEqual(result.status_code, 200, result.get_json())
        self.assertEqual(result.get_json()['data']['id'], self.emails[0])
        self.assertEqual(len(result.get_json()['data']['attachment_urls']), 1)
        self.assertEqual(self.client.post(url, headers=headers, json={'source_email_records_id':self.emails[1]}).status_code, 404)
        self.repo.set_grants(self.user['id'], [])
        self.assertEqual(self.client.post(url, headers=headers, json={'source_email_records_id':self.emails[0]}).status_code, 404)
