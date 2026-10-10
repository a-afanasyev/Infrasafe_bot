"""Shared serialization / role helpers for the addresses API entity routers.

Pure mapping helpers (ORM column extraction + role checks) — NO data-access.
Extracted from the former monolithic router.py so each entity module can map
ORM rows to response schemas without duplicating the column-extraction logic.
"""
from uk_management_bot.authz import has_action_roles
from uk_management_bot.database.models.user import User


def is_manager(user: User) -> bool:
    """Видит неактивные дворы/дома тот, кто управляет справочником адресов
    (действие `addresses.manage`); обходчик — нет. Статус здесь не нужен:
    маршрут уже прошёл свой гейт."""
    return has_action_roles(user, "addresses.manage")


def yard_dict(y) -> dict:
    """Extract column values from Yard ORM object (avoids triggering lazy-loaded @property)."""
    return {c.key: getattr(y, c.key) for c in y.__table__.columns}


def building_dict(b) -> dict:
    """Extract column values from Building ORM object."""
    return {c.key: getattr(b, c.key) for c in b.__table__.columns}


def apartment_dict(a) -> dict:
    """Extract column values from Apartment ORM object."""
    return {c.key: getattr(a, c.key) for c in a.__table__.columns}
