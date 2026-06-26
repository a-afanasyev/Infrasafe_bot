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

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from uk_management_bot.api.dependencies import require_approved_roles
from uk_management_bot.database.session import get_db

router = APIRouter(prefix="/api/v1/access", tags=["access-registry"])

# RBAC-наборы ролей (§6.2/§6.3).
EVENTS_PASSES_ROLES = ("security_operator", "manager", "system_admin")
VEHICLES_REQUESTS_ROLES = ("manager", "system_admin")

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


class EventDetail(_Frozen):
    camera_event: CameraEventDetail
    decisions: list[DecisionRow]
    barrier_commands: list[CommandRow]
    manual_openings: list[ManualOpeningRow]


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


# ------------------------------ хелперы ------------------------------


def _limit(value: int) -> int:
    return Query(value, ge=1, le=MAX_LIMIT, description="размер страницы (max 200)")


def _plate_pat(plate: str) -> str:
    """ILIKE-паттерн contains по нормализованному номеру (нормализация — uppercase)."""
    return f"%{plate.strip().upper()}%"


def _where(conditions: list[str]) -> str:
    return (" WHERE " + " AND ".join(conditions)) if conditions else ""


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
    _user=Depends(require_approved_roles(*EVENTS_PASSES_ROLES)),
) -> EventsPage:
    """История событий: камера-событие + occurred_at + текущее решение группы."""
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
    items = [EventRow(**r) for r in rows]
    return EventsPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/events/{event_id}", response_model=EventDetail)
def get_event(
    event_id: int = Path(..., description="camera_events.id"),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*EVENTS_PASSES_ROLES)),
) -> EventDetail:
    """Деталь события: камера-событие + цепочка решений + команды + ручные открытия."""
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
        plate_photo_url=ce["plate_photo_url"],
        overview_photo_url=ce["overview_photo_url"],
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

    return EventDetail(
        camera_event=camera_event,
        decisions=decisions,
        barrier_commands=commands,
        manual_openings=manual_openings,
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
    return VehicleDetail(
        vehicle=_vehicle_row(r, links), apartments=links, recent_events=recent
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
