"""WRITE-операции менеджера над базой access_control (§6.2, §13.2, §4 п.7).

Сервисный слой менеджерских изменений: создание/блокировка постоянного авто,
создание taxi-пропуска и рассмотрение заявок жителей. Эти операции — общая база
доступа (§4 п.7: постоянный авто активируется только после подтверждения УК),
поверх которой работает Decision Engine §7.

Инварианты:
* номер нормализуется через ``services.normalization`` (§12);
* постоянный авто «реально проходит» только при тройке vehicle(active) +
  vehicle_apartments(active) + access_rule(зона) — поэтому create/approve создают
  все три (§7 шаги 5–6);
* каждое изменение пишет append-only ``access_audit_logs`` с hash-chain (§9.7),
  без ПД в логах (§11) — в ``details`` только идентификаторы/статусы;
* review идемпотентен: повторное рассмотрение завершённой заявки возвращает
  сохранённый результат, не создавая второй авто/правило (§9 п.9).

Таблицы ``vehicles``/``vehicle_apartments``/``access_rules``/``access_passes``/
``resident_access_requests`` НЕ append-only — обновления выполняются UPDATE.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

from access_control.domain.audit import AccessAuditLog
from access_control.domain.enums import (
    PassStatus,
    PassType,
    ResidentRequestStatus,
    VehicleApartmentStatus,
    VehicleStatus,
)
from access_control.domain.passes import (
    AccessPass,
    AccessRule,
    ResidentAccessRequest,
)
from access_control.domain.vehicles import Vehicle, VehicleApartment
from access_control.services.hashchain import next_hash
from access_control.services.normalization import normalize_plate
from access_control.services.resident_notify import (
    KIND_VEHICLE_REQUEST_RESOLVED,
    publish_resident_notification,
)

# Направления правила доступа в пилоте — только entry (§10.3, §14.2 п.3).
PILOT_ALLOWED_DIRECTIONS = ["entry"]
# Тип отношения по умолчанию, если квартира задана без явного relation_type.
DEFAULT_RELATION_TYPE = "owner"

REVIEW_ACTIONS = ("approve", "reject")


# --------------------------- исключения/DTO ---------------------------


class VehicleAlreadyExists(Exception):
    """Активный (неархивный) авто с таким нормализованным номером уже есть (409)."""


class VehicleNotFound(Exception):
    """Авто не найден (404)."""


class RequestNotFound(Exception):
    """Заявка жителя не найдена (404)."""


class PassNotFound(Exception):
    """Пропуск не найден (404)."""


class InvalidReviewAction(Exception):
    """Недопустимое действие рассмотрения (422)."""


@dataclass(frozen=True)
class ReviewOutcome:
    """Результат рассмотрения заявки: финальный статус + (для approve) авто."""

    request_id: int
    status: str
    vehicle_id: int | None
    replayed: bool


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --------------------------- аудит ---------------------------


def write_audit(
    db: Session,
    *,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Append-строка ``access_audit_logs`` с hash-chain (§9.7, §6.2).

    ``details`` — только PD-safe идентификаторы/статусы (§11): без номера/ФИО.
    IP включён в hash-payload (tamper-evident).
    """
    payload = {
        "actor_user_id": actor_user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "details": details,
        "ip_address": ip_address,
    }
    prev_hash, row_hash = next_hash(db, "access_audit_logs", payload)
    db.add(
        AccessAuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details,
            ip_address=ip_address,
            prev_hash=prev_hash,
            row_hash=row_hash,
        )
    )


# --------------------------- хелперы базы ---------------------------


def _active_vehicle_by_plate(db: Session, normalized: str) -> Vehicle | None:
    """Неархивный носитель нормализованного номера (партиал-unique, решение CTO #6)."""
    return (
        db.query(Vehicle)
        .filter(
            Vehicle.plate_number_normalized == normalized,
            Vehicle.status != VehicleStatus.ARCHIVED.value,
        )
        .first()
    )


