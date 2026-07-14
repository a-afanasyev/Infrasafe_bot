"""Reconciliation acts: create, list, download (immutable), mark-sent, cancel (ТЗ §5.7)."""

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import ALL_ROLES, STAFF_ROLES, require_roles
from app.core.deps import correlation_id as _cid
from app.core.errors import bad_request, conflict, not_found
from app.core.ratelimit import HEAVY_LIMIT, limiter
from app.db import get_db
from app.models import Export, ReportingPeriod, User
from app.models.base import utcnow
from app.services.exports import build_rows, checksum_rows, render, snapshot_rows

router = APIRouter(prefix="/exports", tags=["exports"])


def _serialize(export: Export) -> dict:
    return {
        "id": str(export.id),
        "period_month": export.period.month if export.period else None,
        "provider_id": str(export.provider_id) if export.provider_id else None,
        "provider_name": export.provider.name if export.provider else None,
        "format": export.format,
        "status": export.status,
        "is_correction": export.is_correction,
        "filters": export.filters,
        "file_name": export.file_name,
        "checksum": export.checksum,
        "row_count": export.row_count,
        "created_at": export.created_at.isoformat(),
        "sent_at": export.sent_at.isoformat() if export.sent_at else None,
        "sent_channel": export.sent_channel,
        "sent_comment": export.sent_comment,
    }


class ExportCreateIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    format: str = Field(default="xlsx", pattern="^(xlsx|csv|pdf)$")
    provider_id: uuid.UUID | None = None
    resource_type: str | None = None
    object_id: uuid.UUID | None = None
    is_correction: bool = False


@router.post("", response_model=dict, status_code=201)
@limiter.limit(HEAVY_LIMIT)
def create_export(
    request: Request,
    payload: ExportCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*STAFF_ROLES)),
):
    period = db.execute(
        select(ReportingPeriod).where(
            ReportingPeriod.tenant_id == user.tenant_id, ReportingPeriod.month == payload.month
        )
    ).scalar_one_or_none()
    if not period:
        raise not_found(f"Период {payload.month}")

    filters = {
        "provider_id": str(payload.provider_id) if payload.provider_id else None,
        "resource_type": payload.resource_type,
        "object_id": str(payload.object_id) if payload.object_id else None,
    }
    rows = build_rows(db, user.tenant_id, period, filters)
    if not rows:
        raise bad_request("Нет показаний под выбранные фильтры")

    suffix = "-corr" if payload.is_correction else ""
    file_name = f"act-{payload.month}{suffix}.{payload.format}"
    export = Export(
        tenant_id=user.tenant_id,
        reporting_period_id=period.id,
        provider_id=payload.provider_id,
        format=payload.format,
        status="generated",
        is_correction=payload.is_correction,
        filters=filters,
        file_name=file_name,
        checksum=checksum_rows(rows),
        row_count=len(rows),
        created_by=user.id,
    )
    db.add(export)
    db.flush()
    snapshot_rows(db, export, rows)
    write_audit(db, user=user, entity_type="export", entity_id=export.id, action="create",
                after={"month": payload.month, "format": payload.format, "rows": len(rows)},
                correlation_id=_cid(request))
    db.commit()
    return {"data": _serialize(export)}


@router.get("", response_model=dict)
def list_exports(
    period: str | None = None,
    provider_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ALL_ROLES)),
):
    stmt = select(Export).where(Export.tenant_id == user.tenant_id)
    if period:
        stmt = stmt.join(ReportingPeriod, Export.reporting_period_id == ReportingPeriod.id).where(
            ReportingPeriod.month == period
        )
    if provider_id:
        stmt = stmt.where(Export.provider_id == provider_id)
    if status:
        stmt = stmt.where(Export.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(stmt.order_by(Export.created_at.desc()).offset((page - 1) * per_page).limit(per_page))
        .scalars()
        .all()
    )
    return {"data": [_serialize(r) for r in rows], "meta": {"total": total, "page": page, "per_page": per_page}}


def _get_export(db: Session, user: User, export_id: uuid.UUID) -> Export:
    export = db.get(Export, export_id)
    if not export or export.tenant_id != user.tenant_id:
        raise not_found("Экспорт")
    return export


@router.get("/{export_id}", response_model=dict)
def get_export(
    export_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ALL_ROLES)),
):
    export = _get_export(db, user, export_id)
    return {"data": {**_serialize(export), "rows": [r.data for r in export.rows]}}


@router.get("/{export_id}/download")
def download_export(
    export_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ALL_ROLES)),
):
    """Re-render from the immutable row snapshot: repeated downloads are identical."""
    export = _get_export(db, user, export_id)
    if export.status == "cancelled":
        raise conflict("Экспорт отменён")
    rows = [r.data for r in export.rows]
    title = f"Акт сверки {export.period.month if export.period else ''}"
    content, media_type = render(rows, export.format, title)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{export.file_name}"'},
    )


class MarkSentIn(BaseModel):
    channel: str = Field(min_length=1, max_length=100)
    comment: str | None = None


@router.post("/{export_id}/mark-sent", response_model=dict)
def mark_sent(
    export_id: uuid.UUID,
    payload: MarkSentIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*STAFF_ROLES)),
):
    export = _get_export(db, user, export_id)
    if export.status != "generated":
        raise conflict(f"Отметить отправленным можно только сформированный акт (сейчас {export.status})")
    export.status = "sent"
    export.sent_at = utcnow()
    export.sent_by = user.id
    export.sent_channel = payload.channel
    export.sent_comment = payload.comment
    write_audit(db, user=user, entity_type="export", entity_id=export.id, action="mark_sent",
                after={"channel": payload.channel}, correlation_id=_cid(request))
    db.commit()
    return {"data": _serialize(export)}


@router.post("/{export_id}/cancel", response_model=dict)
def cancel_export(
    export_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*STAFF_ROLES)),
):
    export = _get_export(db, user, export_id)
    if export.status == "sent":
        raise conflict("Отправленный акт нельзя отменить; сформируйте корректирующий")
    if export.status == "cancelled":
        raise conflict("Экспорт уже отменён")
    export.status = "cancelled"
    export.cancelled_at = utcnow()
    write_audit(db, user=user, entity_type="export", entity_id=export.id, action="cancel",
                correlation_id=_cid(request))
    db.commit()
    return {"data": _serialize(export)}
