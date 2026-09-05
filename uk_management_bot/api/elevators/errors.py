"""Маппинг доменных ошибок сервиса «Лифты» на HTTP-коды (общий для роутеров модуля).

Validation → 422, NotFound → 404, Conflict/State → 409 (образец
``api/materials/router.py::_http_error``). ``detail`` — текст доменной
ошибки: API отдаёт JSON, сериализатор экранирует сам.
"""
from __future__ import annotations

from fastapi import HTTPException

from uk_management_bot.services.elevator_service import (
    ElevatorConflictError,
    ElevatorNotFoundError,
    ElevatorServiceError,
    ElevatorValidationError,
)


def http_error(exc: ElevatorServiceError) -> HTTPException:
    """Доменная ошибка → ``HTTPException`` с кодом по классу."""
    if isinstance(exc, ElevatorNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ElevatorConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ElevatorValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))
