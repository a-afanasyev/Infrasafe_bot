import asyncio
import traceback
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent
from uk_management_bot.config.settings import settings

# Sentry error tracking (optional — only if SENTRY_DSN is configured)
if settings.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.1,
        environment="production" if not settings.DEBUG else "development",
    )
from uk_management_bot.database.session import engine, SessionLocal
from uk_management_bot.handlers.base import router as base_router, start_router
from uk_management_bot.handlers.requests import router as requests_router
from uk_management_bot.handlers.inspector_requests import router as inspector_requests_router
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
from uk_management_bot.handlers.request_acceptance import router as request_acceptance_router  # Приёмка заявок
from uk_management_bot.handlers.unaccepted_requests import router as unaccepted_requests_router  # Непринятые заявки

# Обработчики передачи смен
from uk_management_bot.handlers.shift_transfer import router as shift_transfer_router

# Обработчики справочника адресов
from uk_management_bot.handlers.address_yards import router as address_yards_router
from uk_management_bot.handlers.address_buildings import router as address_buildings_router
from uk_management_bot.handlers.address_apartments import router as address_apartments_router
from uk_management_bot.handlers.address_moderation import router as address_moderation_router
from uk_management_bot.handlers.user_apartment_selection import router as user_apartment_selection_router
from uk_management_bot.handlers.user_apartments import router as user_apartments_router  # NEW: User apartment management

# Обработчики управления дворами пользователей
from uk_management_bot.handlers.user_yards_management import router as user_yards_router
from uk_management_bot.handlers.feedback import router as feedback_router  # Обратная связь
from uk_management_bot.handlers.access_control import router as access_control_router  # Контроль доступа (ТЗ §6.4)

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

# Планировщик смен
from uk_management_bot.utils.shift_scheduler import start_scheduler, stop_scheduler, get_scheduler_status

# Интеграции
from uk_management_bot.integrations import get_media_client, close_media_client

# Инициализация логирования
setup_structured_logging()
logger = get_logger(__name__, component="main")

async def initialize_scheduler(bot: Bot):
    """Инициализация планировщика смен.

    COD-02: НЕ создаём здесь долгоживущий ``NotificationService`` с сессией,
    которую тут же закрываем — job'ы строят свой ``NotificationService`` на
    свежей сессии (см. ShiftScheduler._notifier). Передаём только бот.
    """
    try:
        # Запускаем планировщик (уведомления — через единый диспетчерский бот)
        await start_scheduler(bot=bot)
        logger.info("Планировщик смен запущен успешно")

        # Получаем и логируем статус
        status = await get_scheduler_status()
        logger.info(f"Планировщик: {status['jobs_count']} задач активно")

    except Exception as e:
        logger.error(f"Ошибка инициализации планировщика: {e}")


async def initialize_media_service():
    """Инициализация медиа-сервиса"""
    try:
        media_client = get_media_client()
        if media_client:
            # Проверяем доступность сервиса
            health = await media_client.health_check()
            logger.info(f"Media Service подключен: {health}")
            return True
        else:
            logger.warning("Media Service отключен в настройках")
            return False
    except Exception as e:
        logger.error(f"Ошибка подключения к Media Service: {e}")
        logger.warning("Бот будет работать без Media Service")
        return False


