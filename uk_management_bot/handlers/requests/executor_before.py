"""«Фото до работ» исполнителя в боте (обычный режим).

Кнопка `executor_before_{n}` на карточке своей заявки (любой незакрытый
статус) → исполнитель шлёт фото (до 4) → «Готово» `executor_before_done_{n}`:
каждое фото скачивается байтами и уходит тем же сервисом, что у TWA
(`services/executor_before_photo.upload_before_photo`). Права, статус, лимит
и идемпотентность решает сервис; здесь — только формат callback_data (его
шлёт КЛИЕНТ), сбор фото в FSM и короткие фразы отказов.

Ключ идемпотентности — UUID5 от (telegram-id, номер, file_unique_id): двойное
нажатие «Готово» или повтор после сбоя не грузят то же фото второй раз.
"""
from __future__ import annotations

import io
import logging
import re
import uuid
from typing import Optional

from aiogram import Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from uk_management_bot.services.executor_before_photo import BEFORE_PHOTO_LIMIT, upload_before_photo
from uk_management_bot.services.executor_completion import COMPLETION_PHOTO_MAX_BYTES, CompletionRefused
from uk_management_bot.services.request_handler_service import RequestHandlerService
from uk_management_bot.utils.fsm_media import append_fsm_media
from uk_management_bot.utils.helpers import get_text, get_user_language

from ._router import router
from uk_management_bot.database.session import run_db

logger = logging.getLogger(__name__)

CB_START = "executor_before_"
CB_DONE = "executor_before_done_"
# Номер YYMMDD-NNN (счётчик может перерасти 3 цифры); чужой формат — отбросить.
_START_RE = re.compile(r"^executor_before_(\d{6}-\d{3,6})$")
_DONE_RE = re.compile(r"^executor_before_done_(\d{6}-\d{3,6})$")
_IDEMPOTENCY_NS = uuid.UUID("8d1f2c3b-4a5e-4f60-8b7c-9d0e1f2a3b4c")
_FSM_KEY = "before_media"

# Код отказа сервиса → ключ короткой фразы.
_REFUSAL_KEYS = {
    "before_limit": "executor_before.err_limit",
    "invalid_status": "executor_before.err_closed",
    "not_assigned": "executor_before.err_not_yours",
    "not_found": "executor_before.err_not_yours",
    "photo_empty": "executor_before.err_photo",
    "photo_too_large": "executor_before.err_photo",
    "unsupported_photo_type": "executor_before.err_photo",
    "media_rejected": "executor_before.err_photo",
    "media_unavailable": "executor_before.err_media",
    "idempotency_unavailable": "executor_before.err_media",
    "in_progress": "executor_before.err_media",
}
_DEFAULT_ERROR_KEY = "executor_before.err_generic"


class ExecutorBeforeStates(StatesGroup):
    waiting_before_media = State()


def parse_number(pattern: re.Pattern, data: Optional[str]) -> Optional[str]:
    """Номер заявки из callback_data или None (формат/длина не те)."""
    if not data or len(data.encode("utf-8")) > 64:
        return None
    match = pattern.match(data)
    return match.group(1) if match else None


def idempotency_key(telegram_id: int, request_number: str, file_unique_id: str) -> str:
    return str(uuid.uuid5(_IDEMPOTENCY_NS, f"{telegram_id}:{request_number}:{file_unique_id}"))


def refusal_key(code: str) -> str:
    return _REFUSAL_KEYS.get(code, _DEFAULT_ERROR_KEY)


def _before_actor_unit(session, telegram_id: int) -> tuple[str, Optional[int]]:
    """DB-юнит (run_db): язык и id исполнителя — скаляры, не ORM."""
    user = RequestHandlerService(session).get_user_by_telegram_id(telegram_id)
    return get_user_language(telegram_id, session), (user.id if user else None)


async def _before_actor(telegram_id: int) -> tuple[str, Optional[int]]:
    return await run_db(lambda s: _before_actor_unit(s, telegram_id))


