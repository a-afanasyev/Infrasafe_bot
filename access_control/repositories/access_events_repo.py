"""Доступ к ``access_events`` (иммутабельный журнал проезда, §9.7) и связке авто↔квартира.

Запись журнала проезда с hash-chain и связностью идентификаторов (§15.10).
Транзакция/lock — в сервисе.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.domain.events import AccessDecision, AccessEvent
from access_control.services.hashchain import next_hash

if TYPE_CHECKING:  # избегаем циклического импорта с services.ingestion
    from access_control.services.ingestion import AnprIngestInput


def apartment_for_vehicle(db: Session, vehicle_id: int) -> int | None:
    """id активной квартиры, привязанной к авто (минимальный id), либо ``None``."""
    return db.execute(
        text(
            "SELECT apartment_id FROM vehicle_apartments "
            "WHERE vehicle_id = :v AND status = 'active' "
            "ORDER BY id ASC LIMIT 1"
        ),
        {"v": vehicle_id},
    ).scalar()


def insert_access_event(
    db: Session,
    *,
    data: "AnprIngestInput",
    camera_event_id: int,
    decision: AccessDecision,
    normalized: str | None,
) -> None:
    """Записать иммутабельный журнал проезда (§9.7) с hash-chain и связностью (§15.10)."""
    apartment_id = None
    if decision.matched_vehicle_id is not None:
        apartment_id = apartment_for_vehicle(db, decision.matched_vehicle_id)
    payload = {
        "controller_id": data.controller_id,
        "event_id": data.event_id,
        "camera_event_id": camera_event_id,
        "decision_id": decision.id,
        "vehicle_id": decision.matched_vehicle_id,
        "pass_id": decision.matched_pass_id,
        "apartment_id": apartment_id,
        "gate_id": data.gate_id,
        "zone_id": data.zone_id,
        "direction": data.direction,
        "plate_number_normalized": normalized,
        "decision": decision.decision,
        "reason": decision.reason,
        "source": data.source,
    }
    prev_hash, row_hash = next_hash(db, "access_events", payload)
    db.add(
        AccessEvent(
            controller_id=data.controller_id,
            event_id=data.event_id,
            camera_event_id=camera_event_id,
            decision_id=decision.id,
            vehicle_id=decision.matched_vehicle_id,
            pass_id=decision.matched_pass_id,
            apartment_id=apartment_id,
            gate_id=data.gate_id,
            zone_id=data.zone_id,
            direction=data.direction,
            plate_number_normalized=normalized,
            decision=decision.decision,
            reason=decision.reason,
            occurred_at=data.captured_at,
            source=data.source,
            prev_hash=prev_hash,
            row_hash=row_hash,
        )
    )
