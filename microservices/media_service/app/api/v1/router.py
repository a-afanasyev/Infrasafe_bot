"""
Главный роутер для API v1
"""

from fastapi import APIRouter

from .media import router as media_router
from .health import router as health_router
from .streaming_upload import router as streaming_router

api_router = APIRouter(prefix="/api/v1")

# Подключаем роутеры
api_router.include_router(media_router)
api_router.include_router(health_router)
api_router.include_router(streaming_router, prefix="/streaming", tags=["streaming"])

__all__ = ["api_router"]