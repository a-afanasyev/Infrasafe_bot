"""
Request Service - Main Application
UK Management Bot - Request Management System

FastAPI application setup with all middleware, routes, and configuration.
"""

import logging
import logging.config
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException
import uvicorn
import time

from app.core.config import settings, get_cors_origins, get_log_config
from app.core.database import init_database, close_database, check_database_health
from app.api import api_router
from app.services import request_number_service
from app.clients.building_directory_cache import initialize_building_cache, close_building_cache

# Configure logging
logging.config.dictConfig(get_log_config())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager

    Handles startup and shutdown events for the Request Service.
    """
    # Startup
    logger.info("Starting Request Service...")

    try:
        # Initialize database
        await init_database()
        logger.info(" Database initialized")

        # Initialize request number service
        await request_number_service.initialize()
        logger.info(" Request number service initialized")

        # Initialize building directory cache
        await initialize_building_cache()
        logger.info(" Building Directory cache initialized")

        logger.info("<� Request Service startup completed")

    except Exception as e:
        logger.error(f"L Startup failed: {e}")
        raise

    yield  # Application runs here

    # Shutdown
    logger.info("=� Shutting down Request Service...")

    try:
        # Close request number service
        await request_number_service.close()
        logger.info(" Request number service closed")

        # Close building directory cache
        await close_building_cache()
        logger.info(" Building Directory cache closed")

        # Close database
        await close_database()
        logger.info(" Database connections closed")

        logger.info("=K Request Service shutdown completed")

    except Exception as e:
        logger.error(f"L Shutdown error: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Request Management Service for UK Management Bot",
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

    # Check Redis health
    try:
        redis_healthy = request_number_service._redis_connected
        health_status["dependencies"]["redis"] = {
            "status": "healthy" if redis_healthy else "unhealthy",
            "url": settings.REDIS_URL.split('@')[-1]  # Hide credentials
        }
    except Exception as e:
        health_status["dependencies"]["redis"] = {
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
        from io import BytesIO

        # Generate Prometheus metrics in standard format
        metrics_output = generate_latest(REGISTRY)

        # Also include request number statistics
        from datetime import date
        from app.core.database import get_async_session

        # Get database session using async generator
        db_generator = get_async_session()
        db = await anext(db_generator)
        try:
            daily_stats = await request_number_service.get_daily_stats(db)
        finally:
            await db.close()

        # Custom metrics (legacy format, will be migrated to prometheus_client)
        custom_metrics = []
        custom_metrics.append("\n# HELP request_service_info Service information")
        custom_metrics.append("# TYPE request_service_info gauge")
        custom_metrics.append(f'request_service_info{{version="{settings.APP_VERSION}",service="{settings.APP_NAME}"}} 1')

        custom_metrics.append("# HELP request_numbers_generated_today Total request numbers generated today")
        custom_metrics.append("# TYPE request_numbers_generated_today counter")
        custom_metrics.append(f'request_numbers_generated_today {daily_stats.get("database_count", 0)}')

        custom_metrics.append("# HELP request_numbers_available_today Available request numbers for today")
        custom_metrics.append("# TYPE request_numbers_available_today gauge")
        custom_metrics.append(f'request_numbers_available_today {daily_stats.get("available_numbers", 999)}')

        custom_metrics.append("# HELP redis_connection_status Redis connection status (1=connected, 0=disconnected)")
        custom_metrics.append("# TYPE redis_connection_status gauge")
        custom_metrics.append(f'redis_connection_status {1 if daily_stats.get("redis_connected") else 0}')

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


# Include API routes
app.include_router(api_router)


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """Root endpoint with service information"""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs_url": "/docs" if settings.DEBUG else None,
        "api_prefix": settings.API_V1_PREFIX
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