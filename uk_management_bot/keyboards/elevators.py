"""Клавиатуры модуля «Лифты» в боте (Ф4a-2, T7).

Три поверхности: выбор лифта дома жителем (``elv:pick:{id}``), вопрос «лифт
сейчас работает?» (``elv:op:1|0``) и подсказка менеджеру о статусе после
подтверждения заявки (``elv:st:{elevator_id}:{status}:{номер заявки}`` +
``elv:keep``). Префиксы короткие — бюджет callback_data 64 байта; самый длинный
``elv:st:1234567:under_repair:260905-1234`` укладывается с запасом.

Подписи статусов — только через ``services.elevator_service.status_label``
(одна локаль для бота и API).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from uk_management_bot.database.models.elevator import ELEVATOR_STATUSES
from uk_management_bot.services.elevator_service import status_label
from uk_management_bot.utils.helpers import get_text

PICK_PREFIX = "elv:pick:"
OPERATIONAL_PREFIX = "elv:op:"
STATUS_PREFIX = "elv:st:"
KEEP_CALLBACK = "elv:keep"
CANCEL_CREATE_CALLBACK = "cancel_create"  # хендлер — requests/create_callbacks.py
# Групповой приём (Ф4b): те же кнопки под корневым фильтром ``gint:`` роутера
# group_intake, без ряда «Отмена» (в группе отмены нет — есть таймаут).
GROUP_PICK_PREFIX = "gint:elv:"
GROUP_OPERATIONAL_PREFIX = "gint:op:"


class ElevatorChoice(Protocol):
    """Минимум, который нужен клавиатуре от DTO лифта (ORM за run_db не выходит)."""

    id: int
    entrance: int
    number: int


def _cancel_row(language: str) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(
        text=get_text("buttons.cancel", language=language), callback_data=CANCEL_CREATE_CALLBACK,
    )]


def _pick_rows(
    options: Sequence[ElevatorChoice], language: str, prefix: str
) -> list[list[InlineKeyboardButton]]:
    """Кнопка на каждый введённый лифт дома: «Подъезд N · лифт M»."""
    return [
        [InlineKeyboardButton(
            text=get_text("requests.elevator.pick_button", language=language,
                          entrance=option.entrance, elevator=option.number),
            callback_data=f"{prefix}{option.id}",
        )]
        for option in options
    ]


def _operational_row(language: str, prefix: str) -> list[InlineKeyboardButton]:
    """«Да, работает» / «Нет, не работает»."""
    return [
        InlineKeyboardButton(
            text=get_text("requests.elevator.operational_yes_button", language=language),
            callback_data=f"{prefix}1",
        ),
        InlineKeyboardButton(
            text=get_text("requests.elevator.operational_no_button", language=language),
            callback_data=f"{prefix}0",
        ),
    ]


def build_elevator_pick_keyboard(
    options: Sequence[ElevatorChoice], language: str = "ru"
) -> InlineKeyboardMarkup:
    """Личный бот: лифты дома + отмена создания."""
    return InlineKeyboardMarkup(
        inline_keyboard=[*_pick_rows(options, language, PICK_PREFIX), _cancel_row(language)]
    )


def build_elevator_operational_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Личный бот: «Да, работает» / «Нет, не работает» + отмена создания."""
    return InlineKeyboardMarkup(inline_keyboard=[
        _operational_row(language, OPERATIONAL_PREFIX),
        _cancel_row(language),
    ])


def build_group_elevator_pick_keyboard(
    options: Sequence[ElevatorChoice], language: str = "ru"
) -> InlineKeyboardMarkup:
    """Групповой приём: лифты дома под ``gint:elv:{id}``, без отмены."""
    return InlineKeyboardMarkup(inline_keyboard=_pick_rows(options, language, GROUP_PICK_PREFIX))


def build_group_elevator_operational_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Групповой приём: «работает?» под ``gint:op:1|0``, без отмены."""
    return InlineKeyboardMarkup(
        inline_keyboard=[_operational_row(language, GROUP_OPERATIONAL_PREFIX)]
    )


def build_elevator_status_hint_keyboard(
    elevator_id: int, request_number: str, current_status: str | None, language: str = "ru"
) -> InlineKeyboardMarkup:
    """Четыре статуса (текущий помечен «• ») по два в ряд + «Оставить как есть»."""
    buttons = [
        InlineKeyboardButton(
            text=("• " if status == current_status else "") + status_label(status, language),
            callback_data=f"{STATUS_PREFIX}{elevator_id}:{status}:{request_number}",
        )
        for status in ELEVATOR_STATUSES
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(
        text=get_text("elevators.hint.keep_button", language=language), callback_data=KEEP_CALLBACK,
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)
