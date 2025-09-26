"""
Health check API endpoints
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db, check_db_connection
from app.schemas import HealthResponse
from app.core.config import settings
from app.services import TelegramClientService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


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
    Детальная проверка здоровья с проверкой зависимостей
    """
    try:
        dependencies = {}
        overall_status = "ok"

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