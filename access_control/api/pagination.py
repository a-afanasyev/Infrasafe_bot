"""Общие хелперы api-роутеров access_control (A6-P2-50).

До дедупа эти определения были посимвольно скопированы по роутерам:
``DEFAULT_LIMIT``/``MAX_LIMIT`` ×4 (equipment, parking_admin, registry,
resident), ``_limit``/``_limit_q`` ×4, ``_raise_404`` ×2, ``_Frozen`` ×3.
Роутеры импортируют отсюда под привычными приватными именами — колл-сайты
не менялись.

``services/resident.py`` держит СВОИ константы лимитов сознательно: слой
сервисов не импортирует из ``api/`` (направление зависимостей api → services).
"""
from __future__ import annotations

from fastapi import HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class Frozen(BaseModel):
    """База response-DTO: иммутабельные строки ответов."""

    model_config = ConfigDict(frozen=True)


def limit_query(value: int = DEFAULT_LIMIT) -> int:
    """Query-параметр размера страницы с общим потолком."""
    return Query(value, ge=1, le=MAX_LIMIT, description="размер страницы (max 200)")


def raise_404(exc) -> None:
    """Доменное «не найдено» → HTTP 404 с текстом исключения."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
