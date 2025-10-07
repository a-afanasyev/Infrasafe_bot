"""
Bot Gateway Service - Main Application
UK Management Bot - Sprint 19-22

Aiogram 3.x bot initialization with microservices integration.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.core.config import settings
from app.core.database import init_database, close_database, check_database_health
from app.core.metrics import init_metrics
from app.core.tracing import init_tracing

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

# Global bot and dispatcher instances
bot: Bot = None
dp: Dispatcher = None
storage: RedisStorage = None


async def on_startup() -> None:
    """
    Actions to perform on bot startup.

    - Initialize database
    - Connect to Redis
    - Setup webhooks (if enabled)
    - Load bot commands
    """
    global bot

    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # Initialize metrics
    init_metrics(
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT
    )

    # Initialize distributed tracing
    init_tracing(
        service_name=settings.APP_NAME,
        service_version=settings.APP_VERSION,
        jaeger_host=settings.JAEGER_HOST,
        jaeger_port=settings.JAEGER_PORT,
        environment=settings.ENVIRONMENT,
        enabled=settings.TRACING_ENABLED
    )

    # Initialize database
    try:
        await init_database()
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise

    # Test Redis connection
    try:
        redis_info = await storage.redis.ping()
        logger.info(f"✅ Redis connected: {settings.REDIS_URL.split('@')[1] if '@' in settings.REDIS_URL else settings.REDIS_URL}")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        raise

    # Setup webhook if enabled
    if settings.TELEGRAM_USE_WEBHOOK:
        logger.info(f"Setting up webhook: {settings.TELEGRAM_WEBHOOK_URL}")
        await bot.set_webhook(
            url=settings.TELEGRAM_WEBHOOK_URL,
            secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
            allowed_updates=settings.ALLOWED_UPDATES,
            drop_pending_updates=settings.SKIP_UPDATES
        )
    else:
        # Delete webhook to use polling
        await bot.delete_webhook(drop_pending_updates=settings.SKIP_UPDATES)
        logger.info("Using long polling mode")

    # Set bot commands
    # TODO: Load from database or configuration
    # await bot.set_my_commands([...])

    logger.info("✅ Bot startup complete")


async def on_shutdown() -> None:
    """
    Actions to perform on bot shutdown.

    - Close database connections
    - Close Redis connections
    - Delete webhooks
    """
    logger.info("🛑 Shutting down bot...")

    # Close database
    await close_database()

    # Close Redis storage
    await storage.close()

    # Close bot session
    await bot.session.close()

    logger.info("✅ Bot shutdown complete")


def create_bot() -> Bot:
    """
    Create and configure Aiogram Bot instance.

    Returns:
        Configured Bot instance
    """
    return Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML if settings.MESSAGE_PARSE_MODE == "HTML" else ParseMode.MARKDOWN
        )
    )


def create_dispatcher() -> Dispatcher:
    """
    Create and configure Aiogram Dispatcher.

    Returns:
        Configured Dispatcher instance
    """
    global storage

    # Initialize Redis FSM storage
    storage = RedisStorage.from_url(
        settings.REDIS_URL,
        state_ttl=settings.REDIS_FSM_TTL,
        data_ttl=settings.REDIS_SESSION_TTL
    )

    # Create dispatcher
    dispatcher = Dispatcher(storage=storage)

    # Register middlewares (order matters: metrics -> rate_limit -> logging -> auth)
    from app.middleware.metrics import MetricsMiddleware
    from app.middleware.rate_limit import RateLimitMiddleware
    from app.middleware.logging import LoggingMiddleware
    from app.middleware.auth import AuthMiddleware

    rate_limiter = RateLimitMiddleware()

    # Apply to messages
    dispatcher.message.middleware(MetricsMiddleware())
    dispatcher.message.middleware(rate_limiter)
    dispatcher.message.middleware(LoggingMiddleware())
    dispatcher.message.middleware(AuthMiddleware())

    # Apply to callback queries
    dispatcher.callback_query.middleware(MetricsMiddleware())
    dispatcher.callback_query.middleware(rate_limiter)
    dispatcher.callback_query.middleware(LoggingMiddleware())
    dispatcher.callback_query.middleware(AuthMiddleware())

    # Register routers (order matters for handler priority)
    from app.routers.common import router as common_router
    from app.routers.requests import router as requests_router
    from app.routers.shifts import router as shifts_router
    from app.routers.admin import router as admin_router

    dispatcher.include_router(common_router)
    dispatcher.include_router(requests_router)
    dispatcher.include_router(shifts_router)
    dispatcher.include_router(admin_router)

    # Register startup/shutdown handlers
    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)

    return dispatcher


async def main_polling() -> None:
    """
    Main entry point for polling mode.

    Starts long polling to receive updates from Telegram.
    """
    global bot, dp

    try:
        # Create bot and dispatcher
        bot = create_bot()
        dp = create_dispatcher()

        # Start polling
        logger.info("Starting polling...")
        await dp.start_polling(
            bot,
            allowed_updates=settings.ALLOWED_UPDATES,
            timeout=settings.TELEGRAM_POLLING_TIMEOUT
        )
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
        raise
    finally:
        await on_shutdown()


async def main_webhook() -> None:
    """
    Main entry point for webhook mode.

    Starts aiohttp web server to receive webhooks from Telegram.
    """
    global bot, dp

    # Create bot and dispatcher
    bot = create_bot()
    dp = create_dispatcher()

    # Create aiohttp application
    app = web.Application()

    # Setup webhook handler
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.TELEGRAM_WEBHOOK_SECRET
    )
    webhook_handler.register(app, path=settings.WEBHOOK_PATH)

    # Setup application
    setup_application(app, dp, bot=bot)

    # Health check endpoint
    async def health(request):
        """Health check endpoint"""
        db_healthy = await check_database_health()

        return web.json_response({
            "status": "healthy" if db_healthy else "unhealthy",
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "database": "connected" if db_healthy else "disconnected"
        })

    # Prometheus metrics endpoint
    async def metrics(request):
        """Prometheus metrics endpoint"""
        return web.Response(
            body=generate_latest(),
            content_type=CONTENT_TYPE_LATEST
        )

    app.router.add_get("/health", health)
    app.router.add_get("/metrics", metrics)

    # Start web server
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        host=settings.WEBHOOK_HOST,
        port=settings.WEBHOOK_PORT
    )

    await site.start()

    logger.info(
        f"✅ Webhook server started on {settings.WEBHOOK_HOST}:{settings.WEBHOOK_PORT}"
    )
    logger.info(f"Webhook path: {settings.WEBHOOK_PATH}")
    logger.info(f"Health check: http://{settings.WEBHOOK_HOST}:{settings.WEBHOOK_PORT}/health")
    logger.info(f"Metrics: http://{settings.WEBHOOK_HOST}:{settings.WEBHOOK_PORT}/metrics")

    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        await runner.cleanup()
        await on_shutdown()


def main() -> None:
    """
    Main entry point.

    Chooses between polling and webhook mode based on configuration.
    """
    if settings.TELEGRAM_USE_WEBHOOK:
        asyncio.run(main_webhook())
    else:
        asyncio.run(main_polling())


if __name__ == "__main__":
    main()
