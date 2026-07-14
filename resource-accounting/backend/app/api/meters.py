"""Meter registry: CRUD, search, consumer links, number correction, replacement (ТЗ §5.2–5.3)."""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import ALL_ROLES, require_roles
from app.core.deps import correlation_id as _cid
from app.core.errors import bad_request, conflict, not_found
from app.db import get_db
from app.models import (
    Meter,
    MeterObjectLink,
    MeterTag,
    ResourceObject,
    Tag,
    User,
    normalize_meter_number,
)
from app.schemas.meters import (
    ConsumerLinkOut,
    CorrectNumberIn,
    MeterCreate,
    MeterOut,
    MeterUpdate,
    ReplaceMeterIn,
)

router = APIRouter(prefix="/meters", tags=["meters"])


def get_meter_or_404(db: Session, user: User, meter_id: uuid.UUID) -> Meter:
    row = db.get(Meter, meter_id)
    if not row or row.tenant_id != user.tenant_id:
        raise not_found("Счётчик")
    return row


def serialize_meter(row: Meter) -> dict:
    out = MeterOut.model_validate(row)
    out.primary_object_name = row.primary_object.name if row.primary_object else None
    out.consumers = [
        ConsumerLinkOut(
            id=link.id,
            object_id=link.object_id,
            object_name=link.object.name if link.object else None,
            link_type=link.link_type,
            description=link.description,
            allocation_percent=link.allocation_percent,
        )
        for link in row.consumer_links
    ]
    return out.model_dump(mode="json")


def _check_active_object(db: Session, user: User, object_id: uuid.UUID) -> ResourceObject:
    obj = db.get(ResourceObject, object_id)
    if not obj or obj.tenant_id != user.tenant_id:
        raise not_found("Объект")
    if not obj.is_active:
        raise bad_request(f"Объект «{obj.name}» архивирован")
    return obj


def _check_unique_number(db: Session, tenant_id, normalized: str, exclude_id=None) -> None:
    stmt = select(Meter).where(
        Meter.tenant_id == tenant_id,
        Meter.meter_number_normalized == normalized,
        Meter.status == "active",
    )
    existing = db.execute(stmt).scalar_one_or_none()
    if existing and existing.id != exclude_id:
        raise conflict(f"Активный счётчик с номером «{normalized}» уже существует")


def _set_meter_tags(db: Session, meter: Meter, tag_ids: list[uuid.UUID], tenant_id) -> None:
    if tag_ids:
        valid = set(
            db.execute(select(Tag.id).where(Tag.tenant_id == tenant_id, Tag.id.in_(tag_ids))).scalars()
        )
        unknown = set(tag_ids) - valid
        if unknown:
            raise bad_request(f"Неизвестные теги: {sorted(str(u) for u in unknown)}")
    db.query(MeterTag).filter(MeterTag.meter_id == meter.id).delete()
    for tag_id in tag_ids:
        db.add(MeterTag(meter_id=meter.id, tag_id=tag_id))


def _set_consumers(db: Session, user: User, meter: Meter, consumers) -> None:
    db.query(MeterObjectLink).filter(MeterObjectLink.meter_id == meter.id).delete()
    db.flush()
    seen: set[uuid.UUID] = set()
    for item in consumers:
        if item.object_id in seen:
            raise bad_request("Дублирующийся потребитель в списке")
        if item.object_id == meter.primary_object_id:
            raise bad_request("Основной объект не указывается повторно как потребитель")
        seen.add(item.object_id)
        _check_active_object(db, user, item.object_id)
        db.add(
            MeterObjectLink(
                meter_id=meter.id,
                object_id=item.object_id,
                link_type="consumer",
                description=item.description,
                allocation_percent=item.allocation_percent,
            )
        )


def _apply_meter_payload(db: Session, user: User, meter: Meter, payload: MeterCreate) -> None:
    meter.name = payload.name
    meter.resource_type = payload.resource_type
    meter.unit = payload.unit
    meter.description = payload.description
    meter.install_location = payload.install_location
    meter.primary_object_id = payload.primary_object_id
    meter.provider_id = payload.provider_id
    meter.provider_account = payload.provider_account
    meter.serial_number = payload.serial_number
    meter.coefficient = payload.coefficient
    meter.max_digits = payload.max_digits
    meter.installed_at = payload.installed_at
    meter.photo_file_id = payload.photo_file_id
    meter.note = payload.note


@router.get("", response_model=dict)
def list_meters(
    number: str | None = None,
    object_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    provider_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    combined: bool | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ALL_ROLES)),
):
    stmt = select(Meter).where(Meter.tenant_id == user.tenant_id)
    if number:
        stmt = stmt.where(Meter.meter_number_normalized == normalize_meter_number(number))
    if object_id:
        consumer_meter_ids = select(MeterObjectLink.meter_id).where(MeterObjectLink.object_id == object_id)
        stmt = stmt.where((Meter.primary_object_id == object_id) | Meter.id.in_(consumer_meter_ids))
    if resource_type:
        stmt = stmt.where(Meter.resource_type == resource_type)
    if provider_id:
        stmt = stmt.where(Meter.provider_id == provider_id)
    if tag_id:
        stmt = stmt.join(MeterTag, MeterTag.meter_id == Meter.id).where(MeterTag.tag_id == tag_id)
    if combined is not None:
        has_consumers = select(MeterObjectLink.meter_id)
        stmt = stmt.where(Meter.id.in_(has_consumers) if combined else Meter.id.not_in(has_consumers))
    if status:
        stmt = stmt.where(Meter.status == status)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            Meter.meter_number.ilike(pattern)
            | Meter.name.ilike(pattern)
            | Meter.description.ilike(pattern)
        )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(stmt.order_by(Meter.meter_number_normalized).offset((page - 1) * per_page).limit(per_page))
        .scalars()
        .all()
    )
    return {
        "data": [serialize_meter(r) for r in rows],
        "meta": {"total": total, "page": page, "per_page": per_page},
    }


