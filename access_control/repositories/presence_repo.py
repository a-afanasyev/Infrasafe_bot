"""Доступ к ``vehicle_presence_sessions`` (§8.3, §10.3): открытие/закрытие сессий.

Presence-сессия мутабельна (open→closed UPDATE) — НЕ append-only. Транзакция/lock —
в сервисе (ingestion открывает/закрывает под тем же advisory-lock, что и приём).

Идемпотентность:
* ``open_session`` — ``ON CONFLICT (vehicle_id, zone_id) WHERE status='open' DO
  NOTHING``: повторный въезд при открытой сессии не создаёт дубль (одна открытая
  сессия авто в зоне, §10.3).
* закрытие — ``UPDATE ... WHERE status='open'``: повтор выезда не трогает уже
  закрытую сессию (0 строк).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.domain.parking import VehiclePresenceSession


def open_session(
    db: Session,
    *,
    vehicle_id: int,
    apartment_id: int | None,
    zone_id: int,
    entered_at: dt.datetime,
    entry_camera_event_id: int | None,
) -> int | None:
    """Открыть presence-сессию авто в зоне (идемпотентно). Вернуть id или None.

    ``None`` — открытая сессия авто в зоне уже существует (ON CONFLICT DO NOTHING):
    повторный въезд не дублирует. Сериализуется advisory-lock'ом приёма.
    """
    return db.execute(
        text(
            "INSERT INTO vehicle_presence_sessions "
            "(vehicle_id, apartment_id, zone_id, entered_at, status, "
            " entry_camera_event_id, created_at) "
            "VALUES (:v, :a, :z, :ts, 'open', :ce, now()) "
            "ON CONFLICT (vehicle_id, zone_id) WHERE status = 'open' "
            "DO NOTHING RETURNING id"
        ),
        {
            "v": vehicle_id,
            "a": apartment_id,
            "z": zone_id,
            "ts": entered_at,
            "ce": entry_camera_event_id,
        },
    ).scalar()


def close_open_session_for_vehicle_zone(
    db: Session,
    *,
    vehicle_id: int,
    zone_id: int,
    exited_at: dt.datetime,
    exit_camera_event_id: int | None,
) -> int | None:
    """Закрыть открытую сессию авто в зоне (выезд). Вернуть id закрытой или None.

    ``None`` — открытой сессии нет (выезд без зафиксированного въезда / уже закрыта):
    идемпотентно, повтор выезда ничего не меняет.
    """
    return db.execute(
        text(
            "UPDATE vehicle_presence_sessions "
            "SET status = 'closed', exited_at = :ts, "
            "    exit_camera_event_id = :ce, close_reason = 'exit_event' "
            "WHERE vehicle_id = :v AND zone_id = :z AND status = 'open' "
            "RETURNING id"
        ),
        {"v": vehicle_id, "z": zone_id, "ts": exited_at, "ce": exit_camera_event_id},
    ).scalar()


def count_open_for_apartment_zone(
    db: Session, *, apartment_ids: list[int], zone_id: int
) -> int:
    """Число ОТКРЫТЫХ сессий квартир(ы) в зоне = текущая занятость мест (§10.3)."""
    if not apartment_ids:
        return 0
    return int(
        db.query(VehiclePresenceSession)
        .filter(
            VehiclePresenceSession.apartment_id.in_(apartment_ids),
            VehiclePresenceSession.zone_id == zone_id,
            VehiclePresenceSession.status == "open",
        )
        .count()
    )


def get_session(db: Session, session_id: int) -> VehiclePresenceSession | None:
    """Сессия по id (или ``None``)."""
    return db.get(VehiclePresenceSession, session_id)


def list_open_sessions(
    db: Session,
    *,
    zone_id: int | None = None,
    apartment_id: int | None = None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """ОТКРЫТЫЕ presence-сессии (для admin-UI выбора сессии под закрытие, §10.3).

    Возвращает ``(items, total)``; каждый item — ``{id, vehicle_id,
    plate_normalized, apartment_id, zone_id, entered_at}`` (номер из ``vehicles``
    для подсказки оператору). Фильтры ``zone_id``/``apartment_id`` опциональны.
    """
    where = "WHERE s.status = 'open'"
    params: dict = {}
    if zone_id is not None:
        where += " AND s.zone_id = :z"
        params["z"] = zone_id
    if apartment_id is not None:
        where += " AND s.apartment_id = :a"
        params["a"] = apartment_id
    base = "FROM vehicle_presence_sessions s LEFT JOIN vehicles v ON v.id = s.vehicle_id "
    total = int(db.execute(text("SELECT count(*) " + base + where), params).scalar() or 0)
    rows = db.execute(
        text(
            "SELECT s.id, s.vehicle_id, v.plate_number_normalized AS plate_normalized, "
            "s.apartment_id, s.zone_id, s.entered_at "
            + base
            + where
            + " ORDER BY s.entered_at DESC, s.id DESC LIMIT :lim OFFSET :off"
        ),
        {**params, "lim": limit, "off": offset},
    ).mappings().all()
    return [dict(r) for r in rows], total


def close_session_manual(
    db: Session,
    *,
    session_id: int,
    closed_by_user_id: int,
    close_reason: str,
    exited_at: dt.datetime,
) -> int | None:
    """Ручное закрытие открытой сессии оператором. Вернуть id или None.

    ``None`` — сессия уже закрыта (идемпотентность: повтор → сохранённый результат).
    """
    return db.execute(
        text(
            "UPDATE vehicle_presence_sessions "
            "SET status = 'closed', exited_at = :ts, "
            "    closed_by_user_id = :u, close_reason = :r "
            "WHERE id = :id AND status = 'open' "
            "RETURNING id"
        ),
        {"id": session_id, "ts": exited_at, "u": closed_by_user_id, "r": close_reason},
    ).scalar()