def _ensure_active_link(
    db: Session,
    *,
    vehicle_id: int,
    apartment_id: int,
    relation_type: str,
    actor_user_id: int,
    now: dt.datetime,
) -> None:
    """Создать/активировать связь авто↔квартира (active, approved) — §5.3.

    Если активная связь уже есть — no-op (идемпотентность approve).
    """
    existing = (
        db.query(VehicleApartment)
        .filter(
            VehicleApartment.vehicle_id == vehicle_id,
            VehicleApartment.apartment_id == apartment_id,
        )
        .first()
    )
    if existing is not None:
        if existing.status != VehicleApartmentStatus.ACTIVE.value:
            existing.status = VehicleApartmentStatus.ACTIVE.value
            existing.approved_by_user_id = actor_user_id
            existing.approved_at = now
        return
    db.add(
        VehicleApartment(
            vehicle_id=vehicle_id,
            apartment_id=apartment_id,
            relation_type=relation_type or DEFAULT_RELATION_TYPE,
            status=VehicleApartmentStatus.ACTIVE.value,
            approved_by_user_id=actor_user_id,
            approved_at=now,
        )
    )


def _add_zone_rule(
    db: Session,
    *,
    vehicle_id: int,
    apartment_id: int | None,
    zone_id: int,
    actor_user_id: int,
) -> None:
    """Создать явное право доступа vehicle+zone (§7 шаг 6, решение CTO #5)."""
    db.add(
        AccessRule(
            vehicle_id=vehicle_id,
            apartment_id=apartment_id,
            zone_id=zone_id,
            allowed_directions=list(PILOT_ALLOWED_DIRECTIONS),
            is_active=True,
            created_by_user_id=actor_user_id,
        )
    )


# --------------------------- публичные операции ---------------------------


def create_vehicle(
    db: Session,
    *,
    actor_user_id: int,
    plate_number_original: str,
    plate_country: str | None = None,
    plate_type: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    color: str | None = None,
    vehicle_class: str | None = None,
    apartment_id: int | None = None,
    relation_type: str | None = None,
    zone_id: int | None = None,
    ip_address: str | None = None,
    now: dt.datetime | None = None,
) -> Vehicle:
    """Создать постоянный авто (§6.2). Опц. привязка к квартире и правило зоны.

    Нормализует номер (§12); 409 при активном дубле номера. ``apartment_id`` →
    активная связь (approved актором); ``zone_id`` → access_rule(entry), чтобы авто
    проходил по Decision Engine §7. Аудит.
    """
    now = now or _utcnow()
    plate = normalize_plate(plate_number_original, plate_country)
    if _active_vehicle_by_plate(db, plate.normalized) is not None:
        db.rollback()
        raise VehicleAlreadyExists(
            "active vehicle with this plate already exists"
        )
    vehicle = Vehicle(
        plate_number_original=plate_number_original,
        plate_number_normalized=plate.normalized,
        plate_country=plate.country,
        plate_type=plate_type or plate.type,
        recognition_key=plate.recognition_key,
        make=brand,
        model=model,
        color=color,
        vehicle_class=vehicle_class,
        status=VehicleStatus.ACTIVE.value,
        created_by_user_id=actor_user_id,
    )
    db.add(vehicle)
    db.flush()

    if apartment_id is not None:
        _ensure_active_link(
            db,
            vehicle_id=vehicle.id,
            apartment_id=apartment_id,
            relation_type=relation_type or DEFAULT_RELATION_TYPE,
            actor_user_id=actor_user_id,
            now=now,
        )
    if zone_id is not None:
        _add_zone_rule(
            db,
            vehicle_id=vehicle.id,
            apartment_id=apartment_id,
            zone_id=zone_id,
            actor_user_id=actor_user_id,
        )
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.vehicle_create",
        entity_type="vehicle",
        entity_id=vehicle.id,
        details={
            "apartment_id": apartment_id,
            "zone_id": zone_id,
            "relation_type": relation_type,
        },
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(vehicle)
    return vehicle


