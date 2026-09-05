"""Клавиатуры группового приёма: список вариантов по индексу.

Одна форма для выбора адреса staff-репорта (``gint:addr:<n>``) и дома для
заявки по лифту (``gint:bld:<n>``): callback несёт ИНДЕКС в серверном списке
кандидата, id объекта клиент не шлёт. Telegram ограничивает текст кнопки —
длинные подписи режутся с многоточием.
"""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

BTN_LABEL_LIMIT = 60


def clip_label(label: str) -> str:
    if len(label) <= BTN_LABEL_LIMIT:
        return label
    return label[: BTN_LABEL_LIMIT - 1] + "…"


def build_options_keyboard(options: Sequence[dict], prefix: str) -> InlineKeyboardMarkup:
    """Кнопка на вариант: текст — ``label_public``, callback — ``{prefix}{index}``."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=clip_label(option["label_public"]), callback_data=f"{prefix}{index}",
            )]
            for index, option in enumerate(options)
        ]
    )
