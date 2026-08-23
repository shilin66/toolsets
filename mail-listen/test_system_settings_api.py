import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault('IMAP_SERVER', 'imap.example.com')
os.environ.setdefault('EMAIL_ADDRESS', 'test@example.com')
os.environ.setdefault('EMAIL_PASSWORD', 'password')
os.environ.setdefault('API_URL', 'https://api.example.com')
os.environ.setdefault('API_TOKEN', 'token')
os.environ.setdefault('API_KEY', 'test-key')

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_server
from database import EmailDatabase


class SystemSettingsApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = EmailDatabase(os.path.join(self.tmpdir.name, 'mail_listener.db'))
        self.db_patch = patch.object(api_server, 'email_db', self.db)
        self.db_patch.start()
        self.client = api_server.app.test_client()
        self.headers = {'Authorization': 'Bearer test-key'}

    def tearDown(self):
        self.db_patch.stop()
        self.tmpdir.cleanup()

    def test_settings_requires_api_key(self):
        response = self.client.get('/api/system/settings')
        self.assertEqual(response.status_code, 401)

    def test_settings_default_empty(self):
        response = self.client.get('/api/system/settings', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertIsNone(payload['data']['guard_start_time'])
        self.assertIsNone(payload['data']['guard_end_time'])

    def test_settings_save_and_read(self):
        response = self.client.put(
            '/api/system/settings',
            headers=self.headers,
            json={'guard_start_time': '2026-07-15 00:00:00', 'guard_end_time': '2026-07-16 06:00:00'},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['data']['guard_start_time'], '2026-07-15 00:00:00')
        self.assertEqual(payload['data']['guard_end_time'], '2026-07-16 06:00:00')

        response = self.client.get('/api/system/settings', headers=self.headers)
        data = response.get_json()['data']
        self.assertEqual(data['guard_start_time'], '2026-07-15 00:00:00')
        self.assertEqual(data['guard_end_time'], '2026-07-16 06:00:00')

    def test_settings_update_partial(self):
        self.client.put(
            '/api/system/settings',
            headers=self.headers,
            json={'guard_start_time': '2026-07-15 08:00:00', 'guard_end_time': '2026-07-15 18:00:00'},
        )
        response = self.client.put(
            '/api/system/settings',
            headers=self.headers,
            json={'guard_end_time': '2026-07-15 20:30:00'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()['data']
        self.assertEqual(data['guard_start_time'], '2026-07-15 08:00:00')
        self.assertEqual(data['guard_end_time'], '2026-07-15 20:30:00')

    def test_settings_clear_with_null(self):
        self.client.put(
            '/api/system/settings',
            headers=self.headers,
            json={'guard_start_time': '2026-07-15 08:00:00'},
        )
        response = self.client.put(
            '/api/system/settings',
            headers=self.headers,
            json={'guard_start_time': None},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()['data']['guard_start_time'])

    def test_settings_rejects_invalid_format(self):
        for bad_value in ('22:00', '2026-07-15', '2026/07/15 00:00:00', '2026-13-15 00:00:00', 'abc', 800):
            response = self.client.put(
                '/api/system/settings',
                headers=self.headers,
                json={'guard_start_time': bad_value},
            )
            self.assertEqual(response.status_code, 400, f'value={bad_value!r}')

    def test_settings_rejects_empty_payload(self):
        response = self.client.put('/api/system/settings', headers=self.headers, json={})
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
