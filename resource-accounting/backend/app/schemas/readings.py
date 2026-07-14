import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.catalog import ORMModel

ReadingKind = Literal["normal", "rollover", "replacement", "correction"]
MissingReason = Literal["no_access", "broken", "replaced", "other"]


class PeriodCreate(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class PeriodOut(ORMModel):
    id: uuid.UUID
    month: str
    status: str


class ReadingIn(BaseModel):
    value: Decimal | None = Field(default=None, ge=0)
    read_at: date | None = None
    kind: ReadingKind = "normal"
    missing_reason: MissingReason | None = None
    comment: str | None = None
    photo_file_id: str | None = None


class BulkReadingItem(ReadingIn):
    meter_id: uuid.UUID


class BulkReadingsIn(BaseModel):
    items: list[BulkReadingItem] = Field(min_length=1, max_length=500)


class CorrectionIn(BaseModel):
    new_value: Decimal = Field(ge=0)
    reason: str = Field(min_length=3)
    kind: ReadingKind = "correction"


class ReadingOut(ORMModel):
    id: uuid.UUID
    meter_id: uuid.UUID
    reporting_period_id: uuid.UUID
    value: Decimal | None
    read_at: date | None
    kind: str
    previous_value: Decimal | None
    consumption: Decimal | None
    status: str
    validation_message: str | None
    missing_reason: str | None
    comment: str | None
    photo_file_id: str | None


class WorksheetRow(BaseModel):
    meter_id: uuid.UUID
    meter_number: str
    meter_name: str
    resource_type: str
    unit: str
    description: str
    primary_object_id: uuid.UUID
    primary_object_name: str
    consumers: list[str] = []
    provider_name: str | None = None
    coefficient: Decimal
    previous_value: Decimal | None = None
    previous_read_at: date | None = None
    reading: ReadingOut | None = None


class WorksheetOut(BaseModel):
    period: PeriodOut
    rows: list[WorksheetRow]


class AnomalyRuleIn(BaseModel):
    resource_type: Literal["electricity", "cold_water"]
    abs_threshold: Decimal | None = Field(default=None, ge=0)
    pct_change_threshold: Decimal | None = Field(default=None, ge=0)
    avg_window_months: int = Field(default=6, ge=1, le=24)
    avg_deviation_pct: Decimal | None = Field(default=None, ge=0)


class AnomalyRuleOut(ORMModel):
    id: uuid.UUID
    resource_type: str
    abs_threshold: Decimal | None
    pct_change_threshold: Decimal | None
    avg_window_months: int
    avg_deviation_pct: Decimal | None
