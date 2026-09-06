"""ORM → Pydantic для модуля «Лифты»: карточки, события, график, заявки, сводка.

Чистые строители: без сессии, без I/O. Контекст страницы (``CardContext``)
собирает сервис одним набором запросов и передаёт сюда — карточка не
делает запросов сама (нет N+1).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from uk_management_bot.database.models.elevator import (
    Elevator,
    ElevatorMaintenanceOccurrence,
    ElevatorStatusEvent,
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.services.elevator_service import (
    resident_requests_blocked,
    ElevatorCounters,
    ElevatorSummary,
    elevator_label,
)
from uk_management_bot.services.elevator_service.grouping import BulkItemResult
from uk_management_bot.utils.datetime_utils import as_utc
from uk_management_bot.utils.request_workflow import normalize_status
from uk_management_bot.utils.user_names import full_name

from .schemas import (
    ElevatorBulkConfirmItemOut,
    ElevatorCardOut,
    ElevatorCountersOut,
    ElevatorDetailOut,
    ElevatorEventOut,
    ElevatorFlagsOut,
    ElevatorMiniOut,
    ElevatorOccurrenceOut,
    ElevatorRequestRowOut,
    ElevatorSummaryOut,
    ElevatorYardSummaryOut,
    ElevatorsConfigOut,
    ElevatorsDowntimeThresholdsOut,
)

# Поля карточки-детали, копируемые из ORM как есть
DETAIL_PLAIN_FIELDS: tuple[str, ...] = (
    "passport_number", "manufacturer", "serial_number", "factory_number", "model",
    "production_year", "capacity_kg", "floors_served", "commissioned_at",
    "downtime_reason", "spare_part_expected_on", "publish_downtime_details",
    "service_org_name", "service_org_phone", "contract_number", "contract_until",
    "cert_number", "cert_valid_until", "cert_act_url", "public_code", "archived_reason",
    "version",
)


@dataclass(frozen=True)
class CardContext:
    """Данные страницы для карточек: бизнес-«сегодня», просрочки, доступность, заявки, дворы."""

    today: date
    language: str
    overdue_ids: frozenset[int]
    availability: Mapping[int, float | None]
    open_requests: Mapping[int, int]
    yard_names: Mapping[int, str]


def aware_utc(value: datetime | None) -> datetime | None:
    return as_utc(value) if value is not None else None


def compute_flags(elevator: Elevator, *, today: date, overdue_ids: frozenset[int]) -> ElevatorFlagsOut:
    """Флаги карточки — тот же критерий, что у фильтров реестра и сводки."""
    return ElevatorFlagsOut(
        no_contract=elevator.contract_until is None or elevator.contract_until < today,
        cert_expired=elevator.cert_valid_until is None or elevator.cert_valid_until < today,
        maintenance_overdue=elevator.id in overdue_ids,
    )


def _card_fields(elevator: Elevator, ctx: CardContext) -> dict[str, Any]:
    building = elevator.building
    return {
        "id": elevator.id,
        "building_id": elevator.building_id,
        "building_address": building.address,
        "yard_id": building.yard_id,
        "yard_name": ctx.yard_names.get(building.yard_id),
        "entrance_number": elevator.entrance_number,
        "elevator_number": elevator.elevator_number,
        "label": elevator_label(elevator, ctx.language),
        "current_status": elevator.current_status,
        "status_since": aware_utc(elevator.status_since),
        "is_commissioned": bool(elevator.is_commissioned),
        "archived_at": aware_utc(elevator.archived_at),
        "is_public": bool(elevator.is_public),
        "flags": compute_flags(elevator, today=ctx.today, overdue_ids=ctx.overdue_ids),
        "availability_30d": ctx.availability.get(elevator.id),
        "open_requests_count": ctx.open_requests.get(elevator.id, 0),
    }


def build_card(elevator: Elevator, ctx: CardContext) -> ElevatorCardOut:
    return ElevatorCardOut(**_card_fields(elevator, ctx))


def build_detail(
    elevator: Elevator, ctx: CardContext, *, apartments_without_entrance_count: int
) -> ElevatorDetailOut:
    return ElevatorDetailOut(
        **_card_fields(elevator, ctx),
        **{name: getattr(elevator, name) for name in DETAIL_PLAIN_FIELDS},
        apartments_without_entrance_count=apartments_without_entrance_count,
        created_at=aware_utc(elevator.created_at),
        updated_at=aware_utc(elevator.updated_at),
    )


def build_mini(
    elevator: Elevator, language: str, *, resident_requests_under_works_allowed: bool = False
) -> ElevatorMiniOut:
    """``resident_request_blocked`` считает домен (Р18a): статус + тумблер конфига."""
    return ElevatorMiniOut(
        id=elevator.id,
        entrance_number=elevator.entrance_number,
        elevator_number=elevator.elevator_number,
        label=elevator_label(elevator, language),
        current_status=elevator.current_status,
        status_since=aware_utc(elevator.status_since),
        resident_request_blocked=resident_requests_blocked(
            elevator.current_status, allowed_by_config=resident_requests_under_works_allowed
        ),
    )


def build_event(event: ElevatorStatusEvent) -> ElevatorEventOut:
    out = ElevatorEventOut.model_validate(event)
    return out.model_copy(update={"occurred_at": as_utc(event.occurred_at)})


def build_occurrence(occurrence: ElevatorMaintenanceOccurrence, label: str) -> ElevatorOccurrenceOut:
    return ElevatorOccurrenceOut(
        id=occurrence.id,
        elevator_id=occurrence.elevator_id,
        elevator_label=label,
        kind=occurrence.kind,
        due_on=occurrence.due_on,
        state=occurrence.state,
        done_at=aware_utc(occurrence.done_at),
        done_by_user_id=occurrence.done_by_user_id,
        comment=occurrence.comment,
        request_number=occurrence.request_number,
        created_at=aware_utc(occurrence.created_at),
    )


def build_request_row(request: Request, users: Mapping[int, User]) -> ElevatorRequestRowOut:
    """Строка заявки лифта; статус — канон (``normalize_status``), ФИО — staff-only."""
    return ElevatorRequestRowOut(
        request_number=request.request_number,
        status=normalize_status(request),
        category=request.category,
        urgency=request.urgency,
        created_at=aware_utc(request.created_at),
        elevator_operational=request.elevator_operational,
        executor_name=full_name(users.get(request.executor_id)) if request.executor_id else None,
        applicant_name=full_name(users.get(request.user_id)),
    )


def build_bulk_item(result: BulkItemResult) -> ElevatorBulkConfirmItemOut:
    return ElevatorBulkConfirmItemOut(
        request_number=result.request_number, ok=result.ok,
        error_kind=result.error_kind, error=result.error,
    )


def _counters(counters: ElevatorCounters) -> ElevatorCountersOut:
    return ElevatorCountersOut(
        total=counters.total,
        by_status=dict(counters.by_status),
        no_contract=counters.no_contract,
        cert_expired=counters.cert_expired,
        maintenance_overdue=counters.maintenance_overdue,
        downtime_over_threshold=counters.downtime_over_threshold,
    )


def build_summary(summary: ElevatorSummary, thresholds: Mapping[str, int | None]) -> ElevatorSummaryOut:
    """Сводка + пороги простоя из конфига (по ним посчитан ``downtime_over_threshold``)."""
    return ElevatorSummaryOut(
        today=summary.today,
        totals=_counters(summary.totals),
        yards=[
            ElevatorYardSummaryOut(
                yard_id=yard.yard_id, yard_name=yard.yard_name, counters=_counters(yard.counters)
            )
            for yard in summary.yards
        ],
        requests_without_elevator=summary.requests_without_elevator,
        downtime_threshold_days=ElevatorsDowntimeThresholdsOut(**thresholds),
    )


def build_config(config: Mapping[str, Any]) -> ElevatorsConfigOut:
    """Полный конфиг модуля (``merge_config`` гарантирует состав ключей)."""
    return ElevatorsConfigOut.model_validate(dict(config))
