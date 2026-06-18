"""Shared serialization / role helpers for the addresses API entity routers.

Pure mapping helpers (ORM column extraction + role checks) — NO data-access.
Extracted from the former monolithic router.py so each entity module can map
ORM rows to response schemas without duplicating the column-extraction logic.
"""
from uk_management_bot.api.dependencies import _parse_user_roles
from uk_management_bot.database.models.user import User


def is_manager(user: User) -> bool:
    """Менеджер сохраняет доступ к неактивным дворам/домам; обходчик — нет."""
    return "manager" in _parse_user_roles(user)


def yard_dict(y) -> dict:
    """Extract column values from Yard ORM object (avoids triggering lazy-loaded @property)."""
    return {c.key: getattr(y, c.key) for c in y.__table__.columns}


def building_dict(b) -> dict:
    """Extract column values from Building ORM object."""
    return {c.key: getattr(b, c.key) for c in b.__table__.columns}


def apartment_dict(a) -> dict:
    """Extract column values from Apartment ORM object."""
    return {c.key: getattr(a, c.key) for c in a.__table__.columns}
