"""Map address-core domain exceptions to HTTP responses.

Registered on the FastAPI app in api/main.py. Lets the address router call
services/addresses/core.py directly and let domain exceptions propagate —
no per-endpoint try/except.
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse

from uk_management_bot.services.addresses.exceptions import (
    AddressNotFound, AddressConflict, AddressValidationError,
)


async def _address_not_found_handler(request: Request, exc: AddressNotFound) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


async def _address_conflict_handler(request: Request, exc: AddressConflict) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


async def _address_validation_handler(request: Request, exc: AddressValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)}
    )


def register_address_exception_handlers(app) -> None:
    """Attach the address domain-exception handlers to a FastAPI app."""
    app.add_exception_handler(AddressNotFound, _address_not_found_handler)
    app.add_exception_handler(AddressConflict, _address_conflict_handler)
    app.add_exception_handler(AddressValidationError, _address_validation_handler)
