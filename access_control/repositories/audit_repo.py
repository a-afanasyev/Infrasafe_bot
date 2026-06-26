"""Доступ к ``access_audit_logs`` (append-only audit, §9.7/§6.3).

Append-запись действия оператора/системы с hash-chain. Транзакция/lock — в сервисе.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from access_control.domain.audit import AccessAuditLog
from access_control.services.hashchain import next_hash


def insert(
    db: Session,
    *,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    barrier_id: int | None,
    source: str,
    reason: str | None,
    ip_address: str | None = None,
    extra_details: dict | None = None,
) -> None:
    """Append-строка access_audit_logs с hash-chain (§9.7, §6.3).

    ``ip_address`` (§6.3) фиксирует источник запроса оператора. ``extra_details``
    дополняет ``details`` (например ``triggered_by_user_id`` для system-действий,
    где ``actor_user_id`` = None). IP включён в hash-payload — tamper-evident.
    """
    details = {"barrier_id": barrier_id, "source": source, "reason": reason}
    if extra_details:
        details.update(extra_details)
    payload = {
        "actor_user_id": actor_user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "details": details,
        "ip_address": ip_address,
    }
    prev_hash, row_hash = next_hash(db, "access_audit_logs", payload)
    db.add(
        AccessAuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details,
            ip_address=ip_address,
            prev_hash=prev_hash,
            row_hash=row_hash,
        )
    )
