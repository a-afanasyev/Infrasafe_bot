"""Карточка лифта (Ф5, T10).

Подпись, статус и с какого времени, доступность 30 дней, ближайший planned-пункт
графика, число открытых заявок; кнопки — статус и ремонт (только у введённого
лифта), ТО (если planned-пункт в ближайшие ``DUE_SOON_DAYS``), назад к дому.
Общие хелперы — ``_common``.
"""

from __future__ import annotations

import re

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from uk_management_bot.database.session import run_db

from ._common import deny, edit_card, parse_int
from ._keyboards import CARD_PREFIX
from ._router import router

CARD_PATTERN = rf"^{re.escape(CARD_PREFIX)}(?P<id>\d+)$"
_CARD_RE = re.compile(CARD_PATTERN)


@router.callback_query(F.data.regexp(CARD_PATTERN))
async def handle_card(callback: CallbackQuery, state: FSMContext, language: str = "ru") -> None:
    """``elvm:card:{id}``: карточка лифта; текущий FSM-шаг лифтёра снимается."""
    match = _CARD_RE.match(callback.data or "")
    elevator_id = parse_int(match.group("id")) if match else None
    if elevator_id is None:
        await deny(callback, "error", language)
        return
    await state.clear()
    await edit_card(run_db, callback, elevator_id, language)
