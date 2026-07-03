"""Health/latency metrics endpoints (§10.2, §14.2 п.17).

Два эндпоинта:

* ``GET /metrics`` — текстовый формат Prometheus (scrape). Латентность по фазам
  (ingestion/decision/db/relay) + gauge'и очереди barrier_commands.
* ``GET /api/v1/access/metrics`` — JSON-сводка: перцентили задержки по фазам,
  бюджет §10.2 (decision p95/p99, relay p95) и агрегаты очереди по контроллерам.

ПД (§11): метки/поля не содержат номер/код/фото — только имена фаз и числовые
``controller_id``. Эндпоинты read-only.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.services import metrics
from access_control.services.barrier_worker import queue_metrics
from uk_management_bot.api.dependencies import require_approved_roles
from uk_management_bot.database.session import get_db

logger = logging.getLogger(__name__)

# SEC-04 (аудит #4): JSON-сводка раскрывает инвентарь контроллеров/бэклог очереди
# (числа, PD-safe, но операционно чувствительны) → гейтим на manager/system_admin.
# Prometheus-текст (/metrics) остаётся без role-gate: его скрейпит внутренний
# Prometheus (bearer-JWT недоступен скрейперу), доступ ограничивается на
# сети/edge (не публикуется наружу).
METRICS_ROLES = ("manager", "system_admin")

# /metrics — без префикса (конвенция Prometheus). JSON-сводка — под /api/v1/access.
prometheus_router = APIRouter(tags=["access-metrics"])
json_router = APIRouter(prefix="/api/v1/access", tags=["access-metrics"])


@prometheus_router.get("/metrics")
def get_prometheus_metrics(db: Session = Depends(get_db)) -> Response:
    """Метрики в формате Prometheus: латентность по фазам + очередь команд (§10.2)."""
    _refresh_queue_gauges(db)
    return Response(
        content=metrics.prometheus_text(),
        media_type=metrics.CONTENT_TYPE_LATEST,
    )


@json_router.get("/metrics")
def get_json_metrics(
    db: Session = Depends(get_db),
    _user=Depends(require_approved_roles(*METRICS_ROLES)),
) -> JSONResponse:
    """JSON-сводка задержки (перцентили + бюджет §10.2) и очереди barrier_commands.

    RBAC (SEC-04): только manager/system_admin (approved); иначе 403, без auth → 401.
    """
    payload = metrics.latency_snapshot_payload()
    payload["queue"] = _queue_summary(db)
    return JSONResponse(content=payload)


def _controller_ids(db: Session) -> list[int]:
    """Id всех контроллеров (для агрегатов очереди). PD-safe (числовые id)."""
    rows = db.execute(text("SELECT id FROM edge_controllers ORDER BY id")).all()
    return [int(r[0]) for r in rows]


def _refresh_queue_gauges(db: Session) -> None:
    """Обновить prometheus-gauge'и очереди по каждому контроллеру (best-effort)."""
    try:
        for cid in _controller_ids(db):
            m = queue_metrics(db, cid)
            metrics.set_queue_gauges(
                controller_id=cid,
                age_seconds=m.max_pending_age_seconds,
                pending=m.pending,
                leased=m.leased,
                dead=m.dead,
            )
    except Exception:  # noqa: BLE001 — наблюдаемость не должна ронять scrape
        logger.exception("queue gauge refresh failed")


def _queue_summary(db: Session) -> dict:
    """Сводка очереди по контроллерам для JSON (PD-safe: только числовые id)."""
    summary: dict[str, dict] = {}
    try:
        for cid in _controller_ids(db):
            m = queue_metrics(db, cid)
            summary[str(cid)] = {
                "max_pending_age_seconds": m.max_pending_age_seconds,
                "pending": m.pending,
                "leased": m.leased,
                "dead": m.dead,
            }
    except Exception:  # noqa: BLE001
        logger.exception("queue summary failed")
    return summary
