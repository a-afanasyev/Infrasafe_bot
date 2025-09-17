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
from uk_management_bot.handlers.clarification_replies import router as clarification_replies_router
from uk_management_bot.handlers.profile_editing import router as profile_editing_router
from uk_management_bot.handlers.health import router as health_router

# Новые обработчики системы смен
from uk_management_bot.handlers.shift_management import router as shift_management_router_new
from uk_management_bot.handlers.my_shifts import router as my_shifts_router

# Обработчики назначения заявок
from uk_management_bot.handlers.request_assignment import router as request_assignment_router
from uk_management_bot.handlers.request_status_management import router as request_status_management_router
from uk_management_bot.handlers.request_comments import router as request_comments_router
from uk_management_bot.handlers.request_reports import router as request_reports_router
from uk_management_bot.middlewares.shift import shift_context_middleware
from uk_management_bot.middlewares.auth import auth_middleware, role_mode_middleware
import sys
import os
from datetime import datetime

# Добавляем путь к проекту в sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка структурированного логирования
from uk_management_bot.utils.structured_logger import setup_structured_logging, get_logger
from uk_management_bot.utils.health_server import start_health_server, stop_health_server

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
    
    # Middleware для внедрения сессии БД (ДОЛЖЕН БЫТЬ ПЕРВЫМ!)
    @dp.update.middleware()
    async def db_middleware(handler, event, data):
        db = SessionLocal()
        data["db"] = db
        try:
            result = await handler(event, data)
            # Коммитим только если не было исключений
            if db.in_transaction():
                db.commit()
            return result
        except Exception as e:
            # Откатываем транзакцию при ошибке
            try:
                if db.in_transaction():
                    db.rollback()
            except Exception:
                pass
            logger.error(f"Ошибка в middleware: {e}")
            raise
        finally:
            # Закрываем сессию в любом случае
            try:
                db.close()
            except Exception as close_err:
                logger.warning(f"Ошибка закрытия сессии БД: {close_err}")

    # Подключаем auth-middleware глобально (должен быть вторым)
    @dp.update.middleware()
    async def _auth_middleware(handler, event, data):
        result = await auth_middleware(handler, event, data)
        return result
    
    # Подключаем role-mode-middleware глобально (должен быть после auth)
    @dp.update.middleware()
    async def _role_mode_middleware(handler, event, data):
        result = await role_mode_middleware(handler, event, data)
        return result

    # Подключаем shift-middleware глобально через декоратор (последний)
    @dp.update.middleware()
    async def _shift_middleware(handler, event, data):
        return await shift_context_middleware(handler, event, data)
    
    # Регистрируем роутеры
    dp.include_router(health_router)  # Health check должен быть первым для быстрого доступа
    dp.include_router(auth_router)
    dp.include_router(onboarding_router)
    dp.include_router(admin_router)  # admin раньше requests для перехвата действий менеджеров
    dp.include_router(profile_editing_router)  # Роутер редактирования профиля (раньше requests)
    dp.include_router(requests_router)  # requests после profile_editing
    
    # Система управления сменами
    dp.include_router(shift_management_router_new)  # Управление сменами для менеджеров
    dp.include_router(my_shifts_router)  # Интерфейс смен для исполнителей
    dp.include_router(shifts_router)  # старый роутер смен
    
    # Система назначения заявок
    dp.include_router(request_assignment_router)
    dp.include_router(request_status_management_router)
    dp.include_router(request_comments_router)
    dp.include_router(request_reports_router)
    
    dp.include_router(user_management_router)  # включаем обратно
    dp.include_router(employee_management_router)  # Роутер управления сотрудниками
    dp.include_router(user_verification_router)  # Новый роутер верификации
    dp.include_router(clarification_replies_router)  # Роутер ответов на уточнения
    dp.include_router(base_router)  # base в конце как fallback для общих команд
    
    logger.info("Бот запускается...")
    
    # Запускаем HTTP health check сервер
    try:
        start_health_server(host='0.0.0.0', port=8000)
        logger.info("HTTP health check сервер запущен на порту 8000")
    except Exception as e:
        logger.error(f"Не удалось запустить health check сервер: {e}")
        # Продолжаем работу бота даже если health сервер не запустился
    
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
        # Останавливаем health сервер
        stop_health_server()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
