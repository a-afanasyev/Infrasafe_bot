"""AUD5-ARCH-3 волна 8 (block-move): общий APIRouter пакета api/shifts/router.

Экземпляр вынесен в отдельный модуль, чтобы под-модули регистрировали маршруты
на одном роутере; порядок регистрации задаёт порядок импортов в __init__.py.
"""
from fastapi import APIRouter

router = APIRouter()