async def send_startup_notification(bot: Bot):
    """Отправляет уведомление о запуске бота"""
    try:
        # Получаем статус планировщика
        scheduler_status = await get_scheduler_status()
        scheduler_info = f"🕐 Планировщик: {scheduler_status['jobs_count']} задач" if scheduler_status['is_running'] else "⏸️ Планировщик: Остановлен"

        # Проверяем статус медиа-сервиса
        media_status = "✅ Активен" if settings.MEDIA_SERVICE_ENABLED else "⏸️ Отключен"

        startup_message = (
            "<b>UK Management Bot запущен!</b>\n\n"
            f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
            "Статус: Активен\n"
            "Версия: 1.0.0\n"
            "База данных: Подключена\n"
            "Система верификации: Активна\n"
            f"{scheduler_info}\n"
            f"Media Service: {media_status}\n\n"
            "Бот готов к работе!"
        )

        # Отправляем уведомление администраторам (HTML is default parse_mode)
        if settings.ADMIN_USER_IDS:
            for admin_id in settings.ADMIN_USER_IDS:
                try:
                    await bot.send_message(admin_id, startup_message)
                    logger.info(f"Уведомление о запуске отправлено администратору {admin_id}")
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление администратору {admin_id}: {e}")

        # Отправляем в канал если указан (placeholder в .env.template игнорируется)
        from uk_management_bot.services.notification_service import _resolve_channel_id
        channel_id = _resolve_channel_id()
        if channel_id:
            try:
                await bot.send_message(channel_id, startup_message)
                logger.info("Уведомление о запуске отправлено в канал")
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление в канал: {e}")
        
        logger.info("✅ Бот успешно запущен и готов к работе")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления о запуске: {e}")

