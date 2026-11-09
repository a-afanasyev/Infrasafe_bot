"""Short-lived JWT proving a verified Telegram identity during registration.
Separate from the MFA token: purpose="register", sub=telegram_id.

AUTH-03 (ревью 2026-11-07): один активный тикет на аккаунт. `/start` кладёт
`jti` в Redis (`reg:ticket:<telegram_id>`); перевыпуск перезаписывает его,
завершение регистрации гасит. Тикет с чужим `jti` — недействителен.
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uk_management_bot.api.auth.service import JWTError, _get_redis, decode_jwt, encode_jwt

logger = logging.getLogger(__name__)

ISSUER = "uk-management"
PURPOSE = "register"
TICKET_TTL_MINUTES = 30
_KEY = "reg:ticket:{}"
_REVOKED = "revoked"


def create_registration_ticket(telegram_id: int, jti: str | None = None) -> str:
    payload = {
        "sub": str(telegram_id),
        "purpose": PURPOSE,
        "iss": ISSUER,
        "jti": jti or uuid.uuid4().hex,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TICKET_TTL_MINUTES),
    }
    return encode_jwt(payload)


def _decode(token: str) -> Optional[dict]:
    try:
        payload = decode_jwt(token, issuer=ISSUER, options={"verify_aud": False})
    except JWTError:
        return None
    if payload.get("purpose") != PURPOSE:
        return None
    try:
        payload["sub"] = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
    return payload


def verify_registration_ticket(token: str) -> Optional[int]:
    """Return telegram_id if signature/purpose/exp are valid, else None (без Redis)."""
    payload = _decode(token)
    return payload["sub"] if payload else None


async def _set_marker(telegram_id: int, value: str) -> None:
    """Fail-open, как и проверка: без Redis тикет живёт по подписи и TTL,
    а /start и завершение регистрации не падают 500."""
    try:
        r = await _get_redis()
        try:
            await r.set(_KEY.format(telegram_id), value, ex=TICKET_TTL_MINUTES * 60)
        finally:
            await r.aclose()
    except Exception as exc:  # noqa: BLE001 — сбой Redis не роняет регистрацию
        logger.warning("registration ticket marker: Redis unavailable: %s", type(exc).__name__)


async def issue_registration_ticket(telegram_id: int) -> str:
    """Выпустить тикет и сделать его единственным активным для аккаунта."""
    jti = uuid.uuid4().hex
    await _set_marker(telegram_id, jti)
    return create_registration_ticket(telegram_id, jti)


async def revoke_registration_tickets(telegram_id: int) -> None:
    """Регистрация завершена — все тикеты аккаунта недействительны до конца TTL."""
    await _set_marker(telegram_id, _REVOKED)


async def check_registration_ticket(token: str) -> Optional[int]:
    """telegram_id для действующего тикета, иначе None.

    Нет метки в Redis — тикет выпущен не через `/start` или метка истекла вместе
    с ним: принимаем по подписи. Redis недоступен — тоже по подписи (fail-open,
    как D3 у вебхуков): отзыв — усиление поверх подписи и TTL, а регистрация
    жителей не должна вставать вместе с Redis.
    """
    payload = _decode(token)
    if payload is None:
        return None
    try:
        r = await _get_redis()
        try:
            current = await r.get(_KEY.format(payload["sub"]))
        finally:
            await r.aclose()
    except Exception as exc:  # noqa: BLE001 — сбой Redis не роняет регистрацию
        logger.warning("registration ticket check: Redis unavailable, by signature: %s",
                       type(exc).__name__)
        return payload["sub"]
    # ponytail: нет метки = принять по подписи; строгий режим «метка обязательна» —
    # если тикеты начнут минтиться вне /start.
    if current is not None and current != payload.get("jti"):
        return None
    return payload["sub"]
