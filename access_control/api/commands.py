"""Durable channel barrier_commands: long-poll lease + compare-and-set ACK (§9.2, §13.1).

Endpoints (edge ↔ backend, пилот — durable доставка команд шлагбаума):

* ``GET  /api/v1/access/edge/{controller_id}/commands/next`` — атомарно лизит ОДНУ
  pending-команду ТОЛЬКО этого контроллера (``FOR UPDATE SKIP LOCKED``); long-poll
  с небольшим таймаутом; 204 если очередь пуста.
* ``POST /api/v1/access/edge/{controller_id}/commands/{command_id}/ack`` —
  compare-and-set по ``(command_id, controller_id, lease_token, status='leased')``;
  идемпотентный повторный ACK возвращает сохранённый результат БЕЗ повторного
  исполнения; неверный/протухший lease_token → 409.

Device-auth (§9.1, Ф6) — полная проверка через ``authenticate_edge``: api_key (хэш) +
HMAC тела + freshness timestamp + anti-replay nonce + IP allowlist + статус
контроллера + изоляция по ``controller_id`` в пути. Запросы к lease/ack дополнительно
скоупятся по ``controller.id`` в SQL — контроллер физически не может лизить/акать
команды чужого ``controller_id``.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
import uuid
from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.domain.equipment import EdgeController
from access_control.services.device_auth import authenticate_edge
from uk_management_bot.database.session import get_db

router = APIRouter(prefix="/api/v1/access/edge", tags=["access-commands"])

logger = logging.getLogger(__name__)

# Lease TTL по умолчанию (§9.2): срок аренды команды edge'ом.
DEFAULT_LEASE_TTL_SECONDS = 30
# Long-poll: короткий цикл ожидания pending-команды (небольшой для тестов).
DEFAULT_LONG_POLL_SECONDS = 0.0
LONG_POLL_INTERVAL_SECONDS = 0.25
MAX_LONG_POLL_SECONDS = 25.0


@dataclass(frozen=True)
class LeasedCommand:
    """Залиженная команда, выдаваемая edge через durable channel.

    ``payload`` — вычисляемый алиас (``command_type`` + ``barrier_id``) для
    backward-compat edge-клиента: дублирует поля, чтобы edge не разбирал плоскую
    структуру. Источник истины — отдельные поля выше.
    """

    command_id: str
    barrier_id: int
    command_type: str
    lease_token: str
    expires_at: dt.datetime | None
    payload: dict


@dataclass(frozen=True)
class AckOutcome:
    """Результат ACK: ``replayed`` — идемпотентный повтор по сохранённому результату."""

    command_id: str
    status: str
    result: dict | None
    replayed: bool


class AckConflict(Exception):
    """Неверный/протухший lease_token или чужой контроллер (compare-and-set провал)."""


def _try_lease(
    db: Session, controller_db_id: int, lease_ttl_seconds: int
) -> LeasedCommand | None:
    """Одна попытка атомарного lease (без long-poll цикла).

    Margin (§9.2): не выдаём команду, чей ``expires_at`` истечёт в течение аренды
    (``expires_at > now() + lease_ttl``) — иначе edge получит команду, протухающую
    до исполнения.
    """
    lease_token = str(uuid.uuid4())
    row = db.execute(
        text(
            """
            UPDATE barrier_commands
            SET status = 'leased',
                lease_token = :tok,
                lease_expires_at = now() + (:ttl * interval '1 second'),
                attempts = attempts + 1,
                leased_at = now(),
                updated_at = now()
            WHERE command_id = (
                SELECT command_id FROM barrier_commands
                WHERE controller_id = :cid
                  AND status = 'pending'
                  AND (
                      expires_at IS NULL
                      OR expires_at > now() + (:ttl * interval '1 second')
                  )
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING command_id, barrier_id, command_type, lease_token, expires_at
            """
        ),
        {"tok": lease_token, "ttl": lease_ttl_seconds, "cid": controller_db_id},
    ).first()
    if row is None:
        # Очередь пуста — фиксируем (закрываем) транзакцию и выходим.
        db.commit()
        return None
    db.commit()
    return LeasedCommand(
        command_id=str(row[0]),
        barrier_id=row[1],
        command_type=row[2],
        lease_token=str(row[3]),
        expires_at=row[4],
        payload={"command_type": row[2], "barrier_id": row[1]},
    )


def lease_next_command(
    db: Session,
    controller_db_id: int,
    *,
    lease_ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    long_poll_seconds: float = DEFAULT_LONG_POLL_SECONDS,
) -> LeasedCommand | None:
    """Лизить ОДНУ pending-команду контроллера атомарно (§9.2); None если пусто.

    Команда скоупится по ``controller_db_id`` — чужие команды не выдаются (§9.1).
    ``long_poll_seconds`` — короткий цикл ожидания (sync-endpoint в threadpool, не
    блокирует event-loop); 0 — одна попытка.
    """
    deadline = time.monotonic() + min(max(long_poll_seconds, 0.0), MAX_LONG_POLL_SECONDS)
    while True:
        leased = _try_lease(db, controller_db_id, lease_ttl_seconds)
        if leased is not None or time.monotonic() >= deadline:
            return leased
        time.sleep(LONG_POLL_INTERVAL_SECONDS)


def ack_command(
    db: Session,
    controller_db_id: int,
    command_id: str,
    lease_token: str,
    result: dict | None,
) -> AckOutcome:
    """Compare-and-set завершение команды (§9.2). Идемпотентен по сохранённому ACK.

    Порядок: (1) CAS ``leased -> acked`` по ``(command_id, controller_id, lease_token)``;
    (2) если 0 строк — это либо повтор уже acked-команды тем же lease_token (вернуть
    сохранённый результат, БЕЗ повторного исполнения), либо чужой/протухший token →
    ``AckConflict``.
    """
    res_json = json.dumps(result) if result is not None else None
    updated = db.execute(
        text(
            """
            UPDATE barrier_commands
            SET status = 'acked',
                acked_at = now(),
                ack_result = CAST(:res AS JSONB),
                updated_at = now()
            WHERE command_id = :cmd
              AND controller_id = :cid
              AND lease_token = :tok
              AND status = 'leased'
            RETURNING ack_result
            """
        ),
        {"res": res_json, "cmd": command_id, "cid": controller_db_id, "tok": lease_token},
    ).first()
    if updated is not None:
        db.commit()
        return AckOutcome(
            command_id=command_id, status="acked", result=updated[0], replayed=False
        )

    # CAS не сработал — разобрать почему.
    row = db.execute(
        text(
            "SELECT status, lease_token, ack_result FROM barrier_commands "
            "WHERE command_id = :cmd AND controller_id = :cid"
        ),
        {"cmd": command_id, "cid": controller_db_id},
    ).first()
    if row is not None and row[0] == "acked" and str(row[1]) == str(lease_token):
        # Повторный ACK после потери ответа: сохранённый результат, без реисполнения.
        db.commit()
        return AckOutcome(
            command_id=command_id, status="acked", result=row[2], replayed=True
        )
    # CAS-провал: НЕ коммитим (нечего фиксировать) — закрываем read-txn и поднимаем.
    db.rollback()
    raise AckConflict(
        f"ack rejected for command {command_id}: stale/invalid lease token or controller"
    )


# ----------------------------- HTTP-слой -----------------------------


class AckRequest(BaseModel):
    """Тело ACK: lease_token аренды + результат исполнения реле.

    ``result`` — ограниченная плоская карта (значения ``bool|str|int|None``):
    неограниченный/вложенный JSONB не принимаем (§9.2), чтобы edge не мог
    протолкнуть произвольный объём данных в ack_result.
    """

    lease_token: str
    result: dict[str, bool | str | int | None] | None = None


@router.get("/{controller_id}/commands/next")
def get_next_command(
    wait: float = Query(
        DEFAULT_LONG_POLL_SECONDS, ge=0.0, le=MAX_LONG_POLL_SECONDS,
        description="long-poll ожидание, c",
    ),
    db: Session = Depends(get_db),
    controller: EdgeController = Depends(authenticate_edge),
) -> Response:
    """Лизить следующую pending-команду контроллера (§9.2). 204 если очередь пуста."""
    leased = lease_next_command(db, controller.id, long_poll_seconds=wait)
    if leased is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return JSONResponse(
        content={
            "command_id": leased.command_id,
            "barrier_id": leased.barrier_id,
            "command_type": leased.command_type,
            "lease_token": leased.lease_token,
            "expires_at": leased.expires_at.isoformat() if leased.expires_at else None,
            "payload": leased.payload,
        }
    )


@router.post("/{controller_id}/commands/{command_id}/ack")
def post_command_ack(
    body: AckRequest,
    command_id: UUID = Path(..., description="UUID команды"),
    db: Session = Depends(get_db),
    controller: EdgeController = Depends(authenticate_edge),
) -> JSONResponse:
    """Подтвердить исполнение команды (§9.2). Идемпотентно; чужой/протухший token → 409.

    ``command_id`` валидируется как UUID на уровне пути: невалидный → 422 (не 500).
    """
    try:
        outcome = ack_command(
            db, controller.id, str(command_id), body.lease_token, body.result
        )
    except AckConflict:
        # PD-safe: только идентификаторы, без номера/фото/кода (§11).
        logger.warning(
            "ack conflict: controller_id=%s command_id=%s (stale/invalid lease)",
            controller.id,
            command_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="stale or invalid lease token",
        )
    return JSONResponse(
        content={
            "command_id": outcome.command_id,
            "status": outcome.status,
            "result": outcome.result,
            "replayed": outcome.replayed,
        }
    )
