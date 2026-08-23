import json
import stat
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from rpa.session_config import PortalSessionSettings
from rpa.session_models import LoginMode, PortalEnvironment, SessionState
from rpa.session_service import PortalSessionService


LOGIN_PAGE = b"""<!doctype html>
<html lang="zh-CN"><body>
<input id="user" placeholder="user">
<input id="password" placeholder="password" type="password">
<input id="captcha-input" placeholder="captcha">
<img id="captcha" width="120" height="40"
 src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='40'%3E%3Crect width='120' height='40' fill='navy'/%3E%3C/svg%3E">
<button id="login" type="button">Login</button>
<script>
document.querySelector('#login').addEventListener('click', () => {
  if (document.querySelector('#user').value === 'operator' &&
      document.querySelector('#password').value === 'secret' &&
      document.querySelector('#captcha-input').value === '42') {
    document.cookie = 'portal_auth=1; path=/';
    window.location.href = '/dashboard';
  }
});
</script></body></html>"""
DASHBOARD_PAGE = (
    b"<!doctype html><html><body><nav id='ready'>"
    b"portal dashboard</nav></body></html>"
)


class SessionPortalHandler(BaseHTTPRequestHandler):
    keepalive_requested = threading.Event()

    def do_GET(self):
        authenticated = "portal_auth=1" in self.headers.get("Cookie", "")
        authenticated_page = self.path in {"/dashboard", "/keepalive"}
        body = DASHBOARD_PAGE if authenticated_page and authenticated else LOGIN_PAGE
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if self.path == "/keepalive" and authenticated:
            self.keepalive_requested.set()
            self.send_header("Set-Cookie", "portal_keepalive=refreshed; path=/")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class PortalSessionServiceTest(unittest.TestCase):
    def test_close_is_idempotent(self):
        service = PortalSessionService(
            PortalSessionSettings.model_construct(),
        )

        service.close()
        service.close()

    def test_unconfigured_environment_returns_unavailable_without_browser(self):
        # Given
        settings = PortalSessionSettings.model_construct(
            production_login_url=None,
            production_mobile_login_url=None,
            production_session_check_url=None,
        )
        service = PortalSessionService(settings)

        # When
        try:
            status = service.status(PortalEnvironment.PRODUCTION)
        finally:
            service.close()

        # Then
        self.assertEqual(status.state, SessionState.UNAVAILABLE)
        self.assertFalse(status.authenticated)
        self.assertFalse(status.configured)
        self.assertEqual(status.environment, PortalEnvironment.PRODUCTION)

    def test_disabled_keepalive_remains_disabled_after_status_check(self):
        # Given
        settings = PortalSessionSettings.model_construct(
            production_login_url=None,
            production_mobile_login_url=None,
            production_session_check_url=None,
            session_keepalive_enabled=False,
        )
        service = PortalSessionService(settings)

        # When
        try:
            service.status(PortalEnvironment.PRODUCTION)
        finally:
            service.close()

        # Then
        self.assertEqual(
            service.keepalive_status().state.value,
            "disabled",
        )

    def test_keepalive_is_skipped_while_report_activity_blocks_it(self):
        # Given
        settings = PortalSessionSettings.model_construct()
        service = PortalSessionService(
            settings,
            keepalive_allowed=lambda: False,
        )

        # When
        try:
            result = service.keep_alive(PortalEnvironment.TEST)
        finally:
            service.close()

        # Then
        self.assertIsNone(result)
        self.assertEqual(service.keepalive_status().state.value, "paused")

    def test_password_login_captures_captcha_and_reuses_saved_session(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), SessionPortalHandler) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = f"http://127.0.0.1:{server.server_port}"
                    state_path = Path(temp_dir) / "auth-state.json"
                    settings = PortalSessionSettings(
                        _env_file=None,
                        test_login_url=f"{root}/login",
                        test_mobile_login_url=f"{root}/login",
                        test_session_check_url=f"{root}/dashboard",
                        username_selector="#user",
                        password_selector="#password",
                        captcha_input_selector="#captcha-input",
                        captcha_image_selector="#captcha",
                        submit_selector="#login",
                        post_login_ready_selector="#ready",
                        test_state_path=state_path,
                        timeout_ms=5_000,
                    )
                    service = PortalSessionService(settings)
                    try:
                        attempt = service.begin(
                            LoginMode.PASSWORD,
                            PortalEnvironment.TEST,
                        )
                        self.assertTrue(
                            attempt.captcha_data_url.startswith(
                                "data:image/png;base64,"
                            )
                        )
                        login_status = service.login_with_password(
                            attempt.attempt_id,
                            "operator",
                            "secret",
                            "42",
                        )
                        self.assertTrue(login_status.authenticated)
                        self.assertEqual(
                            login_status.environment,
                            PortalEnvironment.TEST,
                        )
                        self.assertEqual(
                            service.status(PortalEnvironment.TEST).state,
                            SessionState.AUTHENTICATED,
                        )
                        self.assertEqual(
                            stat.S_IMODE(state_path.stat().st_mode),
                            stat.S_IRUSR | stat.S_IWUSR,
                        )
                    finally:
                        service.close()
            finally:
                server.shutdown()
                thread.join()

    def test_keep_alive_persists_refreshed_portal_cookies(self):
        # Given
        with ThreadingHTTPServer(("127.0.0.1", 0), SessionPortalHandler) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = f"http://127.0.0.1:{server.server_port}"
                    state_path = Path(temp_dir) / "auth-state.json"
                    settings = PortalSessionSettings(
                        _env_file=None,
                        test_login_url=f"{root}/login",
                        test_mobile_login_url=f"{root}/login",
                        test_session_check_url=f"{root}/keepalive",
                        username_selector="#user",
                        password_selector="#password",
                        captcha_input_selector="#captcha-input",
                        captcha_image_selector="#captcha",
                        submit_selector="#login",
                        post_login_ready_selector="#ready",
                        test_state_path=state_path,
                        timeout_ms=5_000,
                    )
                    service = PortalSessionService(settings)
                    try:
                        attempt = service.begin(
                            LoginMode.PASSWORD,
                            PortalEnvironment.TEST,
                        )
                        service.login_with_password(
                            attempt.attempt_id,
                            "operator",
                            "secret",
                            "42",
                        )

                        # When
                        keepalive_status = service.keep_alive(
                            PortalEnvironment.TEST,
                        )

                        # Then
                        if keepalive_status is None:
                            self.fail("expected an authenticated keepalive result")
                        self.assertTrue(keepalive_status.authenticated)
                        saved_state = json.loads(state_path.read_text(encoding="utf-8"))
                        cookies = {
                            cookie["name"]: cookie["value"]
                            for cookie in saved_state["cookies"]
                        }
                        self.assertEqual(cookies["portal_keepalive"], "refreshed")
                        self.assertEqual(
                            service.keepalive_status().state.value,
                            "active",
                        )
                    finally:
                        service.close()
            finally:
                server.shutdown()
                thread.join()

    def test_keep_alive_runs_automatically_after_login(self):
        # Given
        SessionPortalHandler.keepalive_requested.clear()
        with ThreadingHTTPServer(("127.0.0.1", 0), SessionPortalHandler) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = f"http://127.0.0.1:{server.server_port}"
                    settings = PortalSessionSettings(
                        _env_file=None,
                        test_login_url=f"{root}/login",
                        test_mobile_login_url=f"{root}/login",
                        test_session_check_url=f"{root}/keepalive",
                        username_selector="#user",
                        password_selector="#password",
                        captcha_input_selector="#captcha-input",
                        captcha_image_selector="#captcha",
                        submit_selector="#login",
                        post_login_ready_selector="#ready",
                        test_state_path=Path(temp_dir) / "auth-state.json",
                        timeout_ms=5_000,
                    ).model_copy(
                        update={"session_keepalive_interval_seconds": 1},
                    )
                    service = PortalSessionService(settings)
                    try:
                        attempt = service.begin(
                            LoginMode.PASSWORD,
                            PortalEnvironment.TEST,
                        )
                        service.login_with_password(
                            attempt.attempt_id,
                            "operator",
                            "secret",
                            "42",
                        )

                        # When
                        keepalive_ran = SessionPortalHandler.keepalive_requested.wait(3)

                        # Then
                        self.assertTrue(keepalive_ran)
                    finally:
                        service.close()
            finally:
                server.shutdown()
                thread.join()

    def test_login_to_new_environment_invalidates_previous_environment(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), SessionPortalHandler) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = f"http://127.0.0.1:{server.server_port}"
                    test_state_path = Path(temp_dir) / "auth-state-test.json"
                    production_state_path = (
                        Path(temp_dir) / "auth-state-production.json"
                    )
                    settings = PortalSessionSettings(
                        _env_file=None,
                        test_login_url=f"{root}/login",
                        test_mobile_login_url=f"{root}/login",
                        test_session_check_url=f"{root}/dashboard",
                        production_login_url=f"{root}/login",
                        production_mobile_login_url=f"{root}/login",
                        production_session_check_url=f"{root}/dashboard",
                        username_selector="#user",
                        password_selector="#password",
                        captcha_input_selector="#captcha-input",
                        captcha_image_selector="#captcha",
                        submit_selector="#login",
                        post_login_ready_selector="#ready",
                        test_state_path=test_state_path,
                        production_state_path=production_state_path,
                        timeout_ms=5_000,
                    )
                    service = PortalSessionService(settings)
                    try:
                        test_attempt = service.begin(
                            LoginMode.PASSWORD,
                            PortalEnvironment.TEST,
                        )
                        service.login_with_password(
                            test_attempt.attempt_id,
                            "operator",
                            "secret",
                            "42",
                        )

                        production_attempt = service.begin(
                            LoginMode.PASSWORD,
                            PortalEnvironment.PRODUCTION,
                        )
                        production_status = service.login_with_password(
                            production_attempt.attempt_id,
                            "operator",
                            "secret",
                            "42",
                        )

                        self.assertFalse(test_state_path.exists())
                        self.assertTrue(production_state_path.exists())
                        self.assertTrue(production_status.authenticated)
                        self.assertEqual(
                            service.status(PortalEnvironment.TEST).state,
                            SessionState.LOGIN_REQUIRED,
                        )
                        self.assertEqual(
                            service.status(PortalEnvironment.PRODUCTION).state,
                            SessionState.AUTHENTICATED,
                        )
                    finally:
                        service.close()
            finally:
                server.shutdown()
                thread.join()


if __name__ == "__main__":
    unittest.main()
