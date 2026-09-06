"""Pydantic-схемы модуля «Лифты» (/api/v2/elevators).

Входные схемы строгие (``extra="forbid"``, AUD5-APIFE-6): опечатка в ключе —
422, а не тихая потеря данных. Глубокие проверки (ширина колонок, диапазоны
графика, инварианты состояния) выполняет ``services/elevator_service`` —
схемы держат форму. Имена уникальны в приложении (``Elevator*``): OpenAPI
собирается по именам моделей.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

ElevatorStatus = Literal["working", "not_working", "under_repair", "maintenance"]
OccurrenceKind = Literal["maintenance", "certification"]
OccurrenceState = Literal["planned", "done", "cancelled"]
CalendarState = Literal["planned", "done", "cancelled", "all"]
RegistryFlag = Literal["no_contract", "cert_expired", "maintenance_overdue"]
Lang = Literal["ru", "uz"]

MAX_REASON_LEN = 500
MAX_BULK_CONFIRM = 50


class _StrictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _FromAttributes(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Паспорт: вход ────────────────────────────────────────────────────

class ElevatorPassportOptionalIn(_StrictIn):
    """Опциональная часть паспорта/договора/освидетельствования/простоя."""

    factory_number: Optional[str] = None
    model: Optional[str] = None
    production_year: Optional[int] = None
    capacity_kg: Optional[int] = None
    floors_served: Optional[str] = None
    service_org_name: Optional[str] = None
    service_org_phone: Optional[str] = None
    contract_number: Optional[str] = None
    contract_until: Optional[date] = None
    cert_number: Optional[str] = None
    cert_valid_until: Optional[date] = None
    cert_act_url: Optional[str] = None
    downtime_reason: Optional[str] = None
    spare_part_expected_on: Optional[date] = None
    publish_downtime_details: Optional[bool] = None
    is_public: Optional[bool] = None


class ElevatorCreateIn(ElevatorPassportOptionalIn):
    building_id: int = Field(gt=0)
    entrance_number: int = Field(gt=0)
    elevator_number: int = Field(gt=0)
    passport_number: str = Field(min_length=1)
    manufacturer: str = Field(min_length=1)
    serial_number: str = Field(min_length=1)


class ElevatorPatchIn(ElevatorPassportOptionalIn):
    """Все поля опциональны; ``expected_version`` — оптимистичная блокировка (409 при гонке)."""

    building_id: Optional[int] = Field(None, gt=0)
    entrance_number: Optional[int] = Field(None, gt=0)
    elevator_number: Optional[int] = Field(None, gt=0)
    passport_number: Optional[str] = None
    manufacturer: Optional[str] = None
    serial_number: Optional[str] = None
    expected_version: Optional[int] = None


class ElevatorCommissionIn(_StrictIn):
    commissioned_at: Optional[date] = None


class ElevatorArchiveIn(_StrictIn):
    reason: str = Field(min_length=1, max_length=MAX_REASON_LEN)


class ElevatorStatusIn(_StrictIn):
    status: ElevatorStatus
    reason: Optional[str] = Field(None, max_length=MAX_REASON_LEN)
    request_number: Optional[str] = None


# ── График: вход ─────────────────────────────────────────────────────

class ElevatorOccurrenceCreateIn(_StrictIn):
    kind: OccurrenceKind
    due_on: date


class ElevatorOccurrenceGenerateIn(_StrictIn):
    kind: OccurrenceKind
    start: date
    every_months: int
    count: int


class ElevatorOccurrenceRescheduleIn(_StrictIn):
    due_on: date


class ElevatorOccurrenceCompleteIn(_StrictIn):
    """Закрытие записи; для освидетельствования обязательны ``cert_number`` и ``cert_valid_until``."""

    comment: Optional[str] = None
    done_at: Optional[AwareDatetime] = None
    cert_number: Optional[str] = None
    cert_valid_until: Optional[date] = None
    cert_act_url: Optional[str] = None
    request_number: Optional[str] = None


# ── Заявки / конфиг: вход ────────────────────────────────────────────

class ElevatorBulkConfirmIn(_StrictIn):
    request_numbers: list[str] = Field(min_length=1, max_length=MAX_BULK_CONFIRM)


class ElevatorsDowntimeThresholdsIn(_StrictIn):
    """Пороги простоя в днях; явный ``null`` = не напоминать."""

    not_working: Optional[int] = None
    under_repair: Optional[int] = None


class ElevatorsResidentNotificationsIn(_StrictIn):
    repair_started: Optional[bool] = None
    maintenance_started: Optional[bool] = None
    back_in_service: Optional[bool] = None


class ElevatorsStaffRemindersIn(_StrictIn):
    maintenance: Optional[list[int]] = None
    certification: Optional[list[int]] = None
    contract: Optional[list[int]] = None
    overdue_weekly: Optional[bool] = None


class ElevatorsConfigIn(_StrictIn):
    module_public: Optional[bool] = None
    # Р18a: тумблер менеджера. False (дефолт) — житель не создаст заявку по
    # лифту «В ремонте»/«На ТО»; персонала запрет не касается никогда.
    allow_resident_requests_under_works: Optional[bool] = None
    downtime_threshold_days: Optional[ElevatorsDowntimeThresholdsIn] = None
    resident_notifications: Optional[ElevatorsResidentNotificationsIn] = None
    staff_reminders: Optional[ElevatorsStaffRemindersIn] = None


# ── Выход ────────────────────────────────────────────────────────────

class ElevatorFlagsOut(BaseModel):
    no_contract: bool
    cert_expired: bool
    maintenance_overdue: bool


class ElevatorCardOut(BaseModel):
    """Строка реестра. ``label`` собирается бэком (``elevator_label``) — бот и фронт печатают одинаково."""

    id: int
    building_id: int
    building_address: str
    yard_id: int
    yard_name: Optional[str] = None
    entrance_number: int
    elevator_number: int
    label: str
    current_status: Optional[ElevatorStatus] = None
    status_since: Optional[datetime] = None
    is_commissioned: bool
    archived_at: Optional[datetime] = None
    is_public: bool
    flags: ElevatorFlagsOut
    availability_30d: Optional[float] = None
    open_requests_count: int


class ElevatorDetailOut(ElevatorCardOut):
    """Карточка + паспорт + договор/освидетельствование + простой (staff-only)."""

    passport_number: str
    manufacturer: str
    serial_number: str
    factory_number: Optional[str] = None
    model: Optional[str] = None
    production_year: Optional[int] = None
    capacity_kg: Optional[int] = None
    floors_served: Optional[str] = None
    commissioned_at: Optional[date] = None
    downtime_reason: Optional[str] = None
    spare_part_expected_on: Optional[date] = None
    publish_downtime_details: bool
    service_org_name: Optional[str] = None
    service_org_phone: Optional[str] = None
    contract_number: Optional[str] = None
    contract_until: Optional[date] = None
    cert_number: Optional[str] = None
    cert_valid_until: Optional[date] = None
    cert_act_url: Optional[str] = None
    public_code: str
    archived_reason: Optional[str] = None
    apartments_without_entrance_count: int
    version: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ElevatorListOut(BaseModel):
    items: list[ElevatorCardOut]
    total: int


class ElevatorMiniOut(BaseModel):
    """Лифт для выбора в заявке (жителю: только свои дома).

    ``status_since`` нужен шагу «Лифт» в TWA: по лифту «В ремонте»/«На ТО»
    заявка жителя запрещена (Р18), и в отказе показывается, с какого момента.
    ``resident_request_blocked`` — готовый вердикт самообслуживания: сервер уже
    учёл статус и тумблер ``allow_resident_requests_under_works`` (Р18a), клиенту
    не нужно знать про конфиг. Персонала (колл-центр, обходчик, лифтёр) запрет
    не касается — этот флаг про поток жителя.
    """

    id: int
    entrance_number: int
    elevator_number: int
    label: str
    current_status: Optional[ElevatorStatus] = None
    status_since: Optional[datetime] = None
    resident_request_blocked: bool = False


class ElevatorStatusChangeOut(BaseModel):
    changed: bool
    old_status: Optional[ElevatorStatus] = None
    new_status: Optional[ElevatorStatus] = None
    status_since: Optional[datetime] = None
    notified_residents: int


class ElevatorEventOut(_FromAttributes):
    id: int
    elevator_id: int
    event_kind: str
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    occurred_at: datetime
    actor_user_id: Optional[int] = None
    source: str
    request_number: Optional[str] = None
    reason: Optional[str] = None
    payload: Optional[dict[str, Any]] = None


class ElevatorOccurrenceOut(BaseModel):
    id: int
    elevator_id: int
    elevator_label: str
    kind: OccurrenceKind
    due_on: date
    state: OccurrenceState
    done_at: Optional[datetime] = None
    done_by_user_id: Optional[int] = None
    comment: Optional[str] = None
    request_number: Optional[str] = None
    created_at: Optional[datetime] = None


class ElevatorRequestRowOut(BaseModel):
    request_number: str
    status: str
    category: str
    urgency: str
    created_at: Optional[datetime] = None
    elevator_operational: Optional[bool] = None
    executor_name: Optional[str] = None
    applicant_name: Optional[str] = None


class ElevatorBulkConfirmItemOut(BaseModel):
    request_number: str
    ok: bool
    error_kind: Optional[str] = None
    error: Optional[str] = None


class ElevatorsDowntimeThresholdsOut(BaseModel):
    not_working: Optional[int] = None
    under_repair: Optional[int] = None


class ElevatorsResidentNotificationsOut(BaseModel):
    repair_started: bool
    maintenance_started: bool
    back_in_service: bool


class ElevatorsStaffRemindersOut(BaseModel):
    """Стадии напоминаний персоналу в днях до срока (убывающие) + еженедельный повтор просрочки."""

    maintenance: list[int]
    certification: list[int]
    contract: list[int]
    overdue_weekly: bool


class ElevatorCountersOut(BaseModel):
    total: int
    by_status: dict[str, int]
    no_contract: int
    cert_expired: int
    maintenance_overdue: int
    downtime_over_threshold: int


class ElevatorYardSummaryOut(BaseModel):
    yard_id: int
    yard_name: str
    counters: ElevatorCountersOut


class ElevatorSummaryOut(BaseModel):
    today: date
    totals: ElevatorCountersOut
    yards: list[ElevatorYardSummaryOut]
    requests_without_elevator: int
    downtime_threshold_days: ElevatorsDowntimeThresholdsOut


class ElevatorsConfigOut(BaseModel):
    module_public: bool
    allow_resident_requests_under_works: bool
    downtime_threshold_days: ElevatorsDowntimeThresholdsOut
    resident_notifications: ElevatorsResidentNotificationsOut
    staff_reminders: ElevatorsStaffRemindersOut
