"""WRITE/READ-операции admin над реестром оборудования access_control (§6.1, §6.2).

Сервисный слой управления реальными точками въезда: парковочные зоны (+ привязка
фаз ЖК), въезды (gates), камеры, шлагбаумы и edge-контроллеры с device-credentials.

Инварианты:
* каждое изменение пишет append-only ``access_audit_logs`` с hash-chain (§9.7),
  без секретов/ПД в ``details`` (§11);
* удаления нет — деактивация через ``is_active``/``status`` (§9.7);
* device API-ключ контроллера генерируется криптостойко, ВОЗВРАЩАЕТСЯ plaintext
  ровно один раз (на create/rotate), в БД хранится ТОЛЬКО ``api_key_hash``
  (``hash_api_key``); HMAC-секрет НЕ хранится — резолвится из seed+controller_uid
  (решение CTO #8, §9.1);
* уникальность ``code`` (зона/въезд/камера/шлагбаум) и ``controller_uid`` (глобально)
  → конфликт = ``DuplicateCode``/``DuplicateControllerUid`` (HTTP 409);
* внешние ключи (zone_id/gate_id/yard_id) проверяются на существование →
  ``InvalidReference`` (HTTP 422).

Таблицы оборудования НЕ append-only — обновления выполняются UPDATE.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.domain.equipment import (
    AccessBarrier,
    AccessCamera,
    AccessGate,
    EdgeController,
)
from access_control.domain.territory import ParkingZone
from access_control.services.device_auth import hash_api_key
from access_control.services.management import write_audit

# Длина device API-ключа в байтах энтропии (token_urlsafe → ~43 печатных символа).
_API_KEY_BYTES = 32


# --------------------------- исключения ---------------------------


class NotFound(Exception):
    """Сущность не найдена (404)."""


class DuplicateCode(Exception):
    """Сущность с таким ``code`` уже существует (409)."""


class DuplicateControllerUid(Exception):
    """Контроллер с таким ``controller_uid`` уже существует (409)."""


class InvalidReference(Exception):
    """Ссылка на несуществующий FK (zone_id/gate_id/yard_id) (422)."""


# --------------------------- хелперы существования ---------------------------


def _zone_exists(db: Session, zone_id: int) -> bool:
    return db.get(ParkingZone, zone_id) is not None


def _gate_exists(db: Session, gate_id: int) -> bool:
    return db.get(AccessGate, gate_id) is not None


def _yard_exists(db: Session, yard_id: int) -> bool:
    return (
        db.execute(text("SELECT 1 FROM yards WHERE id = :y"), {"y": yard_id}).scalar()
        is not None
    )


def _code_taken(db: Session, model, code: str) -> bool:
    return db.query(model.id).filter(model.code == code).first() is not None


def _generate_api_key() -> str:
    """Криптостойкий device API-ключ (plaintext отдаётся вызывающему один раз)."""
    return secrets.token_urlsafe(_API_KEY_BYTES)


# =============================== ЗОНЫ ===============================


def list_zones(db: Session, *, limit: int, offset: int) -> tuple[list[ParkingZone], int]:
    total = db.query(ParkingZone).count()
    rows = (
        db.query(ParkingZone)
        .order_by(ParkingZone.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return rows, total


def get_zone(db: Session, zone_id: int) -> ParkingZone:
    zone = db.get(ParkingZone, zone_id)
    if zone is None:
        raise NotFound(f"zone {zone_id} not found")
    return zone


def create_zone(
    db: Session,
    *,
    actor_user_id: int,
    code: str,
    name: str,
    description: str | None = None,
    offline_mode: str | None = None,
    parking_type: str | None = None,
    capacity: int | None = None,
    max_permanent_vehicles_per_apartment: int | None = None,
    is_active: bool = True,
    ip_address: str | None = None,
) -> ParkingZone:
    if _code_taken(db, ParkingZone, code):
        raise DuplicateCode(f"zone code {code!r} already exists")
    zone = ParkingZone(
        code=code,
        name=name,
        description=description,
        capacity=capacity,
        max_permanent_vehicles_per_apartment=max_permanent_vehicles_per_apartment,
        is_active=is_active,
    )
    if offline_mode is not None:
        zone.offline_mode = offline_mode
    if parking_type is not None:
        zone.parking_type = parking_type
    db.add(zone)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.zone_create",
        entity_type="parking_zone",
        entity_id=zone.id,
        details={"code": code},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(zone)
    return zone


def update_zone(
    db: Session,
    *,
    zone_id: int,
    actor_user_id: int,
    fields: dict,
    ip_address: str | None = None,
) -> ParkingZone:
    zone = get_zone(db, zone_id)
    if "code" in fields and fields["code"] != zone.code and _code_taken(
        db, ParkingZone, fields["code"]
    ):
        raise DuplicateCode(f"zone code {fields['code']!r} already exists")
    for key, value in fields.items():
        setattr(zone, key, value)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.zone_update",
        entity_type="parking_zone",
        entity_id=zone.id,
        details={"fields": sorted(fields.keys())},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(zone)
    return zone


def get_zone_yard_ids(db: Session, zone_id: int) -> list[int]:
    """yard_ids привязанных к зоне фаз (parking_zone_yards), отсортированы."""
    rows = db.execute(
        text("SELECT yard_id FROM parking_zone_yards WHERE zone_id = :z ORDER BY yard_id"),
        {"z": zone_id},
    ).scalars()
    return list(rows)


def get_zone_yard_ids_map(
    db: Session, zone_ids: list[int]
) -> dict[int, list[int]]:
    """Batch: {zone_id: [yard_id, ...]} для набора зон (один запрос). Пустые — []."""
    result: dict[int, list[int]] = {zid: [] for zid in zone_ids}
    if not zone_ids:
        return result
    rows = db.execute(
        text(
            "SELECT zone_id, yard_id FROM parking_zone_yards "
            "WHERE zone_id = ANY(:zs) ORDER BY zone_id, yard_id"
        ),
        {"zs": list(zone_ids)},
    ).all()
    for zid, yid in rows:
        result.setdefault(zid, []).append(yid)
    return result


def set_zone_yards(
    db: Session,
    *,
    zone_id: int,
    actor_user_id: int,
    add: list[int],
    remove: list[int],
    ip_address: str | None = None,
) -> list[int]:
    """Привязать/отвязать фазы (yards) к зоне (parking_zone_yards). Возвращает yard_ids."""
    get_zone(db, zone_id)
    for yard_id in add:
        if not _yard_exists(db, yard_id):
            raise InvalidReference(f"yard {yard_id} not found")
    for yard_id in add:
        # Идемпотентно: уникальность (zone_id, yard_id) — ON CONFLICT DO NOTHING.
        db.execute(
            text(
                "INSERT INTO parking_zone_yards (zone_id, yard_id) "
                "VALUES (:z, :y) ON CONFLICT (zone_id, yard_id) DO NOTHING"
            ),
            {"z": zone_id, "y": yard_id},
        )
    if remove:
        db.execute(
            text(
                "DELETE FROM parking_zone_yards WHERE zone_id = :z AND yard_id = ANY(:ys)"
            ),
            {"z": zone_id, "ys": list(remove)},
        )
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.zone_yards_update",
        entity_type="parking_zone",
        entity_id=zone_id,
        details={"added": list(add), "removed": list(remove)},
        ip_address=ip_address,
    )
    db.commit()
    rows = db.execute(
        text("SELECT yard_id FROM parking_zone_yards WHERE zone_id = :z ORDER BY yard_id"),
        {"z": zone_id},
    ).scalars()
    return list(rows)


# =============================== ВЪЕЗДЫ (gates) ===============================


def list_gates(db: Session, *, limit: int, offset: int) -> tuple[list[AccessGate], int]:
    total = db.query(AccessGate).count()
    rows = (
        db.query(AccessGate)
        .order_by(AccessGate.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return rows, total


def create_gate(
    db: Session,
    *,
    actor_user_id: int,
    code: str,
    zone_id: int,
    direction: str,
    name: str | None = None,
    controller_id: int | None = None,
    is_active: bool = True,
    ip_address: str | None = None,
) -> AccessGate:
    if not _zone_exists(db, zone_id):
        raise InvalidReference(f"zone {zone_id} not found")
    if _code_taken(db, AccessGate, code):
        raise DuplicateCode(f"gate code {code!r} already exists")
    gate = AccessGate(
        code=code,
        name=name,
        zone_id=zone_id,
        controller_id=controller_id,
        direction=direction,
        is_active=is_active,
    )
    db.add(gate)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.gate_create",
        entity_type="access_gate",
        entity_id=gate.id,
        details={"code": code, "zone_id": zone_id},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(gate)
    return gate


def update_gate(
    db: Session,
    *,
    gate_id: int,
    actor_user_id: int,
    fields: dict,
    ip_address: str | None = None,
) -> AccessGate:
    gate = db.get(AccessGate, gate_id)
    if gate is None:
        raise NotFound(f"gate {gate_id} not found")
    if "zone_id" in fields and not _zone_exists(db, fields["zone_id"]):
        raise InvalidReference(f"zone {fields['zone_id']} not found")
    if "code" in fields and fields["code"] != gate.code and _code_taken(
        db, AccessGate, fields["code"]
    ):
        raise DuplicateCode(f"gate code {fields['code']!r} already exists")
    for key, value in fields.items():
        setattr(gate, key, value)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.gate_update",
        entity_type="access_gate",
        entity_id=gate.id,
        details={"fields": sorted(fields.keys())},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(gate)
    return gate


# =============================== КАМЕРЫ ===============================


def list_cameras(
    db: Session, *, limit: int, offset: int
) -> tuple[list[AccessCamera], int]:
    total = db.query(AccessCamera).count()
    rows = (
        db.query(AccessCamera)
        .order_by(AccessCamera.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return rows, total


def create_camera(
    db: Session,
    *,
    actor_user_id: int,
    code: str,
    gate_id: int,
    direction: str,
    name: str | None = None,
    controller_id: int | None = None,
    vendor: str | None = None,
    model: str | None = None,
    attributes: dict | None = None,
    is_active: bool = True,
    ip_address: str | None = None,
) -> AccessCamera:
    if not _gate_exists(db, gate_id):
        raise InvalidReference(f"gate {gate_id} not found")
    if _code_taken(db, AccessCamera, code):
        raise DuplicateCode(f"camera code {code!r} already exists")
    camera = AccessCamera(
        code=code,
        name=name,
        gate_id=gate_id,
        controller_id=controller_id,
        direction=direction,
        vendor=vendor,
        model=model,
        attributes=attributes,
        is_active=is_active,
    )
    db.add(camera)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.camera_create",
        entity_type="access_camera",
        entity_id=camera.id,
        details={"code": code, "gate_id": gate_id},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(camera)
    return camera


def update_camera(
    db: Session,
    *,
    camera_id: int,
    actor_user_id: int,
    fields: dict,
    ip_address: str | None = None,
) -> AccessCamera:
    camera = db.get(AccessCamera, camera_id)
    if camera is None:
        raise NotFound(f"camera {camera_id} not found")
    if "gate_id" in fields and not _gate_exists(db, fields["gate_id"]):
        raise InvalidReference(f"gate {fields['gate_id']} not found")
    if "code" in fields and fields["code"] != camera.code and _code_taken(
        db, AccessCamera, fields["code"]
    ):
        raise DuplicateCode(f"camera code {fields['code']!r} already exists")
    for key, value in fields.items():
        setattr(camera, key, value)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.camera_update",
        entity_type="access_camera",
        entity_id=camera.id,
        details={"fields": sorted(fields.keys())},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(camera)
    return camera


# =============================== ШЛАГБАУМЫ ===============================


def list_barriers(
    db: Session, *, limit: int, offset: int
) -> tuple[list[AccessBarrier], int]:
    total = db.query(AccessBarrier).count()
    rows = (
        db.query(AccessBarrier)
        .order_by(AccessBarrier.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return rows, total


def create_barrier(
    db: Session,
    *,
    actor_user_id: int,
    code: str,
    gate_id: int,
    name: str | None = None,
    controller_id: int | None = None,
    relay_type: str | None = None,
    relay_channel: int | None = None,
    config: dict | None = None,
    is_active: bool = True,
    ip_address: str | None = None,
) -> AccessBarrier:
    if not _gate_exists(db, gate_id):
        raise InvalidReference(f"gate {gate_id} not found")
    if _code_taken(db, AccessBarrier, code):
        raise DuplicateCode(f"barrier code {code!r} already exists")
    barrier = AccessBarrier(
        code=code,
        name=name,
        gate_id=gate_id,
        controller_id=controller_id,
        relay_type=relay_type,
        relay_channel=relay_channel,
        config=config,
        is_active=is_active,
    )
    db.add(barrier)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.barrier_create",
        entity_type="access_barrier",
        entity_id=barrier.id,
        details={"code": code, "gate_id": gate_id},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(barrier)
    return barrier


def update_barrier(
    db: Session,
    *,
    barrier_id: int,
    actor_user_id: int,
    fields: dict,
    ip_address: str | None = None,
) -> AccessBarrier:
    barrier = db.get(AccessBarrier, barrier_id)
    if barrier is None:
        raise NotFound(f"barrier {barrier_id} not found")
    if "gate_id" in fields and not _gate_exists(db, fields["gate_id"]):
        raise InvalidReference(f"gate {fields['gate_id']} not found")
    if "code" in fields and fields["code"] != barrier.code and _code_taken(
        db, AccessBarrier, fields["code"]
    ):
        raise DuplicateCode(f"barrier code {fields['code']!r} already exists")
    for key, value in fields.items():
        setattr(barrier, key, value)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.barrier_update",
        entity_type="access_barrier",
        entity_id=barrier.id,
        details={"fields": sorted(fields.keys())},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(barrier)
    return barrier


# =============================== КОНТРОЛЛЕРЫ ===============================


@dataclass(frozen=True)
class ControllerCreated:
    """Созданный контроллер + plaintext device API-ключ (отдаётся ОДИН раз)."""

    controller: EdgeController
    api_key: str


def list_controllers(
    db: Session, *, limit: int, offset: int
) -> tuple[list[EdgeController], int]:
    total = db.query(EdgeController).count()
    rows = (
        db.query(EdgeController)
        .order_by(EdgeController.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return rows, total


def get_controller(db: Session, controller_id: int) -> EdgeController:
    ctrl = db.get(EdgeController, controller_id)
    if ctrl is None:
        raise NotFound(f"controller {controller_id} not found")
    return ctrl


def create_controller(
    db: Session,
    *,
    actor_user_id: int,
    controller_uid: str,
    name: str | None = None,
    zone_id: int | None = None,
    gate_id: int | None = None,
    offline_mode: str | None = None,
    ip_allowlist: list | None = None,
    pinned_public_key_id: str | None = None,
    status: str | None = None,
    is_active: bool = True,
    ip_address: str | None = None,
) -> ControllerCreated:
    """Создать edge-контроллер + сгенерировать device API-ключ (§9.1, решение CTO #8).

    Возвращает контроллер и PLAINTEXT ключ (вызывающий обязан отдать его клиенту
    ровно один раз). В БД сохраняется ТОЛЬКО ``api_key_hash``; HMAC-секрет НЕ хранится.
    """
    if db.query(EdgeController.id).filter(
        EdgeController.controller_uid == controller_uid
    ).first() is not None:
        raise DuplicateControllerUid(f"controller_uid {controller_uid!r} already exists")
    if zone_id is not None and not _zone_exists(db, zone_id):
        raise InvalidReference(f"zone {zone_id} not found")
    if gate_id is not None and not _gate_exists(db, gate_id):
        raise InvalidReference(f"gate {gate_id} not found")

    api_key = _generate_api_key()
    controller = EdgeController(
        controller_uid=controller_uid,
        name=name,
        zone_id=zone_id,
        gate_id=gate_id,
        api_key_hash=hash_api_key(api_key),
        ip_allowlist=ip_allowlist,
        pinned_public_key_id=pinned_public_key_id,
        is_active=is_active,
    )
    if offline_mode is not None:
        controller.offline_mode = offline_mode
    if status is not None:
        controller.status = status
    db.add(controller)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.controller_create",
        entity_type="edge_controller",
        entity_id=controller.id,
        details={"controller_uid": controller_uid, "zone_id": zone_id},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(controller)
    return ControllerCreated(controller=controller, api_key=api_key)


def update_controller(
    db: Session,
    *,
    controller_id: int,
    actor_user_id: int,
    fields: dict,
    ip_address: str | None = None,
) -> EdgeController:
    controller = get_controller(db, controller_id)
    if "zone_id" in fields and fields["zone_id"] is not None and not _zone_exists(
        db, fields["zone_id"]
    ):
        raise InvalidReference(f"zone {fields['zone_id']} not found")
    if "gate_id" in fields and fields["gate_id"] is not None and not _gate_exists(
        db, fields["gate_id"]
    ):
        raise InvalidReference(f"gate {fields['gate_id']} not found")
    for key, value in fields.items():
        setattr(controller, key, value)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.controller_update",
        entity_type="edge_controller",
        entity_id=controller.id,
        details={"fields": sorted(fields.keys())},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(controller)
    return controller


def rotate_controller_key(
    db: Session,
    *,
    controller_id: int,
    actor_user_id: int,
    ip_address: str | None = None,
) -> tuple[EdgeController, str]:
    """Ротация device API-ключа (§9.1). Старый ключ инвалидируется (новый hash).

    Возвращает (контроллер, plaintext новый ключ) — ключ отдаётся ОДИН раз; в БД
    только новый ``api_key_hash``.
    """
    controller = get_controller(db, controller_id)
    api_key = _generate_api_key()
    controller.api_key_hash = hash_api_key(api_key)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.controller_rotate_key",
        entity_type="edge_controller",
        entity_id=controller.id,
        details={"controller_uid": controller.controller_uid},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(controller)
    return controller, api_key
