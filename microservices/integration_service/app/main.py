"""
Integration Service - Main Application
UK Management Bot

FastAPI application setup with all middleware, routes, and configuration.
"""

import logging
import logging.config
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException
import uvicorn
import time

from app.core.config import settings, get_cors_origins, get_log_config
from app.core.database import init_database, close_database, check_database_health
from app.core.events import init_event_publisher, shutdown_event_publisher
from app.services.cache_service import init_cache_service, shutdown_cache_service, cache_service
from app.api.v1 import google_sheets, webhooks

# Configure logging
logging.config.dictConfig(get_log_config())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager

    Handles startup and shutdown events for the Integration Service.
    """
    # Startup
    logger.info("🚀 Starting Integration Service...")

    try:
        # Initialize database
        await init_database()
        logger.info("✅ Database initialized")

        # Initialize Cache Service
        await init_cache_service()

        # Initialize Event Publisher
        await init_event_publisher()

        # Initialize Google Sheets adapter
        await google_sheets.initialize_sheets_adapter()

        logger.info("🎯 Integration Service startup completed")

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise

    yield  # Application runs here

    # Shutdown
    logger.info("🛑 Shutting down Integration Service...")

    try:
        # Shutdown Google Sheets adapter
        await google_sheets.shutdown_sheets_adapter()

        # Shutdown Event Publisher
        await shutdown_event_publisher()

        # Shutdown Cache Service
        await shutdown_cache_service()

        # Close database
        await close_database()
        logger.info("✅ Database connections closed")

        logger.info("👋 Integration Service shutdown completed")

    except Exception as e:
        logger.error(f"❌ Shutdown error: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Integration Service for UK Management Bot - Centralized gateway for external integrations",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

if settings.is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "*.uk-management.com"]
    )


# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time header to responses"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    logger.warning(f"Validation error for {request.url}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "detail": exc.errors(),
            "body": exc.body
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    logger.warning(f"HTTP exception for {request.url}: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception for {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred" if settings.is_production else str(exc)
        }
    )


# Health check endpoints
@app.get("/health", tags=["health"])
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": time.time()
    }


@app.get("/health/detailed", tags=["health"])
async def detailed_health_check():
    """Detailed health check with dependency status"""
    health_status = {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": time.time(),
        "dependencies": {}
    }

    # Check database health
    try:
        db_healthy = await check_database_health()
        health_status["dependencies"]["database"] = {
            "status": "healthy" if db_healthy else "unhealthy",
            "url": settings.DATABASE_URL.split('@')[-1]  # Hide credentials
        }
    except Exception as e:
        health_status["dependencies"]["database"] = {
            "status": "error",
            "error": str(e)
        }

    # Check Redis/Cache health
    try:
        cache_healthy = await cache_service.health_check()
        health_status["dependencies"]["cache"] = {
            "status": "healthy" if cache_healthy else "unhealthy",
            "enabled": settings.CACHE_ENABLED
        }
    except Exception as e:
        health_status["dependencies"]["cache"] = {
            "status": "error",
            "error": str(e)
        }

    # Determine overall status
    dependency_statuses = [dep.get("status") for dep in health_status["dependencies"].values()]
    if any(status == "error" for status in dependency_statuses):
        health_status["status"] = "error"
    elif any(status == "unhealthy" for status in dependency_statuses):
        health_status["status"] = "degraded"

    return health_status


@app.get("/metrics", tags=["monitoring"])
async def get_metrics():
    """Prometheus-style metrics endpoint"""
    try:
        from prometheus_client import generate_latest, REGISTRY

        # Generate Prometheus metrics in standard format
        metrics_output = generate_latest(REGISTRY)

        # Custom metrics
        custom_metrics = []
        custom_metrics.append("\n# HELP integration_service_info Service information")
        custom_metrics.append("# TYPE integration_service_info gauge")
        custom_metrics.append(f'integration_service_info{{version="{settings.APP_VERSION}",service="{settings.APP_NAME}"}} 1')

        # Combine Prometheus metrics with custom metrics
        combined_metrics = metrics_output.decode('utf-8') + "\n".join(custom_metrics)

        return JSONResponse(
            content=combined_metrics,
            media_type="text/plain; version=0.0.4; charset=utf-8"
        )

    except Exception as e:
        logger.error(f"Metrics generation failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Metrics unavailable"}
        )


@app.get("/cache/stats", tags=["monitoring"])
async def get_cache_stats(tenant_id: Optional[str] = None):
    """Get cache statistics for all namespaces"""
    try:
        stats = await cache_service.get_all_stats(tenant_id)
        return {
            "cache_enabled": settings.CACHE_ENABLED,
            "default_ttl": settings.CACHE_DEFAULT_TTL,
            "max_connections": settings.REDIS_MAX_CONNECTIONS,
            "tenant_id": tenant_id or settings.MANAGEMENT_COMPANY_ID,
            "namespaces": stats
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Cache stats unavailable"}
        )


# Include API routers
app.include_router(google_sheets.router, prefix=settings.API_V1_PREFIX)
app.include_router(webhooks.router, prefix=settings.API_V1_PREFIX)


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """Root endpoint with service information"""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs_url": "/docs" if settings.DEBUG else None,
        "api_prefix": settings.API_V1_PREFIX,
        "features": [
            "Google Sheets Integration",
            "Geocoding (Google Maps, Yandex Maps)",
            "Webhook Management",
            "Rate Limiting",
            "Response Caching",
            "Event Publishing"
        ]
    }


if __name__ == "__main__":
    # Run with uvicorn for development
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=settings.DEBUG
    )
