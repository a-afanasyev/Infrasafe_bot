"""Единый резолвер 3-уровневого адреса заявки (план «Обходчик», 2026-06).

Единственный источник истины для правил «кто на какой двор/дом/квартиру может
завести заявку». Раньше проверки расходились между API, ботом и листингом
(квартиры не проверяли активность дома/двора, дворы — активность дома и т.д.).

Архитектура: бот работает на sync `Session`, API — на `AsyncSession`, поэтому
один резолвер «в лоб» не годится. Решение:
  * **policy-core без I/O** — `ROLE_ALLOWED_LEVELS`, канонический форматтер и
    конструкторы `select()`-выражений (`_*_stmt`). Выражения диалект-агностичны
    и исполняются как sync, так и async-сессией.
  * **тонкие адаптеры** `resolve_request_address_sync/async` и
    `list_available_request_addresses_sync/async` — только исполняют выражения и
    зовут чистый `_decide(...)`.

Матрица доступа:
  * applicant — свои дворы (через approved-квартиры ∪ UserYard), свои дома и
    квартиры (через approved-квартиры); вся цепочка квартира→дом→двор активна;
  * inspector — любой активный дом (двор активен), принадлежность не требуется;
    уровни yard/apartment запрещены (building-only).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, and_, or_, exists
from sqlalchemy.orm import contains_eager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models import (
    Apartment,
    Building,
    Yard,
    UserApartment,
    UserYard,
)

# ───────────────────────── policy-core (без I/O) ─────────────────────────

# Уровни, доступные роли для создания заявки.
ROLE_ALLOWED_LEVELS: dict[str, tuple[str, ...]] = {
    "applicant": ("yard", "building", "apartment"),
    "inspector": ("building",),
}

ADDRESS_TYPES = ("yard", "building", "apartment")


@dataclass(frozen=True)
class ResolvedAddress:
    """Результат резолва: уровень, ровно один FK и канонический адрес (сервер)."""

    address_type: str  # yard | building | apartment
    canonical_address: str
    apartment_id: Optional[int] = None
    building_id: Optional[int] = None
    yard_id: Optional[int] = None


class AddressResolutionError(Exception):
    """Ошибка резолва адреса. `status_code` — HTTP-семантика для API-слоя.

    403 — адрес существует и активен, но недоступен пользователю (чужой);
    422 — адрес не существует / неактивен / уровень не поддержан ролью.
    """

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ───────────────────────── канонический форматтер ────────────────────────


def format_yard_address(yard: Yard) -> str:
    return yard.name


def format_building_address(building: Building) -> str:
    yard_name = building.yard.name if building.yard else None
    return f"{building.address} ({yard_name})" if yard_name else building.address


def format_apartment_address(apartment: Apartment) -> str:
    building = apartment.building
    yard_name = building.yard.name if (building and building.yard) else None
    base = (
        f"{building.address}, кв. {apartment.apartment_number}"
        if building
        else f"кв. {apartment.apartment_number}"
    )
    return f"{base} ({yard_name})" if yard_name else base


def _check_level_allowed(role: str, address_type: str) -> None:
    allowed = ROLE_ALLOWED_LEVELS.get(role)
    if allowed is None:
        raise AddressResolutionError(f"role '{role}' cannot create requests", 403)
    if address_type not in ADDRESS_TYPES:
        raise AddressResolutionError(f"unsupported address_type '{address_type}'", 422)
    if address_type not in allowed:
        raise AddressResolutionError(
            f"address_type '{address_type}' not allowed for role '{role}'", 422
        )


# ───────────────── select()-конструкторы (pure, без I/O) ──────────────────
# Возвращают диалект-агностичные выражения; исполняются и sync, и async-сессией.


def _exists_stmt(address_type: str, address_id: int):
    """Сущность по id с активной цепочкой — БЕЗ проверки принадлежности.

    Нужна, чтобы отличить «чужой» (403) от «нет/неактивен» (422).
    """
    if address_type == "yard":
        return select(Yard).where(Yard.id == address_id, Yard.is_active.is_(True))
    if address_type == "building":
        return (
            select(Building)
            .join(Building.yard)
            .options(contains_eager(Building.yard))
            .where(
                Building.id == address_id,
                Building.is_active.is_(True),
                Yard.is_active.is_(True),
            )
        )
    # apartment
    return (
        select(Apartment)
        .join(Apartment.building)
        .join(Building.yard)
        .options(contains_eager(Apartment.building).contains_eager(Building.yard))
        .where(
            Apartment.id == address_id,
            Apartment.is_active.is_(True),
            Building.is_active.is_(True),
            Yard.is_active.is_(True),
        )
    )


def _member_stmt(address_type: str, address_id: int, user_id: int):
    """Сущность по id, доступная пользователю (принадлежность + активность).

    Membership через коррелированный EXISTS — не дублирует строки и сохраняет
    contains_eager-загрузку родителей для канонического адреса.
    """
    if address_type == "yard":
        via_apartment = exists().where(
            and_(
                Building.yard_id == Yard.id,
                Building.is_active.is_(True),
                Apartment.building_id == Building.id,
                Apartment.is_active.is_(True),
                UserApartment.apartment_id == Apartment.id,
                UserApartment.user_id == user_id,
                UserApartment.status == "approved",
            )
        )
        via_user_yard = exists().where(
            and_(UserYard.yard_id == Yard.id, UserYard.user_id == user_id)
        )
        return (
            select(Yard)
            .where(Yard.id == address_id, Yard.is_active.is_(True))
            .where(or_(via_apartment, via_user_yard))
        )
    if address_type == "building":
        has_user_apartment = exists().where(
            and_(
                Apartment.building_id == Building.id,
                Apartment.is_active.is_(True),
                UserApartment.apartment_id == Apartment.id,
                UserApartment.user_id == user_id,
                UserApartment.status == "approved",
            )
        )
        return (
            select(Building)
            .join(Building.yard)
            .options(contains_eager(Building.yard))
            .where(
                Building.id == address_id,
                Building.is_active.is_(True),
                Yard.is_active.is_(True),
            )
            .where(has_user_apartment)
        )
    # apartment
    has_membership = exists().where(
        and_(
            UserApartment.apartment_id == Apartment.id,
            UserApartment.user_id == user_id,
            UserApartment.status == "approved",
        )
    )
    return (
        select(Apartment)
        .join(Apartment.building)
        .join(Building.yard)
        .options(contains_eager(Apartment.building).contains_eager(Building.yard))
        .where(
            Apartment.id == address_id,
            Apartment.is_active.is_(True),
            Building.is_active.is_(True),
            Yard.is_active.is_(True),
        )
        .where(has_membership)
    )


def _build_resolved(address_type: str, obj) -> ResolvedAddress:
    if address_type == "yard":
        return ResolvedAddress(
            address_type="yard", yard_id=obj.id, canonical_address=format_yard_address(obj)
        )
    if address_type == "building":
        return ResolvedAddress(
            address_type="building",
            building_id=obj.id,
            canonical_address=format_building_address(obj),
        )
    return ResolvedAddress(
        address_type="apartment",
        apartment_id=obj.id,
        canonical_address=format_apartment_address(obj),
    )


def _decide(role: str, address_type: str, *, member_obj, exists_obj) -> ResolvedAddress:
    """Чистое решение по уже загруженным сущностям (403/422/ok)."""
    if role == "inspector":
        # building-only, принадлежность не требуется — судим по активной сущности.
        if exists_obj is None:
            raise AddressResolutionError("address not found or inactive", 422)
        return _build_resolved(address_type, exists_obj)

    # applicant: нужна принадлежность.
    if member_obj is not None:
        return _build_resolved(address_type, member_obj)
    if exists_obj is not None:
        # Существует и активен, но не свой.
        raise AddressResolutionError("address not available to user", 403)
    raise AddressResolutionError("address not found or inactive", 422)


# ───────────────────────────── sync-адаптер ──────────────────────────────


def resolve_request_address_sync(
    session: Session, user_id: int, role: str, address_type: str, address_id: int
) -> ResolvedAddress:
    """Резолв адреса заявки для бота (sync `Session`, `user.id`)."""
    _check_level_allowed(role, address_type)
    needs_membership = role == "applicant"
    member_obj = (
        session.execute(_member_stmt(address_type, address_id, user_id)).scalars().first()
        if needs_membership
        else None
    )
    exists_obj = session.execute(_exists_stmt(address_type, address_id)).scalars().first()
    return _decide(role, address_type, member_obj=member_obj, exists_obj=exists_obj)


async def resolve_request_address_async(
    session: AsyncSession, user_id: int, role: str, address_type: str, address_id: int
) -> ResolvedAddress:
    """Резолв адреса заявки для API (async `AsyncSession`, `user.id`)."""
    _check_level_allowed(role, address_type)
    needs_membership = role == "applicant"
    member_obj = None
    if needs_membership:
        res = await session.execute(_member_stmt(address_type, address_id, user_id))
        member_obj = res.scalars().first()
    res = await session.execute(_exists_stmt(address_type, address_id))
    exists_obj = res.scalars().first()
    return _decide(role, address_type, member_obj=member_obj, exists_obj=exists_obj)


# ──────────────── листинг доступных адресов (для UI/кнопок) ───────────────
# Те же правила, но возвращают наборы; родительские id несут каскад UI.


def _available_yards_stmt(user_id: int):
    via_apartment = exists().where(
        and_(
            Building.yard_id == Yard.id,
            Building.is_active.is_(True),
            Apartment.building_id == Building.id,
            Apartment.is_active.is_(True),
            UserApartment.apartment_id == Apartment.id,
            UserApartment.user_id == user_id,
            UserApartment.status == "approved",
        )
    )
    via_user_yard = exists().where(
        and_(UserYard.yard_id == Yard.id, UserYard.user_id == user_id)
    )
    return (
        select(Yard)
        .where(Yard.is_active.is_(True))
        .where(or_(via_apartment, via_user_yard))
        .order_by(Yard.name)
    )


def _available_buildings_stmt(user_id: int):
    has_user_apartment = exists().where(
        and_(
            Apartment.building_id == Building.id,
            Apartment.is_active.is_(True),
            UserApartment.apartment_id == Apartment.id,
            UserApartment.user_id == user_id,
            UserApartment.status == "approved",
        )
    )
    return (
        select(Building)
        .join(Building.yard)
        .options(contains_eager(Building.yard))
        .where(Building.is_active.is_(True), Yard.is_active.is_(True))
        .where(has_user_apartment)
        .order_by(Building.address)
    )


def _available_apartments_stmt(user_id: int):
    has_membership = exists().where(
        and_(
            UserApartment.apartment_id == Apartment.id,
            UserApartment.user_id == user_id,
            UserApartment.status == "approved",
        )
    )
    return (
        select(Apartment)
        .join(Apartment.building)
        .join(Building.yard)
        .options(contains_eager(Apartment.building).contains_eager(Building.yard))
        .where(
            Apartment.is_active.is_(True),
            Building.is_active.is_(True),
            Yard.is_active.is_(True),
        )
        .where(has_membership)
        .order_by(Building.address, Apartment.apartment_number)
    )


def _serialize_available(yards, buildings, apartments) -> dict:
    return {
        "yards": [
            {"id": y.id, "label": format_yard_address(y)} for y in yards
        ],
        "buildings": [
            {
                "id": b.id,
                "label": format_building_address(b),
                "yard_id": b.yard_id,
            }
            for b in buildings
        ],
        "apartments": [
            {
                "id": a.id,
                "label": format_apartment_address(a),
                "building_id": a.building_id,
                "yard_id": a.building.yard_id if a.building else None,
            }
            for a in apartments
        ],
    }


def list_available_request_addresses_sync(session: Session, user_id: int) -> dict:
    yards = session.execute(_available_yards_stmt(user_id)).scalars().unique().all()
    buildings = session.execute(_available_buildings_stmt(user_id)).scalars().unique().all()
    apartments = session.execute(_available_apartments_stmt(user_id)).scalars().unique().all()
    return _serialize_available(yards, buildings, apartments)


async def list_available_request_addresses_async(session: AsyncSession, user_id: int) -> dict:
    yres = await session.execute(_available_yards_stmt(user_id))
    bres = await session.execute(_available_buildings_stmt(user_id))
    ares = await session.execute(_available_apartments_stmt(user_id))
    return _serialize_available(
        yres.scalars().unique().all(),
        bres.scalars().unique().all(),
        ares.scalars().unique().all(),
    )
