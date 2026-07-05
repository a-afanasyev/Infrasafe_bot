"""Клавиатуры списания материалов (складской учёт).

Инлайн-список активных материалов с остатком > 0, пагинация 8/страницу
(паттерн keyboards/requests.py::get_pagination_keyboard).
"""
from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from uk_management_bot.utils.helpers import get_text

MATERIALS_PER_PAGE = 8


def unit_label(unit: str, language: str = "ru") -> str:
    """Локализованная подпись канон-единицы ('m' → 'м')."""
    return get_text(f"materials.units.{unit}", language=language)


def _fmt_qty(qty: Decimal) -> str:
    """Количество без хвостовых нулей (10.500 → 10.5, 3.000 → 3)."""
    text = f"{qty.normalize():f}"
    return text


def get_material_list_keyboard(materials: list[dict], page: int = 1,
                               language: str = "ru") -> InlineKeyboardMarkup:
    """Список материалов «Название — остаток ед» + пагинация + отмена.

    Args:
        materials: [{id, name, unit, stock(Decimal)}, ...] — уже с остатком > 0.
        page: страница (с 1).
    """
    total_pages = max(1, (len(materials) + MATERIALS_PER_PAGE - 1) // MATERIALS_PER_PAGE)
    page = min(max(1, page), total_pages)
    start = (page - 1) * MATERIALS_PER_PAGE

    keyboard = [
        [InlineKeyboardButton(
            text=f"{m['name']} — {_fmt_qty(m['stock'])} {unit_label(m['unit'], language)}",
            callback_data=f"matpick_{m['id']}",
        )]
        for m in materials[start:start + MATERIALS_PER_PAGE]
    ]

    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"matpage_{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}",
                                        callback_data="matpage_current"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"matpage_{page + 1}"))
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton(
        text=get_text("buttons.cancel", language=language),
        callback_data="matcancel",
    )])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_material_confirm_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Подтверждение списания."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=get_text("buttons.confirm", language=language),
            callback_data="matconfirm",
        )],
        [InlineKeyboardButton(
            text=get_text("buttons.cancel", language=language),
            callback_data="matcancel",
        )],
    ])
