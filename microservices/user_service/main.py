# User Service - User Management & Profiles
# UK Management Bot - User Service

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from config import settings
from database import create_tables, close_db, check_database_connection
from api.v1.users import router as users_router
from api.v1.profiles import router as profiles_router
from api.v1.verification import router as verification_router
from api.v1.roles import router as roles_router
from api.v1.internal import router as internal_router

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

    # Initialize database
    await create_tables()
    logger.info("Database tables initialized")

    # Check database connection
    db_health = await check_database_connection()
    if db_health["status"] != "healthy":
        logger.error(f"Database connection failed: {db_health}")
        raise Exception("Failed to connect to database")

    logger.info(f"{settings.service_name} started successfully on port {settings.port}")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.service_name}")
    await close_db()
    logger.info(f"{settings.service_name} shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="User Service",
    description="User Management & Profile Service - UK Management Bot",
    version=settings.version,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# Middleware
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

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database connection
        db_health = await check_database_connection()

        return {
            "status": "healthy" if db_health["status"] == "healthy" else "unhealthy",
            "service": settings.service_name,
            "version": settings.version,
            "database": db_health["database"] if "database" in db_health else "unknown",
            "pool_info": {
                "size": db_health.get("engine_pool_size", 0),
                "checked_out": db_health.get("engine_checked_out", 0)
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")

# Ready check endpoint
@app.get("/ready")
async def ready_check():
    """Readiness check endpoint"""
    return {"status": "ready", "service": settings.service_name}

# Service info endpoint
@app.get("/info")
async def service_info():
    """Service information endpoint"""
    return {
        "service": settings.service_name,
        "version": settings.version,
        "features": {
            "user_management": True,
            "profile_management": True,
            "verification_system": True,
            "role_management": True,
            "access_control": True,
            "document_upload": True
        },
        "supported_operations": [
            "user_crud", "profile_management", "verification_workflow",
            "role_assignment", "document_handling", "access_rights"
        ],
        "integrations": [
            "auth-service", "media-service", "notification-service"
        ],
        "database": "PostgreSQL",
        "cache": "Redis"
    }

# Include API routers
app.include_router(users_router, prefix="/api/v1/users", tags=["Users"])
app.include_router(profiles_router, prefix="/api/v1/profiles", tags=["Profiles"])
app.include_router(verification_router, prefix="/api/v1/verification", tags=["Verification"])
app.include_router(roles_router, prefix="/api/v1/roles", tags=["Roles"])
app.include_router(internal_router, prefix="/api/v1/internal", tags=["Internal"])

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "service": settings.service_name}
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )