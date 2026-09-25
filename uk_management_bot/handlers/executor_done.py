"""«Закрыть этим фото?» — callback ``exdone:{n}`` в личке ОСНОВНОГО бота (Фаза 4).

Фото «готово» из рабочей группы групповой бот переслал автору байтами через
основной бот (``handlers/group_intake_done``) с кнопками по заявкам «В работе».
Нажатие приходит сюда: фото берётся из ``callback.message.photo[-1]`` — это
сообщение основного бота, его file_id он открывает сам — и заявка закрывается
тем же атомарным сервисом, что у TWA:
``services/executor_completion.complete_with_photo(..., source="bot")``.

Идемпотентность: ключ — стабильный UUID5 от (chat_id, message_id, номер), так
двойное нажатие / повторная доставка не закрывают заявку дважды и не грузят
второе фото. «Своя ли заявка и можно ли её закрыть» решает канон workflow в
сервисе; здесь — только формат callback_data (его шлёт КЛИЕНТ), личный чат и
«нажимает тот, кому отправлено». Отказы — короткой фразой сообщением (answer
уже потрачен на «Закрываю…»: загрузка может идти дольше окна callback).

AUD3-37: хендлер не объявляет db — БД через run_db-юниты; ``_db`` — тестовый seam.
"""
from __future__ import annotations

import io
import logging
import re
import uuid
from typing import Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from uk_management_bot.database.session import run_db
from uk_management_bot.services import executor_done_prompt as done
from uk_management_bot.services.executor_completion import (
    COMPLETION_PHOTO_MAX_BYTES,
    CompletionRefused,
    complete_with_photo,
)
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

router = Router(name="executor_done")
router.callback_query.filter(F.data.startswith(done.CB_CLOSE_PREFIX))

# Номер заявки YYMMDD-NNN (счётчик может перерасти 3 цифры). Лимит Telegram
# на callback_data — 64 байта; длинное/чужое значение отбрасывается целиком.
_CALLBACK_RE = re.compile(r"^" + re.escape(done.CB_CLOSE_PREFIX) + r"(\d{6}-\d{3,6})$")
_CALLBACK_MAX_BYTES = 64
_IDEMPOTENCY_NS = uuid.UUID("5b0c7a4e-8f3d-4f59-9b8e-0f1c2d3e4a5b")

# Код отказа сервиса → ключ короткой фразы (executor_done.err_*).
_REFUSAL_KEYS = {
    "not_assigned": "executor_done.err_not_yours",
    "not_found": "executor_done.err_not_found",
    "no_active_shift": "executor_done.err_no_shift",
    "invalid_status": "executor_done.err_status",
    "in_progress": "executor_done.err_in_progress",
    "photo_empty": "executor_done.err_photo",
    "photo_too_large": "executor_done.err_photo",
    "unsupported_photo_type": "executor_done.err_photo",
}
_DEFAULT_ERROR_KEY = "executor_done.err_generic"


def parse_close_callback(data: Optional[str]) -> Optional[str]:
    """Номер заявки из ``exdone:{n}`` или None (формат/длина не те)."""
    if not data or len(data.encode("utf-8")) > _CALLBACK_MAX_BYTES:
        return None
    match = _CALLBACK_RE.match(data)
    return match.group(1) if match else None


def idempotency_key(chat_id: int, message_id: int, request_number: str) -> str:
    """Стабильный UUID нажатия: одно сообщение + одна заявка = одна попытка."""
    return str(uuid.uuid5(_IDEMPOTENCY_NS, f"{chat_id}:{message_id}:{request_number}"))


def refusal_key(code: str) -> str:
    return _REFUSAL_KEYS.get(code, _DEFAULT_ERROR_KEY)


