import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.orm import sessionmaker
from uk_management_bot.config.settings import settings
from uk_management_bot.database.session import engine, Base, SessionLocal
from uk_management_bot.handlers.base import router as base_router
from uk_management_bot.handlers.requests import router as requests_router
from uk_management_bot.handlers.shifts import router as shifts_router
from uk_management_bot.handlers.admin import router as admin_router
from uk_management_bot.handlers.auth import router as auth_router
from uk_management_bot.handlers.onboarding import router as onboarding_router
from uk_management_bot.handlers.user_management import router as user_management_router
from uk_management_bot.handlers.employee_management import router as employee_management_router
from uk_management_bot.handlers.user_verification import router as user_verification_router
from uk_management_bot.handlers.health import router as health_router
from uk_management_bot.middlewares.shift import shift_context_middleware
from uk_management_bot.middlewares.auth import auth_middleware, role_mode_middleware
import sys
import os
from datetime import datetime

# Добавляем путь к проекту в sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка структурированного логирования
from uk_management_bot.utils.structured_logger import setup_structured_logging, get_logger

# Инициализация логирования
setup_structured_logging()
logger = get_logger(__name__, component="main")

async def send_startup_notification(bot: Bot):
    """Отправляет уведомление о запуске бота"""
    try:
        startup_message = f"""
🤖 **UK Management Bot запущен!**

📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
✅ Статус: Активен
🔧 Версия: 1.0.0
📊 База данных: Подключена
🔍 Система верификации: Активна

Бот готов к работе! 🚀
        """
        
        # Отправляем уведомление администраторам
        if settings.ADMIN_USER_IDS:
            for admin_id in settings.ADMIN_USER_IDS:
                try:
                    await bot.send_message(admin_id, startup_message, parse_mode="Markdown")
                    logger.info(f"Уведомление о запуске отправлено администратору {admin_id}")
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление администратору {admin_id}: {e}")
        
        # Отправляем в канал если указан
        if settings.TELEGRAM_CHANNEL_ID:
            try:
                await bot.send_message(settings.TELEGRAM_CHANNEL_ID, startup_message, parse_mode="Markdown")
                logger.info("Уведомление о запуске отправлено в канал")
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление в канал: {e}")
        
        logger.info("✅ Бот успешно запущен и готов к работе")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления о запуске: {e}")

async def main():
    """Главная функция запуска бота"""
    
    # Проверяем наличие токена
    if not settings.BOT_TOKEN:
        logger.error("BOT_TOKEN не найден в переменных окружения!")
        return
    
    # Создаем таблицы в базе данных
    import uk_management_bot.database.models  # Импортируем все модели
    Base.metadata.create_all(bind=engine)
    logger.info("База данных инициализирована")
    
    # Инициализируем бота и диспетчер
    bot = Bot(token=settings.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Middleware для внедрения сессии БД
    @dp.update.middleware()
    async def db_middleware(handler, event, data):
        db = SessionLocal()
        data["db"] = db
        try:
            return await handler(event, data)
        finally:
            db.close()

    # Подключаем shift-middleware глобально через декоратор (как DB-middleware)
    @dp.update.middleware()
    async def _shift_middleware(handler, event, data):
        return await shift_context_middleware(handler, event, data)
    
    # Подключаем role-mode-middleware глобально (должен быть после auth)
    @dp.update.middleware()
    async def _role_mode_middleware(handler, event, data):
        return await role_mode_middleware(handler, event, data)
    
    # Подключаем auth-middleware глобально (должен быть первым)
    @dp.update.middleware()
    async def _auth_middleware(handler, event, data):
        return await auth_middleware(handler, event, data)
    
    # Регистрируем роутеры
    dp.include_router(health_router)  # Health check должен быть первым для быстрого доступа
    dp.include_router(auth_router)
    dp.include_router(onboarding_router)
    dp.include_router(requests_router)  # requests раньше base для перехвата "❌ Отмена" в состояниях
    dp.include_router(shifts_router)  # включаем обратно
    dp.include_router(admin_router)
    dp.include_router(user_management_router)  # включаем обратно
    dp.include_router(employee_management_router)  # Роутер управления сотрудниками
    dp.include_router(user_verification_router)  # Новый роутер верификации
    dp.include_router(base_router)  # base в конце как fallback для общих команд
    
    logger.info("Бот запускается...")
    
    try:
        # Отправляем уведомление о запуске
        await send_startup_notification(bot)
        
        # Запускаем бота
        await dp.start_polling(bot)
        
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