def set_vehicle_status(
    db: Session,
    *,
    vehicle_id: int,
    status: str,
    actor_user_id: int,
    reason: str | None = None,
    ip_address: str | None = None,
    now: dt.datetime | None = None,
) -> Vehicle:
    """Сменить статус авто: active|blocked|archived (§6.2 «блокировка»).

    ``blocked`` требует непустого ``reason`` → фиксирует blocked_reason/by/at.
    Прочие статусы очищают поля блокировки. Аудит.
    """
    now = now or _utcnow()
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise VehicleNotFound(f"vehicle {vehicle_id} not found")
    if status == VehicleStatus.BLOCKED.value:
        vehicle.status = VehicleStatus.BLOCKED.value
        vehicle.blocked_reason = reason
        vehicle.blocked_by_user_id = actor_user_id
        vehicle.blocked_at = now
    else:
        vehicle.status = status
        vehicle.blocked_reason = None
        vehicle.blocked_by_user_id = None
        vehicle.blocked_at = None
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.vehicle_status_change",
        entity_type="vehicle",
        entity_id=vehicle.id,
        details={"status": status, "has_reason": bool(reason)},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(vehicle)
    return vehicle


def _relink_apartment(
    db: Session,
    *,
    vehicle_id: int,
    apartment_id: int,
    relation_type: str,
    actor_user_id: int,
    now: dt.datetime,
) -> None:
    """Перепривязать авто к квартире (§5.3): архивирует прочие активные связи,
    ставит/активирует связь к указанной квартире с заданным отношением."""
    links = (
        db.query(VehicleApartment)
        .filter(VehicleApartment.vehicle_id == vehicle_id)
        .all()
    )
    for link in links:
        if (
            link.apartment_id != apartment_id
            and link.status == VehicleApartmentStatus.ACTIVE.value
        ):
            link.status = VehicleApartmentStatus.ARCHIVED.value
    _ensure_active_link(
        db,
        vehicle_id=vehicle_id,
        apartment_id=apartment_id,
        relation_type=relation_type,
        actor_user_id=actor_user_id,
        now=now,
    )
    # _ensure_active_link не меняет relation_type существующей связи — обновим явно.
    target = next((link for link in links if link.apartment_id == apartment_id), None)
    if target is not None:
        target.relation_type = relation_type


def update_vehicle(
    db: Session,
    *,
    vehicle_id: int,
    actor_user_id: int,
    fields: dict,
    ip_address: str | None = None,
    now: dt.datetime | None = None,
) -> Vehicle:
    """Отредактировать карточку авто (§6.2). ``fields`` — только переданные ключи
    среди plate_number_original/plate_country/plate_type/brand/model/color/
    vehicle_class/apartment_id/relation_type (PATCH-семантика).

    Смена номера ре-нормализуется (§12) и проверяется на активный дубль (409,
    исключая сам авто). apartment_id → перепривязка владельца; relation_type без
    apartment_id обновляет отношение текущей активной связи. Аудит.
    """
    now = now or _utcnow()
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise VehicleNotFound(f"vehicle {vehicle_id} not found")

    if "plate_number_original" in fields:
        original = (fields["plate_number_original"] or "").strip()
        if not original:
            raise ValueError("plate_number_original must be non-empty")
        country = fields.get("plate_country", vehicle.plate_country)
        plate = normalize_plate(original, country)
        dup = _active_vehicle_by_plate(db, plate.normalized)
        if dup is not None and dup.id != vehicle.id:
            db.rollback()
            raise VehicleAlreadyExists(
                "active vehicle with this plate already exists"
            )
        vehicle.plate_number_original = original
        vehicle.plate_number_normalized = plate.normalized
        vehicle.plate_country = plate.country
        vehicle.plate_type = fields.get("plate_type", plate.type)
        vehicle.recognition_key = plate.recognition_key
    else:
        if "plate_country" in fields:
            vehicle.plate_country = fields["plate_country"]
        if "plate_type" in fields:
            vehicle.plate_type = fields["plate_type"]
    if "brand" in fields:
        vehicle.make = fields["brand"]
    for key in ("model", "color", "vehicle_class"):
        if key in fields:
            setattr(vehicle, key, fields[key])

    relation = fields.get("relation_type") or DEFAULT_RELATION_TYPE
    if fields.get("apartment_id") is not None:
        _relink_apartment(
            db,
            vehicle_id=vehicle.id,
            apartment_id=fields["apartment_id"],
            relation_type=relation,
            actor_user_id=actor_user_id,
            now=now,
        )
    elif fields.get("relation_type"):
        link = (
            db.query(VehicleApartment)
            .filter(
                VehicleApartment.vehicle_id == vehicle.id,
                VehicleApartment.status == VehicleApartmentStatus.ACTIVE.value,
            )
            .order_by(VehicleApartment.id)
            .first()
        )
        if link is not None:
            link.relation_type = fields["relation_type"]

    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.vehicle_update",
        entity_type="vehicle",
        entity_id=vehicle.id,
        details={
            "fields": sorted(fields.keys()),
            "apartment_id": fields.get("apartment_id"),
        },
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(vehicle)
    return vehicle


