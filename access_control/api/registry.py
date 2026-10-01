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
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from access_control.integrations.media import (
    AccessMediaClient,
    MediaConfigError,
    get_access_media_client,
)
from access_control.repositories import (
    event_history_repo,
    passes_repo,
    residence_directory_repo,
    resident_requests_repo,
    vehicles_repo,
)
from access_control.services import photo_urls
from access_control.services.device_auth import resolve_client_ip
from access_control.services.management import write_audit
from uk_management_bot.api.auth.service import verify_access_token
from uk_management_bot.api.dependencies import require_approved_roles
from uk_management_bot.utils.auth_helpers import get_user_roles
from uk_management_bot.database.session import get_db

router = APIRouter(prefix="/api/v1/access", tags=["access-registry"])

logger = logging.getLogger(__name__)

# RBAC-наборы ролей (§6.2/§6.3).
EVENTS_PASSES_ROLES = ("security_operator", "manager", "system_admin")
VEHICLES_REQUESTS_ROLES = ("manager", "system_admin")
# Отдельное разрешение на ПРОСМОТР фото (§11). Пока совпадает с набором, видящим
# события, НО вынесено отдельно, чтобы потом сузить.
# TODO(§11): сузить до явного photo-view права (а не «кто видит события»).
PHOTO_VIEW_ROLES = ("security_operator", "manager", "system_admin")

# Сколько последних событий по номеру отдаём в детали авто.
VEHICLE_RECENT_EVENTS = 20

# A6-P2-50: пагинация — общая, см. api/pagination.py.
from access_control.api.pagination import (  # noqa: E402
    DEFAULT_LIMIT,
    limit_query as _limit,
)
# A9-P3-12: DTO — в registry_schemas; здесь реэкспорт по прежним именам (их
# импортируют management/resident/parking_admin), SQL — в repositories/.
from access_control.api.registry_schemas import (  # noqa: E402
    AddressInfo,
    ApartmentDetail,
    ApartmentLink,
    ApplicantInfo,
    CameraEventDetail,
    CommandRow,
    DecisionRow,
    EventDetail,
    EventRow,
    EventsPage,
    ManualOpeningRow,
    PassDetail,
    PassRow,
    PassesPage,
    RequestDetail,
    RequestRow,
    RequestsPage,
    ResidentConfirmationRow,
    VehicleDetail,
    VehicleEventRow,
    VehicleRow,
    VehiclesPage,
    ZoneRef,
)


# ------------------------------ хелперы ------------------------------


def _photo_media_id(stored: str) -> str:
    """`media://<id>` → id. Сырой storage/Telegram-URL наружу не отдаём: раньше
    legacy-ветка делала RedirectResponse на него (open-redirect при любом новом
    источнике raw URL — AUD8-SEC-03); сегодня все writer'ы пишут `media://`."""
    if stored.startswith("media://"):
        return stored[len("media://"):]
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="photo not found")


# ------------------------------ photo-view (§11) ------------------------------


def can_view_photos(user) -> bool:
    """Есть ли у пользователя отдельное разрешение на просмотр фото (§11).

    Предикат для гейтинга полей ``*_photo_url`` в реестре (не зависимость — чтобы
    отдавать ``null`` вместо 403 на эндпоинте). TODO(§11): сузить до явного права.
    """
    roles = get_user_roles(user)
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


# --- DTO-сборка поверх repositories/ (SQL — там; здесь только маппинг) ---


def _present_ids(ids: list[int | None]) -> list[int]:
    """Уникальные не-``None`` id (порядок не важен: запросы пакетные)."""
    return [i for i in {*ids} if i is not None]


def _person_name(first_name: str | None, last_name: str | None) -> str | None:
    return " ".join(x for x in (first_name, last_name) if x) or None


def _applicant_info(r: dict) -> ApplicantInfo:
    return ApplicantInfo(
        user_id=r["id"], name=_person_name(r["first_name"], r["last_name"]),
        phone=r["phone"], username=r["username"], telegram_id=r["telegram_id"],
    )


