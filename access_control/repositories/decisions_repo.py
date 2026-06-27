"""Доступ к ``access_decisions`` (append-only, §9.5/§9.7).

Чтение текущего/начального решения и активных pending; запись начальной строки и
строк-переходов lifecycle с hash-chain. Append-only: переходы — НОВЫЕ строки, не
UPDATE (триггер §9.7 запрещает UPDATE/DELETE). Транзакция/lock — в сервисе.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.domain.events import AccessDecision
from access_control.services.hashchain import next_hash


def get(db: Session, decision_id: int) -> AccessDecision | None:
    """Строка решения по id (или ``None``)."""
    return db.get(AccessDecision, decision_id)


def initial_for_event(db: Session, camera_event_id: int) -> AccessDecision | None:
    """Начальное (не замещающее) решение события: ``supersedes_decision_id IS NULL``."""
    return (
        db.query(AccessDecision)
        .filter(
            AccessDecision.camera_event_id == camera_event_id,
            AccessDecision.supersedes_decision_id.is_(None),
        )
        .first()
    )


def latest_for_event(db: Session, camera_event_id: int) -> AccessDecision | None:
    """Текущая (не замещённая) строка группы решений события.

    Транзишн всегда имеет больший id, чем замещаемая строка, поэтому ``max(id)``
    группы события = «текущее» решение.
    """
    return (
        db.query(AccessDecision)
        .filter(AccessDecision.camera_event_id == camera_event_id)
        .order_by(AccessDecision.id.desc())
        .first()
    )


def active_pending_event_for_barrier(
    db: Session, *, barrier_id: int, now: dt.datetime
) -> int | None:
    """camera_event_id активного (несовершённого, несгоревшего) pending по barrier."""
    return db.execute(
        text(
            "SELECT ad.camera_event_id "
            "FROM access_decisions ad "
            "JOIN camera_events ce ON ce.id = ad.camera_event_id "
            "JOIN access_barriers b ON b.gate_id = ce.gate_id "
            "WHERE b.id = :barrier "
            "  AND ad.status = 'pending_review' "
            "  AND ad.id = (SELECT max(id) FROM access_decisions "
            "               WHERE camera_event_id = ad.camera_event_id) "
            "  AND (ad.review_deadline_at IS NULL OR ad.review_deadline_at >= :now) "
            "ORDER BY ad.id DESC LIMIT 1"
        ),
        {"barrier": barrier_id, "now": now},
    ).scalar()


def expired_pending_ids_for_barrier(
    db: Session, *, barrier_id: int, now: dt.datetime
) -> list[int]:
    """id текущих pending этого barrier с истёкшим review_deadline (§9.5)."""
    rows = db.execute(
        text(
            "SELECT ad.id FROM access_decisions ad "
            "JOIN camera_events ce ON ce.id = ad.camera_event_id "
            "JOIN access_barriers b ON b.gate_id = ce.gate_id "
            "WHERE b.id = :barrier "
            "  AND ad.status = 'pending_review' "
            "  AND ad.review_deadline_at IS NOT NULL "
            "  AND ad.review_deadline_at < :now "
            "  AND ad.id = (SELECT max(id) FROM access_decisions "
            "               WHERE camera_event_id = ad.camera_event_id)"
        ),
        {"barrier": barrier_id, "now": now},
    ).fetchall()
    return [did for (did,) in rows]


def insert_initial(
    db: Session,
    *,
    camera_event_id: int,
    decision: str,
    status: str,
    reason: str | None,
    matched_vehicle_id: int | None,
    matched_pass_id: int | None,
    review_deadline_at: dt.datetime | None,
    source: str,
) -> AccessDecision:
    """Записать начальную строку решения (append-only) с hash-chain (§9.5, §9.7)."""
    group_id = uuid.uuid4()
    payload = {
        "camera_event_id": camera_event_id,
        "decision_group_id": str(group_id),
        "decision": decision,
        "status": status,
        "reason": reason,
        "matched_vehicle_id": matched_vehicle_id,
        "matched_pass_id": matched_pass_id,
        "source": source,
    }
    prev_hash, row_hash = next_hash(db, "access_decisions", payload)
    row = AccessDecision(
        camera_event_id=camera_event_id,
        decision_group_id=group_id,
        decision=decision,
        status=status,
        reason=reason,
        matched_vehicle_id=matched_vehicle_id,
        matched_pass_id=matched_pass_id,
        review_deadline_at=review_deadline_at,
        source=source,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )
    db.add(row)
    db.flush()
    return row


def insert_transition(
    db: Session,
    *,
    current: AccessDecision,
    new_status: str,
    new_decision: str,
    operator_user_id: int | None,
    now: dt.datetime,
) -> AccessDecision:
    """Append-строка перехода lifecycle: supersedes текущую, hash-chain (§9.5, §9.7).

    ``source`` решения наследуется от исходного события (connected|edge_offline,
    §8.4) — это происхождение события, а не актор. Оператор/worker фиксируются в
    ``resolved_by_user_id`` и в access_audit_logs (audit source).
    """
    payload = {
        "camera_event_id": current.camera_event_id,
        "decision_group_id": str(current.decision_group_id),
        "supersedes_decision_id": current.id,
        "decision": new_decision,
        "status": new_status,
        "reason": current.reason,
        "source": current.source,
    }
    prev_hash, row_hash = next_hash(db, "access_decisions", payload)
    row = AccessDecision(
        camera_event_id=current.camera_event_id,
        decision_group_id=current.decision_group_id,
        supersedes_decision_id=current.id,
        decision=new_decision,
        status=new_status,
        reason=current.reason,
        matched_vehicle_id=current.matched_vehicle_id,
        matched_pass_id=current.matched_pass_id,
        review_deadline_at=None,
        resolved_by_user_id=operator_user_id,
        resolved_at=now,
        source=current.source,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )
    db.add(row)
    db.flush()
    return row