def create_taxi_pass(
    db: Session,
    *,
    actor_user_id: int,
    apartment_id: int,
    zone_id: int,
    valid_until: dt.datetime,
    plate_number_original: str | None = None,
    valid_from: dt.datetime | None = None,
    max_entries: int = 1,
    ip_address: str | None = None,
) -> AccessPass:
    """Создать taxi-пропуск (§13.2, единая модель §5.4). Аудит.

    Номер нормализуется, если задан. ``status=active``, ``used_entries=0``,
    ``created_by_user_id=актор``, ``source=manager``.
    """
    normalized = None
    if plate_number_original:
        normalized = normalize_plate(plate_number_original).normalized
    ap = AccessPass(
        apartment_id=apartment_id,
        created_by_user_id=actor_user_id,
        pass_type=PassType.TAXI.value,
        zone_id=zone_id,
        plate_number_original=plate_number_original,
        plate_number_normalized=normalized,
        valid_from=valid_from,
        valid_until=valid_until,
        max_entries=max_entries,
        used_entries=0,
        status=PassStatus.ACTIVE.value,
        source="manager",
    )
    db.add(ap)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.pass_create_taxi",
        entity_type="access_pass",
        entity_id=ap.id,
        details={"apartment_id": apartment_id, "zone_id": zone_id,
                 "max_entries": max_entries},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(ap)
    return ap


def update_pass(
    db: Session,
    *,
    pass_id: int,
    actor_user_id: int,
    fields: dict,
    ip_address: str | None = None,
) -> AccessPass:
    """Отредактировать пропуск (§13.2). ``fields`` — переданные ключи среди
    valid_until/max_entries/plate_number_original/status (PATCH-семантика).

    ``status='revoked'`` отзывает пропуск; иное значение status игнорируется (отзыв
    необратим в пилоте). Номер ре-нормализуется. Аудит.
    """
    ap = db.get(AccessPass, pass_id)
    if ap is None:
        raise PassNotFound(f"pass {pass_id} not found")
    if "valid_until" in fields:
        ap.valid_until = fields["valid_until"]
    if "max_entries" in fields:
        ap.max_entries = fields["max_entries"]
    if "plate_number_original" in fields:
        original = fields["plate_number_original"]
        ap.plate_number_original = original
        ap.plate_number_normalized = (
            normalize_plate(original).normalized if original else None
        )
    if fields.get("status") == PassStatus.REVOKED.value:
        ap.status = PassStatus.REVOKED.value
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.pass_update",
        entity_type="access_pass",
        entity_id=ap.id,
        details={"fields": sorted(fields.keys())},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(ap)
    return ap


def _resolve_or_create_vehicle(
    db: Session, req: ResidentAccessRequest, actor_user_id: int
) -> Vehicle:
    """Вернуть авто для одобряемой заявки: связанный, существующий активный или новый."""
    if req.vehicle_id is not None:
        existing = db.get(Vehicle, req.vehicle_id)
        if existing is not None:
            return existing
    if req.plate_number_normalized:
        by_plate = _active_vehicle_by_plate(db, req.plate_number_normalized)
        if by_plate is not None:
            return by_plate
    original = req.plate_number_original or req.plate_number_normalized or ""
    plate = normalize_plate(original)
    vehicle = Vehicle(
        plate_number_original=original,
        plate_number_normalized=req.plate_number_normalized or plate.normalized,
        plate_country=plate.country,
        plate_type=plate.type,
        recognition_key=plate.recognition_key,
        status=VehicleStatus.ACTIVE.value,
        created_by_user_id=actor_user_id,
    )
    db.add(vehicle)
    db.flush()
    return vehicle


