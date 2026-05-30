"""Short-lived JWT proving a verified Telegram identity during registration.
Separate from the MFA token: purpose="register", sub=telegram_id."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from uk_management_bot.api.auth.service import SECRET_KEY, ALGORITHM

ISSUER = "uk-management"
PURPOSE = "register"
TICKET_TTL_MINUTES = 30


def create_registration_ticket(telegram_id: int) -> str:
    payload = {
        "sub": str(telegram_id),
        "purpose": PURPOSE,
        "iss": ISSUER,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TICKET_TTL_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_registration_ticket(token: str) -> Optional[int]:
    """Return telegram_id if valid and purpose=register, else None."""
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            issuer=ISSUER, options={"verify_aud": False},
        )
    except JWTError:
        return None
    if payload.get("purpose") != PURPOSE:
        return None
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
