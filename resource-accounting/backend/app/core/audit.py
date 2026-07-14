from sqlalchemy.orm import Session

from app.models import AuditLog, User


def write_audit(
    db: Session,
    *,
    user: User | None,
    entity_type: str,
    entity_id,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
    correlation_id: str | None = None,
) -> None:
    """Append an audit record within the caller's transaction (committed together)."""
    db.add(
        AuditLog(
            tenant_id=user.tenant_id if user else None,
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            before=before,
            after=after,
            actor_id=user.id if user else None,
            actor_name=user.display_name if user else None,
            correlation_id=correlation_id,
        )
    )
