"""WRITE/READ-операции admin над парковочными местами и закреплениями (§5, §6.2).

Этап 2 управления парковкой поверх реестра оборудования (``equipment_admin``):

* ``parking_spots`` — место в зоне (assigned-зона); создание/patch статуса, без
  удаления (деактивация ``status``); уникальность ``(zone_id, code)``;
* ``parking_spot_assignments`` — закрепление места ЗА КВАРТИРОЙ (решение владельца):
  любой активный авто квартиры (через ``vehicle_apartments``) пользуется её местом.
  ``owned`` может быть бессрочным; ``rented`` требует ``valid_until`` (срок аренды).
  Срок enforce'ится ЖИВО в Decision Engine (``spot_rental_expired`` по
  ``valid_until``) — отдельный воркер истечения НЕ нужен; статусом управляют вручную
  (revoke/продление).

Инварианты (как в ``equipment_admin``): каждое изменение пишет append-only
``access_audit_logs`` с hash-chain (§9.7) без ПД (§11); удаления нет; FK
(zone_id/spot_id/apartment_id) проверяются на существование → ``InvalidReference``
(HTTP 422); дубль ``(zone_id, code)`` → ``DuplicateCode`` (HTTP 409).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.domain.enums import OwnershipType
from access_control.domain.parking import ParkingSpot, ParkingSpotAssignment
from access_control.services.equipment_admin import (
    DuplicateCode,
    InvalidReference,
    NotFound,
    _zone_exists,
)
from access_control.services.management import write_audit
from access_control.services.parking_occupancy import apartment_spot_occupancy

__all__ = [
    "DuplicateCode",
    "InvalidReference",
    "NotFound",
    "RentedRequiresValidUntil",
    "list_spots",
    "create_spot",
    "update_spot",
    "list_spot_assignments",
    "create_spot_assignment",
    "update_spot_assignment",
    "assignment_occupancy",
]


class RentedRequiresValidUntil(Exception):
    """rented-закрепление без ``valid_until`` (срок обязателен) — 422."""


# --------------------------- хелперы существования ---------------------------


def _spot_code_taken(db: Session, zone_id: int, code: str) -> bool:
    return (
        db.query(ParkingSpot.id)
        .filter(ParkingSpot.zone_id == zone_id, ParkingSpot.code == code)
        .first()
        is not None
    )


def _apartment_exists(db: Session, apartment_id: int) -> bool:
    return (
        db.execute(
            text("SELECT 1 FROM apartments WHERE id = :a"), {"a": apartment_id}
        ).scalar()
        is not None
    )


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def assignment_occupancy(db: Session, assignment: ParkingSpotAssignment) -> tuple[int, int]:
    """``(occupied, spots)`` для квартиры закрепления в зоне его места (§10.3).

    Резолвит зону по ``spot_id`` и делегирует ``parking_occupancy`` (реюз источника
    лимита мест). Для UI «занято X из Y» в выдаче закреплений.
    """
    zone_id = db.execute(
        text("SELECT zone_id FROM parking_spots WHERE id = :s"),
        {"s": assignment.spot_id},
    ).scalar()
    if zone_id is None:
        return 0, 0
    return apartment_spot_occupancy(
        db, apartment_id=assignment.apartment_id, zone_id=zone_id
    )


# =============================== МЕСТА (parking_spots) ===============================


def list_spots(
    db: Session,
    *,
    zone_id: int | None = None,
    status: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[ParkingSpot], int]:
    query = db.query(ParkingSpot)
    if zone_id is not None:
        query = query.filter(ParkingSpot.zone_id == zone_id)
    if status is not None:
        query = query.filter(ParkingSpot.status == status)
    total = query.count()
    rows = query.order_by(ParkingSpot.id.desc()).limit(limit).offset(offset).all()
    return rows, total


def create_spot(
    db: Session,
    *,
    actor_user_id: int,
    zone_id: int,
    code: str,
    status: str | None = None,
    ip_address: str | None = None,
) -> ParkingSpot:
    if not _zone_exists(db, zone_id):
        raise InvalidReference(f"zone {zone_id} not found")
    if _spot_code_taken(db, zone_id, code):
        raise DuplicateCode(f"spot code {code!r} already exists in zone {zone_id}")
    spot = ParkingSpot(zone_id=zone_id, code=code)
    if status is not None:
        spot.status = status
    db.add(spot)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.spot_create",
        entity_type="parking_spot",
        entity_id=spot.id,
        details={"zone_id": zone_id, "code": code},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(spot)
    return spot


def update_spot(
    db: Session,
    *,
    spot_id: int,
    actor_user_id: int,
    fields: dict,
    ip_address: str | None = None,
) -> ParkingSpot:
    spot = db.get(ParkingSpot, spot_id)
    if spot is None:
        raise NotFound(f"spot {spot_id} not found")
    if (
        "code" in fields
        and fields["code"] != spot.code
        and _spot_code_taken(db, spot.zone_id, fields["code"])
    ):
        raise DuplicateCode(
            f"spot code {fields['code']!r} already exists in zone {spot.zone_id}"
        )
    for key, value in fields.items():
        setattr(spot, key, value)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.spot_update",
        entity_type="parking_spot",
        entity_id=spot.id,
        details={"fields": sorted(fields.keys())},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(spot)
    return spot


# ====================== ЗАКРЕПЛЕНИЯ (parking_spot_assignments) ======================


def list_spot_assignments(
    db: Session,
    *,
    spot_id: int | None = None,
    apartment_id: int | None = None,
    status: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[ParkingSpotAssignment], int]:
    query = db.query(ParkingSpotAssignment)
    if spot_id is not None:
        query = query.filter(ParkingSpotAssignment.spot_id == spot_id)
    if apartment_id is not None:
        query = query.filter(ParkingSpotAssignment.apartment_id == apartment_id)
    if status is not None:
        query = query.filter(ParkingSpotAssignment.status == status)
    total = query.count()
    rows = (
        query.order_by(ParkingSpotAssignment.id.desc()).limit(limit).offset(offset).all()
    )
    return rows, total


def create_spot_assignment(
    db: Session,
    *,
    actor_user_id: int,
    spot_id: int,
    apartment_id: int,
    ownership_type: str,
    valid_from: dt.datetime | None = None,
    valid_until: dt.datetime | None = None,
    status: str | None = None,
    ip_address: str | None = None,
) -> ParkingSpotAssignment:
    """Закрепить место за квартирой. ``approved_by_user_id``/``approved_at`` ставятся
    из текущего пользователя/now. ``rented`` требует ``valid_until``; ``owned`` может
    быть бессрочным (§5.1). Срок далее enforce'ится живо Decision Engine (§7)."""
    if db.get(ParkingSpot, spot_id) is None:
        raise InvalidReference(f"spot {spot_id} not found")
    if not _apartment_exists(db, apartment_id):
        raise InvalidReference(f"apartment {apartment_id} not found")
    if ownership_type == OwnershipType.RENTED.value and valid_until is None:
        raise RentedRequiresValidUntil(
            "rented assignment requires valid_until (срок аренды)"
        )
    assignment = ParkingSpotAssignment(
        spot_id=spot_id,
        apartment_id=apartment_id,
        ownership_type=ownership_type,
        valid_from=valid_from,
        valid_until=valid_until,
        approved_by_user_id=actor_user_id,
        approved_at=_utcnow(),
    )
    if status is not None:
        assignment.status = status
    db.add(assignment)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.spot_assignment_create",
        entity_type="parking_spot_assignment",
        entity_id=assignment.id,
        details={
            "spot_id": spot_id,
            "apartment_id": apartment_id,
            "ownership_type": ownership_type,
        },
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(assignment)
    return assignment


def update_spot_assignment(
    db: Session,
    *,
    assignment_id: int,
    actor_user_id: int,
    fields: dict,
    ip_address: str | None = None,
) -> ParkingSpotAssignment:
    """Изменить закрепление: revoke (``status``) или продление (``valid_until``).

    Истечение по сроку enforce'ится живо в Decision Engine — отдельного воркера нет.
    """
    assignment = db.get(ParkingSpotAssignment, assignment_id)
    if assignment is None:
        raise NotFound(f"spot assignment {assignment_id} not found")
    for key, value in fields.items():
        setattr(assignment, key, value)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.spot_assignment_update",
        entity_type="parking_spot_assignment",
        entity_id=assignment.id,
        details={"fields": sorted(fields.keys())},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(assignment)
    return assignment
