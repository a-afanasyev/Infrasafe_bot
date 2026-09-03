"""Reply-кнопка → сообщение с inline web_app-кнопкой («Регистрация (форма)», «Ввод показаний»).

Причина (profk, 2026-09-03): Telegram НЕ передаёт initData в Mini App, открытое
с reply-кнопки (`KeyboardButton.web_app`) — по документации WebAppInitData
«is empty if the Mini App was launched from a keyboard button». Страницы
`/uk/register` и `/uk/twa/meter-entry` авторизуют только по initData и
показывали «Откройте из Telegram». Inline-кнопка под сообщением initData несёт.

Контракт: reply-кнопки остаются ТЕКСТОВЫМИ (без web_app); по нажатию бот
отвечает сообщением с одной inline web_app-кнопкой на точный URL.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from uk_management_bot.keyboards.base import METER_ENTRY_ROLE, get_main_keyboard_for_role
from uk_management_bot.tests.handlers.routing_probe import make_message, resolve_ctx
from uk_management_bot.utils.helpers import get_text

FRONTEND = "https://example.test"
H = "uk_management_bot.handlers.webapp_buttons"


def _reply_buttons(markup: ReplyKeyboardMarkup):
    return [btn for row in markup.keyboard for btn in row]


def _inline_buttons(markup: InlineKeyboardMarkup):
    return [btn for row in markup.inline_keyboard for btn in row]


def _message(text: str):
    msg = MagicMock()
    msg.text = text
    msg.from_user = MagicMock(id=123)
    msg.answer = AsyncMock()
    return msg


@pytest.fixture(autouse=True)
def _frontend_url(monkeypatch):
    # Патчим через модули-потребители, как test_base_register_button.py: под
    # `--import-mode=importlib` (CI) объект из `config.settings` может оказаться
    # другой идентичности, и патч «в исходнике» до клавиатур не долетает.
    from uk_management_bot.handlers import webapp_buttons
    from uk_management_bot.keyboards import base as keyboards_base

    monkeypatch.setattr(keyboards_base.settings, "FRONTEND_URL", FRONTEND)
    monkeypatch.setattr(webapp_buttons.settings, "FRONTEND_URL", FRONTEND)


# ─── Клавиатуры: кнопки текстовые, без web_app ───────────────────────────────

def test_main_keyboard_meter_entry_button_is_plain_text():
    kb = get_main_keyboard_for_role(
        "applicant", ["applicant", METER_ENTRY_ROLE], "approved", language="ru"
    )
    text = get_text("base.handlers.btn_meter_entry", language="ru")
    matches = [b for b in _reply_buttons(kb) if b.text == text]
    assert len(matches) == 1, "кнопка «Ввод показаний» должна быть у держателя роли"
    assert matches[0].web_app is None, "reply web_app не передаёт initData — кнопка должна быть текстовой"


# ─── Хендлеры: ответ = одна inline web_app-кнопка на точный URL ──────────────

@pytest.mark.asyncio
async def test_register_text_answers_with_inline_webapp_button():
    from uk_management_bot.handlers.webapp_buttons import open_register_webapp

    msg = _message(get_text("base.handlers.btn_register_webapp", language="ru"))
    await open_register_webapp(msg, language="ru")

    msg.answer.assert_called_once()
    markup = msg.answer.call_args.kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    urls = [b.web_app.url for b in _inline_buttons(markup) if b.web_app is not None]
    assert urls == [f"{FRONTEND}/uk/register"]


@pytest.mark.asyncio
async def test_meter_text_answers_with_inline_webapp_button_for_role_holder():
    from uk_management_bot.handlers.webapp_buttons import open_meter_entry_webapp

    msg = _message(get_text("base.handlers.btn_meter_entry", language="ru"))
    await open_meter_entry_webapp(msg, roles=["applicant", METER_ENTRY_ROLE], language="ru")

    msg.answer.assert_called_once()
    markup = msg.answer.call_args.kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    urls = [b.web_app.url for b in _inline_buttons(markup) if b.web_app is not None]
    assert urls == [f"{FRONTEND}/uk/twa/meter-entry"]


@pytest.mark.asyncio
async def test_meter_text_without_role_is_denied_without_webapp():
    """Текст кнопки шлёт КЛИЕНТ (BUG-169): без роли — отказ, без ссылки."""
    from uk_management_bot.handlers.webapp_buttons import open_meter_entry_webapp

    msg = _message(get_text("base.handlers.btn_meter_entry", language="ru"))
    await open_meter_entry_webapp(msg, roles=["applicant"], language="ru")

    msg.answer.assert_called_once()
    assert msg.answer.call_args.args[0] == get_text("errors.permission_denied", language="ru")
    assert msg.answer.call_args.kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_uz_texts_reach_the_same_handlers():
    from uk_management_bot.handlers.webapp_buttons import open_register_webapp

    msg = _message(get_text("base.handlers.btn_register_webapp", language="uz"))
    await open_register_webapp(msg, language="uz")
    markup = msg.answer.call_args.kwargs["reply_markup"]
    urls = [b.web_app.url for b in _inline_buttons(markup) if b.web_app is not None]
    assert urls == [f"{FRONTEND}/uk/register"]


# ─── Роутинг: тексты кнопок реально доходят до новых хендлеров (BUG-155) ─────

def _main_routers():
    import uk_management_bot.main as main_mod

    order = re.findall(r"dp\.include_router\((\w+)\)", Path(main_mod.__file__).read_text())
    return [getattr(main_mod, name) for name in order]


@pytest.mark.parametrize("lang", ["ru", "uz"])
def test_register_button_text_routes_to_webapp_handler(lang):
    text = get_text("base.handlers.btn_register_webapp", language=lang)
    winner = resolve_ctx(
        _main_routers(), make_message(text), "message",
        roles=["applicant"], user=None, user_status="pending",
    )
    assert winner == (H, "open_register_webapp"), winner


@pytest.mark.parametrize("lang", ["ru", "uz"])
def test_meter_button_text_routes_to_webapp_handler(lang):
    text = get_text("base.handlers.btn_meter_entry", language=lang)
    winner = resolve_ctx(
        _main_routers(), make_message(text), "message",
        roles=["applicant", METER_ENTRY_ROLE], user=None, user_status="approved",
    )
    assert winner == (H, "open_meter_entry_webapp"), winner
