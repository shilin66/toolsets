"""通过 OpenAI-compatible 视觉接口识别图片验证码。"""

import base64
from typing import Final, Protocol

from pydantic import BaseModel, Field, ValidationError
import requests

from rpa.captcha import CaptchaRecognitionError


_CAPTCHA_PROMPT: Final[str] = (
    "识别图片中的算术验证码。只返回完整算式，例如 6*5=?；"
    "不要解释，不要计算答案；无法确定时只返回 UNKNOWN。"
)


class CaptchaRecognizer(Protocol):
    """验证码图片识别器边界。"""

    def recognize(self, image_png: bytes) -> str:
        """返回图片中的算术表达式文本。"""


class _AssistantMessage(BaseModel):
    content: str = Field(min_length=1)


class _CompletionChoice(BaseModel):
    message: _AssistantMessage


class _ChatCompletionResponse(BaseModel):
    choices: list[_CompletionChoice] = Field(min_length=1)


class OpenAICompatibleCaptchaRecognizer:
    """调用兼容 OpenAI Chat Completions 的视觉模型。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
    ) -> None:
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    def recognize(self, image_png: bytes) -> str:
        """仅上传验证码截图，并返回模型识别出的算式。"""
        if not image_png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise CaptchaRecognitionError(reason="验证码截图不是有效的 PNG 图片")

        encoded_image = base64.b64encode(image_png).decode("ascii")
        request_payload = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": 32,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _CAPTCHA_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    "data:image/png;base64,"
                                    f"{encoded_image}"
                                ),
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
        }

        try:
            response = requests.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=request_payload,
                timeout=self._timeout_seconds,
            )
        except requests.Timeout as error:
            raise CaptchaRecognitionError(
                reason="多模态验证码识别请求超时"
            ) from error
        except requests.RequestException as error:
            raise CaptchaRecognitionError(
                reason="无法连接多模态验证码识别服务"
            ) from error

        if not response.ok:
            raise CaptchaRecognitionError(
                reason=(
                    "多模态验证码识别服务返回错误"
                    f"（HTTP {response.status_code}）"
                )
            )

        try:
            completion = _ChatCompletionResponse.model_validate(
                response.json()
            )
        except (requests.exceptions.JSONDecodeError, ValidationError) as error:
            raise CaptchaRecognitionError(
                reason="多模态验证码识别服务返回了无效响应"
            ) from error

        return completion.choices[0].message.content.strip()
