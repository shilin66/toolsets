import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault('IMAP_SERVER', 'imap.example.com')
os.environ.setdefault('EMAIL_ADDRESS', 'test@example.com')
os.environ.setdefault('EMAIL_PASSWORD', 'password')
os.environ.setdefault('API_URL', 'https://api.example.com')
os.environ.setdefault('API_TOKEN', 'token')
os.environ.setdefault('API_KEY', 'test-key')

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_server


class AdminFrontendApiTest(unittest.TestCase):
    def test_admin_page_is_served(self):
        response = api_server.app.test_client().get("/admin")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("NOC 工作台", html)
        # Vue 3 + Element Plus 架构：挂载点与脚本（含版本号注入）
        self.assertIn('<div id="app"></div>', html)
        self.assertIn('/static/vendor/vue.global.prod.js', html)
        self.assertIn('/static/vendor/element-plus.js', html)
        self.assertIn('/static/admin-shared.js?v=', html)
        self.assertIn('/static/admin-views.js?v=', html)
        self.assertIn('/static/admin.js?v=', html)

    def test_auth_check_passes_with_valid_api_key(self):
        client = api_server.app.test_client()

        response = client.get(
            "/api/auth/check",
            headers={"Authorization": "Bearer test-key"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

    def test_auth_check_rejects_missing_or_invalid_key(self):
        client = api_server.app.test_client()

        missing = client.get("/api/auth/check")
        invalid = client.get(
            "/api/auth/check",
            headers={"Authorization": "Bearer wrong-key"},
        )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(invalid.status_code, 401)


if __name__ == "__main__":
    unittest.main()
