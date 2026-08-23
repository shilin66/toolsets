import unittest
import importlib
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from flask.testing import FlaskClient

from rpa.session_models import (
    PortalEnvironment,
    SessionKeepaliveState,
    SessionKeepaliveStatus,
)

api_server = importlib.import_module("api_server")

CAPTCHA_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAIAAAAAsCAIAAAAigicJAAACjklEQVR4nO3aPWgTYRjA8edy"
    "+TJJraDQDEVSxUHBgmkXESSlxHYLFZEg+AW6CFoVGqlVxIoYEFFwEWnJ0KKgQ90qVVcd0rRZ"
    "omhb2miFNlqN5i5fd5dXwkmq1kuWI0+iz29Kjpc3yfvPewe5cOFYHAgeA+JrEwAwqqvQvmM"
    "zLUeVTb5+TzsAH52CkFEAZBQAGQVARgGQUQBkFAAZBUBGAZBRAGQUoDZ+jNPRqzfSnSei2cj"
    "JBQgcsO/a+veXyORZf0j4/L0gZlmvz+ZpNZefNjIjBR+LsgJnfLaOSoPrSTgWD8fiTD+ewMq"
    "HTzJjLJ6Quy990Rp2fzw99DTNGEskFU9gpeK0vqtf55fkRFLxXtScs76oK6//DtjgMCQF1r"
    "wJkgLL5JjWsIN7rTYzBwAzHxUjX3xQ3pFOq6uJl2QQs5pz1iP9AwwedviD31xNhoXlwt1TD"
    "VrDGm3FRe8bSk1M5e+dXl86Pr+kXB4RSk9H+xrVB/v3WAHg7aK806X/e0ak/4cJPhJvnXR0"
    "tVnGJ3MTkXzpfH17LB2ZlY52rvO6V8/gN080dEXzYy+zu7eb1CMtTr606Gs9j+YPeYol/hn"
    "6B3i3KHvdFgDY57ZcGRUAHOrxcz22X4cNPhAG/A7eAB2t5v5QquIOUC0sK72+3+apd/oHaH"
    "HyU7NS+zZTdE5q3shrDRMy7Nl0rrvNMj0nbXGuDiu/Awb8dq7y9QL+92vAtYciAHAcXD/28"
    "+u/1tke+4Xh1MiLrMkIN45rXir+EBhOhc5r5qlHnPq3FLopX310U74m0E8RyCgAMgqAjAIg"
    "owDIKAAyCoCMAiCjAMgoADIKgIwCIKMAyCgAMgqAjAIgowC1cU9YvT1Gqo92AOD6AZ3mE76D"
    "VRRnAAAAAElFTkSuQmCC"
)


class FakePortalSessionService:
    def __init__(self) -> None:
        self.password_payload = None
        self.authenticated = True
        self.status_environment = None
        self.begin_environment = None

    def status(self, environment=None):
        self.status_environment = environment
        selected = environment or PortalEnvironment.TEST
        return SimpleNamespace(
            state=("authenticated" if self.authenticated else "login_required"),
            authenticated=self.authenticated,
            checked_at=datetime.now(UTC),
            message=(
                "综调会话有效"
                if self.authenticated
                else "尚未建立综调会话，请登录"
            ),
            environment=selected,
            configured=True,
            password_login_url="https://test.example.com/portal/#/pLogin",
            mobile_login_url="https://test.example.com/portal/#/login",
            state_path="data/rpa/auth-state-test.json",
            keepalive=SessionKeepaliveStatus(
                enabled=True,
                interval_seconds=600,
                state=SessionKeepaliveState.ACTIVE,
                checked_at=datetime.now(UTC),
                successful_at=datetime.now(UTC),
                environment=selected,
                message="登录保持运行正常",
            ),
        )

    def begin(self, mode, environment=None):
        self.begin_environment = environment
        selected = environment or PortalEnvironment.TEST
        return SimpleNamespace(
            attempt_id="attempt-123",
            mode=mode,
            environment=selected,
            captcha_data_url=CAPTCHA_DATA_URL,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    def refresh_captcha(self, attempt_id):
        return SimpleNamespace(
            attempt_id=attempt_id,
            mode="password",
            environment=PortalEnvironment.TEST,
            captcha_data_url=CAPTCHA_DATA_URL,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    def login_with_password(self, attempt_id, username, password, captcha):
        self.password_payload = (attempt_id, username, password, captcha)
        self.authenticated = True
        return self.status()


class RpaSessionApiTest(unittest.TestCase):
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.service = FakePortalSessionService()
        self.patch_stack = ExitStack()
        self.client: FlaskClient = api_server.app.test_client()
        self.headers: dict[str, str] = {}

    def setUp(self):
        self.service = FakePortalSessionService()
        self.patch_stack = ExitStack()
        self.patch_stack.enter_context(
            patch.object(
                api_server,
                "get_portal_session_service",
                return_value=self.service,
                create=True,
            )
        )
        self.client = api_server.app.test_client()
        self.headers = {"Authorization": "Bearer test-key"}

    def tearDown(self):
        self.patch_stack.close()

    def test_status_returns_session_state(self):
        response = self.client.get("/api/rpa/session", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["state"], "authenticated")
        self.assertTrue(data["keepalive"]["enabled"])
        self.assertEqual(data["keepalive"]["state"], "active")
        self.assertEqual(data["keepalive"]["interval_seconds"], 600)
        self.assertNotIn("secret-value", response.get_data(as_text=True))

    def test_status_routes_to_selected_environment(self):
        # Given / When
        response = self.client.get(
            "/api/rpa/session?environment=production",
            headers=self.headers,
        )

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.service.status_environment,
            PortalEnvironment.PRODUCTION,
        )
        self.assertEqual(response.get_json()["data"]["environment"], "production")

    def test_begin_password_attempt_returns_live_captcha(self):
        response = self.client.post(
            "/api/rpa/session/attempts",
            headers=self.headers,
            json={"mode": "password", "environment": "test"},
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()["data"]
        self.assertEqual(data["attempt_id"], "attempt-123")
        self.assertEqual(data["mode"], "password")
        self.assertEqual(data["environment"], "test")
        self.assertEqual(self.service.begin_environment, PortalEnvironment.TEST)
        self.assertTrue(data["captcha_data_url"].startswith("data:image/png;base64,"))

    def test_password_login_does_not_echo_credentials(self):
        response = self.client.post(
            "/api/rpa/session/attempts/attempt-123/password",
            headers=self.headers,
            json={
                "username": "operator-a",
                "password": "secret-value",
                "captcha": "7-2=5",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.service.password_payload,
            ("attempt-123", "operator-a", "secret-value", "7-2=5"),
        )
        body = response.get_data(as_text=True)
        self.assertNotIn("operator-a", body)
        self.assertNotIn("secret-value", body)
        self.assertNotIn("7-2=5", body)

    def test_invalid_mode_is_rejected_before_service_call(self):
        response = self.client.post(
            "/api/rpa/session/attempts",
            headers=self.headers,
            json={"mode": "unknown"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "INVALID_REQUEST")


if __name__ == "__main__":
    unittest.main()
