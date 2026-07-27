"""Сбор фактов для канон-предиката доступа к заявке (П5, AUD3-14).

Решение принимает `utils/request_access.access_reason` — чистое ядро без
ввода-вывода. Здесь только добыча фактов, и её две: у бота синхронная
`Session`, у API — `AsyncSession`. Обе живут в ОДНОМ файле сознательно: именно
разъезжавшиеся копии этого предиката и есть предмет пункта, поэтому пусть
расхождение бросается в глаза при чтении, а не всплывает в проде.

Оптимизация «дешёвый проход»: сперва спрашиваем ядро по фактам, которые уже
есть в объектах `user`/`request`, подставляя недостающие как False, и лезем в
БД только если доступа не дали. Это корректно потому, что предикат монотонен —
никакой факт не способен доступ отобрать (`MONOTONE_BOOLEAN_FACTS`, свойство
закреплено тестом). Ложноположительного ответа так не получить; возможный
ложноотрицательный исправляет второй, полный проход.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.utils.request_access import (
    RESIDENT_ACCESS_STATUS,
    RequestAccessFacts,
    access_reason,
)
from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.utils.specializations import parse_specializations

_ACTIVE = "active"
_APPROVED = "approved"


def _base_facts(user, request, **extra) -> RequestAccessFacts:
    """Факты, доступные без единого запроса в БД."""
    defaults = dict(
        roles=frozenset(parse_roles_safe(getattr(user, "roles", None))),
        user_id=user.id,
        request_owner_id=getattr(request, "user_id", None),
        request_executor_id=getattr(request, "executor_id", None),
        request_status=getattr(request, "status", "") or "",
        request_apartment_id=getattr(request, "apartment_id", None),
        has_individual_assignment=False,
        group_specializations=frozenset(),
        user_specializations=frozenset(parse_specializations(user)),
        has_active_shift=False,
        is_approved_resident=False,
    )
    defaults.update(extra)
    return RequestAccessFacts(**defaults)


def _needs_group_lookup(facts: RequestAccessFacts) -> bool:
    """Групповое назначение проверяем только если человек вообще исполнитель."""
    return "executor" in facts.roles


def _needs_resident_lookup(facts: RequestAccessFacts) -> bool:
    """Соседство — только для заявки с квартирой и только на статусе приёмки."""
    return (
        facts.request_apartment_id is not None
        and facts.request_status == RESIDENT_ACCESS_STATUS
    )


# ---------------------------------------------------------------------------
# Синхронная сторона (бот)
# ---------------------------------------------------------------------------

def request_access_reason_sync(db: Session, user, request) -> Optional[str]:
    """Причина доступа или None. Порядок правил задаёт ядро, не этот код."""
    cheap = _base_facts(user, request)
    reason = access_reason(cheap)
    if reason is not None:
        return reason

    individual = False
    group_specs: frozenset[str] = frozenset()
    active_shift = False
    if _needs_group_lookup(cheap):
        individual = db.query(RequestAssignment).filter(
            RequestAssignment.request_number == request.request_number,
            RequestAssignment.executor_id == user.id,
            RequestAssignment.status == _ACTIVE,
        ).first() is not None

        if not individual and cheap.user_specializations:
            rows = db.query(RequestAssignment.group_specialization).filter(
                RequestAssignment.request_number == request.request_number,
                RequestAssignment.assignment_type == "group",
                RequestAssignment.status == _ACTIVE,
            ).all()
            group_specs = frozenset(r[0] for r in rows if r[0])
            if group_specs & cheap.user_specializations:
                active_shift = db.query(Shift).filter(
                    Shift.user_id == user.id,
                    Shift.status == _ACTIVE,
                ).first() is not None

    resident = False
    if _needs_resident_lookup(cheap):
        resident = db.query(UserApartment).filter(
            UserApartment.user_id == user.id,
            UserApartment.apartment_id == request.apartment_id,
            UserApartment.status == _APPROVED,
        ).first() is not None

    return access_reason(_base_facts(
        user, request,
        has_individual_assignment=individual,
        group_specializations=group_specs,
        has_active_shift=active_shift,
        is_approved_resident=resident,
    ))


def has_request_access_sync(db: Session, user, request) -> bool:
    return request_access_reason_sync(db, user, request) is not None


# ---------------------------------------------------------------------------
# Асинхронная сторона (API / TWA)
# ---------------------------------------------------------------------------

async def request_access_reason_async(db: AsyncSession, user, request) -> Optional[str]:
    """Асинхронный близнец `request_access_reason_sync`.

    Обязан давать тот же ответ на тех же данных — это проверяет parity-тест
    `tests/api/test_request_access_parity.py`.
    """
    cheap = _base_facts(user, request)
    reason = access_reason(cheap)
    if reason is not None:
        return reason

    individual = False
    group_specs: frozenset[str] = frozenset()
    active_shift = False
    if _needs_group_lookup(cheap):
        found = await db.execute(
            select(RequestAssignment).where(
                RequestAssignment.request_number == request.request_number,
                RequestAssignment.executor_id == user.id,
                RequestAssignment.status == _ACTIVE,
            )
        )
        individual = found.scalars().first() is not None

        if not individual and cheap.user_specializations:
            rows = await db.execute(
                select(RequestAssignment.group_specialization).where(
                    RequestAssignment.request_number == request.request_number,
                    RequestAssignment.assignment_type == "group",
                    RequestAssignment.status == _ACTIVE,
                )
            )
            group_specs = frozenset(r[0] for r in rows.all() if r[0])
            if group_specs & cheap.user_specializations:
                shift = await db.execute(
                    select(Shift).where(
                        Shift.user_id == user.id,
                        Shift.status == _ACTIVE,
                    )
                )
                active_shift = shift.scalars().first() is not None

    resident = False
    if _needs_resident_lookup(cheap):
        found_resident = await db.execute(
            select(UserApartment).where(
                UserApartment.user_id == user.id,
                UserApartment.apartment_id == request.apartment_id,
                UserApartment.status == _APPROVED,
            )
        )
        resident = found_resident.scalars().first() is not None

    return access_reason(_base_facts(
        user, request,
        has_individual_assignment=individual,
        group_specializations=group_specs,
        has_active_shift=active_shift,
        is_approved_resident=resident,
    ))


async def has_request_access_async(db: AsyncSession, user, request) -> bool:
    return (await request_access_reason_async(db, user, request)) is not None
