from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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


def not_found(entity: str) -> ApiError:
    return ApiError(404, "not_found", f"{entity} не найден")


def conflict(message: str, details=None) -> ApiError:
    return ApiError(409, "conflict", message, details)


def bad_request(message: str, details=None) -> ApiError:
    return ApiError(400, "bad_request", message, details)


def forbidden(message: str = "Недостаточно прав") -> ApiError:
    return ApiError(403, "forbidden", message)
