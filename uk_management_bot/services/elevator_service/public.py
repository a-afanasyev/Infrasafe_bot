"""Выборка для публичного виджета статусов лифтов (T16, Р16): что видят жители.

Только чтение, без фильтров и пагинации: лифты, у которых менеджер включил
«Показывать жителям» (``is_public``), введённые в эксплуатацию, неархивные и
со статусом. Порядок — двор → дом → подъезд → номер (группировку в ответ
делает вызывающий). Дом и двор подгружаются ``selectinload`` — карточкам
нужны адрес дома и имя двора, lazy-load в async-сессии невозможен.

``public_code`` здесь не читается и не отдаётся: по решению Р16 код остаётся
зарезервированным и наружу не выходит. Sync-зеркало — образец ``reads.py``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.elevator import (
    Elevator,
    ElevatorMaintenanceOccurrence,
)
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.utils.business_time import business_date_of

MAINTENANCE_KIND = "maintenance"
DONE_STATE = "done"


def _public_elevators_stmt() -> Select:
    return (
        select(Elevator)
        .join(Building, Elevator.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .options(selectinload(Elevator.building).selectinload(Building.yard))
        .where(
            Elevator.is_public.is_(True),
            Elevator.is_commissioned.is_(True),
            Elevator.archived_at.is_(None),
            Elevator.current_status.is_not(None),
        )
        .order_by(
            Yard.name, Yard.id,
            Building.address, Building.id,
            Elevator.entrance_number, Elevator.elevator_number, Elevator.id,
        )
    )


def _done_maintenance_stmt(elevator_ids: Sequence[int]) -> Select:
    """Выполненные ТО по лифтам: ``(elevator_id, due_on, done_at)``."""
    return select(
        ElevatorMaintenanceOccurrence.elevator_id,
        ElevatorMaintenanceOccurrence.due_on,
        ElevatorMaintenanceOccurrence.done_at,
    ).where(
        ElevatorMaintenanceOccurrence.elevator_id.in_(list(elevator_ids)),
        ElevatorMaintenanceOccurrence.kind == MAINTENANCE_KIND,
        ElevatorMaintenanceOccurrence.state == DONE_STATE,
    )


def _as_date(value: object) -> date:
    """sqlite отдаёт ``Date`` строкой — приводим единообразно."""
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _maintenance_date(due_on: object, done_at: datetime | None) -> date:
    """Фактическая дата ТО: бизнес-дата закрытия; без ``done_at`` (легаси) — ``due_on``."""
    if done_at is None:
        return _as_date(due_on)
    return business_date_of(done_at if isinstance(done_at, datetime) else datetime.fromisoformat(str(done_at)))


def _latest_by_elevator(rows: Iterable) -> dict[int, date]:
    result: dict[int, date] = {}
    for elevator_id, due_on, done_at in rows:
        key = int(elevator_id)
        candidate = _maintenance_date(due_on, done_at)
        if key not in result or candidate > result[key]:
            result[key] = candidate
    return result


# ---------------------------------------------------------------------------
# SYNC (бот)
# ---------------------------------------------------------------------------

def list_public_elevators_sync(db: Session) -> list[Elevator]:
    """Публичные лифты с домом и двором, порядок двор → дом → подъезд → номер."""
    return list(db.execute(_public_elevators_stmt()).scalars().all())


def last_maintenance_by_elevator_sync(db: Session, elevator_ids: Sequence[int]) -> dict[int, date]:
    """``{elevator_id: дата последнего выполненного ТО}`` — один запрос; без ТО ключа нет.

    Дата — бизнес-дата закрытия (``done_at`` через ``utils.business_time``);
    у записей без ``done_at`` берётся ``due_on``.
    """
    if not elevator_ids:
        return {}
    return _latest_by_elevator(db.execute(_done_maintenance_stmt(elevator_ids)).all())


# ---------------------------------------------------------------------------
# ASYNC (API)
# ---------------------------------------------------------------------------

async def list_public_elevators_async(db: AsyncSession) -> list[Elevator]:
    """Async-зеркало ``list_public_elevators_sync``."""
    return list((await db.execute(_public_elevators_stmt())).scalars().all())


async def last_maintenance_by_elevator_async(
    db: AsyncSession, elevator_ids: Sequence[int]
) -> dict[int, date]:
    """Async-зеркало ``last_maintenance_by_elevator_sync``."""
    if not elevator_ids:
        return {}
    return _latest_by_elevator((await db.execute(_done_maintenance_stmt(elevator_ids))).all())
