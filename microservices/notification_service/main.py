# Notification Service - UK Management Bot
# Microservice for managing notifications

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Depends
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import uvicorn
# Database imports moved to database.py

from middleware.auth import JWTMiddleware, get_current_user
from middleware.logging import LoggingMiddleware
from middleware.simple_tracing import SimpleTracingMiddleware
from events.simple_publisher import SimpleEventPublisher
from events.simple_subscriber import SimpleEventSubscriber
from services.delivery_pipeline import ProductionDeliveryPipeline
from config import settings
from simple_health import SimpleHealthChecker
from database import create_tables, close_db, get_db, AsyncSessionLocal
from models.notification import Base as NotificationBase
from services.template_service import TemplateService
from services.telegram_service import TelegramNotificationService
from api.v1 import notifications, templates

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database setup is now in database.py

# Event system setup
event_publisher = SimpleEventPublisher()
event_subscriber = SimpleEventSubscriber()

# Production delivery pipeline
delivery_pipeline = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info(f"Starting {settings.service_name}")

    # Initialize database
    await create_tables()

    # Initialize default templates
    async with AsyncSessionLocal() as session:
        template_service = TemplateService(session)
        await template_service.initialize_default_templates()

    # Initialize Telegram service
    telegram_service = TelegramNotificationService()
    await telegram_service.initialize()

    # Initialize event system
    await event_publisher.initialize()
    await event_subscriber.initialize()

    # Initialize production delivery pipeline
    global delivery_pipeline
    async with AsyncSessionLocal() as session:
        delivery_pipeline = ProductionDeliveryPipeline(session)
        await delivery_pipeline.initialize()

    # Start health checker
    health_checker = SimpleHealthChecker()
    await health_checker.start()

    # Store services globally for endpoints
    app.state.health_checker = health_checker
    app.state.delivery_pipeline = delivery_pipeline
    app.state.startup_time = time.time()

    logger.info(f"{settings.service_name} started successfully")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.service_name}")

    # Shutdown delivery pipeline
    if delivery_pipeline:
        await delivery_pipeline.shutdown()

    await event_publisher.close()
    await event_subscriber.close()

    # Close Telegram service
    if 'telegram_service' in locals():
        await telegram_service.close()

    await close_db()
    logger.info(f"{settings.service_name} shutdown complete")

# Create FastAPI app
app = FastAPI(
    title=settings.service_name,
    description="Notification Service - UK Management Bot Microservice for managing multi-channel notifications",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# Include API routers
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(templates.router, prefix="/api/v1")

# Middleware
app.add_middleware(SimpleTracingMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(JWTMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts
)

# Database dependency is now in database.py

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        health_checker = app.state.health_checker

        # Get database session
        async with AsyncSessionLocal() as session:
            # Perform detailed health check
            health_data = await health_checker.detailed_health_check(
                db_session=session,
                redis_client=event_publisher.redis_client if event_publisher else None,
                event_publisher=event_publisher
            )

        # Add delivery pipeline health
        if hasattr(app.state, 'delivery_pipeline') and app.state.delivery_pipeline:
            pipeline_health = await app.state.delivery_pipeline.health_check()
            health_data["delivery_pipeline"] = pipeline_health

        # Add service-specific info
        health_data.update({
            "telegram": "configured" if settings.bot_token else "not_configured",
            "channels": {
                "telegram": settings.telegram_enabled,
                "email": settings.email_enabled,
                "sms": settings.sms_enabled
            },
            "uptime_seconds": time.time() - app.state.startup_time if hasattr(app.state, 'startup_time') else 0
        })

        return health_data

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")

# Ready check endpoint
@app.get("/ready")
async def ready_check():
    """Readiness check endpoint"""
    try:
        # Test critical components
        async with AsyncSessionLocal() as session:
            await session.execute("SELECT 1")

        return {
            "status": "ready",
            "service": settings.service_name,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")

# Metrics endpoint
@app.get("/metrics")
async def get_metrics():
    """Production metrics endpoint for monitoring"""
    try:
        metrics_data = {
            "service": settings.service_name,
            "version": "1.0.0",
            "uptime_seconds": time.time() - app.state.startup_time if hasattr(app.state, 'startup_time') else 0,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Get delivery pipeline metrics
        if hasattr(app.state, 'delivery_pipeline') and app.state.delivery_pipeline:
            pipeline_metrics = await app.state.delivery_pipeline.get_metrics()
            metrics_data["delivery_pipeline"] = pipeline_metrics

        # Get event system metrics
        if event_publisher:
            event_health = await event_publisher.health_check()
            metrics_data["event_publisher"] = event_health

        if event_subscriber:
            subscriber_health = await event_subscriber.health_check()
            metrics_data["event_subscriber"] = subscriber_health

        # Database metrics
        async with AsyncSessionLocal() as session:
            try:
                # Test database connectivity
                await session.execute("SELECT 1")
                metrics_data["database"] = {"status": "healthy", "connected": True}
            except Exception as db_error:
                metrics_data["database"] = {"status": "unhealthy", "error": str(db_error), "connected": False}

        return metrics_data

    except Exception as e:
        logger.error(f"Error collecting metrics: {e}")
        return {"error": "Failed to collect metrics", "detail": str(e)}

# Service info endpoint
@app.get("/info")
async def service_info():
    """Get service information"""
    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "description": "Notification Service for UK Management Bot",
        "features": {
            "multi_channel": True,
            "templates": True,
            "batch_sending": True,
            "retry_mechanism": True,
            "statistics": True
        },
        "supported_channels": ["telegram", "email", "sms"],
        "notification_types": [
            "status_changed", "shift_started", "shift_ended",
            "document_request", "verification_request",
            "verification_approved", "verification_rejected",
            "access_granted", "access_revoked", "system"
        ]
    }

# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )