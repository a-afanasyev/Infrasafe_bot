"""Сборка FastAPI-приложения сервиса контроля доступа (ТЗ §1).

Фабрика ``create_app()`` строит приложение и подключает все пилотные роутеры
(§13): health, ingestion, edge long-poll/ack, edge equipment, operator/admin,
WS-панель охраны и health/latency-метрики (§10.2). Swagger (`/docs`,
`/openapi.json`) по умолчанию **выключен в проде** (fail-closed, SEC-01/аудит #4):
явный ``ACCESS_ENABLE_DOCS`` — высший приоритет, иначе гейтится ``DEBUG``.
"""
import os

from fastapi import FastAPI, Request

from access_control import __version__
from access_control.api.camera_events import router as camera_events_router
from access_control.api.commands import router as commands_router
from access_control.api.diagnostics import router as diagnostics_router
from access_control.api.edge import router as edge_router
from access_control.api.equipment import router as equipment_admin_router
from access_control.api.health import router as health_router
from access_control.api.management import router as management_router
from access_control.api.metrics import json_router as metrics_json_router
from access_control.api.metrics import prometheus_router as metrics_prometheus_router
from access_control.api.operator import router as operator_router
from access_control.api.parking_admin import router as parking_admin_router
from access_control.api.registry import router as registry_router
from access_control.api.resident import router as resident_router
from access_control.api.ws_security import router as ws_security_router


def _docs_enabled() -> bool:
    """Включён ли Swagger (fail-closed по умолчанию, SEC-03/аудит #4).

    ``ACCESS_ENABLE_DOCS`` ∈ {1,true,yes,on} → включено; иное явное значение →
    выключено (высший приоритет — ops может форсировать в любую сторону).
    При ОТСУТСТВИИ переменной решение делегируется ``settings.DEBUG``: в dev
    (``DEBUG=true``) Swagger включён для удобства, в проде (``DEBUG=false``)
    выключен. Раньше отсутствие переменной означало «включено» — забытый env в
    проде раскрывал весь API-контур (`/docs` `/redoc` `/openapi.json`).
    """
    raw = os.getenv("ACCESS_ENABLE_DOCS")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    from uk_management_bot.config.settings import settings
    return bool(settings.DEBUG)


def create_app() -> FastAPI:
    """Собрать и вернуть FastAPI-приложение сервиса ``uk-access-api``.

    Returns:
        FastAPI: приложение со всеми пилотными роутерами §13 + health/latency
        метриками §10.2. Swagger гейтится ``ACCESS_ENABLE_DOCS``/``DEBUG``
        (fail-closed: в проде по умолчанию выключен).
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
    # SEC-05 (аудит #4): baseline security-заголовки на каждом ответе — паритет
    # с бот-API (api/main.py). `setdefault` отдаёт приоритет edge-прокси (если он
    # уже выставил заголовок — не перетираем, лишь заполняем пробелы). API отдаёт
    # JSON и не встраивается во фреймы → X-Frame-Options: DENY безопасен. HSTS
    # действует только по HTTPS (публичный edge), на внутреннем HTTP-хопе инертен.
    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        return response

    app.include_router(health_router)
    app.include_router(metrics_prometheus_router)
    app.include_router(metrics_json_router)
    app.include_router(camera_events_router)
    app.include_router(commands_router)
    app.include_router(edge_router)
    app.include_router(operator_router)
    app.include_router(registry_router)
    app.include_router(management_router)
    app.include_router(resident_router)
    app.include_router(equipment_admin_router)
    app.include_router(parking_admin_router)
    app.include_router(diagnostics_router)
    app.include_router(ws_security_router)
    return app
