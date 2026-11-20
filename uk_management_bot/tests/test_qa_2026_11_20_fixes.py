"""Регрессии живого QA 2026-11-20 (менеджерская часть бота)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendMessage

from uk_management_bot.keyboards.request_comments import get_comments_list_keyboard
from uk_management_bot.services.notification_service.channel import send_to_user

NUMBER = "261120-001"


def _network_error(cause: BaseException) -> TelegramNetworkError:
    """Как aiogram: сетевая ошибка, поднятая ВНУТРИ except исходной."""
    try:
        try:
            raise cause
        except type(cause):
            raise TelegramNetworkError(method=SendMessage(chat_id=1, text="x"), message="boom")
    except TelegramNetworkError as e:
        return e


class TestSendRetry:
    @pytest.mark.asyncio
    async def test_dropped_connection_is_retried_once(self):
        bot = SimpleNamespace(send_message=AsyncMock(
            side_effect=[_network_error(ConnectionResetError()), None]))
        assert await send_to_user(bot, 1, "t") is True
        assert bot.send_message.await_count == 2

    @pytest.mark.asyncio
    async def test_timeout_is_not_retried(self):
        bot = SimpleNamespace(send_message=AsyncMock(
            side_effect=_network_error(asyncio.TimeoutError())))
        assert await send_to_user(bot, 1, "t") is False
        assert bot.send_message.await_count == 1

    @pytest.mark.asyncio
    async def test_second_failure_is_reported(self):
        bot = SimpleNamespace(send_message=AsyncMock(
            side_effect=_network_error(ConnectionResetError())))
        assert await send_to_user(bot, 1, "t") is False
        assert bot.send_message.await_count == 2


class TestCommentsBack:
    def _back(self, markup) -> str:
        return markup.inline_keyboard[-1][0].callback_data

    def test_default_back_is_generic_card(self):
        assert self._back(get_comments_list_keyboard(NUMBER, "ru")) == f"view_request_{NUMBER}"

    def test_back_follows_where_user_came_from(self):
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        from uk_management_bot.handlers.request_comments import _back_callback

        def card(back: str) -> InlineKeyboardMarkup:
            return InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="x", callback_data=f"view_comments_{NUMBER}")],
                [InlineKeyboardButton(text="copy", copy_text={"text": NUMBER})],
                [InlineKeyboardButton(text="back", callback_data=back)]])

        assert _back_callback(NUMBER, card("mreq_page_active_2")) == f"mview_{NUMBER}"
        assert _back_callback(NUMBER, card(f"mreq_back_{NUMBER}")) == f"mview_{NUMBER}"
        assert _back_callback(NUMBER, card("back_list_1")) is None
        assert _back_callback(NUMBER, None) is None
        # фильтр по типу внутри комментариев сохраняет выбранный возврат
        comments = get_comments_list_keyboard(NUMBER, "ru", f"mview_{NUMBER}")
        assert _back_callback(NUMBER, comments) == f"mview_{NUMBER}"
        assert self._back(comments) == f"mview_{NUMBER}"


@pytest.mark.asyncio
async def test_return_cancel_leaves_way_back_to_card():
    from uk_management_bot.handlers.admin import views

    callback = SimpleNamespace(data=f"rtw_cancel_{NUMBER}", message=SimpleNamespace(edit_text=AsyncMock()))
    state = SimpleNamespace(clear=AsyncMock())

    await views.handle_return_to_work_cancel(callback, state, language="ru")

    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert [b.callback_data for row in markup.inline_keyboard for b in row] == [f"mview_{NUMBER}"]


@pytest.mark.asyncio
async def test_comment_filter_with_same_result_is_not_an_error(monkeypatch):
    """Все комментарии одного типа → фильтр даёт тот же текст; «сообщение не
    изменено» раньше показывалось менеджеру как «Произошла ошибка»."""
    from aiogram.exceptions import TelegramBadRequest

    from uk_management_bot.handlers import request_comments as rc

    async def fake_run_db(fn, db=None):
        return "ok", SimpleNamespace(request_number=NUMBER, formatted_comments="текст")

    monkeypatch.setattr(rc, "run_db", fake_run_db)
    not_modified = TelegramBadRequest(
        method=SendMessage(chat_id=1, text="x"), message="Bad Request: message is not modified")
    callback = SimpleNamespace(
        data=f"view_comments_by_type_clarification_{NUMBER}",
        from_user=SimpleNamespace(id=1),
        message=SimpleNamespace(edit_text=AsyncMock(side_effect=not_modified), reply_markup=None),
        answer=AsyncMock())

    await rc.handle_view_comments_by_type(callback, SimpleNamespace(), language="ru")

    callback.answer.assert_awaited_once_with()
