"""«Готово» исполнителя в рабочей группе → личка основным ботом (Фаза 4).

Живёт в процессе ГРУППОВОГО бота (зовётся из ``group_intake.group_message_entry``
до тег-гейтов и LLM). Автор — approved-сотрудник с ролью executor, в
сообщении тег заявки и слово «готово» (``services/group_intake/done_detector``):

* в группе — тишина (ни ответа, ни LLM);
* без фото — основной бот пишет автору «Какую заявку закрыли?» + web_app-
  кнопки по заявкам «В работе»/«Возвращена» и «Все»;
* с фото — фото скачивается ГРУППОВЫМ ботом (его file_id основной бот не
  откроет) и основным ботом уходит автору байтами с подписью «Закрыть этим
  фото?» и callback-кнопками ``exdone:{n}`` по заявкам «В работе». Нажатие
  обрабатывает процесс основного бота (``handlers/executor_done``).

Не исполнитель (житель, инспектор, менеджер) — ``False``: сообщение идёт
обычным путём приёма. Отправка — send-only инстанс основного бота
(``notification_service._get_shared_bot``, его регистрирует
group_intake_main). AUD3-37: БД только через run_db-юниты.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import BufferedInputFile, Message

from uk_management_bot.database.session import run_db
from uk_management_bot.services import executor_done_prompt as done
from uk_management_bot.services.executor_completion import COMPLETION_PHOTO_MAX_BYTES
from uk_management_bot.services.group_intake import pending
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)


def _main_bot():
    from uk_management_bot.services.notification_service import _get_shared_bot

    return _get_shared_bot()


async def download_group_photo(bot: Bot, file_id: str) -> Optional[bytes]:
    """Байты фото ГРУППОВЫМ ботом; None — не удалось (лог без текста исключения)."""
    try:
        file = await bot.get_file(file_id)
        buffer = io.BytesIO()
        await bot.download_file(file.file_path, buffer)
    except Exception as exc:  # noqa: BLE001 — Bot API/сеть: только класс ошибки
        logger.warning("group_intake_done: фото не скачано: %s", type(exc).__name__)
        return None
    data = buffer.getvalue()
    if not data or len(data) > COMPLETION_PHOTO_MAX_BYTES:
        return None
    return data


async def _send_photo_prompt(sender, executor: done.Executor, photo: bytes,
                             tasks: tuple[done.OpenTask, ...]) -> bool:
    caption = get_text("executor_done.close_with_photo", language=executor.lang)
    return await done.send_safely(
        lambda: sender.send_photo(
            executor.telegram_id,
            BufferedInputFile(photo, filename="done.jpg"),
            caption=caption,
            reply_markup=done.photo_pick_markup(tasks),
        ),
        telegram_id=executor.telegram_id, what="фото «готово»",
    )


async def handle_done_report(message: Message, bot: Bot, *, _db=None) -> bool:
    """True — сообщение обработано как «готово» (дальше не обрабатывать)."""
    executor = await run_db(
        lambda s: done.executor_by_telegram_sync(s, message.from_user.id), db=_db
    )
    if executor is None:
        return False
    # Повторная доставка того же апдейта не шлёт вторую личку; сбой Redis —
    # тишина (как у всего группового приёма, fail-closed).
    if not await pending.mark_seen(message.chat.id, message.message_id):
        return True

    sender = _main_bot()
    if message.photo:
        tasks, _total = await run_db(
            lambda s: done.open_tasks_sync(s, executor.user_id, executor.lang,
                                           done.CLOSABLE_STATUSES),
            db=_db,
        )
        if tasks:
            photo = await download_group_photo(bot, message.photo[-1].file_id)
            if photo is not None:
                await _send_photo_prompt(sender, executor, photo, tasks)
                return True
        # Нет заявок «В работе» или фото не скачалось — обычный список.

    tasks, _total = await run_db(
        lambda s: done.open_tasks_sync(s, executor.user_id, executor.lang), db=_db
    )
    await done.send_open_tasks_prompt(sender, executor, tasks)
    return True
