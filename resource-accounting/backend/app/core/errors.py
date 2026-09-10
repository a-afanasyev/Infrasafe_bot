import logging

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

logger = logging.getLogger("resource_api")

# AUD7-COR-03 (сек-ревью H-1/M-3): PG-ошибки ожидания блокировки — не 500.
_PG_LOCK_NOT_AVAILABLE = "55P03"
_PG_DEADLOCK_DETECTED = "40P01"
_PG_QUERY_CANCELED = "57014"


class ApiError(Exception):
    """Domain error rendered as {"error": {code, message, details}} (ТЗ §7)."""

    def __init__(self, status_code: int, code: str, message: str, details: dict | list | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(status_code: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": jsonable_encoder(details)}},
    )


def register_error_handlers(app) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return error_response(422, "validation_error", "Некорректные данные запроса", exc.errors())

    @app.exception_handler(OperationalError)
    async def handle_db_operational_error(request: Request, exc: OperationalError):
        """lock_timeout/deadlock → 409 period_busy, statement_timeout → 503; остальное — 500 как прежде.
        В лог — только pgcode и путь (без SQL и параметров)."""
        pgcode = getattr(exc.orig, "pgcode", None)
        if pgcode in (_PG_LOCK_NOT_AVAILABLE, _PG_DEADLOCK_DETECTED):
            logger.warning("db lock wait failed pgcode=%s path=%s", pgcode, request.url.path)
            return error_response(409, "period_busy", "Период занят другой операцией, повторите попытку")
        if pgcode == _PG_QUERY_CANCELED:
            logger.warning("db statement canceled pgcode=%s path=%s", pgcode, request.url.path)
            return error_response(503, "db_timeout", "Операция с базой данных прервана по таймауту")
        raise exc


def not_found(entity: str) -> ApiError:
    return ApiError(404, "not_found", f"{entity} не найден")


def conflict(message: str, details=None) -> ApiError:
    return ApiError(409, "conflict", message, details)


def bad_request(message: str, details=None) -> ApiError:
    return ApiError(400, "bad_request", message, details)


def forbidden(message: str = "Недостаточно прав") -> ApiError:
    return ApiError(403, "forbidden", message)
