"""Entrypoint ВЫДЕЛЕННОГО бота Group Intake (заявки из ТГ-групп жителей).

Отдельный процесс со своим токеном (GROUP_INTAKE_BOT_TOKEN) — прецедент
asset-bot: один polling на токен. Зачем отдельный бот:
  * основной бот в группы не добавляется вовсе — его privacy mode остаётся
    включённым, а catch-all групповых сообщений не рискует приватными FSM;
  * /setprivacy → Disable (чтение всех сообщений группы) нужен только этому
    боту;
  * LLM-нагрузка и сбои фичи изолированы от основного polling.

У этого диспетчера НЕТ приватных хендлеров: только group_intake-роутер,
auth-middleware (тихий отсев blocked/deleted) и throttling. Deep-link'и в
текстах ведут на ОСНОВНОЙ бот (settings.BOT_USERNAME) — регистрация, адреса
и дальнейшая жизнь заявки остаются в личном боте.

Заявка создаётся тем же save_request в ту же БД. Notification-пути
(auto_dispatch → «вам назначена») регистрируют send-only Bot на ОСНОВНОМ
токене — отправка вторым процессом безопасна, конфликтует только polling.
"""
import asyncio

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from uk_management_bot.config.settings import settings
from uk_management_bot.utils.structured_logger import setup_structured_logging, get_logger
from uk_management_bot.utils.telegram_client import build_bot

setup_structured_logging()
logger = get_logger(__name__, component="group_intake_main")


async def group_intake_error_handler(event: ErrorEvent) -> bool:
    """Только лог, без ответа в чат: философия фичи — тишина в группе при
    любых сбоях («нет номера — нет заявки» объясняет закреп-сообщение)."""
    logger.error(
        "Unhandled exception in group-intake update processing",
        exc_info=event.exception,
    )
    return True


def setup_group_intake_dispatcher(dp: Dispatcher) -> None:
    """Боевой пайплайн диспетчера группового бота — единая точка для main()
    и интеграционных тестов (test_group_intake_routing), как setup_dispatcher
    основного бота."""
    from uk_management_bot.handlers.group_intake import router as group_intake_router
    from uk_management_bot.middlewares.auth import auth_middleware
    from uk_management_bot.middlewares.throttling import ThrottlingMiddleware

    # auth — ради тихого group-path для blocked/deleted (и data["user"] для
    # будущих потребителей); db-middleware не нужен: хендлеры ходят в БД
    # только через run_db (AUD3-37).
    @dp.update.middleware()
    async def _auth_middleware(handler, event, data):
        return await auth_middleware(handler, event, data)

    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))
    dp.include_router(group_intake_router)
    dp.errors.register(group_intake_error_handler)


async def main() -> None:
    """Запуск группового бота. Без флага/токена процессу делать нечего."""
    if not settings.GROUP_INTAKE_ENABLED:
        logger.error("GROUP_INTAKE_ENABLED=false — групповой бот не запускается")
        return
    if not settings.GROUP_INTAKE_BOT_TOKEN:
        logger.error("GROUP_INTAKE_BOT_TOKEN пуст — задайте токен в Doppler")
        return

    import uk_management_bot.database.models  # noqa: F401 — регистрация моделей

    bot = build_bot(settings.GROUP_INTAKE_BOT_TOKEN)

    # Страховка от «один токен — два поллера»: если токен совпал с основным
    # ботом, polling здесь дрался бы с основным процессом за getUpdates.
    try:
        me = await bot.get_me()
        if settings.BOT_USERNAME and me.username == settings.BOT_USERNAME:
            logger.error(
                "GROUP_INTAKE_BOT_TOKEN указывает на ОСНОВНОГО бота "
                f"@{me.username} — второй polling конфликтует, выходим"
            )
            await bot.session.close()
            return
        logger.info(f"Group Intake bot: @{me.username}")
    except Exception as exc:
        # Сеть/авторизация: не падаем — polling сам повторит и залогирует.
        logger.warning(f"getMe() failed on startup: {exc}")

    # Send-only бот на ОСНОВНОМ токене для notification-путей (auto_dispatch
    # и далее): получатели общаются с основным ботом, уведомления должны
    # приходить от него же.
    from uk_management_bot.services.notification_service import set_shared_bot
    sender = build_bot(settings.BOT_TOKEN)
    set_shared_bot(sender)

    from uk_management_bot.services.group_intake import pending
    await pending.startup_ping()

    dp = Dispatcher(storage=MemoryStorage())
    setup_group_intake_dispatcher(dp)

    logger.info("Group Intake bot запускается (polling)...")
    try:
        await dp.start_polling(bot)
    finally:
        await pending.aclose()
        set_shared_bot(None)
        await sender.session.close()
        await bot.session.close()
        from uk_management_bot.database.session import engine
        engine.dispose()
        logger.info("Group Intake bot остановлен")


if __name__ == "__main__":
    asyncio.run(main())
