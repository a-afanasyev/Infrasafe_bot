"""Выбор квартиры при регистрации — постранично (2026-11-03, profk дом 17).

Telegram отклоняет inline-клавиатуру больше 100 кнопок («reply markup is too
long»): дома на 104/140 квартир (profk 1, 6, 17, 20, 21, 26) не открывались —
житель не мог выбрать квартиру.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uk_management_bot.handlers import user_apartment_selection as mod

TELEGRAM_MAX_BUTTONS = 100


def _building(n: int):
    return mod._BuildingApartments(
        address="ул. Тестовая, 17",
        apartments=tuple(
            mod._ApartmentOpt(id=1000 + i, apartment_number=str(i), floor=None, entrance=None)
            for i in range(1, n + 1)
        ),
    )


def _callback(data: str):
    cb = MagicMock()
    cb.data = data
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _state(building_id=17):
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"selected_building_id": building_id, "selected_yard_name": "Двор"})
    return state


def _markup(cb):
    return cb.message.edit_text.await_args.kwargs["reply_markup"]


def _page_markup(cb):
    """Листание меняет только клавиатуру — текст шага остаётся."""
    cb.message.edit_text.assert_not_awaited()
    return cb.message.edit_reply_markup.await_args.kwargs["reply_markup"]


def _buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


def _apartment_ids(markup):
    return [int(b.callback_data.split(":")[1]) for b in _buttons(markup)
            if b.callback_data.startswith("user_apartment_final:")]


@pytest.mark.asyncio
@pytest.mark.parametrize("n", [104, 140])
async def test_big_building_first_page_fits_telegram_limit(n):
    cb = _callback("user_apartment_building:17")
    with patch.object(mod, "_load_building_apartments", return_value=_building(n)):
        await mod.process_building_selection(cb, _state(), language="ru", _db=MagicMock())
    markup = _markup(cb)
    assert len(_buttons(markup)) <= TELEGRAM_MAX_BUTTONS
    assert _apartment_ids(markup) == list(range(1001, 1001 + mod.APARTMENT_PAGE_SIZE))
    assert "user_apartment_page:1" in [b.callback_data for b in _buttons(markup)]


@pytest.mark.asyncio
@pytest.mark.parametrize("n,page,first,last", [(140, 2, 1121, 1140), (104, 1, 1061, 1104)])
async def test_page_handler_shows_last_page_with_back_only(n, page, first, last):
    cb = _callback(f"user_apartment_page:{page}")
    with patch.object(mod, "_load_building_apartments", return_value=_building(n)):
        await mod.process_apartment_page(cb, _state(), language="ru", _db=MagicMock())
    markup = _page_markup(cb)
    assert _apartment_ids(markup) == list(range(first, last + 1))
    datas = [b.callback_data for b in _buttons(markup)]
    assert f"user_apartment_page:{page - 1}" in datas
    assert f"user_apartment_page:{page + 1}" not in datas
    cb.answer.assert_awaited()


def test_page_size_is_60():
    assert mod.APARTMENT_PAGE_SIZE == 60


@pytest.mark.asyncio
async def test_small_building_has_no_navigation():
    cb = _callback("user_apartment_building:17")
    with patch.object(mod, "_load_building_apartments", return_value=_building(30)):
        await mod.process_building_selection(cb, _state(), language="ru", _db=MagicMock())
    datas = [b.callback_data for b in _buttons(_markup(cb))]
    assert not [d for d in datas if d.startswith("user_apartment_page:")]
    assert len(_apartment_ids(_markup(cb))) == 30


@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["user_apartment_page:x", "user_apartment_page:٣", "user_apartment_page:"])
async def test_page_handler_rejects_bad_page(data):
    cb = _callback(data)
    with patch.object(mod, "_load_building_apartments", return_value=_building(140)) as load:
        await mod.process_apartment_page(cb, _state(), language="ru", _db=MagicMock())
    load.assert_not_called()
    cb.message.edit_reply_markup.assert_not_awaited()
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_page_handler_without_building_in_state_answers_not_found():
    cb = _callback("user_apartment_page:1")
    with patch.object(mod, "_load_building_apartments", return_value=_building(140)) as load:
        await mod.process_apartment_page(cb, _state(building_id=None), language="ru", _db=MagicMock())
    load.assert_not_called()
    cb.message.edit_reply_markup.assert_not_awaited()
    cb.answer.assert_awaited()