def _zone_ref_of(r: dict, id_key: str = "id") -> ZoneRef:
    return ZoneRef(id=r[id_key], code=r["code"], name=r["name"])


def _apartments_for(db: Session, vehicle_ids: list[int]) -> dict[int, list[ApartmentLink]]:
    """Связи vehicle_apartments для набора авто (одним запросом, без N+1)."""
    if not vehicle_ids:
        return {}
    rows = vehicles_repo.apartment_links(db, vehicle_ids)
    return {
        vid: [
            ApartmentLink(**{k: v for k, v in r.items() if k != "vehicle_id"})
            for r in rows
            if r["vehicle_id"] == vid
        ]
        for vid in vehicle_ids
    }


def _applicants_for(db: Session, user_ids: list[int | None]) -> dict[int, ApplicantInfo]:
    """Данные жителей (users) по id — для заявителя/владельца (без N+1)."""
    rows = residence_directory_repo.users_by_ids(db, _present_ids(user_ids))
    return {r["id"]: _applicant_info(r) for r in rows}


def _addresses_for(db: Session, apartment_ids: list[int | None]) -> dict[int, AddressInfo]:
    """Адрес квартир (apartment→building→yard) по id (без N+1)."""
    rows = residence_directory_repo.addresses_by_apartment_ids(
        db, _present_ids(apartment_ids)
    )
    return {r["apartment_id"]: AddressInfo(**r) for r in rows}


def _serving_zones_for(db: Session, apartment_ids: list[int | None]) -> dict[int, list[ZoneRef]]:
    """Зоны, обслуживающие квартиру (apartment→building→yard ∈ parking_zone_yards)."""
    ids = _present_ids(apartment_ids)
    rows = residence_directory_repo.serving_zones_by_apartment_ids(db, ids)
    return {
        a: [_zone_ref_of(r, "zone_id") for r in rows if r["apartment_id"] == a]
        for a in ids
    }


def _residents_for(db: Session, apartment_ids: list[int | None]) -> dict[int, list[ApplicantInfo]]:
    """Жители квартир (user_apartments approved → users) — владельцы для карточки авто."""
    ids = _present_ids(apartment_ids)
    rows = residence_directory_repo.approved_residents_by_apartment_ids(db, ids)
    return {
        a: [_applicant_info(r) for r in rows if r["apartment_id"] == a] for a in ids
    }


def _zone_ref(db: Session, zone_id: int | None) -> ZoneRef | None:
    """Краткая ссылка на зону по id (для пропуска)."""
    if zone_id is None:
        return None
    r = residence_directory_repo.get_zone(db, zone_id)
    return _zone_ref_of(r) if r else None


def _vehicle_row(r: dict, links: list[ApartmentLink]) -> VehicleRow:
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


def _audit_photo_view(
    db: Session, *, event_id: int, kind: str, actor: int | None, ip: str | None
) -> None:
    """Аудит ``access.photo_view`` + commit (sync SQL — вызывать из threadpool)."""
    write_audit(
        db,
        actor_user_id=actor,
        action="access.photo_view",
        entity_type="camera_event",
        entity_id=event_id,
        details={"kind": kind, "source": "session" if actor else "signed_url"},
        ip_address=ip,
    )
    db.commit()


