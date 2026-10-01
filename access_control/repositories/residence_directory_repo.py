"""Справочные чтения для обогащения карточек реестра (§6.2): жители, адреса, зоны.

Пакетные запросы по набору id (без N+1) к родительским таблицам UK
(``users``/``apartments``/``buildings``/``yards``/``user_apartments``) и к
``parking_zones``/``parking_zone_yards``. Только чтение; строки — ``dict``.
"""
from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


def users_by_ids(db: Session, user_ids: list[int]) -> list[dict]:
    """Пользователи (id, first_name, last_name, username, phone, telegram_id) по id."""
    if not user_ids:
        return []
    rows = db.execute(
        text(
            "SELECT id, first_name, last_name, username, phone, telegram_id "
            "FROM users WHERE id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": user_ids},
    ).mappings()
    return [dict(r) for r in rows]


def addresses_by_apartment_ids(db: Session, apartment_ids: list[int]) -> list[dict]:
    """Адреса квартир (apartment→building→yard); номер/подъезд/этаж — текстом."""
    if not apartment_ids:
        return []
    rows = db.execute(
        text(
            "SELECT a.id AS apartment_id, a.apartment_number::text AS apartment_number, "
            " a.entrance::text AS entrance, a.floor::text AS floor, "
            " b.id AS building_id, b.address AS building_address, "
            " y.id AS yard_id, y.name AS yard_name "
            "FROM apartments a "
            "LEFT JOIN buildings b ON b.id = a.building_id "
            "LEFT JOIN yards y ON y.id = b.yard_id "
            "WHERE a.id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": apartment_ids},
    ).mappings()
    return [dict(r) for r in rows]


def serving_zones_by_apartment_ids(db: Session, apartment_ids: list[int]) -> list[dict]:
    """Пары (apartment_id, zone_id, code, name): yard квартиры ∈ ``parking_zone_yards``."""
    if not apartment_ids:
        return []
    rows = db.execute(
        text(
            "SELECT a.id AS apartment_id, z.id AS zone_id, z.code, z.name "
            "FROM apartments a "
            "JOIN buildings b ON b.id = a.building_id "
            "JOIN parking_zone_yards pzy ON pzy.yard_id = b.yard_id "
            "JOIN parking_zones z ON z.id = pzy.zone_id "
            "WHERE a.id IN :ids ORDER BY z.id"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": apartment_ids},
    ).mappings()
    return [dict(r) for r in rows]


def approved_residents_by_apartment_ids(
    db: Session, apartment_ids: list[int]
) -> list[dict]:
    """Жители квартир со связью ``user_apartments.status='approved'`` (по user id)."""
    if not apartment_ids:
        return []
    rows = db.execute(
        text(
            "SELECT ua.apartment_id, u.id, u.first_name, u.last_name, u.username, "
            " u.phone, u.telegram_id "
            "FROM user_apartments ua JOIN users u ON u.id = ua.user_id "
            "WHERE ua.apartment_id IN :ids AND ua.status = 'approved' ORDER BY u.id"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": apartment_ids},
    ).mappings()
    return [dict(r) for r in rows]


def get_zone(db: Session, zone_id: int) -> dict | None:
    """Зона парковки (id, code, name) по id либо ``None``."""
    row = db.execute(
        text("SELECT id, code, name FROM parking_zones WHERE id = :id"),
        {"id": zone_id},
    ).mappings().first()
    return dict(row) if row is not None else None
