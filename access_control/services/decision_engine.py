"""Decision Engine пилота (§7 шаги 4–8). Постоянный авто + taxi-pass.

Чистая решающая логика: по входному DTO и сессии БД возвращает ``EngineDecision``
с типом ``allow|deny|manual_review`` и канонической причиной из enum
``DecisionReason``. Движок НЕ пишет в БД — только читает; запись и атомарный
расход пропуска выполняет ingestion (§7 шаг 9). anti-passback в пилоте выключен
(§10.3).

Покрытые ветви:
* confidence ниже порога → manual_review / low_confidence (§9.4);
* активный постоянный авто (vehicles active + active vehicle_apartments +
  access_rules зона/срок/направление) → allow / permanent_vehicle_allowed (§7 5–6);
* заблокированный авто → deny / vehicle_blocked;
* активный авто без валидного правила зоны → deny / zone_not_allowed;
* активный taxi-pass (зона/окно/лимит) → allow / temporary_pass_allowed (§7 7–8);
* истёкший / исчерпанный pass → deny / pass_expired | pass_already_used;
* ничего не найдено → deny / vehicle_not_found.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.domain.enums import (
    DecisionReason,
    DecisionStatus,
    DecisionType,
    ParkingType,
)
from access_control.domain.parking import ParkingSpot, ParkingSpotAssignment
from access_control.domain.passes import AccessPass, AccessRule
from access_control.domain.territory import ParkingZone
from access_control.domain.vehicles import Vehicle, VehicleApartment

# Порог confidence по умолчанию (конфигурируемый). Ниже — аномалия (§9.4).
DEFAULT_CONFIDENCE_THRESHOLD = 0.70


@dataclass(frozen=True)
class AnprDecisionInput:
    """Иммутабельный вход движка (§7). Номер уже нормализован ingestion (§12)."""

    controller_id: int
    zone_id: int | None
    gate_id: int | None
    camera_id: int | None
    plate_number_normalized: str
    recognition_key: str | None
    direction: str
    confidence: float | None
    captured_at: dt.datetime


@dataclass(frozen=True)
class EngineDecision:
    """Иммутабельное решение движка. ``status`` — кандидат для access_decisions."""

    decision: str
    reason: str
    status: str
    matched_vehicle_id: int | None = None
    matched_pass_id: int | None = None


def _within_window(
    moment: dt.datetime,
    valid_from: dt.datetime | None,
    valid_until: dt.datetime | None,
) -> bool:
    """Проверить попадание ``moment`` в окно [from, until]; ``None`` — открытая граница."""
    if valid_from is not None and moment < valid_from:
        return False
    if valid_until is not None and moment > valid_until:
        return False
    return True


def _allow(reason: str, **matched) -> EngineDecision:
    return EngineDecision(
        decision=DecisionType.ALLOW.value,
        reason=reason,
        status=DecisionStatus.ALLOWED.value,
        **matched,
    )


def _deny(reason: str, **matched) -> EngineDecision:
    return EngineDecision(
        decision=DecisionType.DENY.value,
        reason=reason,
        status=DecisionStatus.DENIED.value,
        **matched,
    )


def _manual_review(reason: str, **matched) -> EngineDecision:
    return EngineDecision(
        decision=DecisionType.MANUAL_REVIEW.value,
        reason=reason,
        status=DecisionStatus.PENDING_REVIEW.value,
        **matched,
    )


def _active_apartment_ids(db: Session, vehicle_id: int, moment: dt.datetime) -> list[int]:
    """ID квартир с активной связью авто↔квартира на момент события (§5.3)."""
    links = (
        db.query(VehicleApartment)
        .filter(
            VehicleApartment.vehicle_id == vehicle_id,
            VehicleApartment.status == "active",
        )
        .all()
    )
    return [
        link.apartment_id
        for link in links
        if _within_window(moment, link.valid_from, link.valid_until)
    ]


def _zone_rule_matches(
    db: Session,
    *,
    vehicle_id: int,
    apartment_ids: list[int],
    zone_id: int | None,
    direction: str,
    moment: dt.datetime,
) -> bool:
    """Найти активное правило доступа: зона + срок + направление (§7 шаг 6)."""
    rules = (
        db.query(AccessRule)
        .filter(
            AccessRule.is_active.is_(True),
            AccessRule.zone_id == zone_id,
        )
        .all()
    )
    for rule in rules:
        scoped = rule.vehicle_id == vehicle_id or (
            rule.apartment_id is not None and rule.apartment_id in apartment_ids
        )
        if not scoped:
            continue
        if not _within_window(moment, rule.valid_from, rule.valid_until):
            continue
        allowed = rule.allowed_directions
        if allowed and direction not in allowed:
            continue
        return True
    return False


def _apartment_served_by_zone(db: Session, apartment_id: int, zone_id: int) -> bool:
    """Квартира обслуживается зоной: apartment→building→yard ∈ зоны (§5.1).

    Связь зоны с фазами ЖК — через ``parking_zone_yards`` (зона↔yard); квартира
    привязана к yard через building.
    """
    row = db.execute(
        text(
            "SELECT 1 FROM apartments a "
            "JOIN buildings b ON a.building_id = b.id "
            "JOIN parking_zone_yards pzy ON pzy.yard_id = b.yard_id "
            "WHERE a.id = :apt AND pzy.zone_id = :zone LIMIT 1"
        ),
        {"apt": apartment_id, "zone": zone_id},
    ).first()
    return row is not None


def _count_active_apartment_vehicles(
    db: Session, apartment_id: int, moment: dt.datetime
) -> int:
    """Число активных авто квартиры (§5.3): active vehicle_apartments × active vehicle."""
    links = (
        db.query(VehicleApartment)
        .join(Vehicle, Vehicle.id == VehicleApartment.vehicle_id)
        .filter(
            VehicleApartment.apartment_id == apartment_id,
            VehicleApartment.status == "active",
            Vehicle.status == "active",
        )
        .all()
    )
    return sum(
        1
        for link in links
        if _within_window(moment, link.valid_from, link.valid_until)
    )


def _decide_assigned(
    db: Session,
    *,
    vehicle: Vehicle,
    apartment_ids: list[int],
    zone_id: int | None,
    moment: dt.datetime,
) -> EngineDecision:
    """assigned-зона (§5.1): место закреплено за квартирой авто.

    allow ``assigned_spot_allowed`` — активное закрепление в окне дат;
    deny ``spot_rental_expired`` — есть только просроченное (valid_until прошёл);
    deny ``spot_not_assigned`` — закрепления нет.
    """
    if not apartment_ids:
        return _deny(
            DecisionReason.SPOT_NOT_ASSIGNED.value, matched_vehicle_id=vehicle.id
        )
    rows = (
        db.query(ParkingSpotAssignment)
        .join(ParkingSpot, ParkingSpot.id == ParkingSpotAssignment.spot_id)
        .filter(
            ParkingSpot.zone_id == zone_id,
            ParkingSpot.status == "active",
            ParkingSpotAssignment.apartment_id.in_(apartment_ids),
            ParkingSpotAssignment.status.in_(("active", "expired")),
        )
        .all()
    )
    active_in_window = any(
        r.status == "active"
        and _within_window(moment, r.valid_from, r.valid_until)
        for r in rows
    )
    if active_in_window:
        return _allow(
            DecisionReason.ASSIGNED_SPOT_ALLOWED.value,
            matched_vehicle_id=vehicle.id,
        )
    expired = any(r.valid_until is not None and moment > r.valid_until for r in rows)
    if expired:
        return _deny(
            DecisionReason.SPOT_RENTAL_EXPIRED.value, matched_vehicle_id=vehicle.id
        )
    return _deny(
        DecisionReason.SPOT_NOT_ASSIGNED.value, matched_vehicle_id=vehicle.id
    )


def _decide_shared(
    db: Session,
    *,
    vehicle: Vehicle,
    apartment_ids: list[int],
    zone: ParkingZone,
    moment: dt.datetime,
) -> EngineDecision:
    """shared-зона (§5.1): разрешены все авто обслуживаемой зоной квартиры.

    allow ``shared_access_allowed``; гибкий кап
    ``max_permanent_vehicles_per_apartment`` (NULL — без лимита): превышение →
    manual_review ``per_apartment_limit_exceeded``. Если квартира не обслуживается
    зоной → deny ``zone_not_allowed`` (как до фичи).
    """
    served = [
        apt
        for apt in apartment_ids
        if _apartment_served_by_zone(db, apt, zone.id)
    ]
    if not served:
        return _deny(
            DecisionReason.ZONE_NOT_ALLOWED.value, matched_vehicle_id=vehicle.id
        )
    cap = zone.max_permanent_vehicles_per_apartment
    if cap is not None:
        for apt in served:
            if _count_active_apartment_vehicles(db, apt, moment) > cap:
                return _manual_review(
                    DecisionReason.PER_APARTMENT_LIMIT_EXCEEDED.value,
                    matched_vehicle_id=vehicle.id,
                )
    return _allow(
        DecisionReason.SHARED_ACCESS_ALLOWED.value, matched_vehicle_id=vehicle.id
    )


def _decide_permanent(db: Session, data: AnprDecisionInput) -> EngineDecision | None:
    """Ветвь постоянного авто (§7 шаги 5–6). ``None`` — авто не найдено.

    Порядок: блокировка → СОВМЕСТИМОСТЬ (явный ``access_rule`` остаётся allow-веткой
    ``permanent_vehicle_allowed``, держит существующие тесты) → зоно-типная логика
    (assigned/shared) по ``parking_zones.parking_type``.
    """
    vehicle = (
        db.query(Vehicle)
        .filter(
            Vehicle.plate_number_normalized == data.plate_number_normalized,
            Vehicle.status != "archived",
        )
        .first()
    )
    if vehicle is None:
        return None
    if vehicle.status == "blocked":
        return _deny(
            DecisionReason.VEHICLE_BLOCKED.value, matched_vehicle_id=vehicle.id
        )
    apartment_ids = _active_apartment_ids(db, vehicle.id, data.captured_at)
    # Совместимость: явное правило зоны (§7 шаг 6, решение CTO #5) — allow-ветка.
    # vehicle-scoped правило валидно и без активных apartment-связей.
    rule_ok = _zone_rule_matches(
        db,
        vehicle_id=vehicle.id,
        apartment_ids=apartment_ids,
        zone_id=data.zone_id,
        direction=data.direction,
        moment=data.captured_at,
    )
    if rule_ok:
        return _allow(
            DecisionReason.PERMANENT_VEHICLE_ALLOWED.value,
            matched_vehicle_id=vehicle.id,
        )
    # Зоно-типная логика парковки (§5.1).
    zone = (
        db.query(ParkingZone).filter(ParkingZone.id == data.zone_id).first()
        if data.zone_id is not None
        else None
    )
    parking_type = zone.parking_type if zone is not None else None
    if parking_type == ParkingType.ASSIGNED.value:
        return _decide_assigned(
            db,
            vehicle=vehicle,
            apartment_ids=apartment_ids,
            zone_id=data.zone_id,
            moment=data.captured_at,
        )
    if parking_type == ParkingType.SHARED.value:
        return _decide_shared(
            db,
            vehicle=vehicle,
            apartment_ids=apartment_ids,
            zone=zone,
            moment=data.captured_at,
        )
    # Зона не найдена/без типа → прежнее поведение.
    return _deny(
        DecisionReason.ZONE_NOT_ALLOWED.value, matched_vehicle_id=vehicle.id
    )


def _decide_taxi(db: Session, data: AnprDecisionInput) -> EngineDecision:
    """Ветвь taxi-pass (§7 шаги 7–8). Возвращает решение либо vehicle_not_found."""
    # Включаем 'used': исчерпанный одноразовый pass должен давать
    # pass_already_used (информативнее vehicle_not_found, §15 критерий 3).
    # 'revoked' исключаем — отозванный pass не считается найденным грантом.
    ap = (
        db.query(AccessPass)
        .filter(
            AccessPass.plate_number_normalized == data.plate_number_normalized,
            AccessPass.pass_type == "taxi",
            AccessPass.status.in_(("active", "used")),
        )
        .order_by(AccessPass.created_at.desc())
        .first()
    )
    if ap is None:
        return _deny(DecisionReason.VEHICLE_NOT_FOUND.value)
    if ap.zone_id is not None and data.zone_id is not None and ap.zone_id != data.zone_id:
        return _deny(DecisionReason.ZONE_NOT_ALLOWED.value, matched_pass_id=ap.id)
    if not _within_window(data.captured_at, ap.valid_from, ap.valid_until):
        return _deny(DecisionReason.PASS_EXPIRED.value, matched_pass_id=ap.id)
    if ap.used_entries >= ap.max_entries:
        return _deny(DecisionReason.PASS_ALREADY_USED.value, matched_pass_id=ap.id)
    return _allow(DecisionReason.TEMPORARY_PASS_ALLOWED.value, matched_pass_id=ap.id)


def decide(
    db: Session,
    data: AnprDecisionInput,
    *,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> EngineDecision:
    """Принять решение по ANPR-входу (§7 шаги 4–8). Без записи в БД."""
    # Шаг 4: confidence/аномалии. Низкий confidence → ручной разбор (§9.4).
    if data.confidence is not None and data.confidence < confidence_threshold:
        return _manual_review(DecisionReason.LOW_CONFIDENCE.value)

    # Шаги 5–6: постоянный автомобиль.
    permanent = _decide_permanent(db, data)
    if permanent is not None:
        return permanent

    # Шаги 7–8: временный taxi-pass (либо vehicle_not_found).
    return _decide_taxi(db, data)
