"""Приём контакта вне FSM — ответ на «Запросить номер телефона» с дашборда.

Менеджер запрашивает номер с веб-дашборда → API шлёт пользователю сообщение с
request_contact-клавиатурой (`api/users/phone_request.py`) → пользователь
делится контактом уже БЕЗ активного состояния. Онбординговый хендлер ловит
contact только в ``OnboardingStates.waiting_for_phone``, поэтому здесь свой
stateless-хендлер: только приватный чат, только без FSM-состояния (чужие
FSM-сценарии не перехватываем), только СВОЙ контакт (пересланный чужой
контакт — не подтверждение владения номером).
"""

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message, ReplyKeyboardRemove

from uk_management_bot.database.session import run_db
from uk_management_bot.handlers.base import (
    _build_onboarding_screen,
    _load_menu_context as _load_onboarding_redraw,
    needs_onboarding_redraw,
)
from uk_management_bot.handlers.onboarding import _apply_phone
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == "private")


@router.message(StateFilter(None), F.contact)
async def receive_shared_contact(message: Message, language: str = "ru", *, _db=None):
    """Сохраняет свой контакт, присланный вне онбординга."""
    lang = language

    if message.contact.user_id != message.from_user.id:
        await message.answer(
            get_text("phone_request_flow.foreign_contact", language=lang),
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    phone_number = message.contact.phone_number
    if not phone_number.startswith("+"):
        phone_number = "+" + phone_number

    try:
        saved = await run_db(
            lambda s: _apply_phone(s, message.from_user.id, phone_number), db=_db
        )
    except Exception as e:  # noqa: BLE001 — пользователю честная ошибка, не тишина
        logger.error("Не удалось сохранить контакт %s: %s", message.from_user.id, e)
        saved = False

    if saved:
        logger.info("Сохранён телефон по запросу менеджера для %s", message.from_user.id)
        await message.answer(
            get_text("onboarding.phone_saved", language=lang, phone=phone_number),
            reply_markup=ReplyKeyboardRemove(),
        )
        # Спека 2026-09-03 §3.2: контакт — первый шаг онбординга жителя (и в
        # боте, и в TWA). Дальше показываем экран с «Выбрать квартиру», а НЕ
        # автозапуск выбора: контакт мог прийти из TWA, и inline-список дворов
        # с FSM-состоянием повис бы в чате мёртвым.
        ctx = await run_db(
            lambda s: _load_onboarding_redraw(s, message.from_user.id), db=_db
        )
        if needs_onboarding_redraw(ctx):
            text, keyboard = _build_onboarding_screen(ctx, lang)
            await message.answer(text, reply_markup=keyboard)
    else:
        await message.answer(
            get_text("errors.unknown_error", language=lang),
            reply_markup=ReplyKeyboardRemove(),
        )
