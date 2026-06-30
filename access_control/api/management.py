"""WRITE-эндпоинты менеджера (§13.2, §6.2, §4 п.7).

Менеджерские операции записи поверх общей базы access_control (USER-API, JWT/
cookie — ``require_approved_roles``, НЕ device-auth):

* ``POST  /api/v1/access/vehicles`` — создать постоянный авто (+ привязка/правило);
* ``PATCH /api/v1/access/vehicles/{id}/status`` — active|blocked|archived;
* ``POST  /api/v1/access/passes/taxi`` — taxi-пропуск;
* ``POST  /api/v1/access/requests/{id}/review`` — рассмотреть заявку жителя.

RBAC (§6.2/§6.3): только ``manager``/``system_admin`` управляют базой авто/
пропусков/заявок. security_operator/applicant/executor/inspector → 403; без auth
→ 401. Валидация на границе — pydantic (422). Каждое изменение фиксируется в
``access_audit_logs`` с актором и IP (§6.2, §9.7); ПД в логи не пишутся (§11).

Форма ответа повторяет read-контракт реестра (``VehicleRow``/``PassRow``) — фронт
переиспользует ту же модель; review возвращает ``{ok, request_id, status,
vehicle_id, replayed}``.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from access_control.api.registry import ApartmentLink, PassRow, VehicleRow
from access_control.domain.passes import AccessPass
from access_control.domain.vehicles import Vehicle, VehicleApartment
from access_control.services.management import (
    InvalidReviewAction,
    PassNotFound,
    RequestNotFound,
    VehicleAlreadyExists,
    VehicleNotFound,
    create_taxi_pass,
    create_vehicle,
    review_request,
    set_vehicle_status,
    update_pass,
    update_vehicle,
)
from uk_management_bot.api.dependencies import require_approved_roles
from uk_management_bot.database.session import get_db

router = APIRouter(prefix="/api/v1/access", tags=["access-management"])

# RBAC (§6.2): база авто/пропусков/заявок — только менеджер/админ.
MANAGEMENT_ROLES = ("manager", "system_admin")

# Лимиты длины пользовательских строк (защита от чрезмерного ввода в audit/БД).
_PLATE_MAX_LEN = 32
_REASON_MAX_LEN = 2000
_TEXT_MAX_LEN = 64
_COMMENT_MAX_LEN = 2000


def _client_ip(request: Request) -> str | None:
    """IP источника для audit (§6.2). Для пилота достаточно client.host."""
    return request.client.host if request.client else None


# ------------------------------ тела запросов ------------------------------


class CreateVehicleRequest(BaseModel):
    plate_number_original: str = Field(..., min_length=1, max_length=_PLATE_MAX_LEN)
    plate_country: str | None = Field(None, max_length=8)
    plate_type: str | None = Field(None, max_length=_TEXT_MAX_LEN)
    brand: str | None = Field(None, max_length=_TEXT_MAX_LEN)
    model: str | None = Field(None, max_length=_TEXT_MAX_LEN)
    color: str | None = Field(None, max_length=_TEXT_MAX_LEN)
    vehicle_class: str | None = Field(None, max_length=_TEXT_MAX_LEN)
    apartment_id: int | None = None
    relation_type: Literal["owner", "tenant", "family", "service"] | None = None
    zone_id: int | None = None

    @model_validator(mode="after")
    def _non_blank_plate(self) -> "CreateVehicleRequest":
        if not self.plate_number_original.strip():
            raise ValueError("plate_number_original must be non-empty")
        return self


class VehicleStatusRequest(BaseModel):
    status: Literal["active", "blocked", "archived"]
    reason: str | None = Field(None, max_length=_REASON_MAX_LEN)

    @model_validator(mode="after")
    def _blocked_requires_reason(self) -> "VehicleStatusRequest":
        if self.status == "blocked" and not (self.reason and self.reason.strip()):
            raise ValueError("blocked status requires non-empty reason")
        return self


class UpdateVehicleRequest(BaseModel):
    """Правка карточки авто (§6.2). PATCH: применяются только переданные поля.

    Смена ``plate_number_original`` ре-нормализуется и проверяется на дубль.
    ``apartment_id``/``relation_type`` — перепривязка владельца.
    """

    plate_number_original: str | None = Field(
        None, min_length=1, max_length=_PLATE_MAX_LEN
    )
    plate_country: str | None = Field(None, max_length=8)
    plate_type: str | None = Field(None, max_length=_TEXT_MAX_LEN)
    brand: str | None = Field(None, max_length=_TEXT_MAX_LEN)
    model: str | None = Field(None, max_length=_TEXT_MAX_LEN)
    color: str | None = Field(None, max_length=_TEXT_MAX_LEN)
    vehicle_class: str | None = Field(None, max_length=_TEXT_MAX_LEN)
    apartment_id: int | None = None
    relation_type: Literal["owner", "tenant", "family", "service"] | None = None
    # Явные зоны доступа авто (чекбоксы). Передан → синхронизируется набор правил.
    zone_ids: list[int] | None = None


class UpdatePassRequest(BaseModel):
    """Правка пропуска (§13.2). PATCH: применяются только переданные поля.

    ``status='revoked'`` отзывает пропуск (иное значение не принимается).
    ``zone_id`` меняет зону пропуска (None — снять ограничение зоной).
    """

    valid_until: dt.datetime | None = None
    max_entries: int | None = Field(None, ge=1, le=100)
    plate_number_original: str | None = Field(None, max_length=_PLATE_MAX_LEN)
    zone_id: int | None = None
    status: Literal["revoked"] | None = None


class TaxiPassRequest(BaseModel):
    apartment_id: int
    # zone_id опционален: None → дефолт по адресу жителя (первая обслуживающая зона).
    zone_id: int | None = None
    valid_until: dt.datetime
    plate_number_original: str | None = Field(None, max_length=_PLATE_MAX_LEN)
    valid_from: dt.datetime | None = None
    max_entries: int = Field(1, ge=1, le=100)

    @model_validator(mode="after")
    def _window_ok(self) -> "TaxiPassRequest":
        if self.valid_from is not None and self.valid_from > self.valid_until:
            raise ValueError("valid_from must be <= valid_until")
        return self


class ReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    comment: str | None = Field(None, max_length=_COMMENT_MAX_LEN)
    # Зоны при approve (чекбоксы). zone_ids приоритетнее одиночного zone_id.
    zone_id: int | None = None
    zone_ids: list[int] | None = None


class ReviewResponse(BaseModel):
    ok: bool
    request_id: int
    status: str
    vehicle_id: int | None
    replayed: bool


# ------------------------------ сборка ответа ------------------------------


def _links_for(db: Session, vehicle_id: int) -> list[ApartmentLink]:
    rows = (
        db.query(VehicleApartment)
        .filter(VehicleApartment.vehicle_id == vehicle_id)
        .order_by(VehicleApartment.id)
        .all()
    )
    return [
        ApartmentLink(
            apartment_id=link.apartment_id,
            relation_type=link.relation_type,
            status=link.status,
            valid_from=link.valid_from,
            valid_until=link.valid_until,
            approved_by_user_id=link.approved_by_user_id,
            approved_at=link.approved_at,
        )
        for link in rows
    ]


def _vehicle_response(db: Session, vehicle: Vehicle) -> VehicleRow:
    return VehicleRow(
        id=vehicle.id,
        plate_number_original=vehicle.plate_number_original,
        plate_number_normalized=vehicle.plate_number_normalized,
        plate_country=vehicle.plate_country,
        plate_type=vehicle.plate_type,
        brand=vehicle.make,
        model=vehicle.model,
        color=vehicle.color,
        vehicle_class=vehicle.vehicle_class,
        status=vehicle.status,
        blocked_reason=vehicle.blocked_reason,
        blocked_by_user_id=vehicle.blocked_by_user_id,
        blocked_at=vehicle.blocked_at,
        apartments=_links_for(db, vehicle.id),
    )


def _pass_response(ap: AccessPass) -> PassRow:
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


# ------------------------------ эндпоинты ------------------------------


@router.post(
    "/vehicles", response_model=VehicleRow, status_code=status.HTTP_201_CREATED
)
def post_vehicle(
    body: CreateVehicleRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*MANAGEMENT_ROLES)),
) -> VehicleRow:
    """Создать постоянный авто (§6.2). 409 при активном дубле номера."""
    try:
        vehicle = create_vehicle(
            db,
            actor_user_id=user.id,
            plate_number_original=body.plate_number_original,
            plate_country=body.plate_country,
            plate_type=body.plate_type,
            brand=body.brand,
            model=body.model,
            color=body.color,
            vehicle_class=body.vehicle_class,
            apartment_id=body.apartment_id,
            relation_type=body.relation_type,
            zone_id=body.zone_id,
            ip_address=_client_ip(request),
        )
    except VehicleAlreadyExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "vehicle_already_exists", "message": str(exc)},
        )
    return _vehicle_response(db, vehicle)


@router.patch("/vehicles/{vehicle_id}/status", response_model=VehicleRow)
def patch_vehicle_status(
    body: VehicleStatusRequest,
    request: Request,
    vehicle_id: int = Path(..., description="vehicles.id"),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*MANAGEMENT_ROLES)),
) -> VehicleRow:
    """Сменить статус авто: active|blocked|archived (§6.2). blocked требует reason."""
    try:
        vehicle = set_vehicle_status(
            db,
            vehicle_id=vehicle_id,
            status=body.status,
            actor_user_id=user.id,
            reason=body.reason,
            ip_address=_client_ip(request),
        )
    except VehicleNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="vehicle not found"
        )
    return _vehicle_response(db, vehicle)


@router.patch("/vehicles/{vehicle_id}", response_model=VehicleRow)
def patch_vehicle(
    body: UpdateVehicleRequest,
    request: Request,
    vehicle_id: int = Path(..., description="vehicles.id"),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*MANAGEMENT_ROLES)),
) -> VehicleRow:
    """Отредактировать карточку авто (§6.2): атрибуты, номер, привязка владельца.

    409 при смене номера на активный дубль; 404 если авто нет.
    """
    fields = body.model_dump(exclude_unset=True)
    try:
        vehicle = update_vehicle(
            db,
            vehicle_id=vehicle_id,
            actor_user_id=user.id,
            fields=fields,
            ip_address=_client_ip(request),
        )
    except VehicleNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="vehicle not found"
        )
    except VehicleAlreadyExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "vehicle_already_exists", "message": str(exc)},
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return _vehicle_response(db, vehicle)


@router.post(
    "/passes/taxi", response_model=PassRow, status_code=status.HTTP_201_CREATED
)
def post_taxi_pass(
    body: TaxiPassRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*MANAGEMENT_ROLES)),
) -> PassRow:
    """Создать taxi-пропуск (§13.2)."""
    ap = create_taxi_pass(
        db,
        actor_user_id=user.id,
        apartment_id=body.apartment_id,
        zone_id=body.zone_id,
        valid_until=body.valid_until,
        plate_number_original=body.plate_number_original,
        valid_from=body.valid_from,
        max_entries=body.max_entries,
        ip_address=_client_ip(request),
    )
    return _pass_response(ap)


@router.patch("/passes/{pass_id}", response_model=PassRow)
def patch_pass(
    body: UpdatePassRequest,
    request: Request,
    pass_id: int = Path(..., description="access_passes.id"),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*MANAGEMENT_ROLES)),
) -> PassRow:
    """Отредактировать пропуск (§13.2): срок/лимит/номер; status=revoked — отзыв."""
    fields = body.model_dump(exclude_unset=True)
    try:
        ap = update_pass(
            db,
            pass_id=pass_id,
            actor_user_id=user.id,
            fields=fields,
            ip_address=_client_ip(request),
        )
    except PassNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="pass not found"
        )
    return _pass_response(ap)


@router.post("/requests/{request_id}/review", response_model=ReviewResponse)
def post_review(
    body: ReviewRequest,
    request: Request,
    request_id: int = Path(..., description="resident_access_requests.id"),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*MANAGEMENT_ROLES)),
) -> ReviewResponse:
    """Рассмотреть заявку жителя: approve|reject (§6.2, §4 п.7). Идемпотентно."""
    try:
        outcome = review_request(
            db,
            request_id=request_id,
            action=body.action,
            actor_user_id=user.id,
            comment=body.comment,
            zone_id=body.zone_id,
            zone_ids=body.zone_ids,
            ip_address=_client_ip(request),
        )
    except RequestNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="request not found"
        )
    except InvalidReviewAction as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return ReviewResponse(
        ok=True,
        request_id=outcome.request_id,
        status=outcome.status,
        vehicle_id=outcome.vehicle_id,
        replayed=outcome.replayed,
    )