async def _fetch_photo_bytes(media: AccessMediaClient, media_id: str) -> tuple[bytes, str]:
    """Байты кадра из медиа-сервиса; ошибки media → 404/502 (A9-P2-13).

    404 от media (файл удалён ретеншном/вручную) → 404 клиенту; любая другая
    ошибка (5xx, сеть, не сконфигурирован клиент) → 502: сбой зависимости, а не
    ошибка access-api. Сырой URL/ключ в лог не пишем (§11).
    """
    try:
        return await media.fetch_file(media_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="photo not found")
        logger.warning("media fetch failed: status=%s", exc.response.status_code)
    except (httpx.HTTPError, MediaConfigError) as exc:
        logger.warning("media fetch failed: %s", type(exc).__name__)
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="media unavailable")


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

    Capability по подписи (без Bearer): проверяет подпись+срок → получает байты
    из медиа-сервиса по ``media://{media_id}`` → пишет аудит просмотра
    ``access.photo_view`` (PD-safe details) → отдаёт байты с Content-Type.

    Невалидная подпись → 403, протухшая → 410, отсутствующее фото/событие → 404
    (в т.ч. 404 от медиа-сервиса), прочий сбой медиа-сервиса → 502.

    A9-P2-13: аудит пишется ПОСЛЕ успешного получения байтов — это журнал
    просмотров, а при сбое media просмотра не было (тот же принцип, что у 404
    «фото нет» ниже и AUD8-SEC-03). Раньше аудит коммитился до запроса в media, и
    сбой давал 500 при уже записанном «просмотре». Аудит коммитится ДО отдачи
    ответа: не записался — байты не уходят (fail-closed). Синхронный SQL — в
    threadpool, не в event loop.
    """
    try:
        photo_urls.verify(event_id, kind, exp, sig)
    except photo_urls.PhotoUrlExpired:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="signed url expired")
    except photo_urls.PhotoUrlInvalid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid signature")

    stored = await run_in_threadpool(event_history_repo.photo_ref, db, event_id, kind)
    if not stored:
        # Валидная подпись, но фото нет — просмотра не произошло, аудит не пишем.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="photo not found")
    # AUD8-SEC-03: не-`media://` значение → 404 ДО аудита (просмотра не будет).
    media_id = _photo_media_id(stored)

    # §11: фото лежит в медиа-сервисе — стримим байты, сырой URL наружу не уходит.
    content, content_type = await _fetch_photo_bytes(media, media_id)

    # Просмотр состоялся → аудит (§11/§6.2). Details PD-safe: без номера/URL.
    await run_in_threadpool(
        _audit_photo_view,
        db,
        event_id=event_id,
        kind=kind,
        actor=_optional_actor(request),
        ip=resolve_client_ip(request),
    )
    return Response(content=content, media_type=content_type)


# ------------------------------ /events ------------------------------


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
    total, rows = event_history_repo.page_events(
        db, decision=decision, zone_id=zone_id, gate_id=gate_id, plate=plate,
        date_from=date_from, date_to=date_to, source=source,
        limit=limit, offset=offset,
    )
    can_view = can_view_photos(user)
    items = [
        EventRow(**{
            **r,
            "plate_photo_url": _signed_photo_url(
                r["id"], r["plate_photo_url"], "plate", can_view
            ),
            "overview_photo_url": _signed_photo_url(
                r["id"], r["overview_photo_url"], "overview", can_view
            ),
        })
        for r in rows
    ]
    return EventsPage(items=items, total=total, limit=limit, offset=offset)


def _camera_event_detail(ce: dict, can_view: bool) -> CameraEventDetail:
    attrs = ce["attributes"] or {}
    return CameraEventDetail(
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


def _decision_row(r: dict) -> DecisionRow:
    return DecisionRow(**{
        **r,
        "decision_group_id": str(r["decision_group_id"]) if r["decision_group_id"] else None,
    })


def _manual_opening_row(r: dict) -> ManualOpeningRow:
    return ManualOpeningRow(**{
        **r, "command_id": str(r["command_id"]) if r["command_id"] else None,
    })


def _command_row(r: dict) -> CommandRow:
    return CommandRow(**{**r, "command_id": str(r["command_id"])})


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
    ce = event_history_repo.get_camera_event(db, event_id)
    if ce is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="camera event not found"
        )
    camera_event = _camera_event_detail(ce, can_view_photos(user))
    decisions = [
        _decision_row(r) for r in event_history_repo.decisions_for_event(db, event_id)
    ]
    decision_ids = [d.id for d in decisions]
    manual_openings = [
        _manual_opening_row(r)
        for r in event_history_repo.manual_openings_for_event(db, event_id, decision_ids)
    ]
    mo_cmd_ids = [m.command_id for m in manual_openings if m.command_id]
    commands = [
        _command_row(r)
        for r in event_history_repo.commands_for_event(db, decision_ids, mo_cmd_ids)
    ]
    resident_confirmations = [
        ResidentConfirmationRow(**r)
        for r in event_history_repo.confirmations_for_decisions(db, decision_ids)
    ]
    return EventDetail(
        camera_event=camera_event,
        decisions=decisions,
        barrier_commands=commands,
        manual_openings=manual_openings,
        resident_confirmations=resident_confirmations,
    )


# ------------------------------ /vehicles ------------------------------


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
    total, rows = vehicles_repo.page_vehicles(
        db, status=status_, plate=plate, apartment_id=apartment_id,
        limit=limit, offset=offset,
    )
    links = _apartments_for(db, [r["id"] for r in rows])
    items = [_vehicle_row(r, links.get(r["id"], [])) for r in rows]
    return VehiclesPage(items=items, total=total, limit=limit, offset=offset)


def _apartment_details(db: Session, links: list[ApartmentLink]) -> list[ApartmentDetail]:
    """Связи авто↔квартира + адрес, жители и обслуживающие зоны (пакетно)."""
    apt_ids = [link.apartment_id for link in links]
    addr = _addresses_for(db, apt_ids)
    residents = _residents_for(db, apt_ids)
    zones = _serving_zones_for(db, apt_ids)
    return [
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


@router.get("/vehicles/{vehicle_id}", response_model=VehicleDetail)
def get_vehicle(
    vehicle_id: int = Path(..., description="vehicles.id"),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*VEHICLES_REQUESTS_ROLES)),
) -> VehicleDetail:
    """Деталь авто + связи + последние события по нормализованному номеру."""
    r = vehicles_repo.get_vehicle(db, vehicle_id)
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="vehicle not found"
        )
    links = _apartments_for(db, [vehicle_id]).get(vehicle_id, [])
    recent = [
        VehicleEventRow(**e)
        for e in event_history_repo.recent_events_by_plate(
            db, r["plate_number_normalized"], VEHICLE_RECENT_EVENTS
        )
    ]
    return VehicleDetail(
        vehicle=_vehicle_row(r, links),
        apartments=links,
        apartment_details=_apartment_details(db, links),
        rule_zones=[_zone_ref_of(z) for z in vehicles_repo.rule_zones(db, vehicle_id)],
        recent_events=recent,
    )


@router.get("/apartments/{apartment_id}/serving-zones", response_model=list[ZoneRef])
def get_apartment_serving_zones(
    apartment_id: int = Path(..., description="apartments.id"),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*EVENTS_PASSES_ROLES)),
) -> list[ZoneRef]:
    """Обслуживающие зоны квартиры (apartment→yard→zone) — кандидаты-чекбоксы для
    форм создания пропуска/привязки зон, когда деталь объекта ещё не загружена."""
    return _serving_zones_for(db, [apartment_id]).get(apartment_id, [])


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
    total, rows = passes_repo.page_passes(
        db, pass_type=pass_type, status=status_, apartment_id=apartment_id,
        limit=limit, offset=offset,
    )
    items = [PassRow(**r) for r in rows]
    return PassesPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/passes/{pass_id}", response_model=PassDetail)
def get_pass(
    pass_id: int = Path(..., description="access_passes.id"),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*EVENTS_PASSES_ROLES)),
) -> PassDetail:
    """Деталь пропуска + заявитель (житель), адрес квартиры и зона."""
    r = passes_repo.get_pass(db, pass_id)
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
        serving_zones=_serving_zones_for(db, [r["apartment_id"]]).get(
            r["apartment_id"], []
        ),
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
    total, rows = resident_requests_repo.page_requests(
        db, status=status_, apartment_id=apartment_id, limit=limit, offset=offset,
    )
    items = [RequestRow(**r) for r in rows]
    return RequestsPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/requests/{request_id}", response_model=RequestDetail)
def get_request(
    request_id: int = Path(..., description="resident_access_requests.id"),
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*VEHICLES_REQUESTS_ROLES)),
) -> RequestDetail:
    """Деталь заявки на авто + заявитель (житель), адрес, обслуживающие зоны и авто."""
    r = resident_requests_repo.get_request(db, request_id)
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
        vr = vehicles_repo.get_vehicle(db, r["vehicle_id"])
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
