"""Address CRUD core package — unified async implementation shared by the
Telegram bot adapter and the FastAPI router. See core.py for the contract.
"""
from uk_management_bot.services.addresses import core
from uk_management_bot.services.addresses.exceptions import (
    AddressError, AddressNotFound, AddressConflict, AddressValidationError,
)

__all__ = [
    "core",
    "AddressError",
    "AddressNotFound",
    "AddressConflict",
    "AddressValidationError",
]
