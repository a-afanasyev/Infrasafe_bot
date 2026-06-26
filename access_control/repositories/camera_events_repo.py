"""Доступ к ``camera_events``: идемпотентная вставка и поиск дублей (§10.1).

Хранит SQL приёма ANPR-события. Транзакция/lock — на стороне сервиса.
"""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from access_control.domain.events import CameraEvent

if TYPE_CHECKING:  # избегаем циклического импорта с services.ingestion
    from access_control.services.ingestion import AnprIngestInput


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def find_event_id(db: Session, *, controller_id: int, event_id: str) -> int | None:
    """id ранее принятого события по ключу идемпотентности ``(controller_id, event_id)``."""
    return db.execute(
        text(
            "SELECT id FROM camera_events "
            "WHERE controller_id = :c AND event_id = :e"
        ),
        {"c": controller_id, "e": event_id},
    ).scalar()


def find_window_duplicate(
    db: Session,
    data: "AnprIngestInput",
    normalized: str | None,
    window_seconds: int,
) -> int | None:
    """Найти camera_event-кандидат на дубль в окне (§10.1), исключая текущий ключ.

    Возвращает id найденного раннего события с начальным решением либо ``None``.
    """
    if normalized is None or data.gate_id is None:
        return None
    lo = data.captured_at - dt.timedelta(seconds=window_seconds)
    hi = data.captured_at + dt.timedelta(seconds=window_seconds)
    row = db.execute(
        text(
            """
            SELECT ce.id
            FROM camera_events ce
            JOIN access_decisions ad
              ON ad.camera_event_id = ce.id AND ad.supersedes_decision_id IS NULL
            WHERE ce.gate_id = :gate
              AND ce.direction = :direction
              AND ce.plate_number_normalized = :normalized
              AND ce.captured_at BETWEEN :lo AND :hi
              AND NOT (ce.controller_id = :cid AND ce.event_id = :eid)
            ORDER BY ce.captured_at ASC
            LIMIT 1
            """
        ),
        {
            "gate": data.gate_id,
            "direction": data.direction,
            "normalized": normalized,
            "lo": lo,
            "hi": hi,
            "cid": data.controller_id,
            "eid": data.event_id,
        },
    ).first()
    return row[0] if row else None


def insert_idempotent(
    db: Session, data: "AnprIngestInput", normalized: str | None
) -> int | None:
    """Идемпотентная вставка camera_events (ON CONFLICT DO NOTHING).

    ``normalized`` пробрасывается как ``str | None``: для no-plate колонка
    ``plate_number_normalized`` остаётся NULL (согласовано с access_events) —
    окно дедупа по NULL не срабатывает, но запись не падает (§10.1).

    Возвращает id новой строки либо ``None`` при конфликте (§10.1).
    """
    stmt = (
        pg_insert(CameraEvent.__table__)
        .values(
            controller_id=data.controller_id,
            event_id=data.event_id,
            gate_id=data.gate_id,
            camera_id=data.camera_id,
            zone_id=data.zone_id,
            plate_number_original=data.plate_number_original,
            plate_number_normalized=normalized,
            direction=data.direction,
            confidence=data.confidence,
            captured_at=data.captured_at,
            received_at=_utcnow(),
            plate_photo_url=data.plate_photo_url,
            overview_photo_url=data.overview_photo_url,
            attributes=data.attributes,
            source=data.source,
        )
        .on_conflict_do_nothing(constraint="uq_camera_events_controller_event")
        .returning(CameraEvent.__table__.c.id)
    )
    return db.execute(stmt).scalar()
