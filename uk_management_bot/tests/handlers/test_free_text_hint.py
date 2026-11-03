"""Свободный текст в личке вне сценария → инструкция «как создать заявку».

2026-11-03 (profk): жители писали проблему прямым сообщением боту, бот молчал
(catch-all для лички не было), заявка не появлялась. Теперь последний
хендлер base_router отвечает инструкцией и возвращает меню.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uk_management_bot.handlers import base
from uk_management_bot.utils.helpers import get_text


def _msg(text="течёт кран в ванной", chat_type="private", **media):
    msg = MagicMock()
    msg.text = text
    msg.chat.type = chat_type
    for kind in ("voice", "video", "video_note"):
        setattr(msg, kind, media.get(kind))
    msg.from_user.id = 904007715
    msg.answer = AsyncMock()
    return msg


def _handler():
    return next(h for h in base.router.message.handlers if h.callback is base.free_text_request_hint)


async def _matches(msg, raw_state=None) -> bool:
    ok, _ = await _handler().check(msg, raw_state=raw_state)
    return ok


def test_hint_is_last_message_handler_of_base_router():
    """Catch-all обязан быть последним — иначе съест хендлеры ниже по файлу."""
    assert base.router.message.handlers[-1].callback is base.free_text_request_hint


@pytest.mark.asyncio
async def test_filter_matches_free_text_and_voice_without_state():
    assert await _matches(_msg())
    assert await _matches(_msg(text=None, voice=object()))


@pytest.mark.asyncio
async def test_filter_skips_commands_fsm_state_and_groups():
    assert not await _matches(_msg(text="/unknown"))
    assert not await _matches(_msg(), raw_state="RequestStates:description")
    assert not await _matches(_msg(chat_type="supergroup"))
    assert not await _matches(_msg(text=None))


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["ru", "uz"])
async def test_approved_user_gets_instruction_and_menu(lang):
    msg = _msg()
    kb = object()
    with patch.object(base, "get_user_contextual_keyboard", AsyncMock(return_value=kb)):
        await base.free_text_request_hint(msg, user_status="approved", language=lang)
    text = msg.answer.await_args.args[0]
    assert text == get_text("base.handlers.free_text_hint", language=lang)
    assert text != "base.handlers.free_text_hint"
    assert msg.answer.await_args.kwargs["reply_markup"] is kb


@pytest.mark.asyncio
async def test_pending_user_gets_pending_text():
    msg = _msg()
    with patch.object(base, "get_user_contextual_keyboard", AsyncMock(return_value=None)):
        await base.free_text_request_hint(msg, user_status="pending", language="ru")
    assert msg.answer.await_args.args[0] == get_text("auth.pending", language="ru")


# ── Реальная цепочка роутеров main.py: catch-all не отбирает живые флоу ──

def _resolve(text, raw_state=None):
    import re
    from pathlib import Path

    import uk_management_bot.main as main_mod
    from uk_management_bot.tests.handlers.routing_probe import make_message, resolve_ctx

    order = re.findall(r"dp\.include_router\((\w+)\)", Path(main_mod.__file__).read_text())
    routers = [getattr(main_mod, name) for name in order]
    return resolve_ctx(routers, make_message(text), "message", raw_state=raw_state,
                       roles=["applicant"], user=None)


H = "uk_management_bot.handlers"


def test_routing_free_text_reaches_hint():
    assert _resolve("течёт кран в ванной") == (f"{H}.base", "free_text_request_hint")


def test_routing_live_flows_untouched():
    assert _resolve("📝 Создать заявку")[1] == "start_request_creation"
    assert _resolve("/start") == (f"{H}.base", "cmd_start")
    assert _resolve("течёт кран", raw_state="RequestStates:description") == (
        f"{H}.requests.create", "process_description")
