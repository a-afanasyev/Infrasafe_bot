"""Health-роутер модуля access_control (ТЗ §14.2 п.17 — базовые health metrics).

Единственный эндпоинт каркаса (Фаза 1). Пилотные Equipment/Operator/Admin
префиксы §13 здесь намеренно НЕ объявляются — они относятся к следующим фазам.
"""
from fastapi import APIRouter

from access_control import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness-проба сервиса контроля доступа.

    Возвращает стабильный JSON-конверт без обращений к БД/Redis, чтобы
    docker-compose healthcheck не зависел от внешних зависимостей.
    """
    return {
        "status": "ok",
        "service": "uk-access-api",
        "version": __version__,
    }
