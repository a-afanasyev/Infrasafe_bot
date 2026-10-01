"""Response-DTO реестра access_control (``/api/v1/access`` read-эндпоинты).

Вынесены из ``api/registry.py`` (A9-P3-12), чтобы роутер оставался HTTP-клеем.
``registry`` реэкспортирует их по прежним именам (их импортируют
``management``/``resident``/``parking_admin``).
"""
from __future__ import annotations

import datetime as dt

from pydantic import Field

from access_control.api.pagination import Frozen as _Frozen


# ------------------------------ DTO (frozen) ------------------------------


class EventRow(_Frozen):
    id: int
    event_id: str
    controller_id: int
    zone_id: int | None
    gate_id: int | None
    direction: str
    plate_number_normalized: str | None
    captured_at: dt.datetime
    occurred_at: dt.datetime | None
    source: str
    plate_photo_url: str | None
    overview_photo_url: str | None
    decision: str | None
    status: str | None
    reason: str | None
    decision_id: int | None
    resolved_by_user_id: int | None
    has_command: bool


class EventsPage(_Frozen):
    items: list[EventRow]
    total: int
    limit: int
    offset: int


class CameraEventDetail(_Frozen):
    id: int
    event_id: str
    controller_id: int
    zone_id: int | None
    gate_id: int | None
    camera_id: int | None
    direction: str
    plate_number_original: str | None
    plate_number_normalized: str | None
    confidence: float | None
    captured_at: dt.datetime
    received_at: dt.datetime | None
    source: str
    plate_photo_url: str | None
    overview_photo_url: str | None
    vehicle_class: str | None
    color: str | None


class DecisionRow(_Frozen):
    id: int
    decision: str
    status: str
    reason: str | None
    decision_group_id: str | None
    supersedes_decision_id: int | None
    resolved_by_user_id: int | None
    resolved_at: dt.datetime | None
    review_deadline_at: dt.datetime | None
    created_at: dt.datetime
    prev_hash: str | None
    row_hash: str | None


class CommandRow(_Frozen):
    command_id: str
    decision_id: int | None
    barrier_id: int
    controller_id: int
    command_type: str
    status: str
    attempts: int
    created_at: dt.datetime
    leased_at: dt.datetime | None
    acked_at: dt.datetime | None
    dead_at: dt.datetime | None


class ManualOpeningRow(_Frozen):
    id: int
    barrier_id: int
    command_id: str | None
    decision_id: int | None
    operator_user_id: int
    reason: str
    created_at: dt.datetime


class ResidentConfirmationRow(_Frozen):
    """Совещательный ответ жителя на спорный въезд (§9.4) — оператору на manual_review."""

    user_id: int
    response: str
    created_at: dt.datetime


class EventDetail(_Frozen):
    camera_event: CameraEventDetail
    decisions: list[DecisionRow]
    barrier_commands: list[CommandRow]
    manual_openings: list[ManualOpeningRow]
    resident_confirmations: list[ResidentConfirmationRow]


class ApartmentLink(_Frozen):
    apartment_id: int
    relation_type: str
    status: str
    valid_from: dt.datetime | None
    valid_until: dt.datetime | None
    approved_by_user_id: int | None
    approved_at: dt.datetime | None


class VehicleRow(_Frozen):
    id: int
    plate_number_original: str
    plate_number_normalized: str
    plate_country: str | None
    plate_type: str | None
    brand: str | None  # колонка БД называется make; во фронт отдаём как brand
    model: str | None
    color: str | None
    vehicle_class: str | None
    status: str
    blocked_reason: str | None
    blocked_by_user_id: int | None
    blocked_at: dt.datetime | None
    apartments: list[ApartmentLink]


class VehiclesPage(_Frozen):
    items: list[VehicleRow]
    total: int
    limit: int
    offset: int


class VehicleEventRow(_Frozen):
    id: int
    event_id: str
    captured_at: dt.datetime
    direction: str
    gate_id: int | None
    zone_id: int | None
    decision: str | None
    status: str | None


class VehicleDetail(_Frozen):
    vehicle: VehicleRow
    apartments: list[ApartmentLink]
    apartment_details: list["ApartmentDetail"] = []
    # Явные зоны доступа авто (активные access_rules) — отмеченные чекбоксы в правке.
    rule_zones: list["ZoneRef"] = []
    recent_events: list[VehicleEventRow]


class PassRow(_Frozen):
    id: int
    pass_type: str
    apartment_id: int
    created_by_user_id: int | None
    zone_id: int | None
    plate_number_original: str | None
    plate_number_normalized: str | None
    valid_from: dt.datetime | None
    valid_until: dt.datetime | None
    max_entries: int
    used_entries: int
    status: str
    source: str | None
    created_at: dt.datetime


class PassesPage(_Frozen):
    items: list[PassRow]
    total: int
    limit: int
    offset: int


class RequestRow(_Frozen):
    id: int
    apartment_id: int
    created_by_user_id: int
    vehicle_id: int | None
    plate_number_original: str | None
    plate_number_normalized: str | None
    relation_type: str | None
    status: str
    reviewed_by_user_id: int | None
    reviewed_at: dt.datetime | None
    review_comment: str | None
    created_at: dt.datetime


class RequestsPage(_Frozen):
    items: list[RequestRow]
    total: int
    limit: int
    offset: int


# --- Обогащение деталей: заявитель / адрес / зона (§6.2, экран менеджера) ---


class ApplicantInfo(_Frozen):
    """PD-обогащение: данные жителя (заявитель/владелец) для экрана менеджера."""

    user_id: int
    name: str | None
    phone: str | None
    username: str | None
    telegram_id: int | None


class AddressInfo(_Frozen):
    """Адрес квартиры: apartment→building→yard (справочник адресов)."""

    apartment_id: int
    apartment_number: str | None
    entrance: str | None
    floor: str | None
    building_id: int | None
    building_address: str | None
    yard_id: int | None
    yard_name: str | None


class ZoneRef(_Frozen):
    """Краткая ссылка на зону парковки."""

    id: int
    code: str | None
    name: str | None


class ApartmentDetail(_Frozen):
    """Связь авто↔квартира, обогащённая адресом, жителями и зонами (карточка авто)."""

    apartment_id: int
    relation_type: str
    status: str
    address: AddressInfo | None
    residents: list[ApplicantInfo]
    zones: list[ZoneRef]


class RequestDetail(_Frozen):
    """Деталь заявки на авто: заявитель + адрес + обслуживающие зоны + авто."""

    request: RequestRow
    applicant: ApplicantInfo | None
    address: AddressInfo | None
    serving_zones: list[ZoneRef]
    vehicle: VehicleRow | None


class PassDetail(_Frozen):
    """Деталь пропуска: заявитель + адрес + зона + обслуживающие зоны (кандидаты)."""

    pass_record: PassRow = Field(serialization_alias="pass")
    applicant: ApplicantInfo | None
    address: AddressInfo | None
    zone: ZoneRef | None
    serving_zones: list[ZoneRef] = []


# VehicleDetail.apartment_details ссылается на ApartmentDetail (определён ниже).
VehicleDetail.model_rebuild()