def _keyboard(request_number: str, lang: str, count: int) -> InlineKeyboardMarkup:
    rows = []
    if count:
        rows.append([InlineKeyboardButton(
            text=get_text("executor_before.btn_done", language=lang, count=count),
            callback_data=f"{CB_DONE}{request_number}")])
    rows.append([InlineKeyboardButton(
        text=get_text("common.cancel", language=lang), callback_data=f"view_request_{request_number}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.regexp(_START_RE))
async def executor_before_start(callback: CallbackQuery, state: FSMContext):
    request_number = parse_number(_START_RE, callback.data)
    if request_number is None:
        await callback.answer()
        return
    lang, _ = await _before_actor(callback.from_user.id)
    await state.set_state(ExecutorBeforeStates.waiting_before_media)
    await state.update_data(before_request_number=request_number, **{_FSM_KEY: []})
    await callback.message.answer(
        get_text("executor_before.prompt", language=lang, max=BEFORE_PHOTO_LIMIT),
        reply_markup=_keyboard(request_number, lang, 0))
    await callback.answer()


@router.message(ExecutorBeforeStates.waiting_before_media, F.photo)
async def executor_before_collect(message: Message, state: FSMContext):
    data = await state.get_data()
    request_number = data.get("before_request_number")
    lang, _ = await _before_actor(message.from_user.id)
    photo = message.photo[-1]
    result = await append_fsm_media(
        state, _FSM_KEY, {"file_id": photo.file_id, "file_unique_id": photo.file_unique_id},
        media_group_id=message.media_group_id, message_id=message.message_id, limit=BEFORE_PHOTO_LIMIT)
    if not result.added:
        if result.notify:
            await message.answer(get_text("executor_before.err_limit", language=lang))
        return
    await message.answer(
        get_text("executor_before.added", language=lang, count=result.count),
        reply_markup=_keyboard(request_number, lang, result.count))


async def _download(bot: Bot, file_id: str) -> Optional[bytes]:
    try:
        file = await bot.get_file(file_id)
        buffer = io.BytesIO()
        await bot.download_file(file.file_path, buffer)
    except Exception as exc:  # noqa: BLE001 — Bot API/сеть: только класс ошибки
        logger.warning("executor_before: фото не скачано: %s", type(exc).__name__)
        return None
    data = buffer.getvalue()
    return data if 0 < len(data) <= COMPLETION_PHOTO_MAX_BYTES else None


def _session_factory():
    from uk_management_bot.database.session import AsyncSessionLocal

    return AsyncSessionLocal


@router.callback_query(F.data.regexp(_DONE_RE))
async def executor_before_done(callback: CallbackQuery, state: FSMContext):
    request_number = parse_number(_DONE_RE, callback.data)
    data = await state.get_data()
    if request_number is None or data.get("before_request_number") != request_number:
        await callback.answer()
        return
    lang, user_id = await _before_actor(callback.from_user.id)
    await callback.answer(get_text("executor_before.uploading", language=lang))
    items = list(data.get(_FSM_KEY) or [])
    await state.clear()

    sent = 0
    errors: list[str] = []
    for item in items:
        if user_id is None:
            errors.append(refusal_key("not_assigned"))
            break
        photo_bytes = await _download(callback.bot, item["file_id"])
        if photo_bytes is None:
            errors.append(refusal_key("photo_empty"))
            continue
        try:
            await upload_before_photo(
                _session_factory(), request_number, user_id, photo_bytes,
                idempotency_key(callback.from_user.id, request_number, item["file_unique_id"]))
            sent += 1
        except CompletionRefused as exc:
            errors.append(refusal_key(exc.code))
            if exc.code in ("before_limit", "invalid_status", "not_assigned", "not_found"):
                break  # у следующих фото исход тот же

    lines = []
    if sent:
        lines.append(get_text("executor_before.sent", language=lang, count=sent))
    lines.extend(get_text(key, language=lang) for key in dict.fromkeys(errors))
    await callback.message.answer(
        "\n".join(lines) or get_text(_DEFAULT_ERROR_KEY, language=lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text=get_text("executor_before.btn_back", language=lang),
            callback_data=f"view_request_{request_number}")]]))
