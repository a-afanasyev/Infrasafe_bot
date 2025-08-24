"""
Health Check handlers для мониторинга состояния приложения
"""
import logging
import time
from datetime import datetime
from typing import Dict, Any

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy.orm import Session
from sqlalchemy import text

from uk_management_bot.config.settings import settings
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access

logger = logging.getLogger(__name__)
router = Router()

# Время запуска приложения
_start_time = time.time()


async def check_database_health(db: Session) -> Dict[str, Any]:
    """
    Проверка состояния базы данных
    
    Returns:
        Dict с информацией о состоянии БД
    """
    try:
        start_time = time.time()
        
        # Простой запрос для проверки соединения
        result = db.execute(text("SELECT 1 as health_check"))
        result.fetchone()
        
        response_time = (time.time() - start_time) * 1000  # в миллисекундах
        
        return {
            "status": "healthy",
            "response_time_ms": round(response_time, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


async def check_redis_health() -> Dict[str, Any]:
    """
    Проверка состояния Redis (если используется)
    
    Returns:
        Dict с информацией о состоянии Redis
    """
    if not settings.USE_REDIS_RATE_LIMIT:
        return {
            "status": "disabled",
            "message": "Redis rate limiting is disabled"
        }
    
    try:
        from uk_management_bot.utils.redis_rate_limiter import get_redis_client
        
        start_time = time.time()
        redis = await get_redis_client()
        
        # Проверяем ping
        await redis.ping()
        
        response_time = (time.time() - start_time) * 1000
        
        return {
            "status": "healthy",
            "response_time_ms": round(response_time, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {
            "status": "unhealthy", 
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


async def get_system_info() -> Dict[str, Any]:
    """
    Получение базовой информации о системе
    
    Returns:
        Dict с системной информацией
    """
    uptime_seconds = time.time() - _start_time
    
    return {
        "uptime_seconds": round(uptime_seconds, 2),
        "uptime_human": f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m {int(uptime_seconds % 60)}s",
        "debug_mode": settings.DEBUG,
        "log_level": settings.LOG_LEVEL,
        "supported_languages": settings.SUPPORTED_LANGUAGES,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.message(Command("health"))
async def health_check_command(message: Message, db: Session):
    """
    Команда для проверки здоровья системы (доступна всем пользователям)
    """
    lang = message.from_user.language_code or 'ru'
    
    try:
        # Проверяем все компоненты
        db_health = await check_database_health(db)
        redis_health = await check_redis_health()
        system_info = await get_system_info()
        
        # Определяем общий статус
        overall_status = "healthy"
        if db_health["status"] == "unhealthy":
            overall_status = "unhealthy"
        elif redis_health["status"] == "unhealthy":
            overall_status = "degraded"
        
        # Формируем ответ
        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️", 
            "unhealthy": "❌"
        }
        
        message_text = f"""
{status_emoji[overall_status]} **Статус системы: {overall_status.upper()}**

📊 **База данных:**
└ Статус: {db_health['status']}
└ Время отклика: {db_health.get('response_time_ms', 'N/A')} ms

🔄 **Redis кэш:**
└ Статус: {redis_health['status']}
└ Время отклика: {redis_health.get('response_time_ms', 'N/A')} ms

🖥️ **Система:**
└ Время работы: {system_info['uptime_human']}
└ Режим отладки: {'Включен' if system_info['debug_mode'] else 'Выключен'}
└ Уровень логов: {system_info['log_level']}

🕐 Проверено: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}
        """.strip()
        
        await message.answer(message_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Health check command failed: {e}")
        await message.answer(
            "❌ **Ошибка проверки здоровья системы**\n\n"
            f"Детали ошибки: {str(e)}",
            parse_mode="Markdown"
        )


@router.message(Command("health_detailed"))
async def detailed_health_check_command(message: Message, db: Session, roles: list = None):
    """
    Детальная проверка здоровья системы (только для менеджеров)
    """
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await message.answer(
            get_text('errors.permission_denied', language=lang)
        )
        return
    
    try:
        # Получаем детальную информацию
        db_health = await check_database_health(db)
        redis_health = await check_redis_health()
        system_info = await get_system_info()
        
        # Дополнительные проверки для менеджеров
        config_info = {
            "invite_secret_set": bool(settings.INVITE_SECRET),
            "admin_password_secure": settings.ADMIN_PASSWORD != "12345" and settings.ADMIN_PASSWORD != "dev_password_change_me",
            "redis_enabled": settings.USE_REDIS_RATE_LIMIT,
            "notifications_enabled": settings.ENABLE_NOTIFICATIONS,
            "admin_users_count": len(settings.ADMIN_USER_IDS)
        }
        
        message_text = f"""
🔧 **Детальная информация о системе**

📊 **База данных:**
```json
{db_health}
```

🔄 **Redis:**
```json  
{redis_health}
```

🖥️ **Система:**
```json
{system_info}
```

⚙️ **Конфигурация безопасности:**
└ INVITE_SECRET установлен: {'✅' if config_info['invite_secret_set'] else '❌'}
└ Безопасный пароль админа: {'✅' if config_info['admin_password_secure'] else '❌'}
└ Redis включен: {'✅' if config_info['redis_enabled'] else '⚠️'}
└ Уведомления включены: {'✅' if config_info['notifications_enabled'] else '⚠️'}
└ Количество админов: {config_info['admin_users_count']}

🕐 Проверено: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}
        """.strip()
        
        await message.answer(message_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        await message.answer(
            "❌ **Ошибка детальной проверки**\n\n"
            f"Детали: {str(e)}",
            parse_mode="Markdown"
        )


@router.message(Command("ping"))
async def ping_command(message: Message):
    """Простая ping команда для быстрой проверки доступности"""
    await message.answer("🏓 Pong! Bot is alive and responding.")


# Функция для внешних health check (например, для load balancer)
async def get_health_status(db: Session) -> Dict[str, Any]:
    """
    Получить статус здоровья для внешних систем мониторинга
    
    Returns:
        Dict с полной информацией о здоровье системы
    """
    try:
        db_health = await check_database_health(db)
        redis_health = await check_redis_health()
        system_info = await get_system_info()
        
        # Определяем общий статус
        overall_status = "healthy"
        components_healthy = 0
        total_components = 2  # DB + Redis (если включен)
        
        if db_health["status"] == "healthy":
            components_healthy += 1
        
        if redis_health["status"] in ["healthy", "disabled"]:
            components_healthy += 1
        elif redis_health["status"] == "unhealthy":
            overall_status = "degraded"
        
        if components_healthy == 0:
            overall_status = "unhealthy"
        elif components_healthy < total_components:
            overall_status = "degraded"
        
        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "database": db_health,
                "redis": redis_health,
                "system": system_info
            },
            "summary": {
                "healthy_components": components_healthy,
                "total_components": total_components,
                "uptime_seconds": system_info["uptime_seconds"]
            }
        }
        
    except Exception as e:
        logger.error(f"Health status check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
