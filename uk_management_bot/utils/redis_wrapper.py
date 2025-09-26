"""
Обертка для Redis с поддержкой redis.asyncio (официальный клиент)
"""
import logging
import sys
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Флаг доступности redis
_redis_available = False
_redis_module = None

def _safe_import_redis():
    """Безопасный импорт redis.asyncio"""
    global _redis_available, _redis_module

    if _redis_module is not None:
        return _redis_module

    try:
        # Импорт официального redis клиента с async поддержкой
        import redis.asyncio as redis_asyncio

        # Проверяем что импорт удался
        try:
            # Простой тест на работоспособность
            str(redis_asyncio.from_url)
            _redis_module = redis_asyncio
            _redis_available = True
            logger.info("redis.asyncio successfully imported")
            return redis_asyncio
        except Exception as test_error:
            logger.warning(f"redis.asyncio import test failed: {test_error}")
            raise test_error

    except Exception as e:
        logger.warning(f"redis.asyncio import failed: {e}, falling back to in-memory rate limiting")
        _redis_available = False
        _redis_module = None
        return None

def is_redis_available() -> bool:
    """Проверить доступность redis"""
    if _redis_module is None:
        _safe_import_redis()
    return _redis_available

async def create_redis_client(redis_url: str) -> Optional[Any]:
    """
    Создать Redis клиент с безопасной обработкой ошибок

    Args:
        redis_url: URL для подключения к Redis

    Returns:
        Redis клиент или None если недоступен
    """
    redis_asyncio = _safe_import_redis()
    if redis_asyncio is None:
        return None

    try:
        client = redis_asyncio.from_url(
            redis_url,
            decode_responses=True
        )

        # Проверяем соединение
        await client.ping()
        logger.info("Redis client created and connected successfully")
        return client

    except Exception as e:
        logger.error(f"Failed to create Redis client: {e}")
        return None

def get_redis_version() -> Optional[str]:
    """Получить версию redis если доступна"""
    redis_asyncio = _safe_import_redis()
    if redis_asyncio is None:
        return None

    try:
        import redis
        return getattr(redis, '__version__', 'unknown')
    except:
        return 'unknown'

# Обратная совместимость с aioredis API
is_aioredis_available = is_redis_available
get_aioredis_version = get_redis_version