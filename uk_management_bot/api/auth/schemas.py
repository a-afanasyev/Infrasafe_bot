from pydantic import BaseModel
from typing import Optional


class TokenResponse(BaseModel):
    """TWA / legacy clients: tokens come back in body."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class WebTokenResponse(BaseModel):
    """Web SPA: refresh lives only in httpOnly cookie (plan §7.2)."""
    access_token: str
    token_type: str = "bearer"


class RefreshRequestOptional(BaseModel):
    """Refresh body is optional now — Web SPA uses cookie, TWA uses body (deprecated)."""
    refresh_token: str | None = None


class LogoutRequestOptional(BaseModel):
    refresh_token: str | None = None


class TelegramWidgetLogin(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class TWALogin(BaseModel):
    init_data: str


class PasswordLogin(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class SetPasswordRequest(BaseModel):
    password: str
    confirm_password: str


class MFARequiredResponse(BaseModel):
    mfa_required: bool = True
    mfa_token: str


class VerifyOTPRequest(BaseModel):
    mfa_token: str
    code: str
