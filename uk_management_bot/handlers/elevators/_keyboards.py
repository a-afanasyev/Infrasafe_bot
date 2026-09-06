"""Inline-клавиатуры бота лифтёра (Ф5, T10). Префикс callback — ``elvm:``.

``elv:*`` занят T7 (выбор лифта в заявке, подсказка менеджеру) — здесь своё
пространство: ``elvm:yards``, ``elvm:yard:{id}``, ``elvm:bld:{id}``,
``elvm:card:{id}``, ``elvm:st:{id}[:{status}]``, ``elvm:noreason``,
``elvm:cancel``, ``elvm:skip``, ``elvm:rep:{id}``, ``elvm:urg:{key}``,
``elvm:repst:{id}:{номер}:1|0``, ``elvm:occs:{id}``, ``elvm:occ:{oid}:done``.
Самый длинный — ``elvm:repst:1234567:260905-1234:1`` (34 байта) — в бюджете 64.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from uk_management_bot.database.models.elevator import ELEVATOR_STATUSES
from uk_management_bot.keyboards.requests import get_urgency_buttons_with_internal_keys
from uk_management_bot.services.elevator_service import status_label

from ._texts import elevator_button, occurrence_button, t
from ._units import BuildingRow, CardView, ElevatorRow, OccurrenceRow, YardRow

PREFIX = "elvm:"
YARDS_CB = PREFIX + "yards"
YARD_PREFIX = PREFIX + "yard:"
BUILDING_PREFIX = PREFIX + "bld:"
CARD_PREFIX = PREFIX + "card:"
STATUS_PREFIX = PREFIX + "st:"
NO_REASON_CB = PREFIX + "noreason"
CANCEL_CB = PREFIX + "cancel"
SKIP_CB = PREFIX + "skip"
REPAIR_PREFIX = PREFIX + "rep:"
URGENCY_PREFIX = PREFIX + "urg:"
REPAIR_STATUS_PREFIX = PREFIX + "repst:"
OCCURRENCES_PREFIX = PREFIX + "occs:"
OCCURRENCE_PREFIX = PREFIX + "occ:"
OCCURRENCE_DONE_SUFFIX = ":done"

Row = list[InlineKeyboardButton]


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _back_row(text: str, data: str) -> Row:
    return [_btn(text, data)]


def _cancel_row(language: str) -> Row:
    return [_btn(t("btn_cancel", language), CANCEL_CB)]


def yards_keyboard(yards: Sequence[YardRow], language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn(y.name, f"{YARD_PREFIX}{y.id}")] for y in yards]
    )


def buildings_keyboard(rows: Sequence[BuildingRow], language: str) -> InlineKeyboardMarkup:
    buttons = [
        [_btn(t("building_button", language, address=b.address, count=b.elevators),
              f"{BUILDING_PREFIX}{b.id}")]
        for b in rows
    ]
    buttons.append(_back_row(t("btn_yards", language), YARDS_CB))
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def elevators_keyboard(
    rows: Sequence[ElevatorRow], yard_id: int, language: str
) -> InlineKeyboardMarkup:
    buttons = [
        [_btn(elevator_button(e.entrance, e.number, e.status, language), f"{CARD_PREFIX}{e.id}")]
        for e in rows
    ]
    buttons.append(_back_row(t("btn_back", language), f"{YARD_PREFIX}{yard_id}"))
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def card_keyboard(view: CardView, language: str) -> InlineKeyboardMarkup:
    """Статус и ремонт — только у введённого лифта; ТО — при planned-пункте в ближайшие дни."""
    rows: list[Row] = []
    if view.is_commissioned:
        rows.append([_btn(t("btn_status", language), f"{STATUS_PREFIX}{view.id}")])
        rows.append([_btn(t("btn_repair", language), f"{REPAIR_PREFIX}{view.id}")])
    if view.can_complete:
        rows.append([_btn(t("btn_maintenance", language), f"{OCCURRENCES_PREFIX}{view.id}")])
    rows.append(_back_row(t("btn_back", language), f"{BUILDING_PREFIX}{view.building_id}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def statuses_keyboard(
    elevator_id: int, current: Optional[str], language: str
) -> InlineKeyboardMarkup:
    """Четыре статуса по два в ряд (текущий помечен «• ») + назад к карточке."""
    buttons = [
        _btn(("• " if status == current else "") + status_label(status, language),
             f"{STATUS_PREFIX}{elevator_id}:{status}")
        for status in ELEVATOR_STATUSES
    ]
    rows: list[Row] = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append(_back_row(t("btn_back", language), f"{CARD_PREFIX}{elevator_id}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reason_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(t("btn_no_reason", language), NO_REASON_CB)],
        _cancel_row(language),
    ])


def cancel_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[_cancel_row(language)])


def skip_cancel_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(t("btn_skip", language), SKIP_CB)],
        _cancel_row(language),
    ])


def urgency_keyboard(language: str) -> InlineKeyboardMarkup:
    """Канон срочности (``keyboards/requests``) под собственным префиксом ``elvm:urg:``."""
    rows: list[Row] = [
        [_btn(display, f"{URGENCY_PREFIX}{key}")]
        for display, key in get_urgency_buttons_with_internal_keys(language)
    ]
    rows.append(_cancel_row(language))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def repair_status_offer_keyboard(
    elevator_id: int, request_number: str, language: str
) -> InlineKeyboardMarkup:
    base = f"{REPAIR_STATUS_PREFIX}{elevator_id}:{request_number}:"
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn(t("btn_yes", language), base + "1"),
        _btn(t("btn_no", language), base + "0"),
    ]])


def occurrences_keyboard(
    elevator_id: int, rows: Sequence[OccurrenceRow], language: str
) -> InlineKeyboardMarkup:
    buttons = [
        [_btn(occurrence_button(o.kind, o.due_on, o.overdue, language),
              f"{OCCURRENCE_PREFIX}{o.id}{OCCURRENCE_DONE_SUFFIX}")]
        for o in rows
    ]
    buttons.append(_back_row(t("btn_back", language), f"{CARD_PREFIX}{elevator_id}"))
    return InlineKeyboardMarkup(inline_keyboard=buttons)
