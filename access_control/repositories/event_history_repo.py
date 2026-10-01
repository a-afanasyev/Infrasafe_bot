"""Read-модель истории проездов для реестра (§6.2, §13.2): события + цепочка решения.

Только чтение: список камера-событий с текущим решением группы, деталь события
(решения, команды, ручные открытия, ответы жителя), ссылка на кадр и последние
события по номеру. Строки возвращаются как ``dict`` — DTO собирает API-слой.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from access_control.repositories.sql_filters import plate_contains_pattern, where_clause

# Текущее решение группы = строка с max(id) (транзишн всегда имеет больший id).
_EVENTS_FROM = """
FROM camera_events ce
LEFT JOIN LATERAL (
    SELECT id, decision, status, reason, resolved_by_user_id
    FROM access_decisions ad WHERE ad.camera_event_id = ce.id
    ORDER BY ad.id DESC LIMIT 1
) d ON true
LEFT JOIN LATERAL (
    SELECT occurred_at FROM access_events ae WHERE ae.camera_event_id = ce.id
    ORDER BY ae.id DESC LIMIT 1
) ae ON true
"""

# Заглушки для пустого ``IN :expanding`` (id/UUID, которых заведомо нет).
_NO_ID = -1
_NO_UUID = "00000000-0000-0000-0000-000000000000"


def _event_filters(
    *,
    decision: str | None,
    zone_id: int | None,
    gate_id: int | None,
    plate: str | None,
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    source: str | None,
) -> tuple[list[str], dict]:
    candidates = (
        ("d.decision = :decision", "decision", decision),
        ("ce.zone_id = :zone_id", "zone_id", zone_id),
        ("ce.gate_id = :gate_id", "gate_id", gate_id),
        (
            "ce.plate_number_normalized ILIKE :plate",
            "plate",
            plate_contains_pattern(plate) if plate else None,
        ),
        ("ce.captured_at >= :date_from", "date_from", date_from),
        ("ce.captured_at <= :date_to", "date_to", date_to),
        ("ce.source = :source", "source", source),
    )
    active = [(cond, key, val) for cond, key, val in candidates if val is not None]
    return [c for c, _, _ in active], {k: v for _, k, v in active}


def page_events(
    db: Session,
    *,
    decision: str | None = None,
    zone_id: int | None = None,
    gate_id: int | None = None,
    plate: str | None = None,
    date_from: dt.datetime | None = None,
    date_to: dt.datetime | None = None,
    source: str | None = None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict]]:
    """(total, страница) камера-событий + occurred_at + текущее решение группы.

    Сортировка по ``captured_at`` desc, затем ``id`` desc.
    """
    conds, params = _event_filters(
        decision=decision, zone_id=zone_id, gate_id=gate_id, plate=plate,
        date_from=date_from, date_to=date_to, source=source,
    )
    where = where_clause(conds)
    total = db.execute(
        text(f"SELECT count(*) {_EVENTS_FROM} {where}"), params
    ).scalar_one()
    rows = db.execute(
        text(
            "SELECT ce.id, ce.event_id, ce.controller_id, ce.zone_id, ce.gate_id, "
            " ce.direction, ce.plate_number_normalized, ce.captured_at, "
            " ae.occurred_at, ce.source, ce.plate_photo_url, ce.overview_photo_url, "
            " d.decision, d.status, d.reason, "
            " d.id AS decision_id, d.resolved_by_user_id, "
            " (d.id IS NOT NULL AND EXISTS(SELECT 1 FROM barrier_commands bc "
            "   WHERE bc.decision_id = d.id)) AS has_command "
            f"{_EVENTS_FROM} {where} "
            "ORDER BY ce.captured_at DESC, ce.id DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).mappings()
    return total, [dict(r) for r in rows]


def get_camera_event(db: Session, event_id: int) -> dict | None:
    """Камера-событие по ``camera_events.id`` (с ``attributes``) либо ``None``."""
    row = db.execute(
        text(
            "SELECT id, event_id, controller_id, zone_id, gate_id, camera_id, "
            " direction, plate_number_original, plate_number_normalized, confidence, "
            " captured_at, received_at, source, plate_photo_url, overview_photo_url, "
            " attributes FROM camera_events WHERE id = :id"
        ),
        {"id": event_id},
    ).mappings().first()
    return dict(row) if row is not None else None


def decisions_for_event(db: Session, event_id: int) -> list[dict]:
    """Вся цепочка решений события (по возрастанию id)."""
    rows = db.execute(
        text(
            "SELECT id, decision, status, reason, decision_group_id, "
            " supersedes_decision_id, resolved_by_user_id, resolved_at, "
            " review_deadline_at, created_at, prev_hash, row_hash "
            "FROM access_decisions WHERE camera_event_id = :id ORDER BY id"
        ),
        {"id": event_id},
    ).mappings()
    return [dict(r) for r in rows]


def manual_openings_for_event(
    db: Session, event_id: int, decision_ids: list[int]
) -> list[dict]:
    """Ручные открытия по событию ИЛИ по любому из его решений (по id)."""
    rows = db.execute(
        text(
            "SELECT id, barrier_id, command_id, decision_id, operator_user_id, "
            " reason, created_at FROM manual_openings "
            "WHERE captured_event_id = :id OR decision_id IN :dids ORDER BY id"
        ).bindparams(bindparam("dids", expanding=True)),
        {"id": event_id, "dids": decision_ids or [_NO_ID]},
    ).mappings()
    return [dict(r) for r in rows]


def commands_for_event(
    db: Session, decision_ids: list[int], command_ids: list[str]
) -> list[dict]:
    """Команды шлагбауму по решениям события ИЛИ по id команд ручных открытий."""
    rows = db.execute(
        text(
            "SELECT command_id, decision_id, barrier_id, controller_id, "
            " command_type, status, attempts, created_at, leased_at, acked_at, "
            " dead_at FROM barrier_commands "
            "WHERE decision_id IN :dids OR command_id IN :cmds ORDER BY created_at"
        ).bindparams(
            bindparam("dids", expanding=True), bindparam("cmds", expanding=True)
        ),
        {"dids": decision_ids or [_NO_ID], "cmds": command_ids or [_NO_UUID]},
    ).mappings()
    return [dict(r) for r in rows]


def confirmations_for_decisions(db: Session, decision_ids: list[int]) -> list[dict]:
    """Совещательные ответы жителя (§9.4) по решениям события."""
    rows = db.execute(
        text(
            "SELECT user_id, response, created_at "
            "FROM access_entry_confirmations "
            "WHERE decision_id IN :dids ORDER BY created_at, id"
        ).bindparams(bindparam("dids", expanding=True)),
        {"dids": decision_ids or [_NO_ID]},
    ).mappings()
    return [dict(r) for r in rows]


def photo_ref(db: Session, event_id: int, kind: str) -> str | None:
    """Сохранённая ссылка на кадр события: ``kind='plate'`` → номерной, иначе обзорный."""
    row = db.execute(
        text(
            "SELECT plate_photo_url, overview_photo_url FROM camera_events WHERE id = :id"
        ),
        {"id": event_id},
    ).mappings().first()
    if row is None:
        return None
    return row["plate_photo_url"] if kind == "plate" else row["overview_photo_url"]


def recent_events_by_plate(db: Session, plate_normalized: str, limit: int) -> list[dict]:
    """Последние события по точному нормализованному номеру + текущее решение."""
    rows = db.execute(
        text(
            "SELECT ce.id, ce.event_id, ce.captured_at, ce.direction, ce.gate_id, "
            " ce.zone_id, d.decision, d.status "
            "FROM camera_events ce "
            "LEFT JOIN LATERAL (SELECT decision, status FROM access_decisions ad "
            "  WHERE ad.camera_event_id = ce.id ORDER BY ad.id DESC LIMIT 1) d ON true "
            "WHERE ce.plate_number_normalized = :norm "
            "ORDER BY ce.captured_at DESC, ce.id DESC LIMIT :n"
        ),
        {"norm": plate_normalized, "n": limit},
    ).mappings()
    return [dict(r) for r in rows]
