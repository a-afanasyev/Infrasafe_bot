"""Публичный (без аутентификации) виджет статусов лифтов для табло жителей (T16, Р16).

Первое место, где данные лифтов покидают авторизованный периметр. Наружу
уходит ровно то, что житель видит на табло в подъезде: подпись лифта, статус
и с какого момента, доступность за 30 дней, дата последнего ТО, срок
освидетельствования, обслуживающая организация и «паспортная витрина»
(производитель, модель, год, грузоподъёмность). Детали простоя — только при
``publish_downtime_details``.

Намеренно ОТСУТСТВУЮТ в ответе: ``id`` лифта, ``public_code`` (зарезервирован,
Р16), номера паспорта/серии/договора/акта, ссылки на акты, номера и тексты
заявок, ФИО и id сотрудников, счётчики заявок, флаги договора. Тест
``tests/api/test_public_elevators.py`` обходит весь JSON.

Две «тихие» калитки — обе дают 200 с пустым ответом, не 404: киоск в
подъезде поллит постоянно, и стабильное «ничего нет» ему удобнее стены ошибок
(та же логика, что у ленты ``work_reports/public_router.py``):

* ``settings.ELEVATORS_ENABLED=False`` — модуль тёмный;
* ``elevators_config.module_public=False`` — менеджер не включил витрину.

Схемы ответа — inline (конвенция маленьких публичных роутеров).
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.board_config.service import load_dispatch_phone
from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.services import elevator_service as domain
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.datetime_utils import as_utc

logger = logging.getLogger(__name__)

router = APIRouter()

# Кэш собранного ответа — по образцу _board_cache в api/public/router.py
# (per-worker, без локов, инвалидация только по TTL); слот на каждый язык,
# поскольку подписи лифтов локализованы.
_CACHE_TTL_SECONDS = 30
_public_elevators_cache: dict[str, tuple["PublicElevatorsOut", float]] = {}


# ---------------------------------------------------------------------------
# Схемы ответа
# ---------------------------------------------------------------------------

class PublicElevatorOut(BaseModel):
    """Один лифт глазами жителя. Без ``id`` и без ``public_code`` — намеренно."""

    entrance_number: int
    elevator_number: int
    label: str
    status: str
    status_since: Optional[datetime]
    availability_30d: Optional[float]
    last_maintenance_on: Optional[date]
    cert_valid_until: Optional[date]
    cert_expired: bool
    service_org_name: Optional[str]
    service_org_phone: Optional[str]
    manufacturer: Optional[str]
    model: Optional[str]
    production_year: Optional[int]
    capacity_kg: Optional[int]
    # Только при publish_downtime_details=True, иначе null.
    downtime_reason: Optional[str]
    spare_part_expected_on: Optional[date]


class PublicElevatorBuildingOut(BaseModel):
    id: int
    address: str
    elevators: list[PublicElevatorOut]


class PublicElevatorYardOut(BaseModel):
    id: int
    name: str
    buildings: list[PublicElevatorBuildingOut]


class PublicElevatorsOut(BaseModel):
    yards: list[PublicElevatorYardOut]
    dispatch_phone: Optional[str]
    generated_at: datetime


def _empty() -> PublicElevatorsOut:
    return PublicElevatorsOut(yards=[], dispatch_phone=None, generated_at=datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------

def _elevator_out(
    elevator: Elevator, *, lang: str, today: date,
    availability: Optional[float], last_maintenance_on: Optional[date],
) -> PublicElevatorOut:
    publish = bool(elevator.publish_downtime_details)
    cert_until = elevator.cert_valid_until
    return PublicElevatorOut(
        entrance_number=elevator.entrance_number,
        elevator_number=elevator.elevator_number,
        label=domain.elevator_label(elevator, lang),
        status=elevator.current_status,
        status_since=as_utc(elevator.status_since) if elevator.status_since else None,
        availability_30d=availability,
        last_maintenance_on=last_maintenance_on,
        cert_valid_until=cert_until,
        # Канон реестра (FLAG_CERT_EXPIRED): нет освидетельствования == истекло.
        cert_expired=cert_until is None or cert_until < today,
        service_org_name=elevator.service_org_name or None,
        service_org_phone=elevator.service_org_phone or None,
        manufacturer=elevator.manufacturer or None,
        model=elevator.model or None,
        production_year=elevator.production_year,
        capacity_kg=elevator.capacity_kg,
        downtime_reason=elevator.downtime_reason if publish else None,
        spare_part_expected_on=elevator.spare_part_expected_on if publish else None,
    )


def _group_by_yard_and_building(
    elevators: list[Elevator], outs: list[PublicElevatorOut]
) -> list[PublicElevatorYardOut]:
    """Выборка уже отсортирована двор → дом → подъезд → номер; группировка линейная."""
    yards: dict[int, PublicElevatorYardOut] = {}
    buildings: dict[int, PublicElevatorBuildingOut] = {}
    for elevator, out in zip(elevators, outs):
        building = elevator.building
        yard = building.yard
        yard_out = yards.get(yard.id)
        if yard_out is None:
            yard_out = PublicElevatorYardOut(id=yard.id, name=yard.name, buildings=[])
            yards[yard.id] = yard_out
        building_out = buildings.get(building.id)
        if building_out is None:
            building_out = PublicElevatorBuildingOut(
                id=building.id, address=building.address or "", elevators=[]
            )
            buildings[building.id] = building_out
            yard_out.buildings.append(building_out)
        building_out.elevators.append(out)
    return list(yards.values())


async def _build(db: AsyncSession, lang: str) -> PublicElevatorsOut:
    elevators = await domain.list_public_elevators_async(db)
    ids = [e.id for e in elevators]
    availability = await domain.availability_30d_for_page_async(db, elevators)
    last_maintenance = await domain.last_maintenance_by_elevator_async(db, ids)
    today = business_today()
    outs = [
        _elevator_out(
            e, lang=lang, today=today,
            availability=availability.get(e.id),
            last_maintenance_on=last_maintenance.get(e.id),
        )
        for e in elevators
    ]
    return PublicElevatorsOut(
        yards=_group_by_yard_and_building(elevators, outs),
        dispatch_phone=await load_dispatch_phone(db),
        generated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# GET /elevators
# ---------------------------------------------------------------------------

@router.get("/elevators", response_model=PublicElevatorsOut)
@limiter.limit("120/minute")
async def get_public_elevators(
    request: Request,
    lang: str = Query("ru", pattern="^(ru|uz)$"),
    db: AsyncSession = Depends(get_db),
) -> PublicElevatorsOut:
    """Статусы публичных лифтов для табло жителей, сгруппированные двор → дом.

    Intentionally has NO authentication dependency. Флаг выключен или витрина не
    включена менеджером → 200 с пустым ответом (см. модуль-docstring).
    """
    if not settings.ELEVATORS_ENABLED:
        return _empty()

    # Калитка module_public — ДО кэша, на каждом запросе (один PK-read
    # elevators_config): выключение витрины менеджером видно сразу, а не
    # через TTL кэша собранного ответа.
    config = await domain.load_config_async(db)
    if not config.get("module_public"):
        return _empty()

    now = time.monotonic()
    cached = _public_elevators_cache.get(lang)
    if cached is not None and cached[1] > now:
        return cached[0]

    try:
        result = await _build(db, lang)
    except (OperationalError, ProgrammingError) as exc:
        # Таблицы модуля ещё не накатаны — публичная страница не белеет
        # (конвенция load_board_config / ленты work-reports).
        logger.warning("elevators tables unavailable for public widget: %s", exc)
        return _empty()

    _public_elevators_cache[lang] = (result, now + _CACHE_TTL_SECONDS)
    return result
