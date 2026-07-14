import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.catalog import ORMModel, ProviderOut, TagOut

ResourceType = Literal["electricity", "cold_water"]
MeterUnit = Literal["kWh", "m3"]
MeterStatus = Literal["active", "decommissioned", "archived"]


class ConsumerLinkIn(BaseModel):
    object_id: uuid.UUID
    description: str | None = None
    allocation_percent: Decimal | None = Field(default=None, ge=0, le=100)


class ConsumerLinkOut(ORMModel):
    id: uuid.UUID
    object_id: uuid.UUID
    object_name: str | None = None
    link_type: str
    description: str | None
    allocation_percent: Decimal | None


class MeterCreate(BaseModel):
    meter_number: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    resource_type: ResourceType
    unit: MeterUnit
    description: str = Field(min_length=1)
    install_location: str = Field(min_length=1, max_length=300)
    primary_object_id: uuid.UUID
    provider_id: uuid.UUID | None = None
    provider_account: str | None = Field(default=None, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    coefficient: Decimal = Field(default=Decimal("1"), gt=0)
    max_digits: int | None = Field(default=None, ge=1, le=18)
    installed_at: date | None = None
    photo_file_id: str | None = None
    note: str | None = None
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    consumers: list[ConsumerLinkIn] = Field(default_factory=list)


class MeterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1)
    install_location: str | None = Field(default=None, min_length=1, max_length=300)
    primary_object_id: uuid.UUID | None = None
    provider_id: uuid.UUID | None = None
    provider_account: str | None = None
    serial_number: str | None = None
    coefficient: Decimal | None = Field(default=None, gt=0)
    max_digits: int | None = Field(default=None, ge=1, le=18)
    installed_at: date | None = None
    photo_file_id: str | None = None
    note: str | None = None
    tag_ids: list[uuid.UUID] | None = None
    consumers: list[ConsumerLinkIn] | None = None


class MeterOut(ORMModel):
    id: uuid.UUID
    meter_number: str
    name: str
    resource_type: str
    unit: str
    description: str
    install_location: str
    status: str
    primary_object_id: uuid.UUID
    primary_object_name: str | None = None
    provider_id: uuid.UUID | None
    provider: ProviderOut | None = None
    provider_account: str | None
    serial_number: str | None
    coefficient: Decimal
    max_digits: int | None
    installed_at: date | None
    removed_at: date | None
    replaces_meter_id: uuid.UUID | None
    photo_file_id: str | None
    note: str | None
    tags: list[TagOut] = []
    consumers: list[ConsumerLinkOut] = []
    created_at: datetime
    updated_at: datetime


class CorrectNumberIn(BaseModel):
    new_number: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3)


class ReplaceMeterIn(BaseModel):
    removed_at: date
    final_reading: Decimal | None = Field(default=None, ge=0)
    new_meter: MeterCreate
    reason: str = Field(min_length=3)
