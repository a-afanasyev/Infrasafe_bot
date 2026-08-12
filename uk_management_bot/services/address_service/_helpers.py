"""Внутренние хелперы пакета address_service.

AUD5-ARCH-3 волна 6: block-move из services/address_service.py —
тела `_async_session` и `_Unset`/`_UNSET` перенесены байт-в-байт.
"""
from uk_management_bot.database.session import AsyncSessionLocal


def _async_session():
    """Open a fresh AsyncSession for delegating to the address core.

    The bot runs on PostgreSQL; AsyncSessionLocal is None only in SQLite dev
    mode, where the async address core is not supported.
    """
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "AsyncSessionLocal недоступна — адресный CRUD требует PostgreSQL"
        )
    return AsyncSessionLocal()


# BUG-097: typed sentinel so update_building can tell "GPS arg omitted"
# (leave as-is) from "GPS passed as None" (reset the coordinate to NULL).
# A dedicated type (not a bare object()) keeps the parameter annotations honest.
class _Unset:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


_UNSET = _Unset()
