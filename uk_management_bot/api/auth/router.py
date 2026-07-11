import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from uk_management_bot.api.rate_limit import limiter, auth_ratelimit_guard
from uk_management_bot.api.auth.schemas import (
    TokenResponse, WebTokenResponse,
    TelegramWidgetLogin, TWALogin,
    PasswordLogin, SetPasswordRequest,
    MFARequiredResponse, VerifyOTPRequest,
    RefreshRequestOptional, LogoutRequestOptional,
)
from uk_management_bot.api.auth.service import (
    verify_telegram_widget, verify_twa_init_data,
    verify_password, hash_password,
    create_access_token, create_refresh_token_value, hash_token,
    ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS,
    TWA_REFRESH_TOKEN_EXPIRE_HOURS,
    create_mfa_token, verify_mfa_token, generate_otp, store_otp, verify_otp, send_otp_via_bot,
)
from uk_management_bot.api.dependencies import get_db, get_current_user, _parse_user_roles
from uk_management_bot.api.users.queries import (
    get_user_by_telegram_id, get_user_by_id, require_user_by_id,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.refresh_token import (
    RefreshToken, REASON_ROTATED, REASON_LOGOUT, REASON_REUSE,
)
from uk_management_bot.config.settings import settings

# SEC-04: every route here is a credential/token operation (login, OTP,
# refresh, set-password, logout) — exactly the brute-force surface. Gate the
# whole router fail-closed when the rate-limit backend is degraded.
router = APIRouter(dependencies=[Depends(auth_ratelimit_guard)])


# ---------------------------------------------------------------------------
# Cookie auth helpers (plan §4.2, §7.2)
# ---------------------------------------------------------------------------
# Web SPA carries auth via two httpOnly cookies on the shared infrasafe.uz domain:
#   uk_access  — Path=/uk/      (sent on every UK request, REST + WS handshake)
#   uk_refresh — Path=/uk/api/  (sent only to /uk/api/* — i.e. refresh + logout)
# Path=/uk/api/ (and not the more restrictive /uk/api/auth/) intentionally
# covers both /uk/api/auth/refresh and /uk/api/v2/auth/refresh — see plan §4.2.
COOKIE_ACCESS_NAME = "uk_access"
COOKIE_REFRESH_NAME = "uk_refresh"
COOKIE_ACCESS_PATH = "/uk/"
COOKIE_REFRESH_PATH = "/uk/api/"
_ACCESS_TTL = ACCESS_TOKEN_EXPIRE_MINUTES * 60
_REFRESH_TTL = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def _cookie_secure() -> bool:
    """Cookies are insecure-friendly in DEBUG so local http://localhost works."""
    return not settings.DEBUG


def _set_auth_cookies(response: Response, access_token: str, refresh_value: str) -> None:
    response.set_cookie(
        COOKIE_ACCESS_NAME,
        access_token,
        max_age=_ACCESS_TTL,
        httponly=True,
        secure=_cookie_secure(),
        samesite="strict",
        path=COOKIE_ACCESS_PATH,
    )
    response.set_cookie(
        COOKIE_REFRESH_NAME,
        refresh_value,
        max_age=_REFRESH_TTL,
        httponly=True,
        secure=_cookie_secure(),
        samesite="strict",
        path=COOKIE_REFRESH_PATH,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(COOKIE_ACCESS_NAME, path=COOKIE_ACCESS_PATH)
    response.delete_cookie(COOKIE_REFRESH_NAME, path=COOKIE_REFRESH_PATH)


def _build_token_response(user: User) -> dict:
    roles = _parse_user_roles(user)
    access_token = create_access_token(user.id, roles)
    refresh_value = create_refresh_token_value()
    return {"access_token": access_token, "refresh_value": refresh_value, "roles": roles}


async def _save_refresh_token(
    db: AsyncSession,
    user_id: int,
    token_value: str,
    device_info: str = "",
    ttl: timedelta | None = None,
) -> None:
    # TWA-08: callers may pass a shorter TTL (e.g. login_twa uses 24h instead
    # of 30d) — see TWA_REFRESH_TOKEN_EXPIRE_HOURS.
    # APIFE-14: this is the LOGIN path — every login starts a NEW token family
    # (one family = one login = one device), so a reuse-revoke never spans logins.
    effective_ttl = ttl if ttl is not None else timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    expires = datetime.now(timezone.utc) + effective_ttl
    rt = RefreshToken(
        user_id=user_id,
        token_hash=hash_token(token_value),
        expires_at=expires,
        device_info=device_info,
        family_id=uuid.uuid4().hex,
    )
    db.add(rt)
    await db.commit()


# F-02: refresh-token rotation outcomes (typed so the route maps to HTTP codes).
_REFRESH_OK = "ok"
_REFRESH_INVALID = "invalid"
_REFRESH_NOT_APPROVED = "not_approved"


async def _rotate_refresh_token(
    db: AsyncSession, token_value: str, *, ttl: timedelta | None, device_info: str = ""
) -> tuple[str, User | None, str | None]:
    """F-02 + APIFE-14: atomic refresh-token rotation with family reuse detection.

    Locks the presented token row ``FOR UPDATE``, re-checks state under the lock,
    then either rotates (valid) or reacts to a replay. Returns
    ``(outcome, user, new_refresh_value)``.

    Reuse detection (APIFE-14): presenting an already-rotated token = replay/theft
    (or a benign double-submit the client coordination failed to dedup) → fail
    closed: revoke every still-active token in that family and 401. Only
    ``rotated`` replays trigger this — a logout/admin-revoked (or legacy NULL)
    token just 401s without touching the family, so a stale logout token can't DoS
    the account. NB: this makes a concurrent double-submit of a *valid* token
    self-defeating (the loser revokes the winner's fresh replacement); that's why
    cross-tab client coordination (Web Locks + marker) is a hard prerequisite.

    Assumes READ COMMITTED isolation (Postgres default, not overridden in
    session.py): the loser's FOR UPDATE re-fetches the winner's committed row and
    sees ``revoked_at``/``reason`` set. Under SERIALIZABLE the loser would instead
    raise a serialization failure (500) — don't raise the engine isolation level
    here without revisiting this path.

    NB: any ``raise`` before ``commit`` is safe — ``get_db`` rolls the session
    back on exception, so a rejected rotation persists nothing.
    """
    token_hash = hash_token(token_value)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
    )
    rt = result.scalar_one_or_none()
    if rt is None:
        return _REFRESH_INVALID, None, None

    now = datetime.now(timezone.utc)

    if rt.revoked_at is not None:
        # Already-revoked token presented again.
        if rt.revocation_reason == REASON_ROTATED:
            # Replay of a rotated token → fail-closed: kill the whole family.
            await db.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.family_id == rt.family_id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=now, revocation_reason=REASON_REUSE)
            )
            await db.commit()
        # logout / admin / legacy(NULL): plain 401, no family-wide revoke.
        return _REFRESH_INVALID, None, None

    if not rt.is_valid:  # revoked_at is None here → this means expired
        return _REFRESH_INVALID, None, None

    user = await get_user_by_id(db, rt.user_id)
    if user is None:
        return _REFRESH_INVALID, None, None
    if user.status != "approved":
        # Do not rotate an inactive account's token (no persistence — rollback).
        return _REFRESH_NOT_APPROVED, None, None

    new_value = create_refresh_token_value()
    effective_ttl = ttl if ttl is not None else timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    rt.revoked_at = now
    rt.revocation_reason = REASON_ROTATED
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_value),
        expires_at=now + effective_ttl,
        device_info=device_info,
        family_id=rt.family_id,          # child stays in the same family
        parent_token_id=rt.id,
    ))
    # Single commit persists the revoke and the replacement together.
    await db.commit()
    return _REFRESH_OK, user, new_value


@router.post("/telegram-widget", response_model=WebTokenResponse)
@limiter.limit("10/minute")
async def login_telegram_widget(
    request: Request,
    response: Response,
    data: TelegramWidgetLogin,
    db: AsyncSession = Depends(get_db),
):
    # HMAC must be checked over EXACTLY the payload Telegram signed. Routing it
    # through TelegramWidgetLogin and using model_dump() injects None for any
    # optional field Telegram omitted (last_name/username/photo_url for users
    # without them) — those Nones land in data_check_string and break the hash.
    # Verify against the raw request body instead; `data` stays for typed access.
    try:
        raw_payload = await request.json()
    except Exception:
        raw_payload = None
    if not isinstance(raw_payload, dict) or not verify_telegram_widget(raw_payload):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram auth data")

    user = await get_user_by_telegram_id(db, data.id)
    if not user or user.status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not approved")

    tokens = _build_token_response(user)
    await _save_refresh_token(db, user.id, tokens["refresh_value"])
    # Web flow (plan §7.2): refresh in cookie only, body carries access for clients
    # that want to keep it in memory and the existing "token in body" tests.
    _set_auth_cookies(response, tokens["access_token"], tokens["refresh_value"])
    return WebTokenResponse(access_token=tokens["access_token"])


@router.post("/twa", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login_twa(request: Request, data: TWALogin, db: AsyncSession = Depends(get_db)):
    """TWA flow (plan §4.3): tokens come back in body — Telegram WebView cookie
    handling is unreliable, especially on Android, so the Mini App keeps the
    Bearer flow."""
    user_data = verify_twa_init_data(data.init_data, settings.BOT_TOKEN)
    if not user_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid initData")

    telegram_id = user_data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No user id in initData")

    user = await get_user_by_telegram_id(db, int(telegram_id))
    if not user or user.status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not approved")

    tokens = _build_token_response(user)
    # TWA-08: TWA-issued refresh tokens get 24h TTL (vs 30d for web SPA).
    # Combined with the frontend re-init on auth-failed event, the window
    # for a stolen TWA refresh token is bounded to one day.
    await _save_refresh_token(
        db,
        user.id,
        tokens["refresh_value"],
        ttl=timedelta(hours=TWA_REFRESH_TOKEN_EXPIRE_HOURS),
    )
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_value"])


@router.post("/login")
@limiter.limit("10/minute")
async def login_password(request: Request, data: PasswordLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not approved")

    # MFA: require Telegram OTP
    if not user.telegram_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram account not linked. Use Telegram Widget to login.",
        )

    # Generate and send OTP
    otp_code = generate_otp()
    await store_otp(user.id, otp_code)
    sent = await send_otp_via_bot(user.telegram_id, otp_code)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to send verification code. Try again later.",
        )

    # Return MFA token (short-lived, doesn't grant API access)
    mfa_token = create_mfa_token(user.id)
    return JSONResponse(content={"mfa_required": True, "mfa_token": mfa_token})


