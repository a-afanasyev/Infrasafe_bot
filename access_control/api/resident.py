"""APPLICANT-API контроля доступа: личный кабинет жителя (§6.4, §16.2).

Единый API для бота И TWA (§4 п.4-5): клиент без бизнес-логики. Аутентификация —
существующая JWT/cookie (``require_approved_roles``, НЕ device-auth). RBAC: только
роль ``applicant`` (личный кабинет жителя); прочие роли → 403, без auth → 401.

КЛЮЧЕВАЯ ГРАНИЦА (§6.4): житель видит/создаёт ТОЛЬКО для своих approved-квартир
(``user_apartments.status='approved'``). Чужой ``apartment_id``/чужой пропуск → 403.

Эндпоинты:
* ``GET  /my/vehicles``  — авто approved-квартир (vehicle_apartments active);
* ``GET  /my/passes``    — пропуска своих квартир ИЛИ созданные собой (фильтр status);
* ``GET  /my/requests``  — заявки свои ИЛИ по своим квартирам (фильтр status);
* ``GET  /my/events``    — события по своим авто/квартирам;
* ``POST /requests``     — заявка на постоянный авто (pending);
* ``POST /passes``       — временный пропуск taxi|guest|delivery (active, source=resident);
* ``POST /passes/{id}/cancel`` — отмена своего пропуска (revoked), идемпотентно.

Конверт списка единый: ``{items, total, limit, offset}``. Пагинация: ``limit``
дефолт 50, max 200; ``offset`` ≥ 0. Сортировка по времени desc. Валидация тела —
pydantic (422).
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from access_control.api.registry import (
    ApartmentLink,
    PassesPage,
    PassRow,
    RequestRow,
    RequestsPage,
    VehicleRow,
    VehiclesPage,
)
from access_control.services.resident import (
    ApartmentNotOwned,
    PassNotFound,
    PassNotOwned,
    ZoneNotResolved,
    approved_apartment_ids,
    cancel_resident_pass,
    create_resident_pass,
    create_resident_request,
    list_resident_events,
    list_resident_passes,
    list_resident_requests,
    list_resident_vehicles,
)
from uk_management_bot.api.dependencies import require_approved_roles
from uk_management_bot.database.session import get_db

router = APIRouter(prefix="/api/v1/access", tags=["access-resident"])

# RBAC (§6.4): личный кабинет жителя — только applicant. Прочие роли → 403.
RESIDENT_ROLES = ("applicant",)

# Пагинация (общая для всех списков жителя).
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# Лимиты длины пользовательских строк (защита от чрезмерного ввода).
_PLATE_MAX_LEN = 32
_TEXT_MAX_LEN = 64

# Типы пропусков, доступные жителю (§6.4). Совпадает с RESIDENT_PASS_TYPES сервиса.
ResidentPassType = "taxi", "guest", "delivery"


def _client_ip(request: Request) -> str | None:
    """IP источника для audit (§6.4). Для пилота достаточно client.host."""
    return request.client.host if request.client else None


def _limit(value: int) -> int:
    return Query(value, ge=1, le=MAX_LIMIT, description="размер страницы (max 200)")


# ------------------------------ тела запросов ------------------------------


class CreateResidentRequest(BaseModel):
    """Заявка жителя на постоянный авто (§6.4)."""

    apartment_id: int
    plate_number_original: str = Field(..., min_length=1, max_length=_PLATE_MAX_LEN)
    relation_type: str | None = Field(
        None, description="owner|tenant|family|service"
    )
    # Марка/модель/цвет — необязательные подсказки клиента. В пилоте у заявки нет
    # колонок под них (DATA_MODEL_PILOT фиксирует минимальную модель); атрибуты
    # авто задаёт менеджер при подтверждении (создании vehicle). Принимаются для
    # совместимости контракта клиента (бот+TWA), но не сохраняются.
    brand: str | None = Field(None, max_length=_TEXT_MAX_LEN)
    model: str | None = Field(None, max_length=_TEXT_MAX_LEN)
    color: str | None = Field(None, max_length=_TEXT_MAX_LEN)

    @model_validator(mode="after")
    def _validate(self) -> "CreateResidentRequest":
        if not self.plate_number_original.strip():
            raise ValueError("plate_number_original must be non-empty")
        if self.relation_type is not None and self.relation_type not in (
            "owner", "tenant", "family", "service"
        ):
            raise ValueError("relation_type must be owner|tenant|family|service")
        return self


class CreateResidentPass(BaseModel):
    """Временный пропуск жителем (единая модель §5.4, §6.4)."""

    apartment_id: int
    pass_type: str = Field(..., description="taxi|guest|delivery")
    valid_until: dt.datetime
    plate_number_original: str | None = Field(None, max_length=_PLATE_MAX_LEN)
    valid_from: dt.datetime | None = None
    max_entries: int = Field(1, ge=1, le=100)
    zone_id: int | None = None

    @model_validator(mode="after")
    def _validate(self) -> "CreateResidentPass":
        if self.pass_type not in ResidentPassType:
            raise ValueError(f"pass_type must be one of {ResidentPassType}")
        if self.valid_from is not None and self.valid_from > self.valid_until:
            raise ValueError("valid_from must be <= valid_until")
        return self


class CancelResponse(BaseModel):
    ok: bool
    pass_id: int
    status: str
    replayed: bool


# ------------------------------ DTO событий ------------------------------


class ResidentEventRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    event_id: str
    occurred_at: dt.datetime
    direction: str
    gate_id: int | None
    zone_id: int | None
    apartment_id: int | None
    plate_number_normalized: str | None
    decision: str | None
    reason: str | None


class ResidentEventsPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ResidentEventRow]
    total: int
    limit: int
    offset: int


# ------------------------------ READ: /my/vehicles ------------------------------


def _owned_apartment_links(db: Session, vehicle_ids: list[int],
                           apartment_ids: list[int]) -> dict[int, list[ApartmentLink]]:
    """Связи vehicle_apartments, ограниченные approved-квартирами пользователя (§6.4).

    Возвращаются ТОЛЬКО связи со «своими» квартирами — чужие привязки авто наружу
    не отдаются.
    """
    if not vehicle_ids:
        return {}
    stmt = text(
        "SELECT vehicle_id, apartment_id, relation_type, status, valid_from, "
        " valid_until, approved_by_user_id, approved_at "
        "FROM vehicle_apartments "
        "WHERE vehicle_id IN :vids AND apartment_id IN :apts ORDER BY id"
    ).bindparams(
        bindparam("vids", expanding=True), bindparam("apts", expanding=True)
    )
    out: dict[int, list[ApartmentLink]] = {vid: [] for vid in vehicle_ids}
    for r in db.execute(stmt, {"vids": vehicle_ids, "apts": apartment_ids}).mappings():
        out[r["vehicle_id"]].append(
            ApartmentLink(
                apartment_id=r["apartment_id"],
                relation_type=r["relation_type"],
                status=r["status"],
                valid_from=r["valid_from"],
                valid_until=r["valid_until"],
                approved_by_user_id=r["approved_by_user_id"],
                approved_at=r["approved_at"],
            )
        )
    return out


@router.get("/my/vehicles", response_model=VehiclesPage)
def my_vehicles(
    limit: int = _limit(DEFAULT_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*RESIDENT_ROLES)),
) -> VehiclesPage:
    """Авто, активно привязанные к approved-квартирам жителя (§6.4)."""
    rows, total = list_resident_vehicles(db, user_id=user.id, limit=limit, offset=offset)
    if not rows:
        return VehiclesPage(items=[], total=total, limit=limit, offset=offset)
    apts = approved_apartment_ids(db, user.id)
    links = _owned_apartment_links(db, [r["id"] for r in rows], apts)
    items = [
        VehicleRow(
            id=r["id"],
            plate_number_original=r["plate_number_original"],
            plate_number_normalized=r["plate_number_normalized"],
            plate_country=r["plate_country"],
            plate_type=r["plate_type"],
            brand=r["make"],
            model=r["model"],
            color=r["color"],
            vehicle_class=r["vehicle_class"],
            status=r["status"],
            blocked_reason=r["blocked_reason"],
            blocked_by_user_id=r["blocked_by_user_id"],
            blocked_at=r["blocked_at"],
            apartments=links.get(r["id"], []),
        )
        for r in rows
    ]
    return VehiclesPage(items=items, total=total, limit=limit, offset=offset)


# ------------------------------ READ: /my/passes ------------------------------


@router.get("/my/passes", response_model=PassesPage)
def my_passes(
    status_: str | None = Query(None, alias="status"),
    limit: int = _limit(DEFAULT_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*RESIDENT_ROLES)),
) -> PassesPage:
    """Пропуска квартир жителя ИЛИ созданные им самим (§6.4). Фильтр ``status``."""
    rows, total = list_resident_passes(
        db, user_id=user.id, status=status_, limit=limit, offset=offset
    )
    items = [PassRow(**r) for r in rows]
    return PassesPage(items=items, total=total, limit=limit, offset=offset)


# ------------------------------ READ: /my/requests ------------------------------


@router.get("/my/requests", response_model=RequestsPage)
def my_requests(
    status_: str | None = Query(None, alias="status"),
    limit: int = _limit(DEFAULT_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*RESIDENT_ROLES)),
) -> RequestsPage:
    """Заявки жителя на постоянный авто: созданные им ИЛИ по его квартирам (§6.4)."""
    rows, total = list_resident_requests(
        db, user_id=user.id, status=status_, limit=limit, offset=offset
    )
    items = [RequestRow(**r) for r in rows]
    return RequestsPage(items=items, total=total, limit=limit, offset=offset)


# ------------------------------ READ: /my/events ------------------------------


@router.get("/my/events", response_model=ResidentEventsPage)
def my_events(
    limit: int = _limit(DEFAULT_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*RESIDENT_ROLES)),
) -> ResidentEventsPage:
    """События проезда по авто/квартирам жителя (§6.4: только свои события).

    Сопоставление: ``apartment_id`` ∈ approved-квартиры жителя ИЛИ
    ``plate_number_normalized`` ∈ номера авто его квартир (покрывает и постоянный
    авто, и taxi-pass, где apartment_id у события может отсутствовать).
    """
    rows, total = list_resident_events(db, user_id=user.id, limit=limit, offset=offset)
    items = [ResidentEventRow(**r) for r in rows]
    return ResidentEventsPage(items=items, total=total, limit=limit, offset=offset)


# ------------------------------ WRITE: /requests ------------------------------


@router.post("/requests", response_model=RequestRow, status_code=status.HTTP_201_CREATED)
def post_request(
    body: CreateResidentRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*RESIDENT_ROLES)),
) -> RequestRow:
    """Создать заявку на постоянный авто (§6.4). 403 если квартира не своя."""
    try:
        req = create_resident_request(
            db,
            actor_user_id=user.id,
            apartment_id=body.apartment_id,
            plate_number_original=body.plate_number_original,
            relation_type=body.relation_type,
            ip_address=_client_ip(request),
        )
    except ApartmentNotOwned as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return RequestRow(
        id=req.id,
        apartment_id=req.apartment_id,
        created_by_user_id=req.created_by_user_id,
        vehicle_id=req.vehicle_id,
        plate_number_original=req.plate_number_original,
        plate_number_normalized=req.plate_number_normalized,
        relation_type=req.relation_type,
        status=req.status,
        reviewed_by_user_id=req.reviewed_by_user_id,
        reviewed_at=req.reviewed_at,
        review_comment=req.review_comment,
        created_at=req.created_at,
    )


# ------------------------------ WRITE: /passes ------------------------------


@router.post("/passes", response_model=PassRow, status_code=status.HTTP_201_CREATED)
def post_pass(
    body: CreateResidentPass,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*RESIDENT_ROLES)),
) -> PassRow:
    """Создать временный пропуск (§6.4). 403 если квартира не своя; 422 если зона
    не определена однозначно (нужен ``zone_id``)."""
    try:
        ap = create_resident_pass(
            db,
            actor_user_id=user.id,
            apartment_id=body.apartment_id,
            pass_type=body.pass_type,
            valid_until=body.valid_until,
            plate_number_original=body.plate_number_original,
            valid_from=body.valid_from,
            max_entries=body.max_entries,
            zone_id=body.zone_id,
            ip_address=_client_ip(request),
        )
    except ApartmentNotOwned as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ZoneNotResolved as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "zone_not_resolved", "message": str(exc)},
        )
    return PassRow(
        id=ap.id,
        pass_type=ap.pass_type,
        apartment_id=ap.apartment_id,
        created_by_user_id=ap.created_by_user_id,
        zone_id=ap.zone_id,
        plate_number_original=ap.plate_number_original,
        plate_number_normalized=ap.plate_number_normalized,
        valid_from=ap.valid_from,
        valid_until=ap.valid_until,
        max_entries=ap.max_entries,
        used_entries=ap.used_entries,
        status=ap.status,
        source=ap.source,
        created_at=ap.created_at,
    )


@router.post("/passes/{pass_id}/cancel", response_model=CancelResponse)
def post_cancel_pass(
    request: Request,
    pass_id: int = Path(..., description="access_passes.id"),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*RESIDENT_ROLES)),
) -> CancelResponse:
    """Отменить свой пропуск → ``revoked`` (§6.4). Идемпотентно. 404/403 для чужого."""
    try:
        outcome = cancel_resident_pass(
            db,
            actor_user_id=user.id,
            pass_id=pass_id,
            ip_address=_client_ip(request),
        )
    except PassNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="pass not found"
        )
    except PassNotOwned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="pass not owned"
        )
    return CancelResponse(
        ok=True,
        pass_id=outcome.pass_id,
        status=outcome.status,
        replayed=outcome.replayed,
    )
