"""Мапинг доменных исключений раздела «Жители» в HTTP-ответы.

Регистрируется на приложении в api/main.py — по образцу
`register_address_exception_handlers`. Позволяет роутеру звать сервис-слой
напрямую и не оборачивать каждый вызов в try/except.
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse

from uk_management_bot.services.residents.exceptions import (
    ResidentConflict,
    ResidentNotFound,
    ResidentValidationError,
)


async def _resident_not_found_handler(request: Request, exc: ResidentNotFound) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


async def _resident_conflict_handler(request: Request, exc: ResidentConflict) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


async def _resident_validation_handler(request: Request, exc: ResidentValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": str(exc)}
    )


def register_resident_exception_handlers(app) -> None:
    """Привязать обработчики доменных исключений «Жителей» к приложению."""
    app.add_exception_handler(ResidentNotFound, _resident_not_found_handler)
    app.add_exception_handler(ResidentConflict, _resident_conflict_handler)
    app.add_exception_handler(ResidentValidationError, _resident_validation_handler)