async def main():
    """Главная функция запуска бота"""
    
    # BOT_TOKEN is validated in settings.py at import time
    # DB schema is managed by Alembic migrations (run from API entrypoint)
    import uk_management_bot.database.models  # noqa: F401 — ensure models are registered
    logger.info("Модели БД загружены (миграции выполняются через API entrypoint)")

    # Инициализируем администраторов из ADMIN_USER_IDS
    from uk_management_bot.database.init_admin import init_all_admins
    try:
        created, updated = init_all_admins()
        if created > 0 or updated > 0:
            logger.info(f"Администраторы инициализированы: создано {created}, обновлено {updated}")
    except Exception as e:
        logger.warning(f"Не удалось инициализировать администраторов: {e}")

    # Инициализируем бота и диспетчер
    # ВАЖНО: parse_mode="HTML" позволяет использовать HTML теги (<b>, <i>, <code> и т.д.)
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # COD-03: регистрируем ЕДИНЫЙ диспетчерский бот как shared-bot для всех
    # notification-путей (планировщик, notify_user) → нет второго aiogram Bot
    # с отдельной aiohttp-сессией, нет хазарда «Event loop is closed».
    from uk_management_bot.services.notification_service import set_shared_bot
    set_shared_bot(bot)

    # BUG-BOT-001: Verify configured BOT_USERNAME matches token-derived username.
    # Mismatch produces broken invite links (e.g. https://t.me/<wrong_bot>?start=...).
    # We never crash here — bot must still serve. The goal is loud diagnostic.
    try:
        me = await bot.get_me()
        real_username = me.username or ""
        configured = settings.BOT_USERNAME
        if not configured:
            logger.error(
                f"BUG-BOT-001: BOT_USERNAME is not set in environment. "
                f"Falling back to token-derived username '{real_username}'. "
                f"Set BOT_USERNAME={real_username} in .env to silence this error."
            )
            # Graceful: populate at runtime so invite-link builders work.
            settings.BOT_USERNAME = real_username
        elif configured != real_username:
            logger.error(
                f"BUG-BOT-001: BOT_USERNAME mismatch — configured='{configured}', "
                f"actual (getMe)='{real_username}'. Invite links will point to the wrong bot. "
                f"Update BOT_USERNAME in .env to '{real_username}' and restart."
            )
        else:
            logger.info(f"BOT_USERNAME OK: {real_username}")
    except Exception as exc:  # pragma: no cover — network/auth issues
        logger.error(
            f"BUG-BOT-001: getMe() failed during BOT_USERNAME check: {exc}. "
            f"Bot will continue with configured BOT_USERNAME='{settings.BOT_USERNAME}'."
        )

    # FSM Storage: Redis in production, MemoryStorage in debug
    if not settings.DEBUG and settings.REDIS_URL:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            storage = RedisStorage.from_url(settings.REDIS_URL)
            logger.info("FSM storage: Redis")
        except Exception as e:
            logger.warning(f"Redis FSM storage unavailable, falling back to MemoryStorage: {e}")
            storage = MemoryStorage()
    else:
        storage = MemoryStorage()
        logger.info("FSM storage: MemoryStorage")
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

    # Localization middleware: injects `language` into handler data
    from uk_management_bot.middlewares.localization import localization_middleware
    @dp.update.middleware()
    async def _localization_middleware(handler, event, data):
        return await localization_middleware(handler, event, data)

    # Подключаем shift-middleware глобально через декоратор (последний)
    @dp.update.middleware()
    async def _shift_middleware(handler, event, data):
        return await shift_context_middleware(handler, event, data)

    # Throttling middleware: max 2 messages/sec per user
    from uk_management_bot.middlewares.throttling import ThrottlingMiddleware
    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))

    # Глобальный обработчик ошибок
    from uk_management_bot.utils.helpers import get_text, get_user_language

    async def global_error_handler(event: ErrorEvent) -> bool:
        logger.error(
            f"Unhandled exception: {event.exception!r}\n"
            + traceback.format_exc()
        )
        try:
            update = event.update
            # Определяем chat_id и user_id из апдейта
            chat_id: int | None = None
            user_id: int | None = None
            if update.message:
                chat_id = update.message.chat.id
                user_id = update.message.from_user.id if update.message.from_user else None
            elif update.callback_query:
                chat_id = update.callback_query.message.chat.id if update.callback_query.message else None
                user_id = update.callback_query.from_user.id
            elif update.inline_query:
                user_id = update.inline_query.from_user.id
            if chat_id and user_id:
                db = SessionLocal()
                try:
                    lang = get_user_language(user_id, db)
                finally:
                    db.close()
                error_text = get_text("errors.unexpected", language=lang)
                await bot.send_message(chat_id, error_text)
        except Exception as notify_err:
            logger.warning(f"Не удалось отправить сообщение об ошибке пользователю: {notify_err}")
        return True

    dp.errors.register(global_error_handler)

    # Регистрируем роутеры
    dp.include_router(start_router)  # /start FIRST — catches /start from any FSM state
    dp.include_router(health_router)  # Health check должен быть первым для быстрого доступа
    dp.include_router(auth_router)
    
    # ВАЖНО: profile_editing_router должен быть раньше requests_router для правильной работы смены языка
    # Это обеспечивает, что handlers редактирования профиля срабатывают до handlers заявок
    dp.include_router(profile_editing_router)  # Роутер редактирования профиля (раньше для смены языка)
    
    # ВАЖНО: requests_router должен быть раньше onboarding_router для правильной работы Entry Handler
    # Это обеспечивает, что handler создания заявки срабатывает до handlers онбординга
    # inspector_requests_router — ПЕРЕД requests_router: его insp_* + StateFilter не
    # пересекаются с глобальными (не-стейт-фильтрованными) category_*/confirm_* applicant-flow.
    dp.include_router(inspector_requests_router)  # обходчик: заявка с обхода (building-level)
    dp.include_router(requests_router)  # requests раньше для Entry Handler (создание заявки)
    
    dp.include_router(onboarding_router)
    dp.include_router(admin_router)  # admin раньше для перехвата действий менеджеров

    # Система приёмки заявок (ДОЛЖНА БЫТЬ РАНЬШЕ других handlers заявок!)
    dp.include_router(request_acceptance_router)  # Приёмка заявок - перехватывает accept_request_* и rate_*
    dp.include_router(unaccepted_requests_router)  # Непринятые заявки для менеджеров

    # Система управления сменами
    dp.include_router(shift_management_router_new)  # Управление сменами для менеджеров
    dp.include_router(my_shifts_router)  # Интерфейс смен для исполнителей
    dp.include_router(shift_transfer_router)  # Передача смен между исполнителями
    dp.include_router(shifts_router)  # старый роутер смен

    # Система назначения заявок
    dp.include_router(request_assignment_router)
    dp.include_router(request_status_management_router)
    dp.include_router(request_comments_router)
    dp.include_router(request_reports_router)

    # Справочник адресов (порядок важен: пользовательский выбор → модерация → управление → квартиры → здания → дворы)
    dp.include_router(user_apartment_selection_router)  # Пользовательский выбор квартиры при регистрации
    dp.include_router(user_apartments_router)  # NEW: Управление квартирами из профиля
    dp.include_router(address_moderation_router)
    dp.include_router(address_apartments_router)
    dp.include_router(address_buildings_router)
    dp.include_router(address_yards_router)

    dp.include_router(user_yards_router)  # Управление дворами пользователей (ПЕРЕД user_management!)
    dp.include_router(user_management_router)  # включаем обратно
    dp.include_router(employee_management_router)  # Роутер управления сотрудниками
    dp.include_router(user_verification_router)  # Новый роутер верификации
    dp.include_router(clarification_replies_router)  # Роутер ответов на уточнения
    dp.include_router(feedback_router)  # Обратная связь (перед base_router)
    dp.include_router(access_control_router)  # Контроль доступа жителя (ТЗ §6.4, перед base_router)
    dp.include_router(base_router)  # base в конце как fallback для общих команд
    
    logger.info("Бот запускается...")
    
    # Запускаем HTTP health check сервер
    try:
        start_health_server(host='0.0.0.0', port=8000)
        logger.info("HTTP health check сервер запущен на порту 8000")
    except Exception as e:
        logger.error(f"Не удалось запустить health check сервер: {e}")
        # Продолжаем работу бота даже если health сервер не запустился
    
    resident_notify_task = None
    try:
        # Инициализируем планировщик смен
        await initialize_scheduler(bot)

        # Инициализируем медиа-сервис
        await initialize_media_service()

        # Отправляем уведомление о запуске
        await send_startup_notification(bot)

        # Подписчик резидентских уведомлений (access:resident_notify → Telegram).
        # Best-effort: запускается только при ACCESS_EVENT_BROKER=redis (cross-process),
        # иначе сам залогирует и вернёт None — бот работает без уведомлений.
        from uk_management_bot.services.access_notify_subscriber import (
            start_resident_notify_subscriber,
        )
        resident_notify_task = start_resident_notify_subscriber(bot)

        # Запускаем бота
        await dp.start_polling(bot)
        
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        # Останавливаем подписчик резидентских уведомлений
        if resident_notify_task is not None:
            resident_notify_task.cancel()
            try:
                await resident_notify_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Ошибка остановки подписчика уведомлений: {e}")
            logger.info("Подписчик резидентских уведомлений остановлен")

        # Останавливаем планировщик
        try:
            await stop_scheduler()
            logger.info("Планировщик смен остановлен")
        except Exception as e:
            logger.error(f"Ошибка остановки планировщика: {e}")

        # Закрываем медиа-клиент
        try:
            await close_media_client()
        except Exception as e:
            logger.error(f"Ошибка закрытия Media Service клиента: {e}")

        # Останавливаем health сервер
        stop_health_server()
        await bot.session.close()
        # Сброс shared-bot: не оставляем глобалку на закрытую сессию (reload/тесты).
        try:
            from uk_management_bot.services.notification_service import set_shared_bot
            set_shared_bot(None)
        except Exception:
            pass

        # Закрываем DB-пулы (engine уже импортирован на уровне модуля)
        try:
            from uk_management_bot.database.session import async_engine
            engine.dispose()
            if async_engine:
                await async_engine.dispose()
            logger.info("DB connection pools disposed")
        except Exception as e:
            logger.error(f"Ошибка закрытия DB-пулов: {e}")

if __name__ == "__main__":
    asyncio.run(main())
