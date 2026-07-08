from pydantic import BaseModel, model_validator, Field
from typing import Optional, Literal
from datetime import datetime, date as date_type
import json

from uk_management_bot.utils.auth_helpers import parse_roles_safe

ShiftStatus = Literal["active", "completed", "cancelled", "planned", "paused"]
ShiftType = Literal["regular", "emergency", "overtime", "maintenance"]
TransferAction = Literal["approve", "reject", "cancel"]


def _parse_spec_field(raw) -> list[str]:
    """Разбор ``User.specialization`` в список С СОХРАНЕНИЕМ порядка.

    Хранилище разнородно: JSON-массив (``'["plumber","electric"]'``), CSV из
    инвайта (``'electrician,plumber'``) либо скаляр. Сохраняем текущее поведение
    (JSON-массив как есть; невалидный JSON и JSON-объект → ``[]``), но добавляем
    CSV/скаляр. Вокабуляр спецификаций в проекте фрагментирован (backend-конста
    ``electric/plumbing`` vs фронт/бот ``electrician/plumber``), поэтому канон-
    список не годится для фильтра — распознаём «чистые» словарные токены через
    ``isalpha()`` (отсекает JSON-мусор со скобками/кавычками, пропускает специ).
    """
    if isinstance(raw, (list, tuple)):
        return [str(s).strip() for s in raw if str(s).strip()]
    if not isinstance(raw, str):
        return []
    text = raw.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return []
        return [str(s).strip() for s in parsed if str(s).strip()] if isinstance(parsed, list) else []
    # CSV / скаляр (напр. из инвайта): как спец берём только словарные токены.
    return [t for t in (p.strip() for p in text.split(",")) if t.isalpha()]


class EmployeeBrief(BaseModel):
    id: int
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]
    specialization: list[str]  # parsed from User.specialization (JSON '["electrician"]' или CSV)
    active_shift_id: Optional[int]
    verification_status: str
    status: str = "approved"
    roles: list[str] = []  # parsed from User.roles (JSON) — нужен для бейджа роли в очереди

    model_config = {"from_attributes": True}

    @model_validator(mode='before')
    @classmethod
    def _coerce_from_orm(cls, values):
        """Convert ORM object to dict before field validation, parsing JSON fields."""
        if hasattr(values, '__dict__') and not isinstance(values, dict):
            values = {
                "id": getattr(values, "id", None),
                "first_name": getattr(values, "first_name", None),
                "last_name": getattr(values, "last_name", None),
                "phone": getattr(values, "phone", None),
                "verification_status": getattr(values, "verification_status", ""),
                "active_shift_id": getattr(values, "active_shift_id", None),
                "status": getattr(values, "status", "approved"),
                "specialization": getattr(values, "specialization", None),
                "roles": getattr(values, "roles", None),
            }
        if isinstance(values, dict):
            # Спецификации: JSON-массив / CSV / скаляр → список (порядок сохранён).
            values["specialization"] = _parse_spec_field(values.get("specialization"))
            # Роли: JSON-строка → список; уже-список принимаем как есть.
            raw_roles = values.get("roles")
            if isinstance(raw_roles, (list, tuple)):
                values["roles"] = [str(r).strip() for r in raw_roles if str(r).strip()]
            else:
                values["roles"] = parse_roles_safe(raw_roles)
        return values


class ShiftBrief(BaseModel):
    id: int
    user_id: Optional[int]
    executor_name: Optional[str]  # computed: first_name + last_name
    status: str
    shift_type: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    max_requests: int
    current_request_count: int
    load_percentage: float  # current_request_count / max_requests * 100
    # Week/month views need the specialization to drive the sidebar filter
    # (`MonthResourceGrid` + `SpecializationSidebar`). Without it the client
    # would need a per-shift N+1 fetch into /shifts/{id} just to color-code
    # rows by spec — same data already lives on `Shift.specialization_focus`.
    specialization_focus: Optional[list[str]] = None

    model_config = {"from_attributes": True}


class ShiftDetail(ShiftBrief):
    notes: Optional[str]
    specialization_focus: Optional[list[str]]
    coverage_areas: Optional[list]
    priority_level: int
    completed_requests: int
    efficiency_score: Optional[float]
    quality_rating: Optional[float]
    template_id: Optional[int]
    created_at: Optional[datetime]


class EmployeeDetail(EmployeeBrief):
    active_shift: Optional[ShiftBrief]
    rating: Optional[float]
    total_shifts: int
    total_completed: int


class TransferOut(BaseModel):
    id: int
    shift_id: int
    from_executor_name: Optional[str]
    to_executor_name: Optional[str]
    status: str
    reason: str
    urgency_level: str
    comment: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ShiftStatsOut(BaseModel):
    active_shifts: int
    active_executors: int
    coverage_pct: float
    avg_efficiency: Optional[float]
    shifts_today: int
    pending_transfers: int


# Request bodies
class CreateShiftBody(BaseModel):
    user_id: int
    start_time: datetime
    end_time: datetime
    shift_type: ShiftType = "regular"
    specialization_focus: list[str] = []
    max_requests: int = Field(default=10, ge=1)
    priority_level: int = Field(default=1, ge=1, le=5)
    notes: Optional[str] = None

    @model_validator(mode='after')
    def check_time_order(self):
        if self.end_time <= self.start_time:
            raise ValueError('end_time must be after start_time')
        return self


