"""Edge equipment-endpoint'ы Ф6: heartbeat, sync-events, access-snapshot (§8, §13.1).

Все три endpoint'а защищены полной device-auth (``authenticate_edge``, §9.1): валидный
api_key + HMAC тела + timestamp + nonce + IP allowlist + изоляция по ``controller_id``
в пути. Возвращают/трогают ТОЛЬКО данные аутентифицированного контроллера.

* ``POST /edge/{controller_id}/heartbeat`` — приём clock offset (§8.2): пишет
  ``last_heartbeat_at``/``clock_offset_ms``; |offset|>30000мс → сигнал ``fail_closed``;
  5000<|offset|≤30000мс в connected → ``warning``.
* ``POST /edge/{controller_id}/sync-events`` (§8.4) — идемпотентный приём offline-
  событий по ``(controller_id, event_id)``; source=``edge_offline``; НЕ расход
  пропуска; конфликт/просроченный snapshot → отдельные поля.
* ``GET  /edge/{controller_id}/access-snapshot`` (§8.2) — подписанный fail_closed
  snapshot БЕЗ списка номеров; только данные аутентифицированного контроллера.
"""
from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from access_control.domain.enums import Direction, EventSource
from access_control.domain.equipment import EdgeController
from access_control.integrations.media import (
    KINDS as PHOTO_KINDS,
    AccessMediaClient,
    MediaConfigError,
    delete_media_best_effort,
    get_access_media_client,
)
from access_control.repositories import camera_events_repo
from access_control.services.device_auth import authenticate_edge
from access_control.services.snapshot_signing import build_snapshot, sign_snapshot
from uk_management_bot.database.session import get_db

router = APIRouter(prefix="/api/v1/access/edge", tags=["access-edge"])

logger = logging.getLogger(__name__)

# Пороги дрейфа часов edge (§8.2): connected ≤5c; >30c → fail_closed.
CONNECTED_DRIFT_WARNING_MS = 5_000
FAIL_CLOSED_DRIFT_MS = 30_000


# ------------------------------- heartbeat (§8.2) -------------------------------


class HeartbeatRequest(BaseModel):
    """Heartbeat edge: дрейф часов (мс) + статус линка (§8.2)."""

    clock_offset_ms: int = Field(..., description="Дрейф UTC edge относительно backend, мс")
    status: str | None = Field(None, description="Статус линка edge (connected/...)")


@router.post("/{controller_id}/heartbeat")
def post_heartbeat(
    payload: HeartbeatRequest,
    db: Session = Depends(get_db),
    controller: EdgeController = Depends(authenticate_edge),
) -> JSONResponse:
    """Принять heartbeat: записать offset, сигналить fail_closed/warning по дрейфу (§8.2)."""
    offset = payload.clock_offset_ms
    fail_closed = abs(offset) > FAIL_CLOSED_DRIFT_MS
    warning = (not fail_closed) and abs(offset) > CONNECTED_DRIFT_WARNING_MS
    db.execute(
        text(
            "UPDATE edge_controllers "
            "SET last_heartbeat_at = now(), clock_offset_ms = :o, updated_at = now() "
            "WHERE id = :i"
        ),
        {"o": offset, "i": controller.id},
    )
    db.commit()
    return JSONResponse(
        content={
            "received": True,
            "clock_offset_ms": offset,
            "fail_closed": fail_closed,
            "warning": warning,
            # Подсказка edge: при дрейфе перейти в fail_closed (§8.2).
            "offline_mode": "fail_closed" if fail_closed else None,
        }
    )


# ------------------------------- sync-events (§8.4) -----------------------------


class SyncEvent(BaseModel):
    """Одно отложенное offline-событие edge (§8.4)."""

    event_id: str = Field(..., description="Исходный event_id offline-события")
    captured_at: AwareDatetime | None = None
    plate_number: str | None = None
    direction: Direction = Direction.ENTRY
    # Offline-решение edge (информативно; в расход пропуска не превращается, §8.4).
    decision: str | None = None
    snapshot_expired: bool = False
    conflict: bool = False
    attributes: dict | None = None


class SyncEventsRequest(BaseModel):
    """Пачка offline-событий на синхронизацию после восстановления связи (§8.4)."""

    events: list[SyncEvent] = Field(default_factory=list)


@router.post("/{controller_id}/sync-events")
def post_sync_events(
    payload: SyncEventsRequest,
    db: Session = Depends(get_db),
    controller: EdgeController = Depends(authenticate_edge),
) -> JSONResponse:
    """Идемпотентно принять offline-события (§8.4): дедуп по (controller_id, event_id).

    source=``edge_offline``; событие НЕ превращается в расход временного пропуска и не
    создаёт команду открытия (только журналируется в ``controller_sync_events``).
    Повтор того же event_id — no-op (``ON CONFLICT DO NOTHING``).
    """
    accepted = 0
    duplicates = 0
    conflicts = 0
    for ev in payload.events:
        # source фиксируется в payload — отдельной колонки source у таблицы нет (§8.4).
        stored_payload = {
            **(ev.attributes or {}),
            "source": EventSource.EDGE_OFFLINE.value,
            "decision": ev.decision,
            "plate_number": ev.plate_number,
            "direction": ev.direction.value,
            "captured_at": ev.captured_at.isoformat() if ev.captured_at else None,
        }
        row = db.execute(
            text(
                """
                INSERT INTO controller_sync_events
                  (controller_id, event_id, payload, conflict, snapshot_expired,
                   received_at, created_at)
                VALUES
                  (:cid, :eid, CAST(:pl AS JSONB), :cf, :se, now(), now())
                ON CONFLICT (controller_id, event_id) DO NOTHING
                RETURNING id
                """
            ),
            {
                "cid": controller.id,
                "eid": ev.event_id,
                "pl": json.dumps(stored_payload),
                "cf": ev.conflict,
                "se": ev.snapshot_expired,
            },
        ).first()
        if row is None:
            duplicates += 1
        else:
            accepted += 1
            if ev.conflict or ev.snapshot_expired:
                conflicts += 1
    db.commit()
    return JSONResponse(
        content={
            "accepted": accepted,
            "duplicates": duplicates,
            "conflicts": conflicts,
        }
    )


# ----------------------------- camera-event photos (§11, §10.2) ----------------


@router.post("/{controller_id}/camera-events/{event_id}/photos")
async def post_camera_event_photos(
    request: Request,
    controller_id: str = Path(..., description="controller_uid (device-auth, изоляция)"),
    event_id: str = Path(..., description="camera_events.event_id (стабильный id события)"),
    db: Session = Depends(get_db),
    controller: EdgeController = Depends(authenticate_edge),
    media: AccessMediaClient = Depends(get_access_media_client),
) -> JSONResponse:
    """Догрузить фото проезда ПОСЛЕ решения (§10.2 — ВНЕ горячего пути ingestion).

    Латентность здесь не критична (загрузка в Telegram медленная, секунды): edge
    зовёт этот endpoint уже после fast-path решения, поэтому p95 ingestion ≤500мс
    не страдает. Под полной device-auth (``authenticate_edge``): изоляция по
    ``controller_id`` в пути (чужой controller → 403).

    Каждый присланный кадр (``plate``/``overview``, оба опциональны) грузится в
    ОТДЕЛЬНЫЙ канал медиа-сервиса (``kind``, ``ref=f"{controller_id}|{event_id}"``);
    полученный ``media_id`` пишется в ``camera_events.{plate|overview}_photo_url``
    как ``media://{media_id}``. Идемпотентно: повторная загрузка перезаписывает
    ссылку того же ``kind``. Ответ: ``{ok, updated:[kind...]}``.

    A9-P2-14: порядок «проверка события (короткое чтение) → загрузка всех кадров
    БЕЗ открытой транзакции → одна короткая транзакция записи ссылок». Раньше
    UPDATE plate держал row-lock ``camera_events`` на время загрузки overview (до
    30 с), а при неизвестном событии кадр успевал загрузиться и осиротеть. Сбой
    медиа-сервиса → 502 и best-effort удаление уже загруженного; событие исчезло
    до записи → 404 и то же удаление. SQL — в threadpool, не в event loop.

    Multipart парсится вручную (``request.form()``), а не через ``File(...)``:
    device-auth (``authenticate_edge``) уже прочитал и закэшировал тело для HMAC,
    а декларация ``File`` заставила бы FastAPI прочитать форму ПЕРВОЙ и «съесть»
    поток до device-auth (Stream consumed). Парсинг из кэша тела безопасен.
    """
    form = await request.form()
    frames = []
    for kind in PHOTO_KINDS:
        upload = form.get(kind)
        # Берём только файловые поля (UploadFile); строковые значения игнорируем.
        if isinstance(upload, UploadFile):
            frames.append((kind, upload, await upload.read()))

    # A9-P2-14: controller.id — до завершения транзакции (expire_on_commit).
    controller_pk = controller.id
    exists = await run_in_threadpool(_event_exists, db, controller_pk, event_id)
    if not exists:
        # Событие неизвестно этому контроллеру — кадры некуда привязать, не грузим.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="camera event not found"
        )

    uploaded = await _upload_frames(media, frames, ref=f"{controller_id}|{event_id}")
    try:
        found = await run_in_threadpool(
            _write_photo_refs, db, controller_pk, event_id, uploaded
        )
    except Exception:
        await delete_media_best_effort(media, uploaded.values())
        raise
    if not found:
        # Событие исчезло между проверкой и записью — загруженное не нужно.
        await delete_media_best_effort(media, uploaded.values())
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="camera event not found"
        )
    return JSONResponse(content={"ok": True, "updated": list(uploaded)})


