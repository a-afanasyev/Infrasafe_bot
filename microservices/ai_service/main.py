# AI Service - Smart Assignment & Optimization
# UK Management Bot - Microservices

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from middleware.auth import JWTMiddleware, get_current_user
from middleware.logging import LoggingMiddleware
from middleware.tracing import TracingMiddleware
from events.publisher import EventPublisher
from events.subscriber import EventSubscriber
from config import settings
from health import HealthChecker
from app.api.v1 import assignments

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database setup
class Base(DeclarativeBase):
    pass

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Event system setup
event_publisher = EventPublisher()
event_subscriber = EventSubscriber()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info(f"Starting {settings.service_name}")

    # Initialize database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize event system
    await event_publisher.initialize()
    await event_subscriber.initialize()

    # Start health checker
    health_checker = HealthChecker()
    await health_checker.start()

    logger.info(f"{settings.service_name} started successfully")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.service_name}")
    await event_publisher.close()
    await event_subscriber.close()
    await engine.dispose()
    logger.info(f"{settings.service_name} shutdown complete")

# Create FastAPI app
app = FastAPI(
    title=settings.service_name,
    description=f"{settings.service_name} - UK Management Bot Microservice",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# Middleware
app.add_middleware(TracingMiddleware)
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

# Include API routes
app.include_router(assignments.router, prefix="/api/v1", tags=["assignments"])

# Dependency to get database session
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Health check endpoint
@app.get("/api/v1/health")
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        async with AsyncSessionLocal() as session:
            await session.execute("SELECT 1")

        return {
            "status": "healthy",
            "service": settings.service_name,
            "version": "1.0.0",
            "stage": "1_basic_assignment",
            "ml_enabled": settings.ml_enabled,
            "geo_enabled": settings.geo_enabled,
            "database": "connected",
            "events": "connected" if event_publisher.is_connected else "disconnected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")

# Ready check endpoint
@app.get("/ready")
async def ready_check():
    """Readiness check endpoint"""
    return {"status": "ready", "service": settings.service_name}

# Metrics endpoint
@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    # This would integrate with prometheus_client
    return {"message": "Metrics endpoint - implement prometheus_client"}

# Example protected endpoint
@app.get("/protected")
async def protected_endpoint(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Example protected endpoint requiring authentication"""
    return {
        "message": "This is a protected endpoint",
        "user": current_user
    }

# Example database endpoint
@app.get("/example")
async def example_endpoint(db: AsyncSession = Depends(get_db)):
    """Example endpoint using database"""
    try:
        # Example database operation
        result = await db.execute("SELECT 'Hello from database' as message")
        row = result.fetchone()

        # Publish event
        await event_publisher.publish("example.accessed", {
            "timestamp": "now",
            "service": settings.service_name
        })

        return {"message": row[0] if row else "No data"}
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

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
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )