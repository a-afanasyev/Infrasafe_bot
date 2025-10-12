"""
Главный роутер для API v1
"""

from fastapi import APIRouter

from .media import router as media_router
from .health import router as health_router, simple_health_router
from .streaming_upload import router as streaming_router
from .duplicate_check import router as duplicate_check_router

api_router = APIRouter(prefix="/api/v1")

# Main API router combining all routes
main_router = APIRouter()

# Подключаем роутеры
api_router.include_router(media_router)
api_router.include_router(health_router)
api_router.include_router(streaming_router, prefix="/streaming", tags=["streaming"])
api_router.include_router(duplicate_check_router)

# Add simple health router without prefix to main router
main_router.include_router(simple_health_router)
main_router.include_router(api_router)

__all__ = ["main_router"]