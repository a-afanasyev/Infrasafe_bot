"""Editable object tree: create, move, edit, archive (ТЗ §5.1)."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import ALL_ROLES, require_roles
from app.core.deps import correlation_id as _cid
from app.core.errors import bad_request, conflict, not_found
from app.db import get_db
from app.models import Meter, ObjectTag, ResourceObject, Tag, User
from app.schemas.catalog import ResourceObjectCreate, ResourceObjectOut, ResourceObjectUpdate

router = APIRouter(prefix="/objects", tags=["objects"])


def _get_object(db: Session, user: User, object_id: uuid.UUID) -> ResourceObject:
    row = db.get(ResourceObject, object_id)
    if not row or row.tenant_id != user.tenant_id:
        raise not_found("Объект")
    return row


def _assert_no_cycle(db: Session, obj_id: uuid.UUID, new_parent_id: uuid.UUID) -> None:
    """Walk up from the new parent; meeting obj_id means the move creates a cycle."""
    current: uuid.UUID | None = new_parent_id
    seen = 0
    while current is not None:
        if current == obj_id:
            raise bad_request("Перемещение создаёт цикл в дереве объектов")
        parent_row = db.execute(
            select(ResourceObject.parent_id).where(ResourceObject.id == current)
        ).scalar_one_or_none()
        current = parent_row
        seen += 1
        if seen > 100:
            raise bad_request("Слишком глубокое дерево объектов")


def _set_tags(db: Session, obj: ResourceObject, tag_ids: list[uuid.UUID], tenant_id) -> None:
    valid = set(
        db.execute(select(Tag.id).where(Tag.tenant_id == tenant_id, Tag.id.in_(tag_ids))).scalars()
    ) if tag_ids else set()
    unknown = set(tag_ids) - valid
    if unknown:
        raise bad_request(f"Неизвестные теги: {sorted(str(u) for u in unknown)}")
    db.query(ObjectTag).filter(ObjectTag.object_id == obj.id).delete()
    for tag_id in tag_ids:
        db.add(ObjectTag(object_id=obj.id, tag_id=tag_id))


def _serialize(row: ResourceObject) -> dict:
    return ResourceObjectOut.model_validate(row).model_dump(mode="json")


@router.get("", response_model=dict)
def list_objects(
    parent_id: uuid.UUID | None = None,
    type_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ALL_ROLES)),
):
    stmt = select(ResourceObject).where(ResourceObject.tenant_id == user.tenant_id)
    if parent_id is not None:
        stmt = stmt.where(ResourceObject.parent_id == parent_id)
    if type_id is not None:
        stmt = stmt.where(ResourceObject.type_id == type_id)
    if tag_id is not None:
        stmt = stmt.join(ObjectTag, ObjectTag.object_id == ResourceObject.id).where(ObjectTag.tag_id == tag_id)
    if status == "active":
        stmt = stmt.where(ResourceObject.is_active.is_(True))
    elif status == "archived":
        stmt = stmt.where(ResourceObject.is_active.is_(False))
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            ResourceObject.name.ilike(pattern) | func.coalesce(ResourceObject.code, "").ilike(pattern)
        )
    rows = db.execute(stmt.order_by(ResourceObject.sort_order, ResourceObject.name)).scalars().all()
    return {"data": [_serialize(r) for r in rows]}


@router.post("", response_model=dict, status_code=201)
def create_object(
    payload: ResourceObjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    if payload.code:
        dup = db.execute(
            select(ResourceObject).where(
                ResourceObject.tenant_id == user.tenant_id, ResourceObject.code == payload.code
            )
        ).scalar_one_or_none()
        if dup:
            raise conflict(f"Код «{payload.code}» уже используется")
    if payload.parent_id:
        _get_object(db, user, payload.parent_id)
    row = ResourceObject(
        tenant_id=user.tenant_id,
        name=payload.name,
        code=payload.code,
        type_id=payload.type_id,
        parent_id=payload.parent_id,
        description=payload.description,
        sort_order=payload.sort_order,
    )
    db.add(row)
    db.flush()
    _set_tags(db, row, payload.tag_ids, user.tenant_id)
    write_audit(db, user=user, entity_type="object", entity_id=row.id, action="create",
                after={"name": row.name, "parent_id": str(row.parent_id) if row.parent_id else None},
                correlation_id=_cid(request))
    db.commit()
    db.refresh(row)
    return {"data": _serialize(row)}


@router.get("/{object_id}", response_model=dict)
def get_object(
    object_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ALL_ROLES)),
):
    return {"data": _serialize(_get_object(db, user, object_id))}


@router.patch("/{object_id}", response_model=dict)
def update_object(
    object_id: uuid.UUID,
    payload: ResourceObjectUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    row = _get_object(db, user, object_id)
    before = {"name": row.name, "parent_id": str(row.parent_id) if row.parent_id else None}
    updates = payload.model_dump(exclude_unset=True)

    if updates.get("code"):
        dup = db.execute(
            select(ResourceObject).where(
                ResourceObject.tenant_id == user.tenant_id,
                ResourceObject.code == updates["code"],
                ResourceObject.id != row.id,
            )
        ).scalar_one_or_none()
        if dup:
            raise conflict(f"Код «{updates['code']}» уже используется")

    if payload.clear_parent:
        row.parent_id = None
    elif payload.parent_id is not None:
        _get_object(db, user, payload.parent_id)
        _assert_no_cycle(db, row.id, payload.parent_id)
        row.parent_id = payload.parent_id

    for field in ("name", "code", "type_id", "description", "sort_order"):
        if field in updates:
            setattr(row, field, updates[field])
    if payload.tag_ids is not None:
        _set_tags(db, row, payload.tag_ids, user.tenant_id)

    write_audit(db, user=user, entity_type="object", entity_id=row.id, action="update",
                before=before,
                after={"name": row.name, "parent_id": str(row.parent_id) if row.parent_id else None},
                correlation_id=_cid(request))
    db.commit()
    db.refresh(row)
    return {"data": _serialize(row)}


@router.post("/{object_id}/archive", response_model=dict)
def archive_object(
    object_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    row = _get_object(db, user, object_id)
    active_children = db.execute(
        select(func.count()).select_from(ResourceObject).where(
            ResourceObject.parent_id == row.id, ResourceObject.is_active.is_(True)
        )
    ).scalar_one()
    if active_children:
        raise conflict("Сначала архивируйте или переместите дочерние объекты")
    active_meters = db.execute(
        select(func.count()).select_from(Meter).where(
            Meter.primary_object_id == row.id, Meter.status == "active"
        )
    ).scalar_one()
    if active_meters:
        raise conflict("К объекту привязаны активные счётчики; сначала перенесите или архивируйте их")
    row.is_active = False
    write_audit(db, user=user, entity_type="object", entity_id=row.id, action="archive",
                before={"is_active": True}, after={"is_active": False}, correlation_id=_cid(request))
    db.commit()
    return {"data": _serialize(row)}