def review_request(
    db: Session,
    *,
    request_id: int,
    action: str,
    actor_user_id: int,
    comment: str | None = None,
    zone_id: int | None = None,
    ip_address: str | None = None,
    now: dt.datetime | None = None,
) -> ReviewOutcome:
    """Рассмотреть заявку жителя (§6.2 «подтверждение заявок», §4 п.7).

    ``approve``: создать/активировать авто + связь(active) + (опц.) правило зоны,
    перевести заявку в ``approved``. ``reject``: статус ``rejected`` + comment.
    Идемпотентно: повторное рассмотрение завершённой заявки возвращает сохранённый
    результат (``replayed=True``), не создавая дублей. Аудит.
    """
    now = now or _utcnow()
    if action not in REVIEW_ACTIONS:
        raise InvalidReviewAction(f"unknown action {action!r}")
    req = db.get(ResidentAccessRequest, request_id)
    if req is None:
        raise RequestNotFound(f"request {request_id} not found")

    # Идемпотентность: уже завершённая заявка → сохранённый результат, без записи.
    if req.status != ResidentRequestStatus.PENDING.value:
        return ReviewOutcome(
            request_id=req.id,
            status=req.status,
            vehicle_id=req.vehicle_id,
            replayed=True,
        )

    # Получатель резидентского уведомления — автор заявки (читаем ДО commit).
    recipient_user_id = req.created_by_user_id

    if action == "approve":
        vehicle = _resolve_or_create_vehicle(db, req, actor_user_id)
        if vehicle.status != VehicleStatus.ACTIVE.value:
            vehicle.status = VehicleStatus.ACTIVE.value
            vehicle.blocked_reason = None
            vehicle.blocked_by_user_id = None
            vehicle.blocked_at = None
        _ensure_active_link(
            db,
            vehicle_id=vehicle.id,
            apartment_id=req.apartment_id,
            relation_type=req.relation_type or DEFAULT_RELATION_TYPE,
            actor_user_id=actor_user_id,
            now=now,
        )
        if zone_id is not None:
            _add_zone_rule(
                db,
                vehicle_id=vehicle.id,
                apartment_id=req.apartment_id,
                zone_id=zone_id,
                actor_user_id=actor_user_id,
            )
        req.status = ResidentRequestStatus.APPROVED.value
        req.vehicle_id = vehicle.id
        req.reviewed_by_user_id = actor_user_id
        req.reviewed_at = now
        req.review_comment = comment
        audit_action = "access.request_approve"
        result_vehicle_id: int | None = vehicle.id
    else:  # reject
        req.status = ResidentRequestStatus.REJECTED.value
        req.reviewed_by_user_id = actor_user_id
        req.reviewed_at = now
        req.review_comment = comment
        audit_action = "access.request_reject"
        result_vehicle_id = req.vehicle_id

    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action=audit_action,
        entity_type="resident_access_request",
        entity_id=req.id,
        details={"zone_id": zone_id, "vehicle_id": result_vehicle_id},
        ip_address=ip_address,
    )
    db.commit()
    final_status = req.status

    # Резидентское уведомление автору заявки (§16.2): ПОСЛЕ commit, best-effort —
    # сбой публикации не влияет на уже зафиксированное рассмотрение. PD-safe (§11):
    # полный номер в канал не кладём (бот покажет житель его данные сам).
    publish_resident_notification(
        kind=KIND_VEHICLE_REQUEST_RESOLVED,
        recipient_user_id=recipient_user_id,
        payload={
            "request_id": request_id,
            "status": final_status,
            "comment": comment,
        },
    )

    return ReviewOutcome(
        request_id=req.id,
        status=final_status,
        vehicle_id=result_vehicle_id,
        replayed=False,
    )
