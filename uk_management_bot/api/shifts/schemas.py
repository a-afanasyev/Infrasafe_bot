from pydantic import BaseModel, model_validator
from typing import Optional, Literal
from datetime import datetime, date as date_type
import json

ShiftStatus = Literal["active", "completed", "cancelled", "planned", "paused"]
ShiftType = Literal["regular", "emergency", "overtime", "maintenance"]
TransferAction = Literal["approve", "reject", "cancel"]


class EmployeeBrief(BaseModel):
    id: int
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]
    specialization: list[str]  # parsed from User.specialization (Text JSON like '["electrician"]')
    active_shift_id: Optional[int]
    verification_status: str

    model_config = {"from_attributes": True}

    @model_validator(mode='before')
    @classmethod
    def _coerce_from_orm(cls, values):
        """Convert ORM object to dict before field validation."""
        if hasattr(values, '__dict__') and not isinstance(values, dict):
            # Extract all relevant fields from ORM object
            return {
                "id": getattr(values, "id", None),
                "first_name": getattr(values, "first_name", None),
                "last_name": getattr(values, "last_name", None),
                "phone": getattr(values, "phone", None),
                "verification_status": getattr(values, "verification_status", ""),
                "active_shift_id": getattr(values, "active_shift_id", None),
                "specialization": getattr(values, "specialization", None),
            }
        return values

    @model_validator(mode='after')
    def parse_specialization(self) -> "EmployeeBrief":
        """Parse JSON string specialization into list[str]."""
        raw = self.specialization
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                self.specialization = parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                self.specialization = []
        elif raw is None:
            self.specialization = []
        # if already a list, leave as-is
        return self


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
    shift_type: str = "regular"
    specialization_focus: list[str] = []
    max_requests: int = 10
    priority_level: int = 1
    notes: Optional[str] = None


class UpdateShiftBody(BaseModel):
    status: Optional[str] = None
    user_id: Optional[int] = None
    shift_type: Optional[str] = None
    end_time: Optional[datetime] = None
    notes: Optional[str] = None
    max_requests: Optional[int] = None


class CreateFromTemplateBody(BaseModel):
    template_id: int
    date: date_type  # validated YYYY-MM-DD
    user_ids: Optional[list[int]] = None


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

    model_config = {"from_attributes": True}


class CreateTemplateBody(BaseModel):
    name: str
    description: Optional[str] = None
    start_hour: int
    start_minute: int = 0
    duration_hours: int
    required_specializations: list[str] = []
    min_executors: int = 1
    max_executors: int = 3
    default_max_requests: int = 10
    days_of_week: list[int] = []
    auto_create: bool = False
    default_shift_type: str = "regular"
    priority_level: int = 1


class UpdateTemplateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_hour: Optional[int] = None
    start_minute: Optional[int] = None
    duration_hours: Optional[int] = None
    required_specializations: Optional[list[str]] = None
    min_executors: Optional[int] = None
    max_executors: Optional[int] = None
    default_max_requests: Optional[int] = None
    days_of_week: Optional[list[int]] = None
    auto_create: Optional[bool] = None
    default_shift_type: Optional[str] = None
    priority_level: Optional[int] = None
    is_active: Optional[bool] = None
