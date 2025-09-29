"""
Health check API endpoints with observability metrics
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Response
from sqlalchemy.orm import Session

from app.db.database import get_db, check_db_connection
from app.schemas import HealthResponse
from app.core.config import settings
from app.services import TelegramClientService
from app.services.observability import get_observability

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

# Simple health endpoint without prefix for Docker healthcheck
simple_health_router = APIRouter(tags=["health"])


@router.get("", response_model=HealthResponse)
async def health_check():
    """
    Основная проверка здоровья сервиса
    """
    try:
        return HealthResponse(
            status="ok",
            service="media-service",
            version="1.0.0",
            timestamp=datetime.now(),
            dependencies={}
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@router.get("/detailed", response_model=HealthResponse)
async def detailed_health_check():
    """
    Детальная проверка здоровья с проверкой зависимостей и метриками
    """
    try:
        dependencies = {}
        overall_status = "ok"

        # Get observability service for health metrics
        observability = await get_observability()

        # Проверка базы данных
        try:
            db_status = check_db_connection()
            dependencies["database"] = "ok" if db_status else "error"
            if not db_status:
                overall_status = "degraded"
        except Exception as e:
            dependencies["database"] = f"error: {str(e)}"
            overall_status = "degraded"

        # Проверка Telegram API
        try:
            telegram = TelegramClientService()
            # Простая проверка - получение информации о боте
            bot_info = await telegram.bot.get_me()
            dependencies["telegram"] = "ok" if bot_info else "error"
            await telegram.close()
        except Exception as e:
            dependencies["telegram"] = f"error: {str(e)}"
            overall_status = "degraded"

        # Проверка конфигурации
        try:
            required_settings = [
                "telegram_bot_token",
                "database_url"
            ]
            config_status = all(getattr(settings, setting, None) for setting in required_settings)
            dependencies["configuration"] = "ok" if config_status else "error"
            if not config_status:
                overall_status = "degraded"
        except Exception as e:
            dependencies["configuration"] = f"error: {str(e)}"
            overall_status = "degraded"

        # Get health metrics from observability service
        health_metrics = await observability.get_health_metrics()
        dependencies["health_metrics"] = health_metrics

        # Update overall status based on health metrics
        if health_metrics["status"] == "degraded":
            overall_status = "degraded"
        elif health_metrics["status"] == "unhealthy":
            overall_status = "error"

        return HealthResponse(
            status=overall_status,
            service="media-service",
            version="1.0.0",
            timestamp=datetime.now(),
            dependencies=dependencies
        )

    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Health check error: {str(e)}")


@router.get("/database")
async def database_health():
    """
    Проверка состояния базы данных
    """
    try:
        db_status = check_db_connection()

        if db_status:
            return {"status": "ok", "database": "connected", "timestamp": datetime.now()}
        else:
            raise HTTPException(status_code=503, detail="Database connection failed")

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


@router.get("/telegram")
async def telegram_health():
    """
    Проверка состояния Telegram API
    """
    try:
        telegram = TelegramClientService()

        # Получаем информацию о боте
        bot_info = await telegram.bot.get_me()

        await telegram.close()

        if bot_info:
            return {
                "status": "ok",
                "telegram": "connected",
                "bot_username": bot_info.username,
                "bot_id": bot_info.id,
                "timestamp": datetime.now()
            }
        else:
            raise HTTPException(status_code=503, detail="Telegram API connection failed")

    except Exception as e:
        logger.error(f"Telegram health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Telegram API error: {str(e)}")


@router.get("/ready")
async def readiness_check():
    """
    Проверка готовности сервиса (для Kubernetes)
    """
    try:
        # Проверяем все критически важные компоненты
        db_ok = check_db_connection()

        if not db_ok:
            raise HTTPException(status_code=503, detail="Service not ready - database unavailable")

        # Можно добавить другие проверки готовности

        return {"status": "ready", "timestamp": datetime.now()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service not ready: {str(e)}")


@router.get("/live")
async def liveness_check():
    """
    Проверка жизнеспособности сервиса (для Kubernetes)
    """
    try:
        # Простая проверка что сервис отвечает
        return {"status": "alive", "timestamp": datetime.now()}

    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service not alive: {str(e)}")


@router.get("/metrics")
async def get_metrics():
    """
    Получить подробные метрики сервиса
    """
    try:
        observability = await get_observability()

        # Get comprehensive metrics
        metrics_summary = await observability.metrics.get_metrics_summary()
        system_metrics = await observability.get_system_metrics()
        health_metrics = await observability.get_health_metrics()

        return {
            "timestamp": datetime.now(),
            "metrics": metrics_summary,
            "system": system_metrics,
            "health": health_metrics
        }

    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Metrics error: {str(e)}")


@router.get("/metrics/prometheus")
async def get_prometheus_metrics():
    """
    Получить метрики в формате Prometheus
    """
    try:
        observability = await get_observability()
        prometheus_metrics = await observability.get_prometheus_metrics()

        return Response(
            content=prometheus_metrics,
            media_type="text/plain; charset=utf-8"
        )

    except Exception as e:
        logger.error(f"Prometheus metrics failed: {e}")
        raise HTTPException(status_code=500, detail=f"Prometheus metrics error: {str(e)}")


@router.get("/system")
async def get_system_info():
    """
    Получить информацию о системе
    """
    try:
        observability = await get_observability()
        system_metrics = await observability.get_system_metrics()

        return {
            "timestamp": datetime.now(),
            "service": "media-service",
            "version": "1.0.0",
            "system": system_metrics
        }

    except Exception as e:
        logger.error(f"System info collection failed: {e}")
        raise HTTPException(status_code=500, detail=f"System info error: {str(e)}")


@router.get("/upload-stats")
async def get_upload_statistics():
    """
    Получить статистику загрузок
    """
    try:
        from app.services.enhanced_streaming_upload import StreamingUploadService

        streaming_service = StreamingUploadService()
        upload_stats = await streaming_service.get_upload_statistics()

        return {
            "timestamp": datetime.now(),
            "upload_statistics": upload_stats
        }

    except Exception as e:
        logger.error(f"Upload statistics failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload statistics error: {str(e)}")


# Simple health check endpoint for Docker without prefix
@simple_health_router.get("/health")
async def simple_health_check():
    """
    Simple health check for Docker healthcheck
    """
    try:
        return {
            "status": "ok",
            "service": "media-service",
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"Simple health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")