@router.post("/login/verify-otp", response_model=WebTokenResponse)
@limiter.limit("10/minute")
async def verify_login_otp(
    request: Request,
    response: Response,
    data: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db),
):
    # Verify MFA token
    user_id = verify_mfa_token(data.mfa_token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA session expired. Please login again.",
        )

    # Verify OTP code
    success, error_msg = await verify_otp(user_id, data.code)
    if not success:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_msg)

    # OTP verified — issue full tokens (Web flow)
    user = await get_user_by_id(db, user_id)
    if not user or user.status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not approved")

    tokens = _build_token_response(user)
    await _save_refresh_token(db, user.id, tokens["refresh_value"])
    _set_auth_cookies(response, tokens["access_token"], tokens["refresh_value"])
    return WebTokenResponse(access_token=tokens["access_token"])


@router.post("/login/resend-otp")
@limiter.limit("3/minute")
async def resend_otp(request: Request, data: MFARequiredResponse, db: AsyncSession = Depends(get_db)):
    user_id = verify_mfa_token(data.mfa_token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA session expired")

    user = await get_user_by_id(db, user_id)
    if not user or not user.telegram_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    otp_code = generate_otp()
    await store_otp(user.id, otp_code)
    await send_otp_via_bot(user.telegram_id, otp_code)
    return {"ok": True}


@router.post("/refresh")
@limiter.limit("20/minute")
async def refresh_token(
    request: Request,
    response: Response,
    body: RefreshRequestOptional | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Plan §7.2: Web SPA sends refresh via cookie (uk_refresh, Path=/uk/api/);
    TWA falls back to body. We try cookie first; if absent, accept body and
    flag the response with a Deprecation header so TWA migrates."""
    token_value = request.cookies.get(COOKIE_REFRESH_NAME)
    source = "cookie"
    if not token_value and body is not None and body.refresh_token:
        token_value = body.refresh_token
        source = "body"
        response.headers["Deprecation"] = (
            "refresh-token in body is deprecated; migrate to cookie-based flow"
        )

    if not token_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    # TWA-08: preserve the shorter TTL when rotating a TWA refresh token. The
    # cookie-vs-body distinction is the source signal (web SPA uses cookies, TWA
    # falls back to body — see plan §7.2). Without this, the first /refresh would
    # silently extend a TWA token back to 30 days.
    ttl = None if source == "cookie" else timedelta(hours=TWA_REFRESH_TOKEN_EXPIRE_HOURS)

    # F-02: single atomic transaction (lock → re-check → revoke + issue → commit)
    # instead of an unlocked SELECT then a separate write, which let two parallel
    # requests both see the token valid and mint two sessions.
    outcome, user, new_refresh_value = await _rotate_refresh_token(db, token_value, ttl=ttl)
    if outcome == _REFRESH_INVALID:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
    if outcome == _REFRESH_NOT_APPROVED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")

    access_token = create_access_token(user.id, _parse_user_roles(user))

    if source == "cookie":
        # Refresh and access cookies are rotated together — server-driven.
        _set_auth_cookies(response, access_token, new_refresh_value)
        return {"access_token": access_token, "token_type": "bearer"}

    # TWA / legacy: return both in body (deprecated path).
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_value,
        "token_type": "bearer",
    }


@router.post("/logout")
@limiter.limit("10/minute")
async def logout(
    request: Request,
    response: Response,
    body: LogoutRequestOptional | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Plan §7.2: Web SPA passes refresh via cookie, TWA via body. We accept
    either, revoke the matching DB row if present, and clear cookies for the
    Web client unconditionally."""
    token_value = request.cookies.get(COOKIE_REFRESH_NAME)
    if not token_value and body is not None and body.refresh_token:
        token_value = body.refresh_token

    if token_value:
        token_hash = hash_token(token_value)
        result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        rt = result.scalar_one_or_none()
        if rt and rt.revoked_at is None:
            # APIFE-14: stamp reason=logout so a later replay of THIS token is not
            # mistaken for a rotation replay (which would revoke the whole family).
            rt.revoked_at = datetime.now(timezone.utc)
            rt.revocation_reason = REASON_LOGOUT
            await db.commit()

    _clear_auth_cookies(response)
    return {"ok": True}


@router.post("/set-password")
@limiter.limit("5/minute")
async def set_password(
    request: Request,
    data: SetPasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.password != data.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")
    if len(data.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password too short (min 8)")

    db_user = await require_user_by_id(db, user.id)

    # AUD3-16 (A07): if a password already exists this is a CHANGE — require the
    # current password so a replayed/stolen access token alone can't overwrite
    # it and lock the owner out. First-time set (no hash yet) needs no proof.
    if db_user.password_hash:
        if not data.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="current_password_required",
            )
        if not verify_password(data.current_password, db_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="current_password_invalid",
            )

    db_user.password_hash = hash_password(data.password)
    await db.commit()
    return {"ok": True}
