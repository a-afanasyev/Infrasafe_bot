"""ARCH-012: API application lifespan extracted from `api/main.py`.

Owns the FastAPI startup/shutdown contextmanager and the background loops
(outbox processor, hourly reconciliation, daily outbox retention) plus the
startup rate-limit backend probe. Kept import-light and free of route
definitions so `main.py` stays a thin assembly module.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from uk_management_bot.api.rate_limit import rate_limit_backend_status
from uk_management_bot.config.settings import settings

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup — launch outbox processor if enabled
    from uk_management_bot.services.webhook_sender import process_outbox

    async def _outbox_loop():
        while True:
            try:
                await process_outbox()
            except Exception:
                _logger.exception("Outbox processor error")
            await asyncio.sleep(10)

    async def _reconciliation_loop():
        # Run reconciliation hourly. Sleep first so we don't slam startup.
        await asyncio.sleep(300)  # 5 min warmup
        while True:
            # Each reconciler imports + runs inside its own try/except so an
            # ImportError or runtime failure in one cannot mask or skip the
            # other. Imports are deferred (not module-level) on purpose —
            # keeps lifespan startup resilient to a recon-module bug.
            try:
                from uk_management_bot.services.reconciliation import reconcile_buildings
                result = await reconcile_buildings()
                _logger.info("reconcile_buildings cycle: %s", result)
            except Exception:
                _logger.exception("Reconciliation (buildings) error")
            try:
                from uk_management_bot.services.reconciliation import reconcile_requests
                req_result = await reconcile_requests()
                _logger.info("reconcile_requests cycle: %s", req_result)
            except Exception:
                _logger.exception("Reconciliation (requests) error")
            await asyncio.sleep(3600)  # 1 hour

    async def _outbox_retention_loop():
        # OPS-105: purge old 'sent' outbox records daily. Sleep first so we
        # don't run a DELETE during startup churn.
        from uk_management_bot.services.outbox_retention import purge_old_sent_outbox

        await asyncio.sleep(600)  # 10 min warmup
        while True:
            try:
                result = await purge_old_sent_outbox()
                _logger.info("Outbox retention cycle: %s", result)
            except Exception:
                _logger.exception("Outbox retention error")
            await asyncio.sleep(86400)  # 24 hours

    # SEC-062: surface rate-limiter backend degradation loudly at startup.
    # Fail-open is deliberate, but silent fallback to per-worker in-memory
    # counters must be alertable — log ERROR if Redis is the configured backend
    # yet unreachable.
    try:
        rl_status = await rate_limit_backend_status()
        if rl_status["configured_backend"] == "redis" and rl_status["redis_reachable"] is False:
            _logger.error(
                "Rate-limit Redis backend unreachable at startup — limiter degraded "
                "to per-worker in-memory counters (effective limit ~Nx per worker). "
                "Check REDIS_URL / Redis availability."
            )
        else:
            _logger.info("Rate-limit backend status: %s", rl_status)
    except Exception:
        _logger.exception("Rate-limit backend probe failed")

    # COD-03: register a single API-process Bot as the shared notification bot.
    # API endpoints notify via notification_service._get_shared_bot() (feedback,
    # transfer/acceptance reminders); without registration that helper lazily
    # creates a Bot whose aiohttp session is never closed (leak). Here we own one
    # HTML bot on the uvicorn loop and close it on shutdown.
    api_bot = None
    try:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        from uk_management_bot.services.notification_service import set_shared_bot

        api_bot = Bot(
            token=settings.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        set_shared_bot(api_bot)
        app.state.notification_bot = api_bot
        _logger.info("API notification bot registered")
    except Exception:
        _logger.exception("Failed to register API notification bot")

    task = None
    reconcile_task = None
    retention_task = None
    if settings.INFRASAFE_WEBHOOK_ENABLED:
        task = asyncio.create_task(_outbox_loop())
        _logger.info("Webhook outbox processor started (10s interval)")
        reconcile_task = asyncio.create_task(_reconciliation_loop())
        _logger.info("Reconciliation loop started (1h interval, advisory-lock guarded)")
        retention_task = asyncio.create_task(_outbox_retention_loop())
        _logger.info("Outbox retention loop started (24h interval, 30-day window)")
    yield
    # shutdown
    for bg_task in (task, reconcile_task, retention_task):
        if bg_task:
            bg_task.cancel()
            try:
                await bg_task
            except asyncio.CancelledError:
                pass
    # Close the API notification bot + reset the shared-bot global.
    try:
        from uk_management_bot.services.notification_service import set_shared_bot
        if api_bot is not None:
            await api_bot.session.close()
        set_shared_bot(None)
    except Exception:
        _logger.exception("Error closing API notification bot")
    # Dispose DB connection pools
    try:
        from uk_management_bot.database.session import async_engine
        if async_engine:
            await async_engine.dispose()
            _logger.info("API DB pool disposed")
    except Exception:
        _logger.exception("Error disposing DB pool")
