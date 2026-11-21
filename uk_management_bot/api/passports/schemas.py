"""Тела запросов API «Паспорт дома». Содержимое значений проверяет сервис (коды отказов)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

DB_ID_MAX = 2_147_483_647
VERSION_MAX = 1_000_000_000
KEYS_MAX = 250  # вся схема — около 150 ключей; запас на пометку «нет данных» разом


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0, le=VERSION_MAX)


class PassportPatchIn(_Body):
    values: dict[str, Any] = Field(default_factory=dict, max_length=KEYS_MAX)
    unknown: dict[str, Optional[str]] = Field(default_factory=dict, max_length=KEYS_MAX)
    absent: dict[str, bool] = Field(default_factory=dict, max_length=KEYS_MAX)
    shared_from: dict[str, Optional[int]] = Field(default_factory=dict, max_length=8)
    meta: dict[str, Optional[str]] = Field(default_factory=dict, max_length=8)


class PassportStatusIn(_Body):
    # «Подписан» сюда не входит: подписание и возврат в работу — свои маршруты со своим правом.
    status: Literal["not_started", "collecting", "inspected", "filled"]


class PassportSignIn(_Body):
    pass


class PassportReopenIn(_Body):
    reason: str = Field(max_length=300)
