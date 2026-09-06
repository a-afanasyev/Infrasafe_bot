"""Меню «🛗 Лифты» лифтёра: вход и навигация двор → дом → лифты (Ф5, T10).

Кнопка меню видна всем executor (``keyboards/base.py``); гейт по специализации
«лифты» стоит в юните (``_units.check_access``) — отказ внятный, не тишина.
Здесь же ``elvm:cancel`` — общий выход из текстовых шагов FSM пакета.
"""

from __future__ import annotations

import logging
import re

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from uk_management_bot.database.session import run_db
from uk_management_bot.utils.button_texts import get_elevators_texts

from . import _common
from ._keyboards import (
    BUILDING_PREFIX,
    CANCEL_CB,
    YARD_PREFIX,
    YARDS_CB,
    buildings_keyboard,
    elevators_keyboard,
    yards_keyboard,
)
from ._router import router
from ._texts import buildings_title, deny_text, elevators_title, t
from ._units import OK, YardsView, load_buildings, load_elevators, load_yards

logger = logging.getLogger(__name__)

ELEVATORS_TEXTS = get_elevators_texts()
_YARD_RE = re.compile(rf"^{re.escape(YARD_PREFIX)}(?P<id>\d+)$")
_BUILDING_RE = re.compile(rf"^{re.escape(BUILDING_PREFIX)}(?P<id>\d+)$")


async def _load_yards(telegram_id: int) -> YardsView:
    view = await _common.run_unit(run_db, lambda s: load_yards(s, telegram_id), "список дворов")
    return view if view is not None else YardsView("error")


def _yards_text(view: YardsView, language: str) -> str:
    return t("yards_title", language) if view.yards else t("no_yards", language)


@router.message(F.text.in_(ELEVATORS_TEXTS))
async def handle_elevators_button(message: Message, state: FSMContext, language: str = "ru") -> None:
    """Reply-кнопка «🛗 Лифты»: гейт по специализации, затем активные дворы."""
    view = await _load_yards(message.from_user.id)
    if view.verdict != OK:
        await message.answer(deny_text(view.verdict, language))
        return
    await state.clear()
    await message.answer(_yards_text(view, language), reply_markup=yards_keyboard(view.yards, language),
                         parse_mode="HTML")


@router.callback_query(F.data == YARDS_CB)
async def handle_yards(callback: CallbackQuery, state: FSMContext, language: str = "ru") -> None:
    """``elvm:yards``: назад к списку дворов."""
    view = await _load_yards(callback.from_user.id)
    if view.verdict != OK:
        await _common.deny(callback, view.verdict, language)
        return
    await state.clear()
    await _common.edit(callback, _yards_text(view, language), yards_keyboard(view.yards, language))


@router.callback_query(F.data.regexp(_YARD_RE.pattern))
async def handle_yard(callback: CallbackQuery, language: str = "ru") -> None:
    """``elvm:yard:{id}``: дома двора с числом лифтов."""
    match = _YARD_RE.match(callback.data or "")
    yard_id = _common.parse_int(match.group("id")) if match else None
    if yard_id is None:
        await _common.deny(callback, "error", language)
        return
    view = await _common.run_unit(
        run_db, lambda s: load_buildings(s, callback.from_user.id, yard_id), "дома двора")
    if view is None or view.verdict != OK:
        await _common.deny(callback, view.verdict if view else "error", language)
        return
    text = buildings_title(view, language) if view.buildings else t("no_buildings", language)
    await _common.edit(callback, text, buildings_keyboard(view.buildings, language))


@router.callback_query(F.data.regexp(_BUILDING_RE.pattern))
async def handle_building(callback: CallbackQuery, language: str = "ru") -> None:
    """``elvm:bld:{id}``: лифты дома с эмодзи статуса."""
    match = _BUILDING_RE.match(callback.data or "")
    building_id = _common.parse_int(match.group("id")) if match else None
    if building_id is None:
        await _common.deny(callback, "error", language)
        return
    view = await _common.run_unit(
        run_db, lambda s: load_elevators(s, callback.from_user.id, building_id), "лифты дома")
    if view is None or view.verdict != OK:
        await _common.deny(callback, view.verdict if view else "error", language)
        return
    text = elevators_title(view, language) if view.elevators else t("no_elevators", language)
    await _common.edit(callback, text, elevators_keyboard(view.elevators, view.yard_id, language))


@router.callback_query(F.data == CANCEL_CB)
async def handle_cancel(callback: CallbackQuery, state: FSMContext, language: str = "ru") -> None:
    """``elvm:cancel``: снять шаг FSM и вернуться к карточке лифта (если он известен)."""
    data = await state.get_data()
    await state.clear()
    await _common.cancelled(callback, language)
    elevator_id = data.get("elvm_elevator_id")
    if elevator_id is not None:
        await _common.answer_card(run_db, callback.message, callback.from_user.id, int(elevator_id), language)
