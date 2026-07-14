from fastapi import APIRouter

from app.api import analytics, audit, auth, catalog, exports, imports, meters, objects, periods

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(catalog.router)
api_router.include_router(objects.router)
api_router.include_router(meters.router)
api_router.include_router(periods.router)
api_router.include_router(imports.router)
api_router.include_router(analytics.router)
api_router.include_router(exports.router)
api_router.include_router(audit.router)
