from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .captcha import RpaError


class LoginMode(StrEnum):
    PASSWORD = "password"
    MOBILE = "mobile"


class PortalEnvironment(StrEnum):
    TEST = "test"
    PRODUCTION = "production"


class SessionState(StrEnum):
    AUTHENTICATED = "authenticated"
    LOGIN_REQUIRED = "login_required"
    UNAVAILABLE = "unavailable"


class SessionKeepaliveState(StrEnum):
    DISABLED = "disabled"
    WAITING = "waiting"
    PAUSED = "paused"
    ACTIVE = "active"
    LOGIN_REQUIRED = "login_required"
    UNAVAILABLE = "unavailable"


class BeginSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: LoginMode
    environment: PortalEnvironment | None = None


class SessionStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    environment: PortalEnvironment | None = None


class PasswordLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=500)
    captcha: str = Field(min_length=1, max_length=100)


class MobileSmsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    phone: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=500)
    captcha: str = Field(min_length=1, max_length=100)


class MobileVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sms_code: str = Field(min_length=1, max_length=20)


@dataclass(frozen=True, slots=True)
class SessionKeepaliveStatus:
    enabled: bool
    interval_seconds: int
    state: SessionKeepaliveState
    checked_at: datetime | None
    successful_at: datetime | None
    environment: PortalEnvironment | None
    message: str


@dataclass(frozen=True, slots=True)
class SessionStatus:
    state: SessionState
    authenticated: bool
    checked_at: datetime
    message: str
    environment: PortalEnvironment = PortalEnvironment.TEST
    configured: bool = True
    password_login_url: str | None = None
    mobile_login_url: str | None = None
    state_path: Path = Path("data/rpa/auth-state-test.json")
    keepalive: SessionKeepaliveStatus | None = None


@dataclass(frozen=True, slots=True)
class LoginAttempt:
    attempt_id: str
    mode: LoginMode
    captcha_data_url: str
    expires_at: datetime
    environment: PortalEnvironment = PortalEnvironment.TEST


@dataclass(frozen=True, slots=True)
class PortalEnvironmentInfo:
    environment: PortalEnvironment
    configured: bool
    password_login_url: str | None
    mobile_login_url: str | None
    session_check_url: str | None
    state_path: Path


@dataclass(frozen=True, slots=True)
class ResolvedPortalEnvironment:
    environment: PortalEnvironment
    login_url: str
    mobile_login_url: str
    session_check_url: str
    state_path: Path


@dataclass(frozen=True, slots=True)
class SmsRequestResult:
    attempt_id: str
    sms_requested: bool


@dataclass(frozen=True, slots=True)
class PortalSessionError(RpaError):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message
