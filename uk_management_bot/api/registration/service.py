"""Сервис-слой самостоятельной регистрации (AUD5-ARCH-2 волна 4, ARC-05a-канон).

Юниты НЕ коммитят: транзакция register_applicant охватывает upsert пользователя,
проверку существующей связи и заявку на квартиру (address_core.request_apartment
коммитит сам на успехе); исход остальных веток (commit ранней pending-связи /
rollback перед 4xx) решает роутер. get_db дополнительно откатывает сессию при
исключении.
"""
import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.users.queries import (
    get_user_by_telegram_id, require_user_by_telegram_id,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.utils.auth_helpers import parse_roles_safe

# Типизированные исходы upsert'а — роутер маппит их на HTTP-коды.
UPSERT_OK = "ok"
UPSERT_BLOCKED = "blocked"
UPSERT_APPROVED = "approved"
UPSERT_PRIVILEGED = "privileged"


def _apply_applicant_fields(u: User, *, first_name: str, last_name: str, phone: str) -> None:
    u.first_name = first_name
    u.last_name = last_name
    u.phone = phone
    u.active_role = "applicant"
    r = set(parse_roles_safe(u.roles))
    r.add("applicant")
    u.roles = json.dumps(sorted(r))


def _is_privileged(u: User) -> bool:
    """SEC-06: self-регистрация НЕ должна перетирать pre-provisioned аккаунт.

    Валидный тикет привязан к telegram_id, но если этот аккаунт уже наделён
    ролью, отличной от ``applicant`` (executor/manager/inspector/
    security_operator — заведён менеджером), самостоятельная заявка
    перезаписала бы ``first_name/last_name/phone`` и выставила
    ``active_role="applicant"``. Такой аккаунт ведёт менеджер.
    """
    return bool(set(parse_roles_safe(u.roles)) - {"applicant"})


async def upsert_pending_applicant(
    db: AsyncSession,
    *,
    telegram_id: int,
    first_name: str,
    last_name: str,
    phone: str,
) -> tuple[str, Optional[User]]:
    """Создаёт/обновляет pending-заявителя: add + flush с IntegrityError-ретраем.

    БЕЗ commit — вызывающий решает исход транзакции. → (outcome, user|None);
    user не-None только при UPSERT_OK. Порядок проверок (blocked → approved →
    privileged) одинаков в основной ветке и в ретрае — сохранён 1:1 с
    историческим роутером.
    """
    user = await get_user_by_telegram_id(db, telegram_id)
    if user and user.status == "blocked":
        return UPSERT_BLOCKED, None
    if user and user.status == "approved":
        return UPSERT_APPROVED, None
    if user is not None and _is_privileged(user):
        return UPSERT_PRIVILEGED, None
    if user is None:
        user = User(telegram_id=telegram_id, status="pending")
        db.add(user)
    _apply_applicant_fields(user, first_name=first_name, last_name=last_name, phone=phone)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        user = await require_user_by_telegram_id(db, telegram_id)
        if user.status == "blocked":
            return UPSERT_BLOCKED, None
        if user.status == "approved":
            return UPSERT_APPROVED, None
        if _is_privileged(user):
            return UPSERT_PRIVILEGED, None
        _apply_applicant_fields(user, first_name=first_name, last_name=last_name, phone=phone)
        await db.flush()
    return UPSERT_OK, user


async def apartment_link_of(
    db: AsyncSession, *, user_id: int, apartment_id: int
) -> Optional[UserApartment]:
    """Существующая связь пользователь↔квартира (любой статус) или None."""
    return (await db.execute(select(UserApartment).where(
        UserApartment.user_id == user_id,
        UserApartment.apartment_id == apartment_id,
    ))).scalar_one_or_none()


async def commit_registration(db: AsyncSession) -> None:
    """Фиксирует транзакцию регистрации (ветка «заявка уже pending»)."""
    await db.commit()
