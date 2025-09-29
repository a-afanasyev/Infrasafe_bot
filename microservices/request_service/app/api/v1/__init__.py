"""
Request Service - API v1 Module
UK Management Bot - Request Management System

API version 1 endpoints and router configuration.
"""

from fastapi import APIRouter
from .requests import router as requests_router
from .comments import router as comments_router
from .comments_direct import router as comments_direct_router
from .ratings import router as ratings_router
from .assignments import router as assignments_router
from .materials import router as materials_router
from .media import router as media_router

# Create v1 API router
api_router = APIRouter(prefix="/api/v1")

# Include all endpoint routers
api_router.include_router(requests_router)
api_router.include_router(comments_router)
api_router.include_router(comments_direct_router)  # Direct comment access (/api/v1/comments/{comment_id})
api_router.include_router(ratings_router)
api_router.include_router(assignments_router)
api_router.include_router(materials_router)
api_router.include_router(media_router)

# Include new analytics, search, export, and internal routers
from .search import router as search_router
from .analytics import router as analytics_router
from .export import router as export_router
from .internal import router as internal_router

api_router.include_router(search_router)
api_router.include_router(analytics_router)
api_router.include_router(export_router)
api_router.include_router(internal_router)

# Include AI router
from .ai import router as ai_router
api_router.include_router(ai_router)

# Include Bot integration router
from .bot import router as bot_router
api_router.include_router(bot_router, prefix="/bot", tags=["bot"])

# Include Geocoding router
from .geocoding import router as geocoding_router
api_router.include_router(geocoding_router)

__all__ = ["api_router"]