"""Endpoint приёма ANPR-событий: POST /api/v1/access/camera-events/anpr (§13.1).

Принимает ANPR-DTO от edge/камеры, вызывает идемпотентный ingestion и возвращает
решение (+ команду для allow — fast-path заготовка §9.2). Публичного
``/access-decisions`` нет (§13.2): решение принимается ВНУТРИ ingestion, нельзя
вызвать engine в обход device-auth.

Device-auth (§9.1, Ф6): полная проверка через ``authenticate_edge`` — api_key (хэш),
HMAC подписи тела, freshness timestamp, anti-replay nonce, IP/VPN allowlist и статус
контроллера (is_active И status='active'). Идентичность берётся из подписи, а не из
тела; body.controller_uid обязан совпасть с аутентифицированным контроллером.
"""
from __future__ import annotations

import datetime as dt
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy.orm import Session

from access_control.domain.enums import Direction, EventSource
from access_control.domain.equipment import EdgeController
from access_control.services.device_auth import authenticate_edge
from access_control.services.ingestion import (
    DEFAULT_CAPTURED_AT_MAX_SKEW_SECONDS,
    AnprIngestInput,
    IngestResult,
    ingest_anpr,
    is_captured_at_fresh,
)
from uk_management_bot.database.session import get_db

router = APIRouter(prefix="/api/v1/access", tags=["access-camera-events"])

logger = logging.getLogger(__name__)

# Порог свежести captured_at (§7, §9.2), конфигурируемо через env.
CAPTURED_AT_MAX_SKEW_SECONDS = int(
    os.getenv(
        "ACCESS_CAPTURED_AT_MAX_SKEW_SECONDS",
        str(DEFAULT_CAPTURED_AT_MAX_SKEW_SECONDS),
    )
)


class AnprEventRequest(BaseModel):
    """ANPR-событие от edge/камеры (§7 вход Decision Engine)."""

    controller_uid: str = Field(..., description="Логический id контроллера (device-auth)")
    event_id: str = Field(..., description="Стабильный/детерминированный id события (§10.1)")
    zone_id: int | None = None
    gate_id: int | None = None
    camera_id: int | None = None
    barrier_id: int | None = None
    plate_number: str | None = None
    # Enum-валидация: невалидное direction/source → 422, не 500.
    direction: Direction = Direction.ENTRY
    source: EventSource = EventSource.CONNECTED
    confidence: float | None = None
    # AwareDatetime: timezone-naive captured_at отклоняется (422), иначе дрейф
    # окна дедупа (§10.1).
    captured_at: AwareDatetime


class CommandResponse(BaseModel):
    """Команда открытия в fast-path ответе (§9.2)."""

    command_id: str
    barrier_id: int
    expires_at: dt.datetime | None = None


class AnprEventResponse(BaseModel):
    """Ответ ingestion: решение (+ команда для allow)."""

    decision: str
    status: str
    reason: str | None = None
    decision_id: int | None = None
    decision_group_id: str | None = None
    command: CommandResponse | None = None
    replayed: bool = False


@router.post("/camera-events/anpr", response_model=AnprEventResponse)
def post_anpr_event(
    payload: AnprEventRequest,
    db: Session = Depends(get_db),
    controller: EdgeController = Depends(authenticate_edge),
) -> AnprEventResponse:
    """Принять ANPR-событие, вернуть решение и (для allow) команду открытия (§9.1)."""
    # Идентичность — из device-auth подписи (controller). Тело не может выдавать себя
    # за другой контроллер: body.controller_uid обязан совпасть (§9.1 изоляция).
    if payload.controller_uid != controller.controller_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="controller mismatch",
        )
    # §9.2: caller-управляемый captured_at — момент решения для сроков пропусков/
    # правил. Несвежий timestamp отвергаем (422), иначе обход valid_until.
    if not is_captured_at_fresh(
        payload.captured_at, max_skew_seconds=CAPTURED_AT_MAX_SKEW_SECONDS
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="captured_at not fresh",
        )
    try:
        result: IngestResult = ingest_anpr(
            db,
            AnprIngestInput(
                controller_id=controller.id,
                event_id=payload.event_id,
                zone_id=payload.zone_id,
                gate_id=payload.gate_id,
                camera_id=payload.camera_id,
                barrier_id=payload.barrier_id,
                plate_number_original=payload.plate_number,
                direction=payload.direction.value,
                confidence=payload.confidence,
                captured_at=payload.captured_at,
                source=payload.source.value,
            ),
        )
    except HTTPException:
        raise
    except Exception:
        # PD-safe: логируем без номера/фото/кода; в ответ — без стека/ПД (§11).
        logger.exception(
            "anpr ingest failed (controller_uid=%s event_id=%s)",
            payload.controller_uid,
            payload.event_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="internal error",
        )
    command = (
        CommandResponse(
            command_id=result.command.command_id,
            barrier_id=result.command.barrier_id,
            expires_at=result.command.expires_at,
        )
        if result.command is not None
        else None
    )
    return AnprEventResponse(
        decision=result.decision,
        status=result.status,
        reason=result.reason,
        decision_id=result.decision_id,
        decision_group_id=result.decision_group_id,
        command=command,
        replayed=result.replayed,
    )