async def _download_photo(callback: CallbackQuery) -> Optional[bytes]:
    try:
        file = await callback.bot.get_file(callback.message.photo[-1].file_id)
        buffer = io.BytesIO()
        await callback.bot.download_file(file.file_path, buffer)
    except Exception as exc:  # noqa: BLE001 — Bot API/сеть: только класс ошибки
        logger.warning("executor_done: фото не скачано: %s", type(exc).__name__)
        return None
    data = buffer.getvalue()
    return data if 0 < len(data) <= COMPLETION_PHOTO_MAX_BYTES else None


def _session_factory():
    from uk_management_bot.database.session import AsyncSessionLocal

    return AsyncSessionLocal


async def _reply(callback: CallbackQuery, key: str, lang: str, **params) -> None:
    try:
        await callback.message.answer(get_text(key, language=lang, **params))
    except Exception as exc:  # noqa: BLE001
        logger.warning("executor_done: ответ не отправлен: %s", type(exc).__name__)


async def _post_commit(request_number: str, outcome) -> None:
    """Realtime дашборду + уведомление жителю — как у API; best-effort."""
    from uk_management_bot.services.redis_pubsub import publish_request_event
    from uk_management_bot.services.workflow_notifications import (
        dispatch_notify_intents_detached,
    )
    from uk_management_bot.utils.request_workflow import normalize_status

    try:
        for ev in outcome.post_commit_intents:
            if ev.kind == "realtime":
                await publish_request_event("request.status_changed", {
                    "number": request_number,
                    "old_status": normalize_status(outcome.old_state),
                    "new_status": ev.data.get("status"),
                })
        await dispatch_notify_intents_detached(request_number, outcome.post_commit_intents)
    except Exception as exc:  # noqa: BLE001 — переход уже закоммичен
        logger.warning("executor_done: post-commit %s не выполнен: %s",
                       request_number, type(exc).__name__)


@router.callback_query()
async def close_with_photo(callback: CallbackQuery, *, _db=None) -> None:
    """Кнопка заявки под фото «готово». Ровно один callback.answer()."""
    lang_fallback = callback.from_user.language_code or "ru"
    request_number = parse_close_callback(callback.data)
    message = callback.message
    if request_number is None or message is None:
        await callback.answer(get_text("executor_done.err_generic", language=lang_fallback),
                              show_alert=True)
        return
    # Личка «бот ↔ исполнитель»: chat.id = telegram_id того, кому отправлено.
    if message.chat.type != "private" or message.chat.id != callback.from_user.id:
        await callback.answer(get_text("executor_done.err_not_yours", language=lang_fallback),
                              show_alert=True)
        return
    if not message.photo:
        await callback.answer(get_text("executor_done.err_photo", language=lang_fallback),
                              show_alert=True)
        return
    executor = await run_db(
        lambda s: done.executor_by_telegram_sync(s, callback.from_user.id), db=_db
    )
    if executor is None:
        await callback.answer(get_text("executor_done.err_not_yours", language=lang_fallback),
                              show_alert=True)
        return

    lang = executor.lang
    await callback.answer(get_text("executor_done.closing", language=lang))
    await _close(callback, executor, request_number)


async def _close(callback: CallbackQuery, executor: done.Executor, request_number: str) -> None:
    lang = executor.lang
    session_factory = _session_factory()
    photo = await _download_photo(callback)
    if photo is None or session_factory is None:
        await _reply(callback, "executor_done.err_generic", lang)
        return
    message = callback.message
    try:
        result = await complete_with_photo(
            session_factory, request_number, executor.user_id, photo,
            idempotency_key(message.chat.id, message.message_id, request_number),
            source="bot",
        )
    except CompletionRefused as exc:
        await _reply(callback, refusal_key(exc.code), lang, request_number=request_number)
        return

    try:
        await message.edit_caption(
            caption=get_text("executor_done.closed", language=lang,
                             request_number=request_number),
            reply_markup=None,
        )
    except TelegramBadRequest as exc:
        # Повторное нажатие: подпись уже та же — не ошибка.
        if "message is not modified" not in str(exc):
            logger.warning("executor_done: подпись не обновлена: %s", type(exc).__name__)
    if result.outcome is not None:
        await _post_commit(request_number, result.outcome)
