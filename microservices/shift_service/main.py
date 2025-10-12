# Shift Service - Shift Planning & Management
# UK Management Bot - Shift Service

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from config import settings
from database import create_tables, close_db, check_database_connection, init_database
from api.v1.shifts import router as shifts_router
from api.v1.templates import router as templates_router
from api.v1.assignments import router as assignments_router
from api.v1.transfers import router as transfers_router
from api.v1.analytics import router as analytics_router
from api.v1.schedule import router as schedule_router
from api.v1.internal import router as internal_router
from middleware.auth_middleware import AuthMiddleware
from services.scheduler_service import start_background_tasks, stop_background_tasks

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info(f"Starting {settings.service_name}")

    # Initialize database connection
    init_database()
    logger.info("Database connection initialized")

    # Initialize database
    await create_tables()
    logger.info("Database tables initialized")

    # Check database connection
    db_health = await check_database_connection()
    if db_health["status"] != "healthy":
        logger.error(f"Database connection failed: {db_health}")
        raise Exception("Failed to connect to database")

    # Start background tasks (schedulers)
    await start_background_tasks()
    logger.info("Background task scheduler started")

    logger.info(f"{settings.service_name} started successfully on port {settings.port}")

    yield

    # Shutdown
    logger.info("Shutting down...")

    # Stop background tasks
    await stop_background_tasks()
    logger.info("Background tasks stopped")

    # Close database connections
    await close_db()
    logger.info("Database connections closed")

# Create FastAPI application
app = FastAPI(
    title="Shift Service",
    description="UK Management Bot - Shift Planning & Management Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure based on your needs
)

# Add authentication middleware
app.add_middleware(AuthMiddleware)

# Include routers
app.include_router(shifts_router, prefix="/api/v1/shifts", tags=["Shifts"])
app.include_router(templates_router, prefix="/api/v1/templates", tags=["Templates"])
app.include_router(assignments_router, prefix="/api/v1/assignments", tags=["Assignments"])
app.include_router(transfers_router, prefix="/api/v1/transfers", tags=["Transfers"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["Analytics"])
app.include_router(schedule_router, prefix="/api/v1/schedule", tags=["Schedule Management"])
app.include_router(internal_router, prefix="/api/v1/internal", tags=["Internal"])

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database connection
        db_health = await check_database_connection()

        if db_health["status"] == "healthy":
            return {
                "status": "healthy",
                "service": settings.service_name,
                "version": "1.0.0",
                "database": db_health
            }
        else:
            raise HTTPException(status_code=503, detail="Database unhealthy")

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint"""
    try:
        # Check if service is ready to accept requests
        db_health = await check_database_connection()

        return {
            "status": "ready" if db_health["status"] == "healthy" else "not_ready",
            "service": settings.service_name,
            "checks": {
                "database": db_health["status"]
            }
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "error": str(e)}
        )

@app.get("/info")
async def service_info():
    """Service information endpoint"""
    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "description": "Shift Planning & Management Service",
        "port": settings.port,
        "environment": settings.environment
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.debug
    )