import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from rpa.config import RpaSettings
from rpa.login import LoginFailedError, PortalLoginRpa
from test_rpa_login import (
    DASHBOARD_PAGE,
    FakeCaptchaRecognizer,
    FakePortalHandler,
)


BLOCKED_PAGE = (
    "<!doctype html><html><body>"
    "网页已禁用开发者工具，请关闭开发者工具后刷新页面"
    "</body></html>"
).encode()


class RetryAfterLoginPageBlockHandler(FakePortalHandler):
    login_request_count = 0

    def do_GET(self):
        if self.path == "/login":
            type(self).login_request_count += 1
            if type(self).login_request_count == 1:
                self.send_page(BLOCKED_PAGE)
                return
        super().do_GET()


class RetryAfterPostLoginBlockHandler(FakePortalHandler):
    dashboard_request_count = 0

    def do_GET(self):
        if self.path == "/dashboard":
            type(self).dashboard_request_count += 1
            response_body = (
                BLOCKED_PAGE
                if type(self).dashboard_request_count == 1
                else DASHBOARD_PAGE
            )
            self.send_page(response_body)
            return
        super().do_GET()


class PersistentPostLoginBlockHandler(FakePortalHandler):
    dashboard_request_count = 0

    def do_GET(self):
        if self.path == "/dashboard":
            type(self).dashboard_request_count += 1
            self.send_page(BLOCKED_PAGE)
            return
        super().do_GET()


def make_settings(server_port: int, temp_dir: str) -> RpaSettings:
    """创建隔离的本地登录测试配置。"""
    return RpaSettings(
        login_url=f"http://127.0.0.1:{server_port}/login",
        username="rpa-user",
        password="rpa-password",
        openai_compatible_api_key="test-key",
        openai_compatible_model="vision-test",
        headless=True,
        timeout_ms=5_000,
        captcha_image_selector="#captcha",
        state_path=Path(temp_dir) / "auth-state.json",
        artifact_dir=Path(temp_dir) / "artifacts",
        success_screenshot_path=Path(temp_dir) / "login-success.png",
    )


class PortalAntiDevtoolsTest(unittest.TestCase):
    def test_login_refreshes_once_when_login_page_is_blocked(self):
        # Given
        RetryAfterLoginPageBlockHandler.login_request_count = 0
        with ThreadingHTTPServer(
            ("127.0.0.1", 0),
            RetryAfterLoginPageBlockHandler,
        ) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    settings = make_settings(server.server_port, temp_dir)

                    # When
                    result = PortalLoginRpa(
                        settings,
                        captcha_recognizer=FakeCaptchaRecognizer(),
                    ).login()

                    # Then
                    self.assertTrue(result.final_url.endswith("/dashboard"))
                    self.assertEqual(
                        RetryAfterLoginPageBlockHandler.login_request_count,
                        2,
                    )
            finally:
                server.shutdown()
                server_thread.join()

    def test_login_refreshes_post_login_block_before_success(self):
        # Given
        RetryAfterPostLoginBlockHandler.dashboard_request_count = 0
        with ThreadingHTTPServer(
            ("127.0.0.1", 0),
            RetryAfterPostLoginBlockHandler,
        ) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    settings = make_settings(server.server_port, temp_dir)

                    # When
                    result = PortalLoginRpa(
                        settings,
                        captcha_recognizer=FakeCaptchaRecognizer(),
                    ).login()

                    # Then
                    self.assertTrue(result.final_url.endswith("/dashboard"))
                    self.assertEqual(
                        RetryAfterPostLoginBlockHandler.dashboard_request_count,
                        2,
                    )
            finally:
                server.shutdown()
                server_thread.join()

    def test_login_rejects_persistent_post_login_block(self):
        # Given
        PersistentPostLoginBlockHandler.dashboard_request_count = 0
        with ThreadingHTTPServer(
            ("127.0.0.1", 0),
            PersistentPostLoginBlockHandler,
        ) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    settings = make_settings(server.server_port, temp_dir)

                    # When / Then
                    with self.assertRaises(LoginFailedError) as raised:
                        PortalLoginRpa(
                            settings,
                            captcha_recognizer=FakeCaptchaRecognizer(),
                        ).login()
                    self.assertIn("登录后页面", str(raised.exception))
                    self.assertEqual(
                        PersistentPostLoginBlockHandler.dashboard_request_count,
                        2,
                    )
            finally:
                server.shutdown()
                server_thread.join()


if __name__ == "__main__":
    unittest.main()
