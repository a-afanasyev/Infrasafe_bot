"""Domain exceptions for address CRUD core.

Raised by services/addresses/core.py. Carry Russian-language messages
(consistency with the legacy sync AddressService). The bot adapter returns
str(exc); the API maps them to HTTPException via api/addresses/exception_handlers.py.
"""


class AddressError(Exception):
    """Base class for address domain errors.

    FE-094: optional `code` — a stable, language-agnostic slug the bot adapter
    surfaces instead of the Russian message, so the handler can localize via
    `get_text("address_errors.<code>", lang)`. Raises WITHOUT a code (e.g.
    interpolated messages «...есть N зданий») fall back to their Russian
    `str(exc)` text.
    """

    def __init__(self, message: str = "", code: str | None = None):
        super().__init__(message)
        self.code = code


class AddressNotFound(AddressError):
    """A referenced entity (yard / building / apartment / request) does not exist."""


class AddressConflict(AddressError):
    """Operation violates an invariant (duplicate name, active children block, etc.)."""


class AddressValidationError(AddressError):
    """Input is malformed (empty apartment number, value out of range, etc.)."""