def _event_exists(db: Session, controller_pk: int, event_id: str) -> bool:
    """Короткая проверка события; транзакция закрывается ДО загрузки кадров."""
    try:
        pk = camera_events_repo.find_event_pk(
            db, controller_id=controller_pk, event_id=event_id
        )
    finally:
        # Не держать соединение «idle in transaction» на время загрузки (до 30 с).
        db.rollback()
    return pk is not None


async def _upload_frames(
    media: AccessMediaClient, frames: list, *, ref: str
) -> dict[str, int]:
    """Загрузить все кадры; при сбое — best-effort откат уже загруженных, 502."""
    uploaded: dict[str, int] = {}
    try:
        for kind, upload, content in frames:
            result = await media.upload_access_photo(
                kind=kind,
                ref=ref,
                file_data=content,
                filename=upload.filename or f"{kind}.jpg",
                content_type=upload.content_type or "image/jpeg",
            )
            uploaded[kind] = result["media_id"]
    except (httpx.HTTPError, MediaConfigError) as exc:
        await delete_media_best_effort(media, uploaded.values())
        logger.warning("camera photo upload failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="media unavailable"
        )
    return uploaded


def _write_photo_refs(
    db: Session, controller_pk: int, event_id: str, uploaded: dict[str, int]
) -> bool:
    """Одна короткая транзакция на запись всех ссылок; False — события нет."""
    try:
        for kind, media_id in uploaded.items():
            found = camera_events_repo.update_photo_ref(
                db,
                controller_id=controller_pk,
                event_id=event_id,
                kind=kind,
                ref=f"media://{media_id}",
            )
            if found is None:
                db.rollback()
                return False
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


# ------------------------------ access-snapshot (§8.2) --------------------------


@router.get("/{controller_id}/access-snapshot")
def get_access_snapshot(
    controller: EdgeController = Depends(authenticate_edge),
) -> JSONResponse:
    """Отдать подписанный fail_closed-snapshot контроллера (§8.2), без списка номеров.

    Возвращает только данные аутентифицированного контроллера (§9.1). Snapshot
    подписывается backend'ом (Ed25519); edge проверяет ``key_id``/подпись/срок, но в
    ``fail_closed`` въезд не открывает (reject-only, см. ``edge/snapshot_verifier``).
    """
    snapshot = build_snapshot(
        controller_uid=controller.controller_uid,
        zone_id=controller.zone_id,
        offline_mode="fail_closed",
    )
    signed = sign_snapshot(snapshot)
    return JSONResponse(status_code=status.HTTP_200_OK, content=signed.data)
