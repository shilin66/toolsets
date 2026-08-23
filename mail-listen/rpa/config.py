"""RPA 登录配置。"""

from enum import StrEnum
from pathlib import Path
from typing import Self, assert_never

from pydantic import Field, HttpUrl, SecretStr, model_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict


class CaptchaRecognizerMode(StrEnum):
    MULTIMODAL = "multimodal"
    OCR = "ocr"


class RpaSettings(BaseSettings):
    """从 RPA_ 前缀的环境变量加载并校验登录配置。"""

    model_config = SettingsConfigDict(
        env_prefix="RPA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    login_url: HttpUrl
    username: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)
    headless: bool = True
    ignore_https_errors: bool = False
    timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    slow_mo_ms: int = Field(default=0, ge=0, le=5_000)

    username_selector: str = Field(
        default='input[placeholder="请输入用户名"]',
        min_length=1,
    )
    password_selector: str = Field(
        default='input[placeholder="请输入密码"]',
        min_length=1,
    )
    captcha_input_selector: str = Field(
        default='input[placeholder="请输入验证码"]',
        min_length=1,
    )
    captcha_image_selector: str = Field(
        default=(
            'xpath=//*[@placeholder="请输入验证码"]/following::img[1]'
        ),
        min_length=1,
    )
    captcha_recognizer: CaptchaRecognizerMode = (
        CaptchaRecognizerMode.MULTIMODAL
    )
    submit_selector: str = Field(
        default='button:has-text("登录")',
        min_length=1,
    )
    success_url_pattern: str | None = None

    openai_compatible_base_url: HttpUrl = Field(
        default="https://api.openai.com/v1",
        validation_alias="OPENAI_COMPATIBLE_BASE_URL",
    )
    openai_compatible_api_key: SecretStr | None = Field(
        default=None,
        min_length=1,
        validation_alias="OPENAI_COMPATIBLE_API_KEY",
    )
    openai_compatible_model: str | None = Field(
        default=None,
        min_length=1,
        validation_alias="OPENAI_COMPATIBLE_MODEL",
    )
    openai_compatible_timeout_seconds: int = Field(
        default=120,
        ge=1,
        le=300,
        validation_alias="OPENAI_COMPATIBLE_TIMEOUT_SECONDS",
    )

    state_path: Path = Path("data/rpa/auth-state.json")
    artifact_dir: Path = Path("data/rpa/artifacts")
    success_screenshot_path: Path = Path(
        "data/rpa/artifacts/login-success.png"
    )

    @model_validator(mode="after")
    def require_multimodal_settings(self) -> Self:
        """仅在多模态模式下要求 API Key 和模型名称。"""
        match self.captcha_recognizer:
            case CaptchaRecognizerMode.OCR:
                return self
            case CaptchaRecognizerMode.MULTIMODAL:
                if (
                    self.openai_compatible_api_key is None
                    or self.openai_compatible_model is None
                ):
                    raise PydanticCustomError(
                        "missing_multimodal_settings",
                        (
                            "multimodal 模式必须配置 "
                            "OPENAI_COMPATIBLE_API_KEY 和 "
                            "OPENAI_COMPATIBLE_MODEL"
                        ),
                    )
                return self
            case unreachable:
                assert_never(unreachable)
