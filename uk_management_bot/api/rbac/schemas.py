"""Схемы админки ролей."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

ROLE_KEY_PATTERN = r"^[a-z][a-z0-9_]{2,31}$"


class ActionOut(BaseModel):
    key: str
    title: str
    area: str
    approved_only: bool
    superadmin_only: bool
    default_roles: list[str]


class RoleOut(BaseModel):
    key: str
    title: str
    description: Optional[str] = None
    is_system: bool
    #: Действия, которые роль даёт сейчас (с учётом правок в админке).
    actions: list[str]
    #: Действия, отличающиеся от прав «из коробки» (для системных ролей).
    customized: list[str] = []
    users_count: int = 0


class RolesOut(BaseModel):
    roles: list[RoleOut]
    can_edit: bool


class RoleCreate(BaseModel):
    key: str = Field(pattern=ROLE_KEY_PATTERN, description="латиница, цифры и _; 3–32 символа")
    title: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    actions: list[str] = []


class RoleUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    actions: Optional[list[str]] = None


class UserRolesOut(BaseModel):
    user_id: int
    roles: list[str]
    active_role: Optional[str] = None
    is_superadmin: bool
    can_edit: bool


class UserRolesUpdate(BaseModel):
    roles: list[str] = Field(min_length=1)
