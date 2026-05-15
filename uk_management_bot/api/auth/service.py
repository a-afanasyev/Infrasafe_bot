import hashlib
import hmac
import json
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import unquote, parse_qsl

import bcrypt
import redis.asyncio as aioredis
from jose import jwt, JWTError

from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)

SECRET_KEY = settings.JWT_SECRET or settings.INVITE_SECRET
if not SECRET_KEY:
    if settings.DEBUG:
        SECRET_KEY = "dev-jwt-secret-DO-NOT-USE-IN-PROD"
        logger.warning("Using development JWT secret — NOT safe for production")
    else:
        raise RuntimeError("JWT_SECRET or INVITE_SECRET must be set")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30
# Plan §7.4: tightened from 86400 (24h) to 300s (5min). A stale Telegram
# Widget hash from a previous session can no longer be replayed; users with
# expired session must press Telegram login again.
AUTH_DATE_MAX_AGE_SECONDS = 300


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(
    user_id: int,
    roles: list[str],
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": str(user_id), "roles": roles, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


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
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
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
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

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
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_mfa_token(token: str) -> Optional[int]:
    """Verify MFA token and return user_id or None."""
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            issuer="uk-management", options={"verify_aud": False},
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
        logger.error(f"Failed to send OTP via bot: {e}")
        return False
