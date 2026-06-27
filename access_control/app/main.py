"""Сборка FastAPI-приложения сервиса контроля доступа (ТЗ §1).

Фабрика ``create_app()`` строит приложение и подключает все пилотные роутеры
(§13): health, ingestion, edge long-poll/ack, edge equipment, operator/admin,
WS-панель охраны и health/latency-метрики (§10.2). Swagger (`/docs`,
`/openapi.json`) включён по умолчанию; в проде гейтится env ``ACCESS_ENABLE_DOCS``.
"""
import os

from fastapi import FastAPI

from access_control import __version__
from access_control.api.camera_events import router as camera_events_router
from access_control.api.commands import router as commands_router
from access_control.api.edge import router as edge_router
from access_control.api.equipment import router as equipment_admin_router
from access_control.api.health import router as health_router
from access_control.api.management import router as management_router
from access_control.api.metrics import json_router as metrics_json_router
from access_control.api.metrics import prometheus_router as metrics_prometheus_router
from access_control.api.operator import router as operator_router
from access_control.api.registry import router as registry_router
from access_control.api.ws_security import router as ws_security_router


def _docs_enabled() -> bool:
    """Включён ли Swagger. По умолчанию да (dev); прод может выключить env'ом.

    ``ACCESS_ENABLE_DOCS`` ∈ {1,true,yes,on} → включено; остальное → выключено.
    Отсутствие переменной = включено (удобство dev/пилота).
    """
    raw = os.getenv("ACCESS_ENABLE_DOCS")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def create_app() -> FastAPI:
    """Собрать и вернуть FastAPI-приложение сервиса ``uk-access-api``.

    Returns:
        FastAPI: приложение со всеми пилотными роутерами §13 + health/latency
        метриками §10.2. Swagger гейтится ``ACCESS_ENABLE_DOCS`` (дефолт — вкл).
    """
    docs_on = _docs_enabled()
    app = FastAPI(
        title="UK Access API",
        version=__version__,
        # None отключает соответствующий роут (прод-гейт §14.2 п.18).
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
    )
    app.include_router(health_router)
    app.include_router(metrics_prometheus_router)
    app.include_router(metrics_json_router)
    app.include_router(camera_events_router)
    app.include_router(commands_router)
    app.include_router(edge_router)
    app.include_router(operator_router)
    app.include_router(registry_router)
    app.include_router(management_router)
    app.include_router(equipment_admin_router)
    app.include_router(ws_security_router)
    return app
