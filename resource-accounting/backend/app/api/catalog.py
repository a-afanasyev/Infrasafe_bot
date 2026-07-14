"""CRUD for editable dictionaries: object types, tags, providers (ТЗ §5.1)."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import ALL_ROLES, require_roles
from app.core.deps import correlation_id as _cid
from app.core.errors import conflict, not_found
from app.db import get_db
from app.models import ObjectType, Provider, Tag, User
from app.schemas.catalog import (
    ObjectTypeCreate,
    ObjectTypeOut,
    ObjectTypeUpdate,
    ProviderCreate,
    ProviderOut,
    ProviderUpdate,
    TagCreate,
    TagOut,
    TagUpdate,
)

router = APIRouter(tags=["catalog"])


def _dup_check(db: Session, model, tenant_id, name: str, exclude_id=None) -> None:
    stmt = select(model).where(model.tenant_id == tenant_id, model.name == name)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing and existing.id != exclude_id:
        raise conflict(f"Имя «{name}» уже используется")


# --- Object types ---
@router.get("/object-types", response_model=dict)
def list_object_types(db: Session = Depends(get_db), user: User = Depends(require_roles(*ALL_ROLES))):
    rows = db.execute(
        select(ObjectType).where(ObjectType.tenant_id == user.tenant_id).order_by(ObjectType.name)
    ).scalars().all()
    return {"data": [ObjectTypeOut.model_validate(r).model_dump(mode="json") for r in rows]}


@router.post("/object-types", response_model=dict, status_code=201)
def create_object_type(
    payload: ObjectTypeCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    _dup_check(db, ObjectType, user.tenant_id, payload.name)
    row = ObjectType(tenant_id=user.tenant_id, name=payload.name)
    db.add(row)
    db.flush()
    write_audit(db, user=user, entity_type="object_type", entity_id=row.id, action="create",
                after={"name": row.name}, correlation_id=_cid(request))
    db.commit()
    return {"data": ObjectTypeOut.model_validate(row).model_dump(mode="json")}


@router.patch("/object-types/{type_id}", response_model=dict)
def update_object_type(
    type_id: uuid.UUID,
    payload: ObjectTypeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    row = db.get(ObjectType, type_id)
    if not row or row.tenant_id != user.tenant_id:
        raise not_found("Тип объекта")
    before = {"name": row.name, "is_active": row.is_active}
    if payload.name is not None:
        _dup_check(db, ObjectType, user.tenant_id, payload.name, exclude_id=row.id)
        row.name = payload.name
    if payload.is_active is not None:
        row.is_active = payload.is_active
    write_audit(db, user=user, entity_type="object_type", entity_id=row.id, action="update",
                before=before, after={"name": row.name, "is_active": row.is_active},
                correlation_id=_cid(request))
    db.commit()
    return {"data": ObjectTypeOut.model_validate(row).model_dump(mode="json")}


# --- Tags ---
@router.get("/tags", response_model=dict)
def list_tags(db: Session = Depends(get_db), user: User = Depends(require_roles(*ALL_ROLES))):
    rows = db.execute(
        select(Tag).where(Tag.tenant_id == user.tenant_id).order_by(Tag.name)
    ).scalars().all()
    return {"data": [TagOut.model_validate(r).model_dump(mode="json") for r in rows]}


@router.post("/tags", response_model=dict, status_code=201)
def create_tag(
    payload: TagCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    _dup_check(db, Tag, user.tenant_id, payload.name)
    row = Tag(tenant_id=user.tenant_id, name=payload.name)
    db.add(row)
    db.flush()
    write_audit(db, user=user, entity_type="tag", entity_id=row.id, action="create",
                after={"name": row.name}, correlation_id=_cid(request))
    db.commit()
    return {"data": TagOut.model_validate(row).model_dump(mode="json")}


@router.patch("/tags/{tag_id}", response_model=dict)
def update_tag(
    tag_id: uuid.UUID,
    payload: TagUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    row = db.get(Tag, tag_id)
    if not row or row.tenant_id != user.tenant_id:
        raise not_found("Тег")
    before = {"name": row.name, "is_active": row.is_active}
    if payload.name is not None:
        _dup_check(db, Tag, user.tenant_id, payload.name, exclude_id=row.id)
        row.name = payload.name
    if payload.is_active is not None:
        row.is_active = payload.is_active
    write_audit(db, user=user, entity_type="tag", entity_id=row.id, action="update",
                before=before, after={"name": row.name, "is_active": row.is_active},
                correlation_id=_cid(request))
    db.commit()
    return {"data": TagOut.model_validate(row).model_dump(mode="json")}


# --- Providers ---
@router.get("/providers", response_model=dict)
def list_providers(db: Session = Depends(get_db), user: User = Depends(require_roles(*ALL_ROLES))):
    rows = db.execute(
        select(Provider).where(Provider.tenant_id == user.tenant_id).order_by(Provider.name)
    ).scalars().all()
    return {"data": [ProviderOut.model_validate(r).model_dump(mode="json") for r in rows]}


@router.post("/providers", response_model=dict, status_code=201)
def create_provider(
    payload: ProviderCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    _dup_check(db, Provider, user.tenant_id, payload.name)
    row = Provider(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(row)
    db.flush()
    write_audit(db, user=user, entity_type="provider", entity_id=row.id, action="create",
                after={"name": row.name}, correlation_id=_cid(request))
    db.commit()
    return {"data": ProviderOut.model_validate(row).model_dump(mode="json")}


@router.patch("/providers/{provider_id}", response_model=dict)
def update_provider(
    provider_id: uuid.UUID,
    payload: ProviderUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    row = db.get(Provider, provider_id)
    if not row or row.tenant_id != user.tenant_id:
        raise not_found("Поставщик")
    before = {"name": row.name, "is_active": row.is_active}
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        _dup_check(db, Provider, user.tenant_id, updates["name"], exclude_id=row.id)
    for field, value in updates.items():
        setattr(row, field, value)
    write_audit(db, user=user, entity_type="provider", entity_id=row.id, action="update",
                before=before, after={"name": row.name, "is_active": row.is_active},
                correlation_id=_cid(request))
    db.commit()
    return {"data": ProviderOut.model_validate(row).model_dump(mode="json")}
