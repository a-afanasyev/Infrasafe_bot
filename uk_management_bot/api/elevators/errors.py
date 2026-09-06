"""Маппинг доменных ошибок сервиса «Лифты» на HTTP-коды (общий для роутеров модуля).

Validation → 422, NotFound → 404, Conflict/State → 409 (образец
``api/materials/router.py::_http_error``). ``detail`` — текст доменной
ошибки: API отдаёт JSON, сериализатор экранирует сам.

Исключение — Р18 ``ElevatorUnderWorksError`` (подкласс Validation): 409 со
СТРУКТУРНЫМ ``detail`` (``code``/``status``/``status_since``/``label``), чтобы
клиент показал житель-текст про идущие работы, а не общий тост. Проверяется
РАНЬШЕ базового Validation — иначе получил бы 422.
"""
from __future__ import annotations

from fastapi import HTTPException

from uk_management_bot.services.elevator_service import (
    ElevatorConflictError,
    ElevatorNotFoundError,
    ElevatorServiceError,
    ElevatorUnderWorksError,
    ElevatorValidationError,
)

UNDER_WORKS_CODE = "elevator_under_works"


def under_works_detail(exc: ElevatorUnderWorksError) -> dict:
    """Тело 409 для Р18: машинный код + поля сообщения (время — ISO-8601)."""
    return {
        "code": UNDER_WORKS_CODE,
        "status": exc.status,
        "status_since": exc.status_since.isoformat() if exc.status_since is not None else None,
        "label": exc.label,
    }


def http_error(exc: ElevatorServiceError) -> HTTPException:
    """Доменная ошибка → ``HTTPException`` с кодом по классу."""
    if isinstance(exc, ElevatorNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ElevatorUnderWorksError):
        return HTTPException(status_code=409, detail=under_works_detail(exc))
    if isinstance(exc, ElevatorConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ElevatorValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    # Базовый ElevatorServiceError напрямую домен не бросает; появится новый
    # подкласс — маппить явно выше, а не полагаться на эту ветку. Текст ошибки
    # наружу не отдаём: неизвестная ошибка может нести внутренние детали.
    return HTTPException(status_code=500, detail="Internal error in elevators service")
