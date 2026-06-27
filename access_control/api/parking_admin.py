"""ADMIN-эндпоинты управления парковкой — этап 2 (§5, §6.2, §7, §10.3).

Поверх реестра оборудования (``api/equipment.py``) добавляет управление местами и
закреплениями + занятость зоны. USER-API (JWT/cookie — ``require_approved_roles``):

* МЕСТА (``parking_spots``) и ЗАКРЕПЛЕНИЯ (``parking_spot_assignments``) —
  manager/system_admin (§6.2 «настройка зон»); applicant/executor/inspector/
  security_operator → 403; без auth → 401.
* Удаления нет — деактивация статусом. Конверт списков ``{items,total,limit,offset}``.
* Каждое изменение пишет append-only ``access_audit_logs`` (§9.7):
  ``access.spot_create/spot_update`` и ``access.spot_assignment_create/update``.

Закрепление — ЗА КВАРТИРОЙ (любой активный авто квартиры пользуется местом).
``owned`` бессрочно; ``rented`` требует ``valid_until``. Срок аренды enforce'ится
ЖИВО в Decision Engine (``spot_rental_expired`` по ``valid_until``) — отдельный воркер
истечения НЕ нужен; статусом управляют вручную (revoke). Занятость зоны (§10.3) —
учёт разрешённых въездов (``zone_occupancy``), полезно для UI shared-зон.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from access_control.services import equipment_admin as eq_svc
from access_control.services import parking_admin as svc
from access_control.services.parking_occupancy import zone_occupancy
from uk_management_bot.api.dependencies import require_approved_roles
from uk_management_bot.database.session import get_db

router = APIRouter(prefix="/api/v1/access/admin", tags=["access-admin-parking"])

# Парковка (места/закрепления/занятость) — настройка зон (§6.2): менеджер+админ.
ZONE_GATE_ROLES = ("manager", "system_admin")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
_CODE_MAX = 64

SpotStatusLit = Literal["active", "inactive", "archived"]
OwnershipTypeLit = Literal["owned", "rented"]
AssignmentStatusLit = Literal["active", "expired", "revoked", "archived"]


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _limit_q() -> int:
    return Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="размер страницы (max 200)")


# ------------------------------ response DTO ------------------------------


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class SpotRow(_Frozen):
    id: int
    zone_id: int
    code: str
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime | None


class AssignmentRow(_Frozen):
    id: int
    spot_id: int
    apartment_id: int
    ownership_type: str
    valid_from: dt.datetime | None
    valid_until: dt.datetime | None
    status: str
    approved_by_user_id: int | None
    approved_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime | None


class OccupancyRow(_Frozen):
    zone_id: int
    entries: int
    exits: int
    occupancy: int
    capacity: int | None


def _page_model(name: str, row_type):
    return type(name, (_Frozen,), {
        "__annotations__": {
            "items": list[row_type], "total": int, "limit": int, "offset": int
        }
    })


SpotsPage = _page_model("SpotsPage", SpotRow)
AssignmentsPage = _page_model("AssignmentsPage", AssignmentRow)


def _spot_row(s) -> SpotRow:
    return SpotRow(
        id=s.id, zone_id=s.zone_id, code=s.code, status=s.status,
        created_at=s.created_at, updated_at=s.updated_at,
    )


def _assignment_row(a) -> AssignmentRow:
    return AssignmentRow(
        id=a.id, spot_id=a.spot_id, apartment_id=a.apartment_id,
        ownership_type=a.ownership_type, valid_from=a.valid_from,
        valid_until=a.valid_until, status=a.status,
        approved_by_user_id=a.approved_by_user_id, approved_at=a.approved_at,
        created_at=a.created_at, updated_at=a.updated_at,
    )


# ------------------------------ error mapping ------------------------------


def _raise_409_dup(exc) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": "duplicate_code", "message": str(exc)},
    )


def _raise_422_ref(exc) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"error": "invalid_reference", "message": str(exc)},
    )


def _raise_422_rented(exc) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"error": "rented_requires_valid_until", "message": str(exc)},
    )


def _raise_404(exc) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# =============================== МЕСТА ===============================


class SpotCreate(BaseModel):
    zone_id: int
    code: str = Field(..., min_length=1, max_length=_CODE_MAX)
    status: SpotStatusLit | None = None


class SpotPatch(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=_CODE_MAX)
    status: SpotStatusLit | None = None


@router.get("/spots", response_model=SpotsPage)
def list_spots(
    zone_id: int | None = Query(None),
    status_: SpotStatusLit | None = Query(None, alias="status"),
    limit: int = _limit_q(),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    rows, total = svc.list_spots(
        db, zone_id=zone_id, status=status_, limit=limit, offset=offset
    )
    return SpotsPage(
        items=[_spot_row(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("/spots", response_model=SpotRow, status_code=status.HTTP_201_CREATED)
def create_spot(
    body: SpotCreate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    try:
        spot = svc.create_spot(
            db, actor_user_id=user.id, zone_id=body.zone_id, code=body.code,
            status=body.status, ip_address=_client_ip(request),
        )
    except svc.InvalidReference as exc:
        _raise_422_ref(exc)
    except svc.DuplicateCode as exc:
        _raise_409_dup(exc)
    return _spot_row(spot)


@router.patch("/spots/{spot_id}", response_model=SpotRow)
def patch_spot(
    body: SpotPatch,
    request: Request,
    spot_id: int = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    fields = body.model_dump(exclude_unset=True)
    try:
        spot = svc.update_spot(
            db, spot_id=spot_id, actor_user_id=user.id, fields=fields,
            ip_address=_client_ip(request),
        )
    except svc.NotFound as exc:
        _raise_404(exc)
    except svc.DuplicateCode as exc:
        _raise_409_dup(exc)
    return _spot_row(spot)


# =============================== ЗАКРЕПЛЕНИЯ ===============================


class AssignmentCreate(BaseModel):
    spot_id: int
    apartment_id: int
    ownership_type: OwnershipTypeLit
    valid_from: dt.datetime | None = None
    valid_until: dt.datetime | None = None
    status: AssignmentStatusLit | None = None


class AssignmentPatch(BaseModel):
    status: AssignmentStatusLit | None = None
    valid_until: dt.datetime | None = None


@router.get("/spot-assignments", response_model=AssignmentsPage)
def list_spot_assignments(
    spot_id: int | None = Query(None),
    apartment_id: int | None = Query(None),
    status_: AssignmentStatusLit | None = Query(None, alias="status"),
    limit: int = _limit_q(),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    rows, total = svc.list_spot_assignments(
        db, spot_id=spot_id, apartment_id=apartment_id, status=status_,
        limit=limit, offset=offset,
    )
    return AssignmentsPage(
        items=[_assignment_row(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/spot-assignments", response_model=AssignmentRow,
    status_code=status.HTTP_201_CREATED,
)
def create_spot_assignment(
    body: AssignmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    try:
        assignment = svc.create_spot_assignment(
            db, actor_user_id=user.id, spot_id=body.spot_id,
            apartment_id=body.apartment_id, ownership_type=body.ownership_type,
            valid_from=body.valid_from, valid_until=body.valid_until,
            status=body.status, ip_address=_client_ip(request),
        )
    except svc.InvalidReference as exc:
        _raise_422_ref(exc)
    except svc.RentedRequiresValidUntil as exc:
        _raise_422_rented(exc)
    return _assignment_row(assignment)


@router.patch("/spot-assignments/{assignment_id}", response_model=AssignmentRow)
def patch_spot_assignment(
    body: AssignmentPatch,
    request: Request,
    assignment_id: int = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    fields = body.model_dump(exclude_unset=True)
    try:
        assignment = svc.update_spot_assignment(
            db, assignment_id=assignment_id, actor_user_id=user.id, fields=fields,
            ip_address=_client_ip(request),
        )
    except svc.NotFound as exc:
        _raise_404(exc)
    return _assignment_row(assignment)


# =============================== ЗАНЯТОСТЬ ЗОНЫ ===============================


@router.get("/zones/{zone_id}/occupancy", response_model=OccupancyRow)
def get_zone_occupancy(
    zone_id: int = Path(...),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*ZONE_GATE_ROLES)),
):
    """Учёт заездов зоны (§10.3): разрешённые въезды − выезды (выезд off → exits=0).

    ``capacity`` — информативная ёмкость зоны (для UI shared-зон). 404 — зоны нет.
    """
    try:
        zone = eq_svc.get_zone(db, zone_id)
    except eq_svc.NotFound as exc:
        _raise_404(exc)
    occ = zone_occupancy(db, zone_id)
    return OccupancyRow(
        zone_id=occ.zone_id, entries=occ.entries, exits=occ.exits,
        occupancy=occ.occupancy, capacity=zone.capacity,
    )
