"""
Redis Rate Limiter для production окружения
Поддерживает горизонтальное масштабирование
"""
import asyncio
import time
import logging
from typing import Optional
from config.settings import settings

logger = logging.getLogger(__name__)

# Глобальный Redis клиент (будет инициализирован если нужен)
_redis_client: Optional[object] = None

async def get_redis_client():
    """Получить Redis клиент (ленивая инициализация)"""
    global _redis_client
    
    if _redis_client is None:
        try:
            import aioredis
            _redis_client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
            # Проверяем соединение
            await _redis_client.ping()
            logger.info("Redis client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
            _redis_client = None
            raise
    
    return _redis_client


class RedisRateLimiter:
    """Redis-based rate limiter с поддержкой скользящего окна"""
    
    @staticmethod
    async def is_allowed(key: str, max_requests: int, window_seconds: int) -> bool:
        """
        Проверить, разрешен ли запрос согласно rate limit
        
        Args:
            key: Уникальный ключ для rate limiting (например, user_id)
            max_requests: Максимальное количество запросов
            window_seconds: Размер окна в секундах
            
        Returns:
            True если запрос разрешен
        """
        try:
            redis = await get_redis_client()
            if redis is None:
                # Fallback к in-memory если Redis недоступен
                logger.warning("Redis unavailable, falling back to in-memory rate limiting")
                return InMemoryRateLimiter.is_allowed(key, max_requests, window_seconds)
            
            now = time.time()
            pipeline = redis.pipeline()
            
            # Используем скользящее окно с sorted set
            redis_key = f"rate_limit:{key}"
            
            # Удаляем старые записи за пределами окна
            pipeline.zremrangebyscore(redis_key, 0, now - window_seconds)
            
            # Подсчитываем текущие запросы
            pipeline.zcard(redis_key)
            
            # Добавляем текущий запрос
            pipeline.zadd(redis_key, {str(now): now})
            
            # Устанавливаем TTL для автоочистки
            pipeline.expire(redis_key, window_seconds + 1)
            
            results = await pipeline.execute()
            current_requests = results[1]  # Результат zcard
            
            allowed = current_requests < max_requests
            
            if not allowed:
                # Удаляем добавленный запрос если превышен лимит
                await redis.zrem(redis_key, str(now))
                logger.warning(f"Rate limit exceeded for key {key}: {current_requests}/{max_requests}")
            
            return allowed
            
        except Exception as e:
            logger.error(f"Redis rate limiting error for key {key}: {e}")
            # Fallback к in-memory при ошибках Redis
            return InMemoryRateLimiter.is_allowed(key, max_requests, window_seconds)
    
    @staticmethod
    async def get_remaining_time(key: str, window_seconds: int) -> int:
        """
        Получить время до сброса лимита
        
        Returns:
            Секунды до сброса лимита
        """
        try:
            redis = await get_redis_client()
            if redis is None:
                return InMemoryRateLimiter.get_remaining_time(key, window_seconds)
            
            now = time.time()
            redis_key = f"rate_limit:{key}"
            
            # Получаем самую старую запись в окне
            oldest_entries = await redis.zrange(redis_key, 0, 0, withscores=True)
            
            if not oldest_entries:
                return 0
            
            oldest_time = oldest_entries[0][1]
            remaining = window_seconds - (now - oldest_time)
            
            return max(0, int(remaining))
            
        except Exception as e:
            logger.error(f"Error getting remaining time for key {key}: {e}")
            return InMemoryRateLimiter.get_remaining_time(key, window_seconds)


class InMemoryRateLimiter:
    """Fallback in-memory rate limiter (как было раньше)"""
    
    _storage = {}
    
    @classmethod
    def is_allowed(cls, key: str, max_requests: int, window_seconds: int) -> bool:
        """In-memory rate limiting с очисткой старых записей"""
        now = time.time()
        
        if key not in cls._storage:
            cls._storage[key] = []
        
        # Очищаем старые записи
        cls._storage[key] = [
            timestamp for timestamp in cls._storage[key] 
            if now - timestamp < window_seconds
        ]
        
        # Проверяем лимит
        if len(cls._storage[key]) >= max_requests:
            return False
        
        # Добавляем текущий запрос
        cls._storage[key].append(now)
        return True
    
    @classmethod
    def get_remaining_time(cls, key: str, window_seconds: int) -> int:
        """Время до сброса in-memory лимита"""
        now = time.time()
        
        if key not in cls._storage or not cls._storage[key]:
            return 0
        
        oldest_time = min(cls._storage[key])
        remaining = window_seconds - (now - oldest_time)
        
        return max(0, int(remaining))


# Фабрика для выбора rate limiter
async def get_rate_limiter():
    """Получить соответствующий rate limiter в зависимости от конфигурации"""
    if settings.USE_REDIS_RATE_LIMIT:
        return RedisRateLimiter
    else:
        return InMemoryRateLimiter


# Удобные функции для использования в коде
async def is_rate_limited(key: str, max_requests: int, window_seconds: int) -> bool:
    """
    Проверить rate limit для ключа
    
    Returns:
        True если превышен лимит (запрос должен быть отклонен)
    """
    limiter = await get_rate_limiter()
    if settings.USE_REDIS_RATE_LIMIT:
        # Redis limiter (async) - это экземпляр класса
        redis_limiter = limiter()
        return not await redis_limiter.is_allowed(key, max_requests, window_seconds)
    else:
        # In-memory limiter (sync) - это класс с классовыми методами
        return not limiter.is_allowed(key, max_requests, window_seconds)


async def get_rate_limit_remaining_time(key: str, window_seconds: int) -> int:
    """Получить время до сброса лимита"""
    limiter = await get_rate_limiter()
    if settings.USE_REDIS_RATE_LIMIT:
        # Redis limiter (async) - это экземпляр класса
        redis_limiter = limiter()
        return await redis_limiter.get_remaining_time(key, window_seconds)
    else:
        # In-memory limiter (sync) - это класс с классовыми методами
        return limiter.get_remaining_time(key, window_seconds)
