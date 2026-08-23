from pathlib import Path
from typing import assert_never

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

from .session_models import (
    PortalEnvironment,
    PortalEnvironmentInfo,
    PortalSessionError,
    ResolvedPortalEnvironment,
)


class PortalSessionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="RPA_",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
        frozen=True,
    )

    default_environment: PortalEnvironment = PortalEnvironment.TEST
    test_login_url: HttpUrl | None = None
    test_mobile_login_url: HttpUrl | None = None
    test_session_check_url: HttpUrl | None = None
    production_login_url: HttpUrl | None = None
    production_mobile_login_url: HttpUrl | None = None
    production_session_check_url: HttpUrl | None = None
    headless: bool = True
    ignore_https_errors: bool = False
    timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    slow_mo_ms: int = Field(default=0, ge=0, le=5_000)
    report_action_delay_ms: int = Field(default=800, ge=0, le=5_000)
    viewport_width: int = Field(default=1_920, ge=1_024, le=3_840)
    viewport_height: int = Field(default=1_080, ge=720, le=2_160)
    attempt_ttl_seconds: int = Field(default=300, ge=60, le=900)
    captcha_refresh_wait_ms: int = Field(default=500, ge=100, le=3_000)
    session_keepalive_enabled: bool = True
    session_keepalive_interval_seconds: int = Field(
        default=600,
        ge=60,
        le=86_400,
    )

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
    captcha_image_selector: str = (
        'xpath=//*[@placeholder="请输入验证码"]/following::img[1]'
    )
    submit_selector: str = 'button:has-text("登录")'
    mobile_phone_selector: str = 'input[placeholder="手机号"]'
    mobile_password_selector: str = 'input[placeholder="密码"]'
    mobile_captcha_input_selector: str = 'input[placeholder="图形验证码"]'
    mobile_captcha_image_selector: str = (
        'xpath=//*[@placeholder="图形验证码"]/following::img[1]'
    )
    mobile_sms_input_selector: str = 'input[placeholder="验证码"]'
    mobile_sms_button_selector: str = 'text=获取验证码'
    mobile_submit_selector: str = 'button:has-text("登录")'
    success_url_pattern: str | None = None
    post_login_ready_selector: str | None = 'text=工单处理'

    test_state_path: Path = Path("data/rpa/auth-state-test.json")
    production_state_path: Path = Path("data/rpa/auth-state-production.json")
    artifact_dir: Path = Path("data/rpa/artifacts")
    report_excel_import_selector: str = 'text=EXCEL导入'
    report_dialog_selector: str = 'text=传输任务及影响电路导入'
    report_file_input_selector: str = 'input[type="file"]'
    report_submit_selector: str = 'button:has-text("提交")'
    report_success_selector: str | None = None
    report_backbone_ready_selector: str = 'text=传输一干'
    report_backbone_submit_selector: str = 'button:has-text("提交")'
    report_backbone_attachment_selector: str = 'input[type="file"]'
    report_backbone_success_selector: str | None = 'text=提交成功'

    def describe_environment(
        self,
        environment: PortalEnvironment,
    ) -> PortalEnvironmentInfo:
        match environment:
            case PortalEnvironment.TEST:
                login_url = self.test_login_url
                mobile_login_url = self.test_mobile_login_url
                session_check_url = self.test_session_check_url
                state_path = self.test_state_path
            case PortalEnvironment.PRODUCTION:
                login_url = self.production_login_url
                mobile_login_url = self.production_mobile_login_url
                session_check_url = self.production_session_check_url
                state_path = self.production_state_path
            case unreachable:
                assert_never(unreachable)

        configured = all(
            value is not None
            for value in (login_url, mobile_login_url, session_check_url)
        )
        return PortalEnvironmentInfo(
            environment=environment,
            configured=configured,
            password_login_url=str(login_url) if login_url is not None else None,
            mobile_login_url=(
                str(mobile_login_url)
                if mobile_login_url is not None
                else None
            ),
            session_check_url=(
                str(session_check_url)
                if session_check_url is not None
                else None
            ),
            state_path=state_path,
        )

    def resolve_environment(
        self,
        environment: PortalEnvironment,
    ) -> ResolvedPortalEnvironment:
        info = self.describe_environment(environment)
        if not info.configured:
            match environment:
                case PortalEnvironment.TEST:
                    label = "测试"
                case PortalEnvironment.PRODUCTION:
                    label = "生产"
                case unreachable:
                    assert_never(unreachable)
            raise PortalSessionError(
                "ENVIRONMENT_NOT_CONFIGURED",
                f"{label}环境地址未配置，请检查 .env 中对应的 RPA 地址",
            )
        if (
            info.password_login_url is None
            or info.mobile_login_url is None
            or info.session_check_url is None
        ):
            raise PortalSessionError(
                "ENVIRONMENT_NOT_CONFIGURED",
                "综调环境地址配置不完整",
            )
        return ResolvedPortalEnvironment(
            environment=environment,
            login_url=info.password_login_url,
            mobile_login_url=info.mobile_login_url,
            session_check_url=info.session_check_url,
            state_path=info.state_path,
        )

    def inactive_state_path(self, environment: PortalEnvironment) -> Path:
        match environment:
            case PortalEnvironment.TEST:
                return self.production_state_path
            case PortalEnvironment.PRODUCTION:
                return self.test_state_path
            case unreachable:
                assert_never(unreachable)
