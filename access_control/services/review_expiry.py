"""Review-expiry worker (§9.5): просроченный pending → expired, append-only.

Worker гоняется не реже раза в 10 c (§9.5). ``expire_due_reviews`` (один tick)
находит ТЕКУЩИЕ pending с истёкшим ``review_deadline_at`` и атомарно, под
per-barrier advisory lock, добавляет append-строку status=expired (без команды).
Идемпотентно: повторный tick не создаёт второй переход (после первого решение
уже не pending). Resolve/read-пути дополнительно делают lazy expiry, чтобы
остановка worker не позволила обработать просроченное.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.domain.enums import DecisionStatus, DecisionType
from access_control.domain.events import AccessDecision
from access_control.services.hashchain import next_hash
from access_control.services.lifecycle import _write_audit
from access_control.services.locks import advisory_xact_lock


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _write_expired_transition(
    db: Session, current: AccessDecision, now: dt.datetime
) -> AccessDecision:
    """Append-строка expired (supersedes current) с hash-chain (§9.5, §9.7)."""
    payload = {
        "camera_event_id": current.camera_event_id,
        "decision_group_id": str(current.decision_group_id),
        "supersedes_decision_id": current.id,
        "decision": DecisionType.MANUAL_REVIEW.value,
        "status": DecisionStatus.EXPIRED.value,
        "reason": current.reason,
        "source": current.source,
    }
    prev_hash, row_hash = next_hash(db, "access_decisions", payload)
    row = AccessDecision(
        camera_event_id=current.camera_event_id,
        decision_group_id=current.decision_group_id,
        supersedes_decision_id=current.id,
        decision=DecisionType.MANUAL_REVIEW.value,
        status=DecisionStatus.EXPIRED.value,
        reason=current.reason,
        matched_vehicle_id=current.matched_vehicle_id,
        matched_pass_id=current.matched_pass_id,
        review_deadline_at=None,
        resolved_at=now,
        source=current.source,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )
    db.add(row)
    db.flush()
    return row


def expire_due_reviews(db: Session, *, now: dt.datetime | None = None) -> int:
    """Один tick worker: перевести просроченные current pending в expired.

    Возвращает число переведённых решений. Каждый перевод — под per-barrier
    advisory lock с повторной проверкой (current + всё ещё pending), атомарно.
    """
    now = now or _utcnow()
    # H1/L3: канонический lock-ключ событием (активный barrier → gate → controller).
    # ``LEFT JOIN`` на активный barrier: если barrier деактивирован после приёма,
    # просроченный pending всё равно найдётся и истечёт (ключ падает на gate_id) —
    # pending не «вечный» (M4). ``barrier_id`` (активный, может быть NULL) идёт в
    # audit отдельно.
    due = db.execute(
        text(
            "SELECT ad.id, b.id AS barrier_id, "
            "       COALESCE(b.id, ce.gate_id, ce.controller_id) AS lock_key "
            "FROM access_decisions ad "
            "JOIN camera_events ce ON ce.id = ad.camera_event_id "
            "LEFT JOIN access_barriers b "
            "  ON b.gate_id = ce.gate_id AND b.is_active = true "
            "WHERE ad.status = 'pending_review' "
            "  AND ad.review_deadline_at IS NOT NULL "
            "  AND ad.review_deadline_at < :now "
            "  AND ad.id = (SELECT max(id) FROM access_decisions "
            "               WHERE camera_event_id = ad.camera_event_id) "
            "ORDER BY ad.id"
        ),
        {"now": now},
    ).fetchall()

    expired_count = 0
    for decision_id, barrier_id, lock_key in due:
        advisory_xact_lock(db, lock_key)
        # Повторная проверка под lock: решение всё ещё current и pending.
        current = _current_decision_if_pending(db, decision_id)
        if current is None:
            db.commit()
            continue
        expired = _write_expired_transition(db, current, now)
        # L5: каждый переход в expired — append-строка audit (actor system).
        _write_audit(
            db,
            actor_user_id=None,
            action="access.review_expired",
            entity_type="access_decision",
            entity_id=expired.id,
            barrier_id=barrier_id,
            source="review_expiry_worker",
            reason=None,
        )
        db.commit()
        expired_count += 1
    return expired_count


def _current_decision_if_pending(
    db: Session, decision_id: int
) -> AccessDecision | None:
    """Вернуть решение, если оно ещё pending_review и НЕ замещено (под lock)."""
    current = db.get(AccessDecision, decision_id)
    if current is None or current.status != DecisionStatus.PENDING_REVIEW.value:
        return None
    superseded = db.execute(
        text(
            "SELECT 1 FROM access_decisions "
            "WHERE supersedes_decision_id = :id LIMIT 1"
        ),
        {"id": decision_id},
    ).scalar()
    return None if superseded is not None else current
