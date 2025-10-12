"""
Analytics Service - Main Application Entry Point

Sprint 16-18: Analytics Service Implementation
Author: Analytics Team
Date: October 6, 2025
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import settings
from api.v1 import health, metrics, consumer, websocket, realtime, aggregates, scheduler as scheduler_api, dashboards, cache as cache_api
from db.session import engine, init_db
from scheduler import get_aggregation_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager"""
    logger.info("🚀 Starting Analytics Service...")

    # Initialize database
    try:
        await init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise

    # Start aggregation scheduler
    try:
        scheduler = get_aggregation_scheduler()
        scheduler.start()
        logger.info("✅ Aggregation scheduler started")
    except Exception as e:
        logger.error(f"❌ Scheduler startup failed: {e}")
        # Continue without scheduler (non-critical)

    yield

    # Cleanup
    logger.info("🛑 Shutting down Analytics Service...")

    # Stop scheduler
    try:
        scheduler = get_aggregation_scheduler()
        scheduler.stop()
        logger.info("✅ Scheduler stopped")
    except Exception as e:
        logger.error(f"❌ Scheduler shutdown failed: {e}")

    await engine.dispose()


# Create FastAPI application
app = FastAPI(
    title="Analytics Service",
    description="Real-time analytics and metrics collection service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred"
        }
    )


# Include routers
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
app.include_router(consumer.router, prefix="/api/v1", tags=["consumer"])
app.include_router(websocket.router, prefix="/api/v1", tags=["websocket"])
app.include_router(realtime.router, prefix="/api/v1", tags=["realtime"])
app.include_router(aggregates.router, prefix="/api/v1", tags=["aggregates"])
app.include_router(scheduler_api.router, prefix="/api/v1", tags=["scheduler"])
app.include_router(dashboards.router, prefix="/api/v1", tags=["dashboards"])
app.include_router(cache_api.router, prefix="/api/v1", tags=["cache"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Analytics Service",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
