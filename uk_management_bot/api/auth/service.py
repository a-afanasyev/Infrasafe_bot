import hashlib
import hmac
import json
import logging
import random
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import unquote, parse_qsl

import bcrypt
import redis.asyncio as aioredis
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError, JWTClaimsError

from uk_management_bot.config.settings import settings
from uk_management_bot.utils.http_errors import describe_http_error

logger = logging.getLogger(__name__)

# SEC-02: JWT is signed with its OWN secret — never the invite-token HMAC key.
# settings.py already fails fast in prod when JWT_SECRET is unset; the prod
# branch here is defence-in-depth.
SECRET_KEY = settings.JWT_SECRET
if not SECRET_KEY:
    if settings.DEBUG:
        # Dev only: ephemeral per-process secret. NOT a hardcoded constant —
        # a leaked literal could forge tokens. Tokens won't survive a dev
        # restart, which is acceptable locally.
        SECRET_KEY = secrets.token_urlsafe(32)
        logger.warning("JWT_SECRET unset — using an ephemeral dev secret (NOT for production)")
    else:
        raise RuntimeError("JWT_SECRET must be set")

ALGORITHM = "HS256"

# ARCH-107: graceful-ротация JWT_SECRET по форме webhook-секретов (§4.4/R-18).
# Набор ключей {primary, next}; каждый выпущенный токен несёт `kid` в заголовке,
# верификатор принимает любой ключ набора, подписант переключается флагом
# JWT_USE_NEXT_SECRET. Настройки читаются лениво (на каждый вызов, не на импорт):
# ротационное окно живёт через рестарт контейнера с новым env, а тестам не нужен
# reload модуля. Процедура ротации → .claude/skills/uk-deploy/SKILL.md.
_KID_PRIMARY = "primary"
_KID_NEXT = "next"


def _key_set() -> dict[str, str]:
    keys = {_KID_PRIMARY: SECRET_KEY}
    next_key = getattr(settings, "JWT_SECRET_NEXT", "")
    if next_key:
        keys[_KID_NEXT] = next_key
    return keys


def _signing_kid_and_key() -> tuple[str, str]:
    keys = _key_set()
    if getattr(settings, "JWT_USE_NEXT_SECRET", False) and _KID_NEXT in keys:
        return _KID_NEXT, keys[_KID_NEXT]
    return _KID_PRIMARY, keys[_KID_PRIMARY]


def encode_jwt(payload: dict) -> str:
    """Sign a JWT with the active key, stamping its `kid` into the header."""
    kid, key = _signing_kid_and_key()
    return jwt.encode(payload, key, algorithm=ALGORITHM, headers={"kid": kid})


def decode_jwt(token: str, **decode_kwargs) -> dict:
    """Decode a JWT against the key set; raises JWTError if no key matches.

    The token's `kid` only orders the candidates — every configured key is
    tried, because two legitimate token populations don't map onto the set:
    tokens issued before this rollout carry no `kid` at all, and after a
    finished rotation (NEXT promoted to primary) live tokens still say
    kid="next" while their key is now registered as "primary".
    """
    keys = _key_set()
    kid = jwt.get_unverified_header(token).get("kid")  # JWTError on malformed token
    candidates = [keys[kid]] if kid in keys else []
    candidates += [k for name, k in keys.items() if name != kid]
    last_err: JWTError = JWTError("no JWT keys configured")
    for key in candidates:
        try:
            return jwt.decode(token, key, algorithms=[ALGORITHM], **decode_kwargs)
        except (ExpiredSignatureError, JWTClaimsError):
            # Signature already matched this key (claims are checked after it),
            # so no other key can succeed — surface the precise error.
            raise
        except JWTError as e:
            last_err = e
    raise last_err


ACCESS_TOKEN_EXPIRE_MINUTES = 60
# NICE-082: tightened 30d → 7d to shrink the stolen-refresh-token window.
# (TWA endpoint issues an even shorter 24h refresh — see below.)
REFRESH_TOKEN_EXPIRE_DAYS = 7
# TWA-08: refresh tokens issued from the TWA endpoint get a shorter TTL.
# Telegram WebApp is re-opened by the user often (each open returns fresh
# initData and a new refresh token), so 24h covers normal usage while
# shrinking the window for a stolen refresh-token from 30d → 1d.
TWA_REFRESH_TOKEN_EXPIRE_HOURS = 24
# Plan §7.4: tightened from 86400 (24h) to 300s (5min). A stale Telegram
# Widget hash from a previous session can no longer be replayed; users with
# expired session must press Telegram login again.
AUTH_DATE_MAX_AGE_SECONDS = 300


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a bcrypt password. Returns False on any malformed-hash error
    instead of leaking the bcrypt ValueError to the caller — a corrupted
    stored hash (wrong format, missing salt, truncated by shell-escape, etc.)
    must look like a failed credential check (401), not a 500 server error.
    """
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except (ValueError, TypeError):
        return False


def create_access_token(
    user_id: int,
    roles: list[str],
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": str(user_id), "roles": roles, "exp": expire}
    return encode_jwt(payload)


def verify_access_token(token: str) -> Optional[dict]:
    try:
        payload = decode_jwt(token)
    except JWTError:
        return None
    # SEC-01: purpose-scoped tokens (mfa_token from /login) are signed with the
    # same key and carry `sub`; without this check they pass as full access
    # tokens, bypassing the OTP second factor. Access tokens never set `purpose`.
    if payload.get("purpose"):
        return None
    return payload


def create_refresh_token_value() -> str:
    import secrets
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_telegram_widget(data: dict) -> bool:
    """Verify Telegram Widget login data. Does NOT mutate the input dict."""
    data = dict(data)  # defensive copy
    received_hash = data.pop("hash", None)
    if not received_hash:
        return False

    # Plan §7.4: auth_date is mandatory and must be fresh. Without this a
    # leaked widget payload can be replayed indefinitely.
    auth_date = data.get("auth_date")
    if not auth_date:
        return False
    try:
        if time.time() - int(auth_date) > AUTH_DATE_MAX_AGE_SECONDS:
            return False
    except (ValueError, TypeError):
        return False

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hashlib.sha256(settings.BOT_TOKEN.encode()).digest()
    # INV-087: hmac.digest — one-shot, стабильнее при апгрейдах stdlib.
    expected_hash = hmac.digest(secret_key, data_check_string.encode(), "sha256").hex()
    return hmac.compare_digest(expected_hash, received_hash)


def verify_twa_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """Verify TWA initData. Returns user dict or None."""
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    # Plan §7.4: auth_date is mandatory and must be fresh.
    auth_date = parsed.get("auth_date")
    if not auth_date:
        return None
    try:
        if time.time() - int(auth_date) > AUTH_DATE_MAX_AGE_SECONDS:
            return None
    except (ValueError, TypeError):
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.digest(b"WebAppData", bot_token.encode(), "sha256")
    expected_hash = hmac.digest(secret_key, data_check_string.encode(), "sha256").hex()

    if not hmac.compare_digest(expected_hash, received_hash):
        return None

    user_str = parsed.get("user")
    if user_str:
        try:
            return json.loads(unquote(user_str))
        except json.JSONDecodeError:
            return None
    return parsed


# ---------------------------------------------------------------------------
# MFA / OTP helpers
# ---------------------------------------------------------------------------

MFA_TOKEN_EXPIRE_MINUTES = 5
MFA_MAX_ATTEMPTS = 3


def create_mfa_token(user_id: int) -> str:
    """Create a short-lived JWT that only proves password was verified, NOT full access."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=MFA_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "purpose": "mfa",
        "exp": expire,
        "iss": "uk-management",
    }
    return encode_jwt(payload)


def verify_mfa_token(token: str) -> Optional[int]:
    """Verify MFA token and return user_id or None."""
    try:
        payload = decode_jwt(
            token, issuer="uk-management", options={"verify_aud": False},
        )
        if payload.get("purpose") != "mfa":
            return None
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None


def generate_otp() -> str:
    """Generate a 6-digit OTP using cryptographically secure random."""
    return f"{random.SystemRandom().randint(100000, 999999)}"


