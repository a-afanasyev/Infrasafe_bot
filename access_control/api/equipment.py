"""ADMIN-эндпоинты управления оборудованием контроля доступа (§6.1, §6.2, §9.1).

Реестр реальной точки въезда: парковочные зоны (+ привязка фаз ЖК) и въезды
(gates) — manager/system_admin (§6.2 «настройка зон»); камеры, шлагбаумы,
edge-контроллеры + device-credentials — ТОЛЬКО system_admin (§6.1). USER-API
(JWT/cookie — ``require_approved_roles``, НЕ device-auth).

RBAC: applicant/executor/inspector/security_operator → 403; без auth → 401.
Конверт списков — ``{items, total, limit, offset}`` (как registry). Create/PATCH
возвращают объект сущности. Удаления нет — деактивация через ``is_active``/``status``.

Device API-ключ контроллера (§9.1, решение CTO #8): генерируется криптостойко,
возвращается PLAINTEXT ровно один раз (create + rotate-key); в БД хранится ТОЛЬКО
``api_key_hash``; HMAC-секрет не хранится. В GET/списках секрет/хэш не отдаются.
Каждое изменение пишет append-only ``access_audit_logs`` с hash-chain (§9.7).
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from access_control.services import equipment_admin as svc
from uk_management_bot.api.dependencies import require_approved_roles
from uk_management_bot.database.session import get_db

router = APIRouter(prefix="/api/v1/access/admin", tags=["access-admin-equipment"])

# RBAC-наборы (решение CTO): зоны/въезды — менеджер+админ; остальное — только админ.
ZONE_GATE_ROLES = ("manager", "system_admin")
ADMIN_ONLY_ROLES = ("system_admin",)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

_CODE_MAX = 64
_NAME_MAX = 255
_TEXT_MAX = 128

OfflineModeLit = Literal["fail_closed", "cached_permanent_only"]
DirectionLit = Literal["entry", "exit"]
ControllerStatusLit = Literal["active", "inactive", "decommissioned"]


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _limit_q() -> int:
    return Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="размер страницы (max 200)")


# ------------------------------ response DTO ------------------------------


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class ZoneRow(_Frozen):
    id: int
    code: str
    name: str
    description: str | None
    offline_mode: str
    max_permanent_vehicles_per_apartment: int | None
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime | None


class GateRow(_Frozen):
    id: int
    code: str
    name: str | None
    zone_id: int
    controller_id: int | None
    direction: str
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime | None


class CameraRow(_Frozen):
    id: int
    code: str
    name: str | None
    gate_id: int
    controller_id: int | None
    direction: str
    vendor: str | None
    model: str | None
    attributes: dict | None
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime | None


class BarrierRow(_Frozen):
    id: int
    code: str
    name: str | None
    gate_id: int
    controller_id: int | None
    relay_type: str | None
    relay_channel: int | None
    config: dict | None
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime | None


class ControllerRow(_Frozen):
    """Безопасная выдача контроллера: БЕЗ ``api_key``/``api_key_hash`` (§9.1, §11)."""

    id: int
    controller_uid: str
    name: str | None
    zone_id: int | None
    gate_id: int | None
    offline_mode: str
    ip_allowlist: list | None
    pinned_public_key_id: str | None
    last_heartbeat_at: dt.datetime | None
    clock_offset_ms: int | None
    status: str
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime | None


class ControllerCreatedRow(ControllerRow):
    """Ответ создания: безопасные поля + PLAINTEXT ``api_key`` (ровно один раз)."""

    api_key: str


class RotateKeyResponse(_Frozen):
    controller_id: int
    controller_uid: str
    api_key: str


def _page_model(name: str, row_type):
    return type(name, (_Frozen,), {
        "__annotations__": {
            "items": list[row_type], "total": int, "limit": int, "offset": int
        }
    })


ZonesPage = _page_model("ZonesPage", ZoneRow)
GatesPage = _page_model("GatesPage", GateRow)
CamerasPage = _page_model("CamerasPage", CameraRow)
BarriersPage = _page_model("BarriersPage", BarrierRow)
ControllersPage = _page_model("ControllersPage", ControllerRow)


# ------------------------------ row builders ------------------------------


def _zone_row(z) -> ZoneRow:
    return ZoneRow(
        id=z.id, code=z.code, name=z.name, description=z.description,
        offline_mode=z.offline_mode,
        max_permanent_vehicles_per_apartment=z.max_permanent_vehicles_per_apartment,
        is_active=z.is_active, created_at=z.created_at, updated_at=z.updated_at,
    )


def _gate_row(g) -> GateRow:
    return GateRow(
        id=g.id, code=g.code, name=g.name, zone_id=g.zone_id,
        controller_id=g.controller_id, direction=g.direction, is_active=g.is_active,
        created_at=g.created_at, updated_at=g.updated_at,
    )


def _camera_row(c) -> CameraRow:
    return CameraRow(
        id=c.id, code=c.code, name=c.name, gate_id=c.gate_id,
        controller_id=c.controller_id, direction=c.direction, vendor=c.vendor,
        model=c.model, attributes=c.attributes, is_active=c.is_active,
        created_at=c.created_at, updated_at=c.updated_at,
    )


def _barrier_row(b) -> BarrierRow:
    return BarrierRow(
        id=b.id, code=b.code, name=b.name, gate_id=b.gate_id,
        controller_id=b.controller_id, relay_type=b.relay_type,
        relay_channel=b.relay_channel, config=b.config, is_active=b.is_active,
        created_at=b.created_at, updated_at=b.updated_at,
    )


def _controller_fields(c) -> dict:
    return dict(
        id=c.id, controller_uid=c.controller_uid, name=c.name, zone_id=c.zone_id,
        gate_id=c.gate_id, offline_mode=c.offline_mode, ip_allowlist=c.ip_allowlist,
        pinned_public_key_id=c.pinned_public_key_id,
        last_heartbeat_at=c.last_heartbeat_at, clock_offset_ms=c.clock_offset_ms,
        status=c.status, is_active=c.is_active, created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _controller_row(c) -> ControllerRow:
    return ControllerRow(**_controller_fields(c))


# ------------------------------ error mapping ------------------------------


def _raise_409_dup_code(exc) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": "duplicate_code", "message": str(exc)},
    )


def _raise_409_dup_uid(exc) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": "duplicate_controller_uid", "message": str(exc)},
    )


def _raise_422_ref(exc) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"error": "invalid_reference", "message": str(exc)},
    )


def _raise_404(exc) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# =============================== ЗОНЫ ===============================


class ZoneCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=_CODE_MAX)
    name: str = Field(..., min_length=1, max_length=_NAME_MAX)
    description: str | None = None
    offline_mode: OfflineModeLit | None = None
    max_permanent_per_apartment: int | None = Field(None, ge=0)
    is_active: bool = True


class ZonePatch(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=_CODE_MAX)
    name: str | None = Field(None, min_length=1, max_length=_NAME_MAX)
    description: str | None = None
    offline_mode: OfflineModeLit | None = None
    max_permanent_per_apartment: int | None = Field(None, ge=0)
    is_active: bool | None = None


class ZoneYardsRequest(BaseModel):
    add: list[int] = Field(default_factory=list)
    remove: list[int] = Field(default_factory=list)


class ZoneYardsResponse(_Frozen):
    zone_id: int
    yard_ids: list[int]


@router.get("/zones", response_model=ZonesPage)
def list_zones(
    limit: int = _limit_q(),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    rows, total = svc.list_zones(db, limit=limit, offset=offset)
    return ZonesPage(items=[_zone_row(r) for r in rows], total=total, limit=limit, offset=offset)


@router.post("/zones", response_model=ZoneRow, status_code=status.HTTP_201_CREATED)
def create_zone(
    body: ZoneCreate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    try:
        zone = svc.create_zone(
            db, actor_user_id=user.id, code=body.code, name=body.name,
            description=body.description, offline_mode=body.offline_mode,
            max_permanent_vehicles_per_apartment=body.max_permanent_per_apartment,
            is_active=body.is_active, ip_address=_client_ip(request),
        )
    except svc.DuplicateCode as exc:
        _raise_409_dup_code(exc)
    return _zone_row(zone)


@router.patch("/zones/{zone_id}", response_model=ZoneRow)
def patch_zone(
    body: ZonePatch,
    request: Request,
    zone_id: int = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    fields = body.model_dump(exclude_unset=True)
    if "max_permanent_per_apartment" in fields:
        fields["max_permanent_vehicles_per_apartment"] = fields.pop(
            "max_permanent_per_apartment"
        )
    try:
        zone = svc.update_zone(
            db, zone_id=zone_id, actor_user_id=user.id, fields=fields,
            ip_address=_client_ip(request),
        )
    except svc.NotFound as exc:
        _raise_404(exc)
    except svc.DuplicateCode as exc:
        _raise_409_dup_code(exc)
    return _zone_row(zone)


@router.post("/zones/{zone_id}/yards", response_model=ZoneYardsResponse)
def set_zone_yards(
    body: ZoneYardsRequest,
    request: Request,
    zone_id: int = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    try:
        yard_ids = svc.set_zone_yards(
            db, zone_id=zone_id, actor_user_id=user.id, add=body.add,
            remove=body.remove, ip_address=_client_ip(request),
        )
    except svc.NotFound as exc:
        _raise_404(exc)
    except svc.InvalidReference as exc:
        _raise_422_ref(exc)
    return ZoneYardsResponse(zone_id=zone_id, yard_ids=yard_ids)


# =============================== ВЪЕЗДЫ ===============================


class GateCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=_CODE_MAX)
    zone_id: int
    direction: DirectionLit
    name: str | None = Field(None, max_length=_NAME_MAX)
    controller_id: int | None = None
    is_active: bool = True


class GatePatch(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=_CODE_MAX)
    zone_id: int | None = None
    direction: DirectionLit | None = None
    name: str | None = Field(None, max_length=_NAME_MAX)
    controller_id: int | None = None
    is_active: bool | None = None


@router.get("/gates", response_model=GatesPage)
def list_gates(
    limit: int = _limit_q(),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    rows, total = svc.list_gates(db, limit=limit, offset=offset)
    return GatesPage(items=[_gate_row(r) for r in rows], total=total, limit=limit, offset=offset)


@router.post("/gates", response_model=GateRow, status_code=status.HTTP_201_CREATED)
def create_gate(
    body: GateCreate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    try:
        gate = svc.create_gate(
            db, actor_user_id=user.id, code=body.code, zone_id=body.zone_id,
            direction=body.direction, name=body.name, controller_id=body.controller_id,
            is_active=body.is_active, ip_address=_client_ip(request),
        )
    except svc.InvalidReference as exc:
        _raise_422_ref(exc)
    except svc.DuplicateCode as exc:
        _raise_409_dup_code(exc)
    return _gate_row(gate)


@router.patch("/gates/{gate_id}", response_model=GateRow)
def patch_gate(
    body: GatePatch,
    request: Request,
    gate_id: int = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    fields = body.model_dump(exclude_unset=True)
    try:
        gate = svc.update_gate(
            db, gate_id=gate_id, actor_user_id=user.id, fields=fields,
            ip_address=_client_ip(request),
        )
    except svc.NotFound as exc:
        _raise_404(exc)
    except svc.InvalidReference as exc:
        _raise_422_ref(exc)
    except svc.DuplicateCode as exc:
        _raise_409_dup_code(exc)
    return _gate_row(gate)


# =============================== КАМЕРЫ (admin-only) ===============================


class CameraCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=_CODE_MAX)
    gate_id: int
    direction: DirectionLit
    name: str | None = Field(None, max_length=_NAME_MAX)
    controller_id: int | None = None
    vendor: str | None = Field(None, max_length=_TEXT_MAX)
    model: str | None = Field(None, max_length=_TEXT_MAX)
    attributes: dict | None = None
    is_active: bool = True


class CameraPatch(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=_CODE_MAX)
    gate_id: int | None = None
    direction: DirectionLit | None = None
    name: str | None = Field(None, max_length=_NAME_MAX)
    controller_id: int | None = None
    vendor: str | None = Field(None, max_length=_TEXT_MAX)
    model: str | None = Field(None, max_length=_TEXT_MAX)
    attributes: dict | None = None
    is_active: bool | None = None


@router.get("/cameras", response_model=CamerasPage)
def list_cameras(
    limit: int = _limit_q(),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*ADMIN_ONLY_ROLES)),
):
    rows, total = svc.list_cameras(db, limit=limit, offset=offset)
    return CamerasPage(items=[_camera_row(r) for r in rows], total=total, limit=limit, offset=offset)


@router.post("/cameras", response_model=CameraRow, status_code=status.HTTP_201_CREATED)
def create_camera(
    body: CameraCreate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ADMIN_ONLY_ROLES)),
):
    try:
        camera = svc.create_camera(
            db, actor_user_id=user.id, code=body.code, gate_id=body.gate_id,
            direction=body.direction, name=body.name, controller_id=body.controller_id,
            vendor=body.vendor, model=body.model, attributes=body.attributes,
            is_active=body.is_active, ip_address=_client_ip(request),
        )
    except svc.InvalidReference as exc:
        _raise_422_ref(exc)
    except svc.DuplicateCode as exc:
        _raise_409_dup_code(exc)
    return _camera_row(camera)


@router.patch("/cameras/{camera_id}", response_model=CameraRow)
def patch_camera(
    body: CameraPatch,
    request: Request,
    camera_id: int = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ADMIN_ONLY_ROLES)),
):
    fields = body.model_dump(exclude_unset=True)
    try:
        camera = svc.update_camera(
            db, camera_id=camera_id, actor_user_id=user.id, fields=fields,
            ip_address=_client_ip(request),
        )
    except svc.NotFound as exc:
        _raise_404(exc)
    except svc.InvalidReference as exc:
        _raise_422_ref(exc)
    except svc.DuplicateCode as exc:
        _raise_409_dup_code(exc)
    return _camera_row(camera)


# =============================== ШЛАГБАУМЫ (admin-only) ===============================


class BarrierCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=_CODE_MAX)
    gate_id: int
    name: str | None = Field(None, max_length=_NAME_MAX)
    controller_id: int | None = None
    relay_type: str | None = Field(None, max_length=64)
    relay_channel: int | None = None
    config: dict | None = None
    is_active: bool = True


class BarrierPatch(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=_CODE_MAX)
    gate_id: int | None = None
    name: str | None = Field(None, max_length=_NAME_MAX)
    controller_id: int | None = None
    relay_type: str | None = Field(None, max_length=64)
    relay_channel: int | None = None
    config: dict | None = None
    is_active: bool | None = None


@router.get("/barriers", response_model=BarriersPage)
def list_barriers(
    limit: int = _limit_q(),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*ADMIN_ONLY_ROLES)),
):
    rows, total = svc.list_barriers(db, limit=limit, offset=offset)
    return BarriersPage(items=[_barrier_row(r) for r in rows], total=total, limit=limit, offset=offset)


@router.post("/barriers", response_model=BarrierRow, status_code=status.HTTP_201_CREATED)
def create_barrier(
    body: BarrierCreate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ADMIN_ONLY_ROLES)),
):
    try:
        barrier = svc.create_barrier(
            db, actor_user_id=user.id, code=body.code, gate_id=body.gate_id,
            name=body.name, controller_id=body.controller_id, relay_type=body.relay_type,
            relay_channel=body.relay_channel, config=body.config,
            is_active=body.is_active, ip_address=_client_ip(request),
        )
    except svc.InvalidReference as exc:
        _raise_422_ref(exc)
    except svc.DuplicateCode as exc:
        _raise_409_dup_code(exc)
    return _barrier_row(barrier)


@router.patch("/barriers/{barrier_id}", response_model=BarrierRow)
def patch_barrier(
    body: BarrierPatch,
    request: Request,
    barrier_id: int = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ADMIN_ONLY_ROLES)),
):
    fields = body.model_dump(exclude_unset=True)
    try:
        barrier = svc.update_barrier(
            db, barrier_id=barrier_id, actor_user_id=user.id, fields=fields,
            ip_address=_client_ip(request),
        )
    except svc.NotFound as exc:
        _raise_404(exc)
    except svc.InvalidReference as exc:
        _raise_422_ref(exc)
    except svc.DuplicateCode as exc:
        _raise_409_dup_code(exc)
    return _barrier_row(barrier)


# =============================== КОНТРОЛЛЕРЫ (admin-only) ===============================


class ControllerCreate(BaseModel):
    controller_uid: str = Field(..., min_length=1, max_length=128)
    name: str | None = Field(None, max_length=_NAME_MAX)
    zone_id: int | None = None
    gate_id: int | None = None
    offline_mode: OfflineModeLit | None = None
    ip_allowlist: list[str] | None = None
    pinned_public_key_id: str | None = Field(None, max_length=128)
    status: ControllerStatusLit | None = None
    is_active: bool = True


class ControllerPatch(BaseModel):
    name: str | None = Field(None, max_length=_NAME_MAX)
    zone_id: int | None = None
    gate_id: int | None = None
    offline_mode: OfflineModeLit | None = None
    ip_allowlist: list[str] | None = None
    pinned_public_key_id: str | None = Field(None, max_length=128)
    status: ControllerStatusLit | None = None
    is_active: bool | None = None


@router.get("/controllers", response_model=ControllersPage)
def list_controllers(
    limit: int = _limit_q(),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*ADMIN_ONLY_ROLES)),
):
    rows, total = svc.list_controllers(db, limit=limit, offset=offset)
    return ControllersPage(
        items=[_controller_row(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/controllers/{controller_id}", response_model=ControllerRow)
def get_controller(
    controller_id: int = Path(...),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*ADMIN_ONLY_ROLES)),
):
    try:
        controller = svc.get_controller(db, controller_id)
    except svc.NotFound as exc:
        _raise_404(exc)
    return _controller_row(controller)


@router.post(
    "/controllers", response_model=ControllerCreatedRow,
    status_code=status.HTTP_201_CREATED,
)
def create_controller(
    body: ControllerCreate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ADMIN_ONLY_ROLES)),
):
    """Создать контроллер + device API-ключ (§9.1). ``api_key`` отдаётся ОДИН раз."""
    try:
        created = svc.create_controller(
            db, actor_user_id=user.id, controller_uid=body.controller_uid,
            name=body.name, zone_id=body.zone_id, gate_id=body.gate_id,
            offline_mode=body.offline_mode, ip_allowlist=body.ip_allowlist,
            pinned_public_key_id=body.pinned_public_key_id, status=body.status,
            is_active=body.is_active, ip_address=_client_ip(request),
        )
    except svc.DuplicateControllerUid as exc:
        _raise_409_dup_uid(exc)
    except svc.InvalidReference as exc:
        _raise_422_ref(exc)
    return ControllerCreatedRow(
        **_controller_fields(created.controller), api_key=created.api_key
    )


@router.patch("/controllers/{controller_id}", response_model=ControllerRow)
def patch_controller(
    body: ControllerPatch,
    request: Request,
    controller_id: int = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ADMIN_ONLY_ROLES)),
):
    fields = body.model_dump(exclude_unset=True)
    try:
        controller = svc.update_controller(
            db, controller_id=controller_id, actor_user_id=user.id, fields=fields,
            ip_address=_client_ip(request),
        )
    except svc.NotFound as exc:
        _raise_404(exc)
    except svc.InvalidReference as exc:
        _raise_422_ref(exc)
    return _controller_row(controller)


@router.post("/controllers/{controller_id}/rotate-key", response_model=RotateKeyResponse)
def rotate_controller_key(
    request: Request,
    controller_id: int = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ADMIN_ONLY_ROLES)),
):
    """Ротация device API-ключа (§9.1). Новый ``api_key`` отдаётся ОДИН раз."""
    try:
        controller, api_key = svc.rotate_controller_key(
            db, controller_id=controller_id, actor_user_id=user.id,
            ip_address=_client_ip(request),
        )
    except svc.NotFound as exc:
        _raise_404(exc)
    return RotateKeyResponse(
        controller_id=controller.id, controller_uid=controller.controller_uid,
        api_key=api_key,
    )
