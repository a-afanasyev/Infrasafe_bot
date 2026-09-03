"""Reply-кнопки, открывающие Mini App: «Регистрация (форма)», «Ввод показаний».

Почему не `KeyboardButton(web_app=…)`: Telegram не передаёт initData в Mini App,
открытое с reply-кнопки (WebAppInitData «is empty if the Mini App was launched
from a keyboard button»). Страницы `/uk/register` и `/uk/twa/meter-entry`
авторизуют только по initData — с reply-кнопки они показывали «Откройте из
Telegram» (profk, 2026-09-03). Inline web_app-кнопка под сообщением initData
несёт на всех клиентах, поэтому reply-кнопка — текст, а ссылка — здесь.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from uk_management_bot.config.settings import settings
from uk_management_bot.keyboards.base import METER_ENTRY_ROLE
from uk_management_bot.utils.button_texts import (
    get_meter_entry_texts,
    get_register_webapp_texts,
)
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

router = Router()

REGISTER_WEBAPP_TEXTS = get_register_webapp_texts()
METER_ENTRY_TEXTS = get_meter_entry_texts()

REGISTER_PATH = "/uk/register"
METER_ENTRY_PATH = "/uk/twa/meter-entry"


def _open_webapp_markup(path: str, language: str) -> InlineKeyboardMarkup:
    """Одна inline web_app-кнопка на `{FRONTEND_URL}{path}` (FRONTEND_URL — bare origin)."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=get_text("base.handlers.btn_open_webapp", language=language),
            web_app=WebAppInfo(url=f"{settings.FRONTEND_URL}{path}"),
        )
    ]])


async def _answer_with_webapp(message: Message, prompt_key: str, path: str, language: str) -> None:
    if not settings.FRONTEND_URL:
        # Кнопки рисуются только при заданном FRONTEND_URL; сюда попадёт лишь
        # клиент со старой клавиатурой — честно скажем, что ссылки нет.
        await message.answer(get_text("errors.unknown_error", language=language))
        return
    await message.answer(
        get_text(prompt_key, language=language),
        reply_markup=_open_webapp_markup(path, language),
    )


@router.message(F.text.in_(REGISTER_WEBAPP_TEXTS))
async def open_register_webapp(message: Message, language: str = "ru", **_kwargs) -> None:
    """«📝 Регистрация (форма)» → inline-кнопка на форму регистрации жителя."""
    await _answer_with_webapp(message, "base.handlers.register_webapp_prompt", REGISTER_PATH, language)


@router.message(F.text.in_(METER_ENTRY_TEXTS))
async def open_meter_entry_webapp(
    message: Message, roles: list[str] | None = None, language: str = "ru", **_kwargs
) -> None:
    """«📊 Ввод показаний» → inline-кнопка на Mini App контролёра.

    Текст кнопки присылает клиент (BUG-169): роль проверяем здесь, а не
    доверяем факту наличия кнопки в клавиатуре.
    """
    if METER_ENTRY_ROLE not in (roles or []):
        logger.warning("meter-entry webapp requested without role by tg=%s", message.from_user.id)
        await message.answer(get_text("errors.permission_denied", language=language))
        return
    await _answer_with_webapp(message, "base.handlers.meter_entry_prompt", METER_ENTRY_PATH, language)
