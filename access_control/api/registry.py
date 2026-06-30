"""READ-эндпоинты реестра access_control: история событий + база (§6, §11, §13.2).

Экраны охранника и менеджера. Все эндпоинты read-only (USER-API, JWT/cookie —
``require_approved_roles``, НЕ device-auth). Конверт ответа единый:
``{items, total, limit, offset}`` (фронт-контракт).

RBAC (§6.2/§6.3):
* ``/events*`` и ``/passes`` — ``security_operator``/``manager``/``system_admin``;
* ``/vehicles*`` и ``/requests`` — только ``manager``/``system_admin``
  (оператор не управляет базой авто/заявок).
applicant/executor/inspector → 403; без auth → 401.

PD (§11): полный номер допустим в ответах уполномоченным ролям (экран охраны/
менеджера); в логи ПД не пишем (эндпоинты ничего не логируют). Пагинация:
``limit`` дефолт 50, max 200; ``offset`` ≥ 0. Сортировка по времени desc.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from access_control.integrations.media import AccessMediaClient, get_access_media_client
from access_control.services import photo_urls
from access_control.services.management import write_audit
from uk_management_bot.api.auth.service import verify_access_token
from uk_management_bot.api.dependencies import (
    _parse_user_roles,
    require_approved_roles,
)
from uk_management_bot.database.session import get_db

router = APIRouter(prefix="/api/v1/access", tags=["access-registry"])

# RBAC-наборы ролей (§6.2/§6.3).
EVENTS_PASSES_ROLES = ("security_operator", "manager", "system_admin")
VEHICLES_REQUESTS_ROLES = ("manager", "system_admin")
# Отдельное разрешение на ПРОСМОТР фото (§11). Пока совпадает с набором, видящим
# события, НО вынесено отдельно, чтобы потом сузить.
# TODO(§11): сузить до явного photo-view права (а не «кто видит события»).
PHOTO_VIEW_ROLES = ("security_operator", "manager", "system_admin")

# Пагинация (общая для всех списков).
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
# Сколько последних событий по номеру отдаём в детали авто.
VEHICLE_RECENT_EVENTS = 20


# ------------------------------ DTO (frozen) ------------------------------


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class EventRow(_Frozen):
    id: int
    event_id: str
    controller_id: int
    zone_id: int | None
    gate_id: int | None
    direction: str
    plate_number_normalized: str | None
    captured_at: dt.datetime
    occurred_at: dt.datetime | None
    source: str
    plate_photo_url: str | None
    overview_photo_url: str | None
    decision: str | None
    status: str | None
    reason: str | None
    decision_id: int | None
    resolved_by_user_id: int | None
    has_command: bool


class EventsPage(_Frozen):
    items: list[EventRow]
    total: int
    limit: int
    offset: int


class CameraEventDetail(_Frozen):
    id: int
    event_id: str
    controller_id: int
    zone_id: int | None
    gate_id: int | None
    camera_id: int | None
    direction: str
    plate_number_original: str | None
    plate_number_normalized: str | None
    confidence: float | None
    captured_at: dt.datetime
    received_at: dt.datetime | None
    source: str
    plate_photo_url: str | None
    overview_photo_url: str | None
    vehicle_class: str | None
    color: str | None


class DecisionRow(_Frozen):
    id: int
    decision: str
    status: str
    reason: str | None
    decision_group_id: str | None
    supersedes_decision_id: int | None
    resolved_by_user_id: int | None
    resolved_at: dt.datetime | None
    review_deadline_at: dt.datetime | None
    created_at: dt.datetime
    prev_hash: str | None
    row_hash: str | None


class CommandRow(_Frozen):
    command_id: str
    decision_id: int | None
    barrier_id: int
    controller_id: int
    command_type: str
    status: str
    attempts: int
    created_at: dt.datetime
    leased_at: dt.datetime | None
    acked_at: dt.datetime | None
    dead_at: dt.datetime | None


class ManualOpeningRow(_Frozen):
    id: int
    barrier_id: int
    command_id: str | None
    decision_id: int | None
    operator_user_id: int
    reason: str
    created_at: dt.datetime


class ResidentConfirmationRow(_Frozen):
    """Совещательный ответ жителя на спорный въезд (§9.4) — оператору на manual_review."""

    user_id: int
    response: str
    created_at: dt.datetime


class EventDetail(_Frozen):
    camera_event: CameraEventDetail
    decisions: list[DecisionRow]
    barrier_commands: list[CommandRow]
    manual_openings: list[ManualOpeningRow]
    resident_confirmations: list[ResidentConfirmationRow]


class ApartmentLink(_Frozen):
    apartment_id: int
    relation_type: str
    status: str
    valid_from: dt.datetime | None
    valid_until: dt.datetime | None
    approved_by_user_id: int | None
    approved_at: dt.datetime | None


class VehicleRow(_Frozen):
    id: int
    plate_number_original: str
    plate_number_normalized: str
    plate_country: str | None
    plate_type: str | None
    brand: str | None  # колонка БД называется make; во фронт отдаём как brand
    model: str | None
    color: str | None
    vehicle_class: str | None
    status: str
    blocked_reason: str | None
    blocked_by_user_id: int | None
    blocked_at: dt.datetime | None
    apartments: list[ApartmentLink]


class VehiclesPage(_Frozen):
    items: list[VehicleRow]
    total: int
    limit: int
    offset: int


class VehicleEventRow(_Frozen):
    id: int
    event_id: str
    captured_at: dt.datetime
    direction: str
    gate_id: int | None
    zone_id: int | None
    decision: str | None
    status: str | None


class VehicleDetail(_Frozen):
    vehicle: VehicleRow
    apartments: list[ApartmentLink]
    apartment_details: list["ApartmentDetail"] = []
    recent_events: list[VehicleEventRow]


class PassRow(_Frozen):
    id: int
    pass_type: str
    apartment_id: int
    created_by_user_id: int | None
    zone_id: int | None
    plate_number_original: str | None
    plate_number_normalized: str | None
    valid_from: dt.datetime | None
    valid_until: dt.datetime | None
    max_entries: int
    used_entries: int
    status: str
    source: str | None
    created_at: dt.datetime


class PassesPage(_Frozen):
    items: list[PassRow]
    total: int
    limit: int
    offset: int


class RequestRow(_Frozen):
    id: int
    apartment_id: int
    created_by_user_id: int
    vehicle_id: int | None
    plate_number_original: str | None
    plate_number_normalized: str | None
    relation_type: str | None
    status: str
    reviewed_by_user_id: int | None
    reviewed_at: dt.datetime | None
    review_comment: str | None
    created_at: dt.datetime


class RequestsPage(_Frozen):
    items: list[RequestRow]
    total: int
    limit: int
    offset: int


# --- Обогащение деталей: заявитель / адрес / зона (§6.2, экран менеджера) ---


class ApplicantInfo(_Frozen):
    """PD-обогащение: данные жителя (заявитель/владелец) для экрана менеджера."""

    user_id: int
    name: str | None
    phone: str | None
    username: str | None
    telegram_id: int | None


class AddressInfo(_Frozen):
    """Адрес квартиры: apartment→building→yard (справочник адресов)."""

    apartment_id: int
    apartment_number: str | None
    entrance: str | None
    floor: str | None
    building_id: int | None
    building_address: str | None
    yard_id: int | None
    yard_name: str | None


class ZoneRef(_Frozen):
    """Краткая ссылка на зону парковки."""

    id: int
    code: str | None
    name: str | None


class ApartmentDetail(_Frozen):
    """Связь авто↔квартира, обогащённая адресом, жителями и зонами (карточка авто)."""

    apartment_id: int
    relation_type: str
    status: str
    address: AddressInfo | None
    residents: list[ApplicantInfo]
    zones: list[ZoneRef]


class RequestDetail(_Frozen):
    """Деталь заявки на авто: заявитель + адрес + обслуживающие зоны + авто."""

    request: RequestRow
    applicant: ApplicantInfo | None
    address: AddressInfo | None
    serving_zones: list[ZoneRef]
    vehicle: VehicleRow | None


class PassDetail(_Frozen):
    """Деталь пропуска: заявитель + адрес + зона."""

    pass_record: PassRow = Field(serialization_alias="pass")
    applicant: ApplicantInfo | None
    address: AddressInfo | None
    zone: ZoneRef | None


# VehicleDetail.apartment_details ссылается на ApartmentDetail (определён ниже).
VehicleDetail.model_rebuild()


# ------------------------------ хелперы ------------------------------


def _limit(value: int) -> int:
    return Query(value, ge=1, le=MAX_LIMIT, description="размер страницы (max 200)")


def _plate_pat(plate: str) -> str:
    """ILIKE-паттерн contains по нормализованному номеру (нормализация — uppercase)."""
    return f"%{plate.strip().upper()}%"


def _where(conditions: list[str]) -> str:
    return (" WHERE " + " AND ".join(conditions)) if conditions else ""


# ------------------------------ photo-view (§11) ------------------------------


def can_view_photos(user) -> bool:
    """Есть ли у пользователя отдельное разрешение на просмотр фото (§11).

    Предикат для гейтинга полей ``*_photo_url`` в реестре (не зависимость — чтобы
    отдавать ``null`` вместо 403 на эндпоинте). TODO(§11): сузить до явного права.
    """
    roles = _parse_user_roles(user)
    return any(r in roles for r in PHOTO_VIEW_ROLES)


def require_photo_view():
    """Зависимость отдельного разрешения на просмотр фото (§11).

    Сейчас = ``PHOTO_VIEW_ROLES`` + approved (как остальной реестр). Вынесена
    отдельно от ``EVENTS_PASSES_ROLES`` намеренно.
    TODO(§11): сузить до явного photo-view права.
    """
    return require_approved_roles(*PHOTO_VIEW_ROLES)


def _signed_photo_url(event_id: int, stored: str | None, kind: str, can_view: bool) -> str | None:
    """Подписанный короткоживущий URL на ``/photos`` вместо сырого storage-URL (§11).

    ``None`` если фото нет ИЛИ у пользователя нет photo-view (сырой URL наружу не
    отдаётся никогда).
    """
    if not stored or not can_view:
        return None
    return photo_urls.sign(event_id, kind)


def _apartments_for(db: Session, vehicle_ids: list[int]) -> dict[int, list[ApartmentLink]]:
    """Связи vehicle_apartments для набора авто (одним запросом, без N+1)."""
    if not vehicle_ids:
        return {}
    stmt = text(
        "SELECT vehicle_id, apartment_id, relation_type, status, valid_from, "
        " valid_until, approved_by_user_id, approved_at "
        "FROM vehicle_apartments WHERE vehicle_id IN :vids ORDER BY id"
    ).bindparams(bindparam("vids", expanding=True))
    out = {vid: [] for vid in vehicle_ids}
    for r in db.execute(stmt, {"vids": vehicle_ids}).mappings():
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


def _applicants_for(db: Session, user_ids: list[int | None]) -> dict[int, ApplicantInfo]:
    """Данные жителей (users) по id — для заявителя/владельца (без N+1)."""
    ids = [u for u in {*user_ids} if u is not None]
    if not ids:
        return {}
    stmt = text(
        "SELECT id, first_name, last_name, username, phone, telegram_id "
        "FROM users WHERE id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    out: dict[int, ApplicantInfo] = {}
    for r in db.execute(stmt, {"ids": ids}).mappings():
        name = " ".join(x for x in (r["first_name"], r["last_name"]) if x) or None
        out[r["id"]] = ApplicantInfo(
            user_id=r["id"], name=name, phone=r["phone"],
            username=r["username"], telegram_id=r["telegram_id"],
        )
    return out


def _addresses_for(db: Session, apartment_ids: list[int | None]) -> dict[int, AddressInfo]:
    """Адрес квартир (apartment→building→yard) по id (без N+1)."""
    ids = [a for a in {*apartment_ids} if a is not None]
    if not ids:
        return {}
    stmt = text(
        "SELECT a.id AS apartment_id, a.apartment_number::text AS apartment_number, "
        " a.entrance::text AS entrance, a.floor::text AS floor, "
        " b.id AS building_id, b.address AS building_address, "
        " y.id AS yard_id, y.name AS yard_name "
        "FROM apartments a "
        "LEFT JOIN buildings b ON b.id = a.building_id "
        "LEFT JOIN yards y ON y.id = b.yard_id "
        "WHERE a.id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    return {
        r["apartment_id"]: AddressInfo(**r)
        for r in db.execute(stmt, {"ids": ids}).mappings()
    }


def _serving_zones_for(db: Session, apartment_ids: list[int | None]) -> dict[int, list[ZoneRef]]:
    """Зоны, обслуживающие квартиру (apartment→building→yard ∈ parking_zone_yards)."""
    ids = [a for a in {*apartment_ids} if a is not None]
    if not ids:
        return {}
    stmt = text(
        "SELECT a.id AS apartment_id, z.id AS zone_id, z.code, z.name "
        "FROM apartments a "
        "JOIN buildings b ON b.id = a.building_id "
        "JOIN parking_zone_yards pzy ON pzy.yard_id = b.yard_id "
        "JOIN parking_zones z ON z.id = pzy.zone_id "
        "WHERE a.id IN :ids ORDER BY z.id"
    ).bindparams(bindparam("ids", expanding=True))
    out: dict[int, list[ZoneRef]] = {a: [] for a in ids}
    for r in db.execute(stmt, {"ids": ids}).mappings():
        out[r["apartment_id"]].append(
            ZoneRef(id=r["zone_id"], code=r["code"], name=r["name"])
        )
    return out


def _residents_for(db: Session, apartment_ids: list[int | None]) -> dict[int, list[ApplicantInfo]]:
    """Жители квартир (user_apartments approved → users) — владельцы для карточки авто."""
    ids = [a for a in {*apartment_ids} if a is not None]
    if not ids:
        return {}
    stmt = text(
        "SELECT ua.apartment_id, u.id, u.first_name, u.last_name, u.username, "
        " u.phone, u.telegram_id "
        "FROM user_apartments ua JOIN users u ON u.id = ua.user_id "
        "WHERE ua.apartment_id IN :ids AND ua.status = 'approved' ORDER BY u.id"
    ).bindparams(bindparam("ids", expanding=True))
    out: dict[int, list[ApplicantInfo]] = {a: [] for a in ids}
    for r in db.execute(stmt, {"ids": ids}).mappings():
        name = " ".join(x for x in (r["first_name"], r["last_name"]) if x) or None
        out[r["apartment_id"]].append(
            ApplicantInfo(
                user_id=r["id"], name=name, phone=r["phone"],
                username=r["username"], telegram_id=r["telegram_id"],
            )
        )
    return out


def _zone_ref(db: Session, zone_id: int | None) -> ZoneRef | None:
    """Краткая ссылка на зону по id (для пропуска)."""
    if zone_id is None:
        return None
    r = db.execute(
        text("SELECT id, code, name FROM parking_zones WHERE id = :id"),
        {"id": zone_id},
    ).mappings().first()
    return ZoneRef(id=r["id"], code=r["code"], name=r["name"]) if r else None


def _vehicle_row(r, links: list[ApartmentLink]) -> VehicleRow:
    return VehicleRow(
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
        apartments=links,
    )


# ------------------------------ /events ------------------------------

# Текущее решение группы = строка с max(id) (транзишн всегда имеет больший id).
_EVENTS_FROM = """
FROM camera_events ce
LEFT JOIN LATERAL (
    SELECT id, decision, status, reason, resolved_by_user_id
    FROM access_decisions ad WHERE ad.camera_event_id = ce.id
    ORDER BY ad.id DESC LIMIT 1
) d ON true
LEFT JOIN LATERAL (
    SELECT occurred_at FROM access_events ae WHERE ae.camera_event_id = ce.id
    ORDER BY ae.id DESC LIMIT 1
) ae ON true
"""


# ------------------------------ /photos (§11) ------------------------------


def _optional_actor(request: Request) -> int | None:
    """Достать actor_user_id из web-сессии (cookie), если она есть.

    Эндпоинт /photos — capability по signed-URL и НЕ требует Bearer (иначе
    ``<img>`` не загрузится). Но если браузер прислал session-cookie (она уходит
    с ``<img>`` автоматически для same-origin) — фиксируем актора в аудите; иначе
    ``None`` (источник доступа — сам signed-URL).
    """
    token = request.cookies.get("uk_access") or request.cookies.get("access_token")
    if not token:
        return None
    payload = verify_access_token(token)
    if not payload:
        return None
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        return None


@router.get("/photos/{kind}/{event_id}")
async def get_photo(
    request: Request,
    kind: str = Path(..., description="plate|overview"),
    event_id: int = Path(..., description="camera_events.id"),
    exp: int = Query(..., description="срок действия signed-URL (unix)"),
    sig: str = Query(..., description="HMAC-подпись signed-URL"),
    db: Session = Depends(get_db),
    media: AccessMediaClient = Depends(get_access_media_client),
):
    """Выдать фото события по короткоживущему signed-URL (§11).

    Capability по подписи (без Bearer): проверяет подпись+срок → пишет аудит
    просмотра ``access.photo_view`` (PD-safe details) → отдаёт фото:

    * сохранённое значение вида ``media://{media_id}`` → СТРИМ байтов из
      медиа-сервиса (``AccessMediaClient.fetch_file``) с корректным Content-Type;
    * иначе (сырой storage-URL) → прежний 302 redirect (обратная совместимость).

    Невалидная подпись → 403, протухшая → 410, отсутствующее фото/событие → 404.
    """
    try:
        photo_urls.verify(event_id, kind, exp, sig)
    except photo_urls.PhotoUrlExpired:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="signed url expired")
    except photo_urls.PhotoUrlInvalid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid signature")

    row = db.execute(
        text(
            "SELECT plate_photo_url, overview_photo_url FROM camera_events WHERE id = :id"
        ),
        {"id": event_id},
    ).mappings().first()
    stored = None if row is None else (
        row["plate_photo_url"] if kind == "plate" else row["overview_photo_url"]
    )
    if not stored:
        # Валидная подпись, но фото нет — просмотра не произошло, аудит не пишем.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="photo not found")

    # Просмотр состоялся → аудит (§11/§6.2). Details PD-safe: без номера/URL.
    actor = _optional_actor(request)
    write_audit(
        db,
        actor_user_id=actor,
        action="access.photo_view",
        entity_type="camera_event",
        entity_id=event_id,
        details={"kind": kind, "source": "session" if actor else "signed_url"},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()

    if stored.startswith("media://"):
        # Новый путь (§11): фото лежит в медиа-сервисе — стримим байты, сырой
        # storage/Telegram-URL наружу не уходит.
        media_id = stored[len("media://"):]
        content, content_type = await media.fetch_file(media_id)
        return Response(content=content, media_type=content_type)

    # Обратная совместимость: сохранённый сырой storage-URL → redirect.
    return RedirectResponse(url=stored, status_code=status.HTTP_302_FOUND)


@router.get("/events", response_model=EventsPage)
def list_events(
    decision: str | None = Query(None),
    zone_id: int | None = Query(None),
    gate_id: int | None = Query(None),
    plate: str | None = Query(None, description="contains по нормализованному номеру"),
    date_from: dt.datetime | None = Query(None),
    date_to: dt.datetime | None = Query(None),
    source: str | None = Query(None),
    limit: int = _limit(DEFAULT_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*EVENTS_PASSES_ROLES)),
) -> EventsPage:
    """История событий: камера-событие + occurred_at + текущее решение группы.

    Фото (§11): ``*_photo_url`` отдаются как ПОДПИСАННЫЕ короткоживущие URL на
    ``/photos`` (не сырой storage-URL) и только пользователю с photo-view.
    """
    conds: list[str] = []
    params: dict = {}
    if decision is not None:
        conds.append("d.decision = :decision")
        params["decision"] = decision
    if zone_id is not None:
        conds.append("ce.zone_id = :zone_id")
        params["zone_id"] = zone_id
    if gate_id is not None:
        conds.append("ce.gate_id = :gate_id")
        params["gate_id"] = gate_id
    if plate:
        conds.append("ce.plate_number_normalized ILIKE :plate")
        params["plate"] = _plate_pat(plate)
    if date_from is not None:
        conds.append("ce.captured_at >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        conds.append("ce.captured_at <= :date_to")
        params["date_to"] = date_to
    if source is not None:
        conds.append("ce.source = :source")
        params["source"] = source
    where = _where(conds)

    total = db.execute(
        text(f"SELECT count(*) {_EVENTS_FROM} {where}"), params
    ).scalar_one()
    rows = db.execute(
        text(
            "SELECT ce.id, ce.event_id, ce.controller_id, ce.zone_id, ce.gate_id, "
            " ce.direction, ce.plate_number_normalized, ce.captured_at, "
            " ae.occurred_at, ce.source, ce.plate_photo_url, ce.overview_photo_url, "
            " d.decision, d.status, d.reason, "
            " d.id AS decision_id, d.resolved_by_user_id, "
            " (d.id IS NOT NULL AND EXISTS(SELECT 1 FROM barrier_commands bc "
            "   WHERE bc.decision_id = d.id)) AS has_command "
            f"{_EVENTS_FROM} {where} "
            "ORDER BY ce.captured_at DESC, ce.id DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).mappings()
    can_view = can_view_photos(user)
    items = []
    for r in rows:
        d = dict(r)
        d["plate_photo_url"] = _signed_photo_url(
            r["id"], r["plate_photo_url"], "plate", can_view
        )
        d["overview_photo_url"] = _signed_photo_url(
            r["id"], r["overview_photo_url"], "overview", can_view
        )
        items.append(EventRow(**d))
    return EventsPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/events/{event_id}", response_model=EventDetail)
def get_event(
    event_id: int = Path(..., description="camera_events.id"),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*EVENTS_PASSES_ROLES)),
) -> EventDetail:
    """Деталь события: камера-событие + цепочка решений + команды + ручные открытия.

    Фото (§11): ``*_photo_url`` — подписанные короткоживущие URL на ``/photos``
    (не сырой storage-URL), только для пользователя с photo-view.
    """
    ce = db.execute(
        text(
            "SELECT id, event_id, controller_id, zone_id, gate_id, camera_id, "
            " direction, plate_number_original, plate_number_normalized, confidence, "
            " captured_at, received_at, source, plate_photo_url, overview_photo_url, "
            " attributes FROM camera_events WHERE id = :id"
        ),
        {"id": event_id},
    ).mappings().first()
    if ce is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="camera event not found"
        )
    attrs = ce["attributes"] or {}
    can_view = can_view_photos(user)
    camera_event = CameraEventDetail(
        id=ce["id"],
        event_id=ce["event_id"],
        controller_id=ce["controller_id"],
        zone_id=ce["zone_id"],
        gate_id=ce["gate_id"],
        camera_id=ce["camera_id"],
        direction=ce["direction"],
        plate_number_original=ce["plate_number_original"],
        plate_number_normalized=ce["plate_number_normalized"],
        confidence=ce["confidence"],
        captured_at=ce["captured_at"],
        received_at=ce["received_at"],
        source=ce["source"],
        plate_photo_url=_signed_photo_url(ce["id"], ce["plate_photo_url"], "plate", can_view),
        overview_photo_url=_signed_photo_url(
            ce["id"], ce["overview_photo_url"], "overview", can_view
        ),
        vehicle_class=attrs.get("vehicle_class") if isinstance(attrs, dict) else None,
        color=attrs.get("color") if isinstance(attrs, dict) else None,
    )

    decisions = [
        DecisionRow(
            id=r["id"],
            decision=r["decision"],
            status=r["status"],
            reason=r["reason"],
            decision_group_id=str(r["decision_group_id"]) if r["decision_group_id"] else None,
            supersedes_decision_id=r["supersedes_decision_id"],
            resolved_by_user_id=r["resolved_by_user_id"],
            resolved_at=r["resolved_at"],
            review_deadline_at=r["review_deadline_at"],
            created_at=r["created_at"],
            prev_hash=r["prev_hash"],
            row_hash=r["row_hash"],
        )
        for r in db.execute(
            text(
                "SELECT id, decision, status, reason, decision_group_id, "
                " supersedes_decision_id, resolved_by_user_id, resolved_at, "
                " review_deadline_at, created_at, prev_hash, row_hash "
                "FROM access_decisions WHERE camera_event_id = :id ORDER BY id"
            ),
            {"id": event_id},
        ).mappings()
    ]
    decision_ids = [d.id for d in decisions]

    manual_openings = [
        ManualOpeningRow(
            id=r["id"],
            barrier_id=r["barrier_id"],
            command_id=str(r["command_id"]) if r["command_id"] else None,
            decision_id=r["decision_id"],
            operator_user_id=r["operator_user_id"],
            reason=r["reason"],
            created_at=r["created_at"],
        )
        for r in db.execute(
            text(
                "SELECT id, barrier_id, command_id, decision_id, operator_user_id, "
                " reason, created_at FROM manual_openings "
                "WHERE captured_event_id = :id OR decision_id IN :dids ORDER BY id"
            ).bindparams(bindparam("dids", expanding=True)),
            {"id": event_id, "dids": decision_ids or [-1]},
        ).mappings()
    ]
    mo_cmd_ids = [m.command_id for m in manual_openings if m.command_id]

    commands = [
        CommandRow(
            command_id=str(r["command_id"]),
            decision_id=r["decision_id"],
            barrier_id=r["barrier_id"],
            controller_id=r["controller_id"],
            command_type=r["command_type"],
            status=r["status"],
            attempts=r["attempts"],
            created_at=r["created_at"],
            leased_at=r["leased_at"],
            acked_at=r["acked_at"],
            dead_at=r["dead_at"],
        )
        for r in db.execute(
            text(
                "SELECT command_id, decision_id, barrier_id, controller_id, "
                " command_type, status, attempts, created_at, leased_at, acked_at, "
                " dead_at FROM barrier_commands "
                "WHERE decision_id IN :dids OR command_id IN :cmds ORDER BY created_at"
            ).bindparams(
                bindparam("dids", expanding=True), bindparam("cmds", expanding=True)
            ),
            {"dids": decision_ids or [-1], "cmds": mo_cmd_ids or ["00000000-0000-0000-0000-000000000000"]},
        ).mappings()
    ]

    resident_confirmations = [
        ResidentConfirmationRow(
            user_id=r["user_id"],
            response=r["response"],
            created_at=r["created_at"],
        )
        for r in db.execute(
            text(
                "SELECT user_id, response, created_at "
                "FROM access_entry_confirmations "
                "WHERE decision_id IN :dids ORDER BY created_at, id"
            ).bindparams(bindparam("dids", expanding=True)),
            {"dids": decision_ids or [-1]},
        ).mappings()
    ]

    return EventDetail(
        camera_event=camera_event,
        decisions=decisions,
        barrier_commands=commands,
        manual_openings=manual_openings,
        resident_confirmations=resident_confirmations,
    )


# ------------------------------ /vehicles ------------------------------

_VEHICLE_COLS = (
    "id, plate_number_original, plate_number_normalized, plate_country, plate_type, "
    "make, model, color, vehicle_class, status, blocked_reason, blocked_by_user_id, "
    "blocked_at"
)


@router.get("/vehicles", response_model=VehiclesPage)
def list_vehicles(
    status_: str | None = Query(None, alias="status"),
    plate: str | None = Query(None, description="contains по нормализованному номеру"),
    apartment_id: int | None = Query(None),
    limit: int = _limit(DEFAULT_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*VEHICLES_REQUESTS_ROLES)),
) -> VehiclesPage:
    """База авто + связи vehicle_apartments."""
    conds: list[str] = []
    params: dict = {}
    if status_ is not None:
        conds.append("v.status = :status")
        params["status"] = status_
    if plate:
        conds.append("v.plate_number_normalized ILIKE :plate")
        params["plate"] = _plate_pat(plate)
    if apartment_id is not None:
        conds.append(
            "EXISTS(SELECT 1 FROM vehicle_apartments va "
            "WHERE va.vehicle_id = v.id AND va.apartment_id = :apt)"
        )
        params["apt"] = apartment_id
    where = _where(conds)

    total = db.execute(
        text(f"SELECT count(*) FROM vehicles v {where}"), params
    ).scalar_one()
    rows = list(
        db.execute(
            text(
                f"SELECT {_VEHICLE_COLS} FROM vehicles v {where} "
                "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": limit, "offset": offset},
        ).mappings()
    )
    links = _apartments_for(db, [r["id"] for r in rows])
    items = [_vehicle_row(r, links.get(r["id"], [])) for r in rows]
    return VehiclesPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/vehicles/{vehicle_id}", response_model=VehicleDetail)
def get_vehicle(
    vehicle_id: int = Path(..., description="vehicles.id"),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*VEHICLES_REQUESTS_ROLES)),
) -> VehicleDetail:
    """Деталь авто + связи + последние события по нормализованному номеру."""
    r = db.execute(
        text(f"SELECT {_VEHICLE_COLS} FROM vehicles v WHERE id = :id"),
        {"id": vehicle_id},
    ).mappings().first()
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="vehicle not found"
        )
    links = _apartments_for(db, [vehicle_id]).get(vehicle_id, [])
    recent = [
        VehicleEventRow(
            id=e["id"],
            event_id=e["event_id"],
            captured_at=e["captured_at"],
            direction=e["direction"],
            gate_id=e["gate_id"],
            zone_id=e["zone_id"],
            decision=e["decision"],
            status=e["status"],
        )
        for e in db.execute(
            text(
                "SELECT ce.id, ce.event_id, ce.captured_at, ce.direction, ce.gate_id, "
                " ce.zone_id, d.decision, d.status "
                "FROM camera_events ce "
                "LEFT JOIN LATERAL (SELECT decision, status FROM access_decisions ad "
                "  WHERE ad.camera_event_id = ce.id ORDER BY ad.id DESC LIMIT 1) d ON true "
                "WHERE ce.plate_number_normalized = :norm "
                "ORDER BY ce.captured_at DESC, ce.id DESC LIMIT :n"
            ),
            {"norm": r["plate_number_normalized"], "n": VEHICLE_RECENT_EVENTS},
        ).mappings()
    ]
    apt_ids = [link.apartment_id for link in links]
    addr = _addresses_for(db, apt_ids)
    residents = _residents_for(db, apt_ids)
    zones = _serving_zones_for(db, apt_ids)
    apartment_details = [
        ApartmentDetail(
            apartment_id=link.apartment_id,
            relation_type=link.relation_type,
            status=link.status,
            address=addr.get(link.apartment_id),
            residents=residents.get(link.apartment_id, []),
            zones=zones.get(link.apartment_id, []),
        )
        for link in links
    ]
    return VehicleDetail(
        vehicle=_vehicle_row(r, links),
        apartments=links,
        apartment_details=apartment_details,
        recent_events=recent,
    )


# ------------------------------ /passes ------------------------------


@router.get("/passes", response_model=PassesPage)
def list_passes(
    pass_type: str | None = Query(None),
    status_: str | None = Query(None, alias="status"),
    apartment_id: int | None = Query(None),
    limit: int = _limit(DEFAULT_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*EVENTS_PASSES_ROLES)),
) -> PassesPage:
    """Временные пропуска (пилот — taxi)."""
    conds: list[str] = []
    params: dict = {}
    if pass_type is not None:
        conds.append("pass_type = :pass_type")
        params["pass_type"] = pass_type
    if status_ is not None:
        conds.append("status = :status")
        params["status"] = status_
    if apartment_id is not None:
        conds.append("apartment_id = :apt")
        params["apt"] = apartment_id
    where = _where(conds)

    total = db.execute(
        text(f"SELECT count(*) FROM access_passes {where}"), params
    ).scalar_one()
    rows = db.execute(
        text(
            "SELECT id, pass_type, apartment_id, created_by_user_id, zone_id, "
            " plate_number_original, plate_number_normalized, valid_from, valid_until, "
            " max_entries, used_entries, status, source, created_at "
            f"FROM access_passes {where} "
            "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).mappings()
    items = [PassRow(**r) for r in rows]
    return PassesPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/passes/{pass_id}", response_model=PassDetail)
def get_pass(
    pass_id: int = Path(..., description="access_passes.id"),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*EVENTS_PASSES_ROLES)),
) -> PassDetail:
    """Деталь пропуска + заявитель (житель), адрес квартиры и зона."""
    r = db.execute(
        text(
            "SELECT id, pass_type, apartment_id, created_by_user_id, zone_id, "
            " plate_number_original, plate_number_normalized, valid_from, valid_until, "
            " max_entries, used_entries, status, source, created_at "
            "FROM access_passes WHERE id = :id"
        ),
        {"id": pass_id},
    ).mappings().first()
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="pass not found"
        )
    applicant = _applicants_for(db, [r["created_by_user_id"]]).get(
        r["created_by_user_id"]
    )
    address = _addresses_for(db, [r["apartment_id"]]).get(r["apartment_id"])
    return PassDetail(
        pass_record=PassRow(**r),
        applicant=applicant,
        address=address,
        zone=_zone_ref(db, r["zone_id"]),
    )


# ------------------------------ /requests ------------------------------


@router.get("/requests", response_model=RequestsPage)
def list_requests(
    status_: str | None = Query(None, alias="status"),
    apartment_id: int | None = Query(None),
    limit: int = _limit(DEFAULT_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*VEHICLES_REQUESTS_ROLES)),
) -> RequestsPage:
    """Заявки жителей на постоянный автомобиль (resident_access_requests).

    Примечание: у ``resident_access_requests`` нет колонки ``zone_id`` (см.
    DATA_MODEL_PILOT) — поле в ответе отсутствует, в отличие от черновика ТЗ.
    """
    conds: list[str] = []
    params: dict = {}
    if status_ is not None:
        conds.append("status = :status")
        params["status"] = status_
    if apartment_id is not None:
        conds.append("apartment_id = :apt")
        params["apt"] = apartment_id
    where = _where(conds)

    total = db.execute(
        text(f"SELECT count(*) FROM resident_access_requests {where}"), params
    ).scalar_one()
    rows = db.execute(
        text(
            "SELECT id, apartment_id, created_by_user_id, vehicle_id, "
            " plate_number_original, plate_number_normalized, relation_type, status, "
            " reviewed_by_user_id, reviewed_at, review_comment, created_at "
            f"FROM resident_access_requests {where} "
            "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).mappings()
    items = [RequestRow(**r) for r in rows]
    return RequestsPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/requests/{request_id}", response_model=RequestDetail)
def get_request(
    request_id: int = Path(..., description="resident_access_requests.id"),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*VEHICLES_REQUESTS_ROLES)),
) -> RequestDetail:
    """Деталь заявки на авто + заявитель (житель), адрес, обслуживающие зоны и авто."""
    r = db.execute(
        text(
            "SELECT id, apartment_id, created_by_user_id, vehicle_id, "
            " plate_number_original, plate_number_normalized, relation_type, status, "
            " reviewed_by_user_id, reviewed_at, review_comment, created_at "
            "FROM resident_access_requests WHERE id = :id"
        ),
        {"id": request_id},
    ).mappings().first()
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="request not found"
        )
    applicant = _applicants_for(db, [r["created_by_user_id"]]).get(
        r["created_by_user_id"]
    )
    address = _addresses_for(db, [r["apartment_id"]]).get(r["apartment_id"])
    serving_zones = _serving_zones_for(db, [r["apartment_id"]]).get(
        r["apartment_id"], []
    )
    vehicle = None
    if r["vehicle_id"] is not None:
        vr = db.execute(
            text(f"SELECT {_VEHICLE_COLS} FROM vehicles v WHERE id = :id"),
            {"id": r["vehicle_id"]},
        ).mappings().first()
        if vr is not None:
            vehicle = _vehicle_row(
                vr, _apartments_for(db, [vr["id"]]).get(vr["id"], [])
            )
    return RequestDetail(
        request=RequestRow(**r),
        applicant=applicant,
        address=address,
        serving_zones=serving_zones,
        vehicle=vehicle,
    )
