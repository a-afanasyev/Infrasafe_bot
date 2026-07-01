"""
Health Check handlers для мониторинга состояния приложения
"""
import logging
import time
from datetime import datetime
from typing import Dict, Any

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy.orm import Session
from sqlalchemy import text

from uk_management_bot.config.settings import settings
from uk_management_bot.utils.helpers import get_text, get_user_language

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

    redis = None
    try:
        from uk_management_bot.utils.redis_rate_limiter import get_redis_client

        start_time = time.time()
        redis = await get_redis_client()

        if redis is None:
            return {
                "status": "disabled",
                "message": "Redis client not initialized"
            }

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
    finally:
        pass  # Don't close global Redis singleton — it's managed by startup/shutdown lifecycle


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
    lang = get_user_language(message.from_user.id, db)

    try:
        # Проверяем все компоненты
        db_health = await check_database_health(db)
        redis_health = await check_redis_health()
        system_info = await get_system_info()

        # Определяем общий статус
        overall_status = "healthy"
        if db_health["status"] == "unhealthy":
            overall_status = "unhealthy"
        elif redis_health["status"] == "unhealthy" and settings.USE_REDIS_RATE_LIMIT:
            overall_status = "degraded"

        # Формируем ответ
        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "unhealthy": "❌"
        }

        system_status_text = get_text("health.system_status", language=lang)
        database_text = get_text("health.database", language=lang)
        status_text = get_text("health.status", language=lang)
        response_time_text = get_text("health.response_time", language=lang)
        redis_cache_text = get_text("health.redis_cache", language=lang)
        system_text = get_text("health.system", language=lang)
        uptime_text = get_text("health.uptime", language=lang)
        debug_mode_text = get_text("health.debug_mode", language=lang)
        enabled_text = get_text("health.enabled", language=lang)
        disabled_text = get_text("health.disabled", language=lang)
        log_level_text = get_text("health.log_level", language=lang)
        checked_at_text = get_text("health.checked_at", language=lang)

        message_text = f"""
{status_emoji[overall_status]} <b>{system_status_text}: {overall_status.upper()}</b>

📊 <b>{database_text}:</b>
└ {status_text}: {db_health['status']}
└ {response_time_text}: {db_health.get('response_time_ms', 'N/A')} ms

🔄 <b>{redis_cache_text}:</b>
└ {status_text}: {redis_health['status']}
└ {response_time_text}: {redis_health.get('response_time_ms', 'N/A')} ms

🖥️ <b>{system_text}:</b>
└ {uptime_text}: {system_info['uptime_human']}
└ {debug_mode_text}: {enabled_text if system_info['debug_mode'] else disabled_text}
└ {log_level_text}: {system_info['log_level']}

🕐 {checked_at_text}: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}
        """.strip()

        await message.answer(message_text)

    except Exception as e:
        logger.error(f"Health check command failed: {e}")
        lang = get_user_language(message.from_user.id, db)
        error_title = get_text("health.error_title", language=lang)
        error_details = get_text("health.error_details", language=lang)
        await message.answer(
            f"❌ <b>{error_title}</b>\n\n"
            f"{error_details}: {str(e)}"
        )


@router.message(Command("health_detailed"))
async def detailed_health_check_command(message: Message, db: Session, roles: list = None):
    """
    Детальная проверка здоровья системы (только для менеджеров)
    """
    lang = get_user_language(message.from_user.id, db)

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
            "admin_users_count": len(settings.ADMIN_USER_IDS)
        }

        detailed_info_text = get_text("health.detailed_info", language=lang)
        database_text = get_text("health.database", language=lang)
        redis_text = get_text("health.redis", language=lang)
        system_text = get_text("health.system", language=lang)
        security_config_text = get_text("health.security_config", language=lang)
        invite_secret_set_text = get_text("health.invite_secret_set", language=lang)
        admin_password_secure_text = get_text("health.admin_password_secure", language=lang)
        redis_enabled_text = get_text("health.redis_enabled", language=lang)
        admin_count_text = get_text("health.admin_count", language=lang)
        checked_at_text = get_text("health.checked_at", language=lang)

        message_text = f"""
🔧 <b>{detailed_info_text}</b>

📊 <b>{database_text}:</b>
{db_health}

🔄 <b>{redis_text}:</b>
{redis_health}

🖥️ <b>{system_text}:</b>
{system_info}

⚙️ <b>{security_config_text}:</b>
└ {invite_secret_set_text}: {'✅' if config_info['invite_secret_set'] else '❌'}
└ {admin_password_secure_text}: {'✅' if config_info['admin_password_secure'] else '❌'}
└ {redis_enabled_text}: {'✅' if config_info['redis_enabled'] else '⚠️'}
└ {admin_count_text}: {config_info['admin_users_count']}

🕐 {checked_at_text}: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}
        """.strip()

        await message.answer(message_text)

    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        lang = get_user_language(message.from_user.id, db)
        detailed_error_title = get_text("health.detailed_error_title", language=lang)
        error_details = get_text("health.error_details", language=lang)
        await message.answer(
            f"❌ <b>{detailed_error_title}</b>\n\n"
            f"{error_details}: {str(e)}"
        )


@router.message(Command("ping"))
async def ping_command(message: Message, db: Session):
    """Простая ping команда для быстрой проверки доступности"""
    lang = get_user_language(message.from_user.id, db)
    await message.answer(get_text("health.ping_response", language=lang))


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
        total_components = 1  # DB обязательный
        
        # Проверяем базу данных (критично)
        if db_health["status"] == "healthy":
            components_healthy += 1
        else:
            overall_status = "unhealthy"
        
        # Redis опциональный, учитываем только если включен
        if settings.USE_REDIS_RATE_LIMIT:
            total_components += 1
            if redis_health["status"] == "healthy":
                components_healthy += 1
            elif redis_health["status"] == "unhealthy":
                overall_status = "degraded" if overall_status == "healthy" else overall_status
        # Если Redis отключен, не влияет на общий статус
        
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
