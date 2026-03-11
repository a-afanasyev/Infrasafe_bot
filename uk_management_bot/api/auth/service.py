import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import unquote, parse_qsl

import bcrypt
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
AUTH_DATE_MAX_AGE_SECONDS = 86400  # 24 hours


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

    # Check auth_date freshness
    auth_date = data.get("auth_date")
    if auth_date:
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

    # Check auth_date freshness
    auth_date = parsed.get("auth_date")
    if auth_date:
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
