import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Object types ---
class ObjectTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ObjectTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None


class ObjectTypeOut(ORMModel):
    id: uuid.UUID
    name: str
    is_active: bool


# --- Tags ---
class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None


class TagOut(ORMModel):
    id: uuid.UUID
    name: str
    is_active: bool


# --- Providers ---
class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact: str | None = None
    export_template: str | None = None


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    contact: str | None = None
    export_template: str | None = None
    is_active: bool | None = None


class ProviderOut(ORMModel):
    id: uuid.UUID
    name: str
    contact: str | None
    export_template: str | None
    is_active: bool


# --- Resource objects ---
class ResourceObjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=64)
    type_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    description: str | None = None
    sort_order: int = 0
    tag_ids: list[uuid.UUID] = Field(default_factory=list)


class ResourceObjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=64)
    type_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    clear_parent: bool = False
    description: str | None = None
    sort_order: int | None = None
    tag_ids: list[uuid.UUID] | None = None


class ResourceObjectOut(ORMModel):
    id: uuid.UUID
    name: str
    code: str | None
    type_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    description: str | None
    sort_order: int
    is_active: bool
    tags: list[TagOut] = []
    created_at: datetime
    updated_at: datetime
