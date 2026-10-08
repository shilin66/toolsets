import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rpa.vision import OpenAICompatibleCaptchaRecognizer


class FakeVisionApiHandler(BaseHTTPRequestHandler):
    request_payload: dict[str, object] | None = None
    authorization: str | None = None

    def do_POST(self) -> None:
        content_length = int(self.headers["Content-Length"])
        type(self).request_payload = json.loads(self.rfile.read(content_length))
        type(self).authorization = self.headers.get("Authorization")
        response_body = json.dumps(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "vision-test",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "6 × 5 = ?",
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, format, *args) -> None:
        return


class OpenAICompatibleCaptchaRecognizerTest(unittest.TestCase):
    def test_sends_only_captcha_image_as_data_url_and_returns_expression(self):
        # Given
        with ThreadingHTTPServer(
            ("127.0.0.1", 0),
            FakeVisionApiHandler,
        ) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                recognizer = OpenAICompatibleCaptchaRecognizer(
                    base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    api_key="secret-test-key",
                    model="vision-test",
                    timeout_seconds=5,
                )

                # When
                expression = recognizer.recognize(b"\x89PNG\r\n\x1a\ncaptcha")

                # Then
                self.assertEqual(expression, "6 × 5 = ?")
                self.assertEqual(
                    FakeVisionApiHandler.authorization,
                    "Bearer secret-test-key",
                )
                payload = FakeVisionApiHandler.request_payload
                self.assertIsNotNone(payload)
                messages = payload["messages"]
                image_url = messages[0]["content"][1]["image_url"]["url"]
                self.assertTrue(image_url.startswith("data:image/png;base64,"))
                self.assertNotIn("rpa-user", json.dumps(payload))
                self.assertNotIn("rpa-password", json.dumps(payload))
            finally:
                server.shutdown()
                server_thread.join()


if __name__ == "__main__":
    unittest.main()
