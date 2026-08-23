from io import BytesIO
import stat
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pydantic import ValidationError

from rpa.captcha import CaptchaRecognitionError
from rpa.config import CaptchaRecognizerMode, RpaSettings
from rpa.login import (
    PortalLoginRpa,
    build_captcha_recognizer,
)
from rpa.ocr import RapidOcrCaptchaRecognizer
from rpa.vision import OpenAICompatibleCaptchaRecognizer


LOGIN_PAGE = """<!doctype html>
<html lang="zh-CN">
<body>
  <input placeholder="请输入用户名">
  <input placeholder="请输入密码" type="password">
  <input placeholder="请输入验证码">
  <img
    id="captcha"
    alt=""
    width="120"
    height="40"
    style="background: white"
  >
  <button type="button">登录</button>
  <script>
    setTimeout(() => {
      document.querySelector("#captcha").src =
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='40'%3E%3Crect width='120' height='40' fill='black'/%3E%3C/svg%3E";
    }, 1000);
    document.querySelector("button").addEventListener("click", () => {
      const inputs = document.querySelectorAll("input");
      if (
        inputs[0].value === "rpa-user" &&
        inputs[1].value === "rpa-password" &&
        inputs[2].value === "30"
      ) {
        window.location.href = "/dashboard";
      }
    });
  </script>
</body>
</html>""".encode()
DASHBOARD_PAGE = b"<!doctype html><html><body><h1>dashboard</h1></body></html>"


class FakePortalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Given
        response_body = (
            DASHBOARD_PAGE if self.path == "/dashboard" else LOGIN_PAGE
        )

        # When
        self.send_page(response_body)

    def send_page(self, response_body: bytes) -> None:
        """返回测试页面。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()

        # Then
        self.wfile.write(response_body)

    def log_message(self, format, *args):
        return


class FakeCaptchaRecognizer:
    def __init__(self) -> None:
        self.received_image: bytes | None = None

    def recognize(self, image_png: bytes) -> str:
        self.received_image = image_png
        with Image.open(BytesIO(image_png)) as captcha_image:
            grayscale_image = captcha_image.convert("L")
            center_pixel = grayscale_image.getpixel(
                (
                    grayscale_image.width // 2,
                    grayscale_image.height // 2,
                )
            )
        if center_pixel > 240:
            raise CaptchaRecognitionError(
                reason="测试验证码图片尚未加载"
            )
        return "6 x 5 = ?"


class PortalLoginRpaTest(unittest.TestCase):
    def test_settings_reject_empty_password_at_environment_boundary(self):
        # Given
        invalid_password = ""

        # When / Then
        with self.assertRaises(ValidationError):
            RpaSettings(
                login_url="https://portal.example.com/login",
                username="rpa-user",
                password=invalid_password,
                openai_compatible_api_key="test-key",
                openai_compatible_model="vision-test",
            )

    def test_settings_load_openai_compatible_environment_variables(self):
        # Given
        environment = {
            "RPA_LOGIN_URL": "https://portal.example.com/login",
            "RPA_USERNAME": "rpa-user",
            "RPA_PASSWORD": "rpa-password",
            "OPENAI_COMPATIBLE_BASE_URL": "https://vision.example.com/v1",
            "OPENAI_COMPATIBLE_API_KEY": "secret-test-key",
            "OPENAI_COMPATIBLE_MODEL": "vision-test",
            "OPENAI_COMPATIBLE_TIMEOUT_SECONDS": "45",
        }

        # When
        with patch.dict("os.environ", environment, clear=True):
            settings = RpaSettings(_env_file=None)

        # Then
        self.assertEqual(
            str(settings.openai_compatible_base_url),
            "https://vision.example.com/v1",
        )
        self.assertEqual(
            settings.openai_compatible_api_key.get_secret_value(),
            "secret-test-key",
        )
        self.assertEqual(settings.openai_compatible_model, "vision-test")
        self.assertEqual(settings.openai_compatible_timeout_seconds, 45)

    def test_settings_select_local_ocr_from_environment(self):
        # Given
        environment = {
            "RPA_LOGIN_URL": "https://portal.example.com/login",
            "RPA_USERNAME": "rpa-user",
            "RPA_PASSWORD": "rpa-password",
            "RPA_CAPTCHA_RECOGNIZER": "ocr",
        }

        # When
        with patch.dict("os.environ", environment, clear=True):
            settings = RpaSettings(_env_file=None)
            recognizer = build_captcha_recognizer(settings)

        # Then
        self.assertEqual(
            settings.captcha_recognizer,
            CaptchaRecognizerMode.OCR,
        )
        self.assertIsInstance(recognizer, RapidOcrCaptchaRecognizer)

    def test_settings_use_multimodal_recognizer_by_default(self):
        # Given
        settings = RpaSettings(
            login_url="https://portal.example.com/login",
            username="rpa-user",
            password="rpa-password",
            captcha_recognizer="multimodal",
            openai_compatible_api_key="test-key",
            openai_compatible_model="vision-test",
        )

        # When
        recognizer = build_captcha_recognizer(settings)

        # Then
        self.assertEqual(
            settings.captcha_recognizer,
            CaptchaRecognizerMode.MULTIMODAL,
        )
        self.assertIsInstance(
            recognizer,
            OpenAICompatibleCaptchaRecognizer,
        )

    def test_login_saves_private_storage_state_when_credentials_are_valid(self):
        # Given
        with ThreadingHTTPServer(("127.0.0.1", 0), FakePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    state_path = Path(temp_dir) / "auth-state.json"
                    success_screenshot_path = (
                        Path(temp_dir) / "login-success.png"
                    )
                    settings = RpaSettings(
                        login_url=f"http://127.0.0.1:{server.server_port}/login",
                        username="rpa-user",
                        password="rpa-password",
                        openai_compatible_api_key="test-key",
                        openai_compatible_model="vision-test",
                        headless=True,
                        captcha_image_selector="#captcha",
                        state_path=state_path,
                        artifact_dir=Path(temp_dir) / "artifacts",
                        success_screenshot_path=success_screenshot_path,
                    )
                    captcha_recognizer = FakeCaptchaRecognizer()

                    # When
                    result = PortalLoginRpa(
                        settings,
                        captcha_recognizer=captcha_recognizer,
                    ).login()

                    # Then
                    self.assertTrue(result.final_url.endswith("/dashboard"))
                    self.assertIsNotNone(captcha_recognizer.received_image)
                    self.assertTrue(
                        captcha_recognizer.received_image.startswith(b"\x89PNG")
                    )
                    self.assertEqual(result.storage_state_path, state_path)
                    self.assertEqual(
                        result.success_screenshot_path,
                        success_screenshot_path,
                    )
                    self.assertTrue(success_screenshot_path.is_file())
                    self.assertTrue(
                        success_screenshot_path.read_bytes().startswith(
                            b"\x89PNG"
                        )
                    )
                    self.assertEqual(
                        stat.S_IMODE(
                            success_screenshot_path.stat().st_mode
                        ),
                        stat.S_IRUSR | stat.S_IWUSR,
                    )
                    self.assertTrue(state_path.is_file())
                    self.assertEqual(
                        stat.S_IMODE(state_path.stat().st_mode),
                        stat.S_IRUSR | stat.S_IWUSR,
                    )
            finally:
                server.shutdown()
                server_thread.join()

if __name__ == "__main__":
    unittest.main()
