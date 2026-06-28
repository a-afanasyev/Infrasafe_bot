"""WRITE-операции жителя над общей базой access_control (§6.4, §16.2).

Личный кабинет жителя: заявка на постоянный авто, временный пропуск, отмена
своего пропуска. Это тот же единый API и та же общая база (§4 п.4-5), которой
пользуются И бот, И TWA — клиент без бизнес-логики.

КЛЮЧЕВАЯ ГРАНИЦА БЕЗОПАСНОСТИ (§6.4): житель создаёт/отменяет ТОЛЬКО для своих
``approved``-квартир (``user_apartments.status='approved'``). Любой чужой
``apartment_id``/чужой пропуск → ``ApartmentNotOwned``/``PassNotOwned`` (403 на
границе API). Связь со статусом ``pending`` владения НЕ даёт.

Инварианты:
* номер нормализуется через ``services.normalization`` (§12);
* заявка создаётся как ``pending`` — постоянный авто активируется только после
  подтверждения УК (§4 п.7, review делает менеджер);
* пропуск создаётся как ``active`` c ``source='resident'`` (единая модель §5.4);
* зона пропуска: если не задана явно — резолвится по обслуживающим квартиру зонам
  (apartment→building→yard ∈ ``parking_zone_yards``); одна → берётся, несколько/
  ноль → ``ZoneNotResolved`` (422), требуется явный ``zone_id``;
* каждое изменение пишет append-only ``access_audit_logs`` с hash-chain (§9.7),
  без ПД в логах (§11);
* отмена идемпотентна: повторная отмена revoked-пропуска возвращает результат без
  второй аудит-строки.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from access_control.domain.enums import PassStatus, ResidentRequestStatus
from access_control.domain.passes import AccessPass, ResidentAccessRequest
from access_control.services.management import write_audit
from access_control.services.normalization import normalize_plate

# Типы пропусков, которые житель вправе создавать самостоятельно (§6.4). Полный
# enum (courier/service/contractor/emergency) — служебные, создаются УК/системой.
RESIDENT_PASS_TYPES = ("taxi", "guest", "delivery")


# --------------------------- исключения/DTO ---------------------------


class ApartmentNotOwned(Exception):
    """Квартира не принадлежит пользователю как approved (403)."""


class ZoneNotResolved(Exception):
    """Зона пропуска не определена однозначно — нужен явный ``zone_id`` (422)."""


class PassNotFound(Exception):
    """Пропуск не найден (404)."""


class PassNotOwned(Exception):
    """Пропуск принадлежит чужой квартире/создан другим пользователем (403)."""


@dataclass(frozen=True)
class CancelOutcome:
    """Результат отмены пропуска: финальный статус + признак повтора."""

    pass_id: int
    status: str
    replayed: bool


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --------------------------- владение (§6.4) ---------------------------


def approved_apartment_ids(db: Session, user_id: int) -> list[int]:
    """``apartment_id`` всех approved-квартир пользователя (граница владения §6.4)."""
    rows = db.execute(
        text(
            "SELECT apartment_id FROM user_apartments "
            "WHERE user_id = :u AND status = 'approved'"
        ),
        {"u": user_id},
    ).scalars()
    return list(rows)


def _ensure_owns_apartment(db: Session, user_id: int, apartment_id: int) -> None:
    if apartment_id not in approved_apartment_ids(db, user_id):
        raise ApartmentNotOwned(
            f"apartment {apartment_id} is not an approved apartment of user {user_id}"
        )


def _serving_zone_ids(db: Session, apartment_id: int) -> list[int]:
    """Зоны, обслуживающие квартиру: apartment→building→yard ∈ parking_zone_yards."""
    rows = db.execute(
        text(
            "SELECT DISTINCT pzy.zone_id "
            "FROM apartments a "
            "JOIN buildings b ON b.id = a.building_id "
            "JOIN parking_zone_yards pzy ON pzy.yard_id = b.yard_id "
            "WHERE a.id = :a"
        ),
        {"a": apartment_id},
    ).scalars()
    return list(rows)


def _resolve_zone_id(db: Session, apartment_id: int, zone_id: int | None) -> int:
    """Определить зону пропуска (§ зоно-резолв). Явный zone_id имеет приоритет."""
    if zone_id is not None:
        return zone_id
    serving = _serving_zone_ids(db, apartment_id)
    if len(serving) == 1:
        return serving[0]
    raise ZoneNotResolved(
        "zone_id is required: "
        + (
            "no parking zone serves this apartment"
            if not serving
            else "multiple parking zones serve this apartment"
        )
    )


# --------------------------- публичные операции ---------------------------


def create_resident_request(
    db: Session,
    *,
    actor_user_id: int,
    apartment_id: int,
    plate_number_original: str,
    relation_type: str | None = None,
    ip_address: str | None = None,
) -> ResidentAccessRequest:
    """Создать заявку жителя на постоянный авто (§6.4, §4 п.7).

    Проверяет владение квартирой (approved), нормализует номер (§12), создаёт
    ``pending``-заявку с ``created_by_user_id=actor``. Подтверждает заявку менеджер
    через существующий ``/requests/{id}/review`` (он же задаёт марку/модель авто).
    Аудит ``access.resident_request_create`` (PD-safe).
    """
    _ensure_owns_apartment(db, actor_user_id, apartment_id)
    plate = normalize_plate(plate_number_original)
    req = ResidentAccessRequest(
        apartment_id=apartment_id,
        created_by_user_id=actor_user_id,
        plate_number_original=plate_number_original,
        plate_number_normalized=plate.normalized,
        relation_type=relation_type,
        status=ResidentRequestStatus.PENDING.value,
    )
    db.add(req)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.resident_request_create",
        entity_type="resident_access_request",
        entity_id=req.id,
        details={"apartment_id": apartment_id, "relation_type": relation_type},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(req)
    return req


def create_resident_pass(
    db: Session,
    *,
    actor_user_id: int,
    apartment_id: int,
    pass_type: str,
    valid_until: dt.datetime,
    plate_number_original: str | None = None,
    valid_from: dt.datetime | None = None,
    max_entries: int = 1,
    zone_id: int | None = None,
    ip_address: str | None = None,
) -> AccessPass:
    """Создать временный пропуск жителем (единая модель §5.4, §6.4).

    Проверяет владение квартирой, резолвит зону (явный ``zone_id`` или единственная
    обслуживающая зона), нормализует номер (если задан), создаёт ``active``-пропуск
    c ``source='resident'``, ``used_entries=0``. Аудит ``access.resident_pass_create``.
    """
    _ensure_owns_apartment(db, actor_user_id, apartment_id)
    resolved_zone = _resolve_zone_id(db, apartment_id, zone_id)
    normalized = None
    if plate_number_original:
        normalized = normalize_plate(plate_number_original).normalized
    ap = AccessPass(
        apartment_id=apartment_id,
        created_by_user_id=actor_user_id,
        pass_type=pass_type,
        zone_id=resolved_zone,
        plate_number_original=plate_number_original,
        plate_number_normalized=normalized,
        valid_from=valid_from,
        valid_until=valid_until,
        max_entries=max_entries,
        used_entries=0,
        status=PassStatus.ACTIVE.value,
        source="resident",
    )
    db.add(ap)
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.resident_pass_create",
        entity_type="access_pass",
        entity_id=ap.id,
        details={"apartment_id": apartment_id, "zone_id": resolved_zone,
                 "pass_type": pass_type, "max_entries": max_entries},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(ap)
    return ap


def _owns_pass(db: Session, user_id: int, ap: AccessPass) -> bool:
    """Принадлежит ли пропуск пользователю: создан им ИЛИ по его approved-квартире."""
    if ap.created_by_user_id == user_id:
        return True
    return ap.apartment_id in approved_apartment_ids(db, user_id)


def cancel_resident_pass(
    db: Session,
    *,
    actor_user_id: int,
    pass_id: int,
    ip_address: str | None = None,
) -> CancelOutcome:
    """Отменить свой пропуск → ``revoked`` (§6.4). Идемпотентно.

    404 если пропуска нет; 403 (``PassNotOwned``) если чужой. Повторная отмена
    revoked-пропуска возвращает результат без второй аудит-строки (``replayed``).
    Аудит ``access.resident_pass_cancel``.
    """
    ap = db.get(AccessPass, pass_id)
    if ap is None:
        raise PassNotFound(f"pass {pass_id} not found")
    if not _owns_pass(db, actor_user_id, ap):
        raise PassNotOwned(f"pass {pass_id} does not belong to user {actor_user_id}")

    if ap.status == PassStatus.REVOKED.value:
        return CancelOutcome(pass_id=ap.id, status=ap.status, replayed=True)

    ap.status = PassStatus.REVOKED.value
    db.flush()
    write_audit(
        db,
        actor_user_id=actor_user_id,
        action="access.resident_pass_cancel",
        entity_type="access_pass",
        entity_id=ap.id,
        details={"apartment_id": ap.apartment_id},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(ap)
    return CancelOutcome(pass_id=ap.id, status=ap.status, replayed=False)


# --------------------------- READ-хелперы (§6.4) ---------------------------


def user_vehicle_plates(db: Session, apartment_ids: list[int]) -> list[str]:
    """Нормализованные номера авто, активно привязанных к квартирам пользователя."""
    if not apartment_ids:
        return []
    stmt = text(
        "SELECT DISTINCT v.plate_number_normalized "
        "FROM vehicles v JOIN vehicle_apartments va ON va.vehicle_id = v.id "
        "WHERE va.status = 'active' AND va.apartment_id IN :apts"
    ).bindparams(bindparam("apts", expanding=True))
    rows = db.execute(stmt, {"apts": apartment_ids}).scalars()
    return [p for p in rows if p]


# --------------------------- READ-списки (§6.4) ---------------------------
#
# Единый источник для клиентов без бизнес-логики (бот И TWA, §4 п.4-5): и REST-роутер
# ``api/resident.py``, и Telegram-бот зовут ОДНИ функции — SQL и граница владения не
# дублируются. Возвращают ``(rows, total)`` где ``rows`` — список dict (плоские
# строки БД); presentation (pydantic-DTO для API, текст для бота) делает клиент.

# Пагинация (общие дефолты для всех списков жителя).
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

_VEHICLE_COLS = (
    "v.id, v.plate_number_original, v.plate_number_normalized, v.plate_country, "
    "v.plate_type, v.make, v.model, v.color, v.vehicle_class, v.status, "
    "v.blocked_reason, v.blocked_by_user_id, v.blocked_at"
)

_VEHICLE_OWNED = (
    "EXISTS (SELECT 1 FROM vehicle_apartments va WHERE va.vehicle_id = v.id "
    "AND va.status = 'active' AND va.apartment_id IN :apts)"
)


def approved_apartments(db: Session, user_id: int) -> list[dict]:
    """approved-квартиры пользователя с номером для выбора в UI (§6.4).

    Возвращает ``[{"id", "apartment_number"}]`` отсортированными по id. Нужен
    клиенту (боту/TWA), когда у жителя несколько квартир и требуется выбор.
    """
    apts = approved_apartment_ids(db, user_id)
    if not apts:
        return []
    stmt = text(
        "SELECT id, apartment_number FROM apartments WHERE id IN :apts ORDER BY id"
    ).bindparams(bindparam("apts", expanding=True))
    return [dict(r) for r in db.execute(stmt, {"apts": apts}).mappings()]


def list_resident_vehicles(
    db: Session, *, user_id: int, limit: int = DEFAULT_LIMIT, offset: int = 0
) -> tuple[list[dict], int]:
    """Авто, активно привязанные к approved-квартирам жителя (§6.4)."""
    apts = approved_apartment_ids(db, user_id)
    if not apts:
        return [], 0
    params = {"apts": apts}
    total = db.execute(
        text(f"SELECT count(*) FROM vehicles v WHERE {_VEHICLE_OWNED}").bindparams(
            bindparam("apts", expanding=True)
        ),
        params,
    ).scalar_one()
    rows = db.execute(
        text(
            f"SELECT {_VEHICLE_COLS} FROM vehicles v WHERE {_VEHICLE_OWNED} "
            "ORDER BY v.created_at DESC, v.id DESC LIMIT :limit OFFSET :offset"
        ).bindparams(bindparam("apts", expanding=True)),
        {**params, "limit": limit, "offset": offset},
    ).mappings()
    return [dict(r) for r in rows], total


def list_resident_passes(
    db: Session, *, user_id: int, status: str | None = None,
    limit: int = DEFAULT_LIMIT, offset: int = 0,
) -> tuple[list[dict], int]:
    """Пропуска квартир жителя ИЛИ созданные им самим (§6.4). Фильтр ``status``."""
    apts = approved_apartment_ids(db, user_id)
    conds = ["(created_by_user_id = :uid OR apartment_id IN :apts)"]
    params: dict = {"uid": user_id, "apts": apts or [-1]}
    if status is not None:
        conds.append("status = :status")
        params["status"] = status
    where = " WHERE " + " AND ".join(conds)
    total = db.execute(
        text(f"SELECT count(*) FROM access_passes {where}").bindparams(
            bindparam("apts", expanding=True)
        ),
        params,
    ).scalar_one()
    rows = db.execute(
        text(
            "SELECT id, pass_type, apartment_id, created_by_user_id, zone_id, "
            " plate_number_original, plate_number_normalized, valid_from, valid_until, "
            " max_entries, used_entries, status, source, created_at "
            f"FROM access_passes {where} "
            "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
        ).bindparams(bindparam("apts", expanding=True)),
        {**params, "limit": limit, "offset": offset},
    ).mappings()
    return [dict(r) for r in rows], total


def list_resident_requests(
    db: Session, *, user_id: int, status: str | None = None,
    limit: int = DEFAULT_LIMIT, offset: int = 0,
) -> tuple[list[dict], int]:
    """Заявки жителя на постоянный авто: созданные им ИЛИ по его квартирам (§6.4)."""
    apts = approved_apartment_ids(db, user_id)
    conds = ["(created_by_user_id = :uid OR apartment_id IN :apts)"]
    params: dict = {"uid": user_id, "apts": apts or [-1]}
    if status is not None:
        conds.append("status = :status")
        params["status"] = status
    where = " WHERE " + " AND ".join(conds)
    total = db.execute(
        text(f"SELECT count(*) FROM resident_access_requests {where}").bindparams(
            bindparam("apts", expanding=True)
        ),
        params,
    ).scalar_one()
    rows = db.execute(
        text(
            "SELECT id, apartment_id, created_by_user_id, vehicle_id, "
            " plate_number_original, plate_number_normalized, relation_type, status, "
            " reviewed_by_user_id, reviewed_at, review_comment, created_at "
            f"FROM resident_access_requests {where} "
            "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
        ).bindparams(bindparam("apts", expanding=True)),
        {**params, "limit": limit, "offset": offset},
    ).mappings()
    return [dict(r) for r in rows], total


def list_resident_events(
    db: Session, *, user_id: int, limit: int = DEFAULT_LIMIT, offset: int = 0
) -> tuple[list[dict], int]:
    """События проезда по авто/квартирам жителя (§6.4: только свои события).

    Сопоставление: ``apartment_id`` ∈ approved-квартиры жителя ИЛИ
    ``plate_number_normalized`` ∈ номера авто его квартир (покрывает и постоянный
    авто, и taxi-pass, где apartment_id у события может отсутствовать).
    """
    apts = approved_apartment_ids(db, user_id)
    plates = user_vehicle_plates(db, apts)
    conds: list[str] = []
    params: dict = {}
    if apts:
        conds.append("apartment_id IN :apts")
        params["apts"] = apts
    if plates:
        conds.append("plate_number_normalized IN :plates")
        params["plates"] = plates
    if not conds:
        return [], 0
    where = " WHERE (" + " OR ".join(conds) + ")"
    binds = []
    if apts:
        binds.append(bindparam("apts", expanding=True))
    if plates:
        binds.append(bindparam("plates", expanding=True))
    total = db.execute(
        text(f"SELECT count(*) FROM access_events {where}").bindparams(*binds),
        params,
    ).scalar_one()
    rows = db.execute(
        text(
            "SELECT id, event_id, occurred_at, direction, gate_id, zone_id, "
            " apartment_id, plate_number_normalized, decision, reason "
            f"FROM access_events {where} "
            "ORDER BY occurred_at DESC, id DESC LIMIT :limit OFFSET :offset"
        ).bindparams(*binds),
        {**params, "limit": limit, "offset": offset},
    ).mappings()
    return [dict(r) for r in rows], total