class UpdateShiftBody(BaseModel):
    status: Optional[ShiftStatus] = None
    user_id: Optional[int] = None
    shift_type: Optional[ShiftType] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    notes: Optional[str] = None
    max_requests: Optional[int] = Field(default=None, ge=1)
    priority_level: Optional[int] = Field(default=None, ge=1, le=5)
    specialization_focus: Optional[list[str]] = None


class CreateFromTemplateBody(BaseModel):
    template_id: int
    date: date_type  # validated YYYY-MM-DD
    user_ids: list[int] = Field(..., min_length=1)


class ReassignShiftBody(BaseModel):
    # REG-02: прямой менеджерский reassign смены (без согласия получателя).
    executor_id: int


class HandleTransferBody(BaseModel):
    action: TransferAction
    to_executor_id: Optional[int] = None  # required when action == "approve"


class TemplateBrief(BaseModel):
    id: int
    name: str
    description: Optional[str]
    start_hour: int
    start_minute: int
    duration_hours: int
    default_shift_type: str
    days_of_week: Optional[list]
    is_active: bool
    min_executors: int
    max_executors: int
    auto_create: bool
    required_specializations: Optional[list]
    default_max_requests: int
    priority_level: int
    recurrence_mode: Literal["weekday", "cycle"] = "weekday"
    cycle_days_on: Optional[int] = None
    cycle_days_off: Optional[int] = None
    cycle_anchor_date: Optional[date_type] = None

    model_config = {"from_attributes": True}


class CreateTemplateBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    start_hour: int = Field(ge=0, le=23)
    start_minute: int = Field(default=0, ge=0, le=59)
    duration_hours: int = Field(ge=1, le=24)
    required_specializations: list[str] = []
    min_executors: int = Field(default=1, ge=1)
    max_executors: int = Field(default=3, ge=1)
    default_max_requests: int = Field(default=10, ge=1)
    days_of_week: list[int] = Field(default=[])
    auto_create: bool = False
    default_shift_type: ShiftType = "regular"
    priority_level: int = Field(default=1, ge=1, le=5)
    recurrence_mode: Literal["weekday", "cycle"] = "weekday"
    cycle_days_on: Optional[int] = Field(default=None, ge=1, le=365)
    cycle_days_off: Optional[int] = Field(default=None, ge=0, le=365)
    cycle_anchor_date: Optional[date_type] = None

    @model_validator(mode='after')
    def check_executor_range(self):
        if self.min_executors > self.max_executors:
            raise ValueError('min_executors cannot exceed max_executors')
        if any(d < 0 or d > 6 for d in self.days_of_week):
            raise ValueError('days_of_week values must be 0-6')
        if self.recurrence_mode == "cycle":
            if self.cycle_days_on is None:
                raise ValueError('cycle_days_on is required when recurrence_mode is cycle')
            if self.cycle_anchor_date is None:
                raise ValueError('cycle_anchor_date is required when recurrence_mode is cycle')
            if self.cycle_days_on + (self.cycle_days_off or 0) > 366:
                raise ValueError('cycle_days_on + cycle_days_off cannot exceed 366')
        return self


class DeleteEmployeeRequest(BaseModel):
    reason: str = Field(min_length=1)
    reassign_to: Optional[int] = None


class ActiveRequestsCount(BaseModel):
    count: int


class CreateInviteRequest(BaseModel):
    role: Literal["executor", "manager"]
    specializations: list[str] = []
    hours: int = Field(default=24, ge=1, le=168)


class CreateInviteResponse(BaseModel):
    token: str
    bot_link: str
    expires_at: datetime


class CreateEmployeeRequest(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    phone: str = Field(min_length=10)
    role: Literal["executor", "manager"]
    specializations: list[str] = []
    status: Literal["approved", "pending"] = "approved"


class UpdateTemplateBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    start_hour: Optional[int] = Field(default=None, ge=0, le=23)
    start_minute: Optional[int] = Field(default=None, ge=0, le=59)
    duration_hours: Optional[int] = Field(default=None, ge=1, le=24)
    required_specializations: Optional[list[str]] = None
    min_executors: Optional[int] = Field(default=None, ge=1)
    max_executors: Optional[int] = Field(default=None, ge=1)
    default_max_requests: Optional[int] = Field(default=None, ge=1)
    days_of_week: Optional[list[int]] = None
    auto_create: Optional[bool] = None
    default_shift_type: Optional[ShiftType] = None
    priority_level: Optional[int] = Field(default=None, ge=1, le=5)
    recurrence_mode: Optional[Literal["weekday", "cycle"]] = None
    cycle_days_on: Optional[int] = Field(default=None, ge=1, le=365)
    cycle_days_off: Optional[int] = Field(default=None, ge=0, le=365)
    cycle_anchor_date: Optional[date_type] = None
    # is_active removed: soft-delete must go through the DELETE endpoint

    @model_validator(mode='after')
    def check_executor_range(self):
        if self.min_executors is not None and self.max_executors is not None:
            if self.min_executors > self.max_executors:
                raise ValueError('min_executors cannot exceed max_executors')
        if self.days_of_week is not None:
            if any(d < 0 or d > 6 for d in self.days_of_week):
                raise ValueError('days_of_week values must be 0-6')
        if self.recurrence_mode == "cycle":
            if self.cycle_days_on is None:
                raise ValueError('cycle_days_on is required when recurrence_mode is cycle')
            if self.cycle_anchor_date is None:
                raise ValueError('cycle_anchor_date is required when recurrence_mode is cycle')
        if self.cycle_days_on is not None:
            if self.cycle_days_on + (self.cycle_days_off or 0) > 366:
                raise ValueError('cycle_days_on + cycle_days_off cannot exceed 366')
        return self
