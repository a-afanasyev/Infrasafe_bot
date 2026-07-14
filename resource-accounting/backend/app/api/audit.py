"""Audit journal listing (read-only; append happens inside domain endpoints)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.db import get_db
from app.models import AuditLog, User

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=dict)
def list_audit(
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    stmt = select(AuditLog).where(AuditLog.tenant_id == user.tenant_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page))
        .scalars()
        .all()
    )
    return {
        "data": [
            {
                "id": str(r.id),
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "action": r.action,
                "before": r.before,
                "after": r.after,
                "actor_name": r.actor_name,
                "correlation_id": r.correlation_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "meta": {"total": total, "page": page, "per_page": per_page},
    }
