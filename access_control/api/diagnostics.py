"""ADMIN-эндпоинт диагностики точки въезда: синтетический ANPR через Decision Engine.

Замена камеры для приёмки (§6.1, §7, §11, §15): ``system_admin`` шлёт синтетическое
ANPR-событие на контроллер серверно (без device-auth — это аутентифицированное
admin-действие), оно проходит ТОТ ЖЕ Decision Engine, что и реальное событие с
камеры: ``ingest_anpr`` пишет camera_events/access_decisions/access_events, при allow
создаёт ``barrier_command`` и публикует PD-safe live-событие охране (как обычное).

Назначение — проверить корректность конфигурации реальной точки (привязка зоны/
gate/шлагбаума, правила доступа авто, генерация команды) без реальной камеры.

USER-API (JWT/cookie — ``require_approved_roles``, НЕ device-auth). RBAC: только
``system_admin`` (как управление контроллерами, §6.1); прочие → 403, без auth → 401.

PD (§11): синтетический номер по умолчанию (``DIAG…``); в аудит номер НЕ пишется —
только флаг diagnostic + контроллер + направление + diag-event_id.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from access_control.domain.enums import EventSource
from access_control.repositories import equipment_repo
from access_control.services import equipment_admin as svc
from access_control.services.ingestion import (
    AnprIngestInput,
    IngestResult,
    ingest_anpr,
)
from access_control.services.management import write_audit
from uk_management_bot.api.dependencies import require_approved_roles
from uk_management_bot.database.session import get_db

router = APIRouter(prefix="/api/v1/access/admin", tags=["access-admin-diagnostics"])

logger = logging.getLogger(__name__)

# RBAC: диагностика приравнена к управлению оборудованием (§6.1) — только админ.
ADMIN_ONLY_ROLES = ("system_admin",)

# Синтетические дефолты приёмки (§15): номер не ПД, confidence заведомо выше порога.
DEFAULT_DIAG_PLATE = "DIAG0001"
DEFAULT_DIAG_CONFIDENCE = 0.99

DirectionLit = Literal["entry", "exit"]


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TestEventRequest(BaseModel):
    """Тело диагностики: всё опционально, дефолты — синтетические (§15)."""

    plate_number: str = Field(
        default=DEFAULT_DIAG_PLATE, min_length=1, max_length=32,
        description="Синтетический номер (дефолт DIAG0001)",
    )
    direction: DirectionLit = "entry"
    confidence: float = Field(default=DEFAULT_DIAG_CONFIDENCE, ge=0.0, le=1.0)


class TestEventCommand(BaseModel):
    command_id: str
    barrier_id: int


class TestEventResponse(BaseModel):
    """Результат диагностики: решение движка + выведенный scope точки + команда."""

    decision: str
    status: str
    reason: str | None = None
    decision_id: int | None = None
    event_id: str
    zone_id: int | None = None
    gate_id: int | None = None
    barrier_id: int | None = None
    command: TestEventCommand | None = None


@router.post(
    "/controllers/{controller_id}/test-event", response_model=TestEventResponse
)
def post_test_event(
    body: TestEventRequest,
    request: Request,
    controller_id: int = Path(..., description="edge_controllers.id"),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*ADMIN_ONLY_ROLES)),
) -> TestEventResponse:
    """Прогнать синтетическое ANPR-событие через реальный Decision Engine (§7).

    Серверный вызов ``ingest_anpr`` (без device-auth): scope (zone/gate/barrier)
    выводится из КОНТРОЛЛЕРА, как для реального события, а не из тела. ``event_id``
    — уникальный ``diag-<uuid>`` (каждый тест новый, идемпотентность не нужна),
    ``captured_at=now`` (свежий — пройдёт freshness), ``attributes.diagnostic=true``,
    ``source=connected``. Неполная конфигурация точки (нет gate/barrier) НЕ ошибка:
    возвращаем решение как есть (команда null), чтобы диагностика её показала.
    """
    try:
        controller = svc.get_controller(db, controller_id)
    except svc.NotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    # Scope для отчёта диагностики выводим из контроллера ТАК ЖЕ, как ingestion
    # (§9.1): zone контроллера → первый активный gate → первый активный barrier.
    zone_id = controller.zone_id
    gate_id = equipment_repo.first_active_gate_for_controller(db, controller_id)
    barrier_id = (
        equipment_repo.first_active_barrier_for_gate(db, gate_id)
        if gate_id is not None
        else None
    )

    event_id = f"diag-{uuid.uuid4()}"

    # Аудит admin-действия (§6.2/§11): PD-safe — без номера, только флаг diagnostic
    # + контроллер + направление + diag-event_id. Отдельный commit: фиксируем факт
    # запуска диагностики независимо от исхода приёма.
    write_audit(
        db,
        actor_user_id=user.id,
        action="access.diagnostic_test_event",
        entity_type="edge_controller",
        entity_id=controller_id,
        details={
            "diagnostic": True,
            "direction": body.direction,
            "event_id": event_id,
        },
        ip_address=_client_ip(request),
    )
    db.commit()

    try:
        result: IngestResult = ingest_anpr(
            db,
            AnprIngestInput(
                controller_id=controller_id,
                event_id=event_id,
                # zone/gate/barrier выводятся из контроллера ВНУТРИ ingestion (§9.1).
                zone_id=None,
                gate_id=None,
                camera_id=None,
                barrier_id=None,
                plate_number_original=body.plate_number,
                direction=body.direction,
                confidence=body.confidence,
                captured_at=_utcnow(),
                attributes={"diagnostic": True},
                source=EventSource.CONNECTED.value,
            ),
        )
    except Exception:
        # PD-safe: логируем без номера/фото; в ответ — без стека/ПД (§11).
        logger.exception(
            "diagnostic test-event failed (controller_id=%s event_id=%s)",
            controller_id,
            event_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal error"
        )

    command = (
        TestEventCommand(
            command_id=result.command.command_id, barrier_id=result.command.barrier_id
        )
        if result.command is not None
        else None
    )
    return TestEventResponse(
        decision=result.decision,
        status=result.status,
        reason=result.reason,
        decision_id=result.decision_id,
        event_id=event_id,
        zone_id=zone_id,
        gate_id=gate_id,
        barrier_id=barrier_id,
        command=command,
    )