async def _get_redis() -> aioredis.Redis:
    """Get async Redis client for OTP storage."""
    url = getattr(settings, "REDIS_URL", "redis://redis:6379/0")
    return aioredis.from_url(url, decode_responses=True)


async def store_otp(user_id: int, code: str) -> None:
    """Store OTP in Redis with TTL and attempt counter."""
    r = await _get_redis()
    key = f"mfa:otp:{user_id}"
    await r.hset(key, mapping={"code": code, "attempts": str(MFA_MAX_ATTEMPTS)})
    await r.expire(key, MFA_TOKEN_EXPIRE_MINUTES * 60)
    await r.aclose()


async def verify_otp(user_id: int, code: str) -> tuple[bool, str]:
    """Verify OTP. Returns (success, error_message)."""
    r = await _get_redis()
    key = f"mfa:otp:{user_id}"
    data = await r.hgetall(key)

    if not data:
        await r.aclose()
        return False, "OTP expired or not found. Please login again."

    attempts = int(data.get("attempts", "0"))
    if attempts <= 0:
        await r.delete(key)
        await r.aclose()
        return False, "Too many attempts. Please login again."

    stored_code = data.get("code", "")
    if not hmac.compare_digest(code, stored_code):
        await r.hincrby(key, "attempts", -1)
        remaining = attempts - 1
        await r.aclose()
        if remaining <= 0:
            return False, "Too many attempts. Please login again."
        return False, f"Invalid code. {remaining} attempts remaining."

    # Success — delete OTP
    await r.delete(key)
    await r.aclose()
    return True, ""


async def send_otp_via_bot(telegram_id: int, code: str) -> bool:
    """Send OTP code to user via Telegram bot."""
    import httpx

    try:
        url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={
                "chat_id": telegram_id,
                "text": (
                    f"\U0001f510 Код входа в панель управления: <b>{code}</b>\n\n"
                    "Код действителен 5 минут. Не сообщайте его никому."
                ),
                "parse_mode": "HTML",
            })
            return resp.status_code == 200
    except Exception as e:
        logger.error("Failed to send OTP via bot: %s", describe_http_error(e))
        return False


# ---------------------------------------------------------------------------
# Refresh-token persistence (AUD5-ARCH-2 волна 3 — data-access из router.py)
# ---------------------------------------------------------------------------
# Импорты локализованы в секции: модуль исторически «чистое крипто + redis»,
# и его тянут пути без БД (registration, access_control-контракт).

import uuid  # noqa: E402

from sqlalchemy import select as _sa_select, update as _sa_update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from uk_management_bot.api.users.queries import get_user_by_id  # noqa: E402
from uk_management_bot.database.models.refresh_token import (  # noqa: E402
    RefreshToken, REASON_ROTATED, REASON_LOGOUT, REASON_REUSE,
)
from uk_management_bot.database.models.user import User  # noqa: E402


async def user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Пользователь по email (password-login) или None."""
    return (
        await db.execute(_sa_select(User).where(User.email == email))
    ).scalar_one_or_none()


async def save_refresh_token(
    db: AsyncSession,
    user_id: int,
    token_value: str,
    device_info: str = "",
    ttl: Optional[timedelta] = None,
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
    db: AsyncSession, token_value: str, *, ttl: Optional[timedelta], device_info: str = ""
) -> tuple:
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
        _sa_select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
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
                _sa_update(RefreshToken)
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


async def revoke_refresh_token(db: AsyncSession, token_value: str) -> None:
    """Logout: помечает предъявленный refresh-токен revoked (reason=logout).

    APIFE-14: stamp reason=logout so a later replay of THIS token is not
    mistaken for a rotation replay (which would revoke the whole family).
    Незнакомый/уже-revoked токен — no-op.
    """
    token_hash = hash_token(token_value)
    result = await db.execute(
        _sa_select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()
    if rt and rt.revoked_at is None:
        rt.revoked_at = datetime.now(timezone.utc)
        rt.revocation_reason = REASON_LOGOUT
        await db.commit()


async def persist_password_hash(db: AsyncSession, user: User, password_hash: str) -> None:
    """Сохраняет новый password_hash (проверки current-password — у роутера)."""
    user.password_hash = password_hash
    await db.commit()