@router.post("", response_model=dict, status_code=201)
def create_meter(
    payload: MeterCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin", "resource_operator")),
):
    normalized = normalize_meter_number(payload.meter_number)
    _check_unique_number(db, user.tenant_id, normalized)
    _check_active_object(db, user, payload.primary_object_id)

    meter = Meter(
        tenant_id=user.tenant_id,
        meter_number=payload.meter_number.strip(),
        meter_number_normalized=normalized,
        status="active",
    )
    _apply_meter_payload(db, user, meter, payload)
    db.add(meter)
    db.flush()
    _set_meter_tags(db, meter, payload.tag_ids, user.tenant_id)
    _set_consumers(db, user, meter, payload.consumers)
    write_audit(db, user=user, entity_type="meter", entity_id=meter.id, action="create",
                after={"meter_number": meter.meter_number, "name": meter.name},
                correlation_id=_cid(request))
    db.commit()
    db.refresh(meter)
    return {"data": serialize_meter(meter)}


@router.get("/{meter_id}", response_model=dict)
def get_meter(
    meter_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ALL_ROLES)),
):
    return {"data": serialize_meter(get_meter_or_404(db, user, meter_id))}


@router.patch("/{meter_id}", response_model=dict)
def update_meter(
    meter_id: uuid.UUID,
    payload: MeterUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin", "resource_operator")),
):
    meter = get_meter_or_404(db, user, meter_id)
    before = {"name": meter.name, "primary_object_id": str(meter.primary_object_id)}
    updates = payload.model_dump(exclude_unset=True)

    if payload.primary_object_id is not None:
        _check_active_object(db, user, payload.primary_object_id)
        meter.primary_object_id = payload.primary_object_id
    for field in (
        "name", "description", "install_location", "provider_id", "provider_account",
        "serial_number", "coefficient", "max_digits", "installed_at", "photo_file_id", "note",
    ):
        if field in updates:
            setattr(meter, field, updates[field])
    if payload.tag_ids is not None:
        _set_meter_tags(db, meter, payload.tag_ids, user.tenant_id)
    if payload.consumers is not None:
        _set_consumers(db, user, meter, payload.consumers)

    write_audit(db, user=user, entity_type="meter", entity_id=meter.id, action="update",
                before=before,
                after={"name": meter.name, "primary_object_id": str(meter.primary_object_id)},
                correlation_id=_cid(request))
    db.commit()
    db.refresh(meter)
    return {"data": serialize_meter(meter)}


@router.post("/{meter_id}/archive", response_model=dict)
def archive_meter(
    meter_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    meter = get_meter_or_404(db, user, meter_id)
    if meter.status == "archived":
        raise conflict("Счётчик уже архивирован")
    before = {"status": meter.status}
    meter.status = "archived"
    write_audit(db, user=user, entity_type="meter", entity_id=meter.id, action="archive",
                before=before, after={"status": "archived"}, correlation_id=_cid(request))
    db.commit()
    return {"data": serialize_meter(meter)}


@router.post("/{meter_id}/correct-number", response_model=dict)
def correct_number(
    meter_id: uuid.UUID,
    payload: CorrectNumberIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    """Number correction keeps the meter and its history; the old number stays in the audit trail."""
    meter = get_meter_or_404(db, user, meter_id)
    normalized = normalize_meter_number(payload.new_number)
    if normalized == meter.meter_number_normalized:
        raise bad_request("Новый номер совпадает с текущим")
    _check_unique_number(db, user.tenant_id, normalized, exclude_id=meter.id)
    before = {"meter_number": meter.meter_number}
    meter.meter_number = payload.new_number.strip()
    meter.meter_number_normalized = normalized
    write_audit(db, user=user, entity_type="meter", entity_id=meter.id, action="correct_number",
                before=before, after={"meter_number": meter.meter_number, "reason": payload.reason},
                correlation_id=_cid(request))
    db.commit()
    return {"data": serialize_meter(meter)}


@router.post("/{meter_id}/replace", response_model=dict)
def replace_meter(
    meter_id: uuid.UUID,
    payload: ReplaceMeterIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin", "resource_operator")),
):
    """Physical replacement: decommission the old meter, create a new one linked via replaces_meter_id."""
    old = get_meter_or_404(db, user, meter_id)
    if old.status != "active":
        raise conflict("Заменить можно только активный счётчик")

    old.status = "decommissioned"
    old.removed_at = payload.removed_at
    db.flush()

    normalized = normalize_meter_number(payload.new_meter.meter_number)
    _check_unique_number(db, user.tenant_id, normalized)
    _check_active_object(db, user, payload.new_meter.primary_object_id)
    new = Meter(
        tenant_id=user.tenant_id,
        meter_number=payload.new_meter.meter_number.strip(),
        meter_number_normalized=normalized,
        status="active",
        replaces_meter_id=old.id,
    )
    _apply_meter_payload(db, user, new, payload.new_meter)
    db.add(new)
    db.flush()
    _set_meter_tags(db, new, payload.new_meter.tag_ids, user.tenant_id)
    _set_consumers(db, user, new, payload.new_meter.consumers)

    write_audit(db, user=user, entity_type="meter", entity_id=old.id, action="replace",
                before={"status": "active"},
                after={"status": "decommissioned", "replaced_by": str(new.id),
                       "final_reading": str(payload.final_reading) if payload.final_reading is not None else None,
                       "reason": payload.reason},
                correlation_id=_cid(request))
    db.commit()
    db.refresh(new)
    return {"data": {"old": serialize_meter(old), "new": serialize_meter(new)}}
