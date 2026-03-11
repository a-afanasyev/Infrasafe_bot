from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address

from uk_management_bot.api.auth.schemas import (
    TokenResponse, TelegramWidgetLogin, TWALogin,
    PasswordLogin, RefreshRequest, SetPasswordRequest,
)
from uk_management_bot.api.auth.service import (
    verify_telegram_widget, verify_twa_init_data,
    verify_password, hash_password,
    create_access_token, create_refresh_token_value, hash_token,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from uk_management_bot.api.dependencies import get_db, get_current_user, _parse_user_roles
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.refresh_token import RefreshToken
from uk_management_bot.config.settings import settings

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _build_token_response(user: User) -> dict:
    roles = _parse_user_roles(user)
    access_token = create_access_token(user.id, roles)
    refresh_value = create_refresh_token_value()
    return {"access_token": access_token, "refresh_value": refresh_value, "roles": roles}


async def _save_refresh_token(db: AsyncSession, user_id: int, token_value: str, device_info: str = "") -> None:
    expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    rt = RefreshToken(
        user_id=user_id,
        token_hash=hash_token(token_value),
        expires_at=expires,
        device_info=device_info,
    )
    db.add(rt)
    await db.commit()


@router.post("/telegram-widget", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login_telegram_widget(request: Request, data: TelegramWidgetLogin, db: AsyncSession = Depends(get_db)):
    data_dict = data.model_dump()
    if not verify_telegram_widget(data_dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram auth data")

    result = await db.execute(select(User).where(User.telegram_id == data.id))
    user = result.scalar_one_or_none()
    if not user or user.status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not approved")

    tokens = _build_token_response(user)
    await _save_refresh_token(db, user.id, tokens["refresh_value"])
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_value"])


@router.post("/twa", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login_twa(request: Request, data: TWALogin, db: AsyncSession = Depends(get_db)):
    user_data = verify_twa_init_data(data.init_data, settings.BOT_TOKEN)
    if not user_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid initData")

    telegram_id = user_data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No user id in initData")

    result = await db.execute(select(User).where(User.telegram_id == int(telegram_id)))
    user = result.scalar_one_or_none()
    if not user or user.status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not approved")

    tokens = _build_token_response(user)
    await _save_refresh_token(db, user.id, tokens["refresh_value"])
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_value"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login_password(request: Request, data: PasswordLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not approved")

    tokens = _build_token_response(user)
    await _save_refresh_token(db, user.id, tokens["refresh_value"])
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_value"])


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(data.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    rt = result.scalar_one_or_none()

    if not rt or not rt.is_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    # Rotate: revoke old, issue new
    rt.revoked_at = datetime.now(timezone.utc)
    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one()

    tokens = _build_token_response(user)
    await _save_refresh_token(db, user.id, tokens["refresh_value"])
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_value"])


@router.post("/logout")
@limiter.limit("10/minute")
async def logout(request: Request, data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(data.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    rt = result.scalar_one_or_none()
    if rt:
        rt.revoked_at = datetime.now(timezone.utc)
        await db.commit()
    return {"ok": True}


@router.post("/set-password")
async def set_password(data: SetPasswordRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if data.password != data.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")
    if len(data.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password too short (min 8)")

    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.password_hash = hash_password(data.password)
    await db.commit()
    return {"ok": True}
