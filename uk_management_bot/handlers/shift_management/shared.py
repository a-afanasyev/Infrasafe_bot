"""Shift-management handlers — cross-cutting shared layer.

Helpers and the specialization-label map used across the split
shift_management/ submodules. The Router lives in _router.py.
"""


from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from uk_management_bot.database.session import session_scope
from uk_management_bot.utils.helpers import get_text


@contextmanager
def _db_scope(db):
    """Сессия для хендлера: инъецированная (владелец — вызывающий, НЕ закрываем
    здесь) либо свежая через ``session_scope()`` (закроется на выходе).

    CODE-04: заменяет ``db = next(get_db())`` + ``finally: db.close()``. Сохраняет
    seam внедрения ``db`` в тестах (близкий к исходному: переданный db не трогаем,
    а если db нет — берём и гарантированно закрываем).
    """
    if db is not None:
        yield db
    else:
        with session_scope() as scoped:
            yield scoped


def _format_end_label(start_dt: Optional[datetime], end_dt: Optional[datetime]) -> str:
    """Время конца смены 'ЧЧ:ММ'; добавляет '+N', если смена переходит на
    следующий день(и) (например суточная 08:00→08:00 показывается как '08:00 +1').

    start_dt и end_dt должны быть в одной таймзоне (берутся из одной смены —
    start_time/end_time или planned_*), поэтому сравнение .date() согласовано.
    """
    if not end_dt:
        return "—"
    label = end_dt.strftime('%H:%M')
    if start_dt and end_dt.date() > start_dt.date():
        label += f" +{(end_dt.date() - start_dt.date()).days}"
    return label


# Словарь локализации специализаций
SPECIALIZATION_TRANSLATIONS = {
    "ru": {
        "electric": "Электрика",
        "plumbing": "Сантехника",
        "hvac": "Вентиляция",
        "security": "Охрана",
        "cleaning": "Уборка",
        "universal": "Универсальная",
        "carpentry": "Плотницкие работы",
        "painting": "Малярные работы",
        "landscaping": "Благоустройство",
        "maintenance": "Обслуживание",
        "it": "IT поддержка",
        "reception": "Ресепшн"
    },
    "uz": {
        "electric": "Elektr",
        "plumbing": "Santexnika",
        "hvac": "Ventilyatsiya",
        "security": "Xavfsizlik",
        "cleaning": "Tozalash",
        "universal": "Universal",
        "carpentry": "Duradgorlik",
        "painting": "Bo'yoqchilik",
        "landscaping": "Obodonlashtirish",
        "maintenance": "Texnik xizmat",
        "it": "IT qo'llab-quvvatlash",
        "reception": "Qabulxona"
    }
}

def translate_specializations(specializations: list, language: str = "ru") -> str:
    """Переводит список специализаций на указанный язык"""
    if not specializations:
        return get_text("shift_management.any_specialization", language=language)

    translations = SPECIALIZATION_TRANSLATIONS.get(language, SPECIALIZATION_TRANSLATIONS["ru"])
    translated = [translations.get(spec, spec) for spec in specializations]
    return ", ".join(translated)


def _get_confirm_keyboard(yes_callback: str, no_callback: str, lang: str) -> InlineKeyboardMarkup:
    """Inline keyboard with Yes/No buttons for destructive confirmation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=get_text("shift_planning.confirm_yes", language=lang),
                callback_data=yes_callback,
            ),
            InlineKeyboardButton(
                text=get_text("shift_planning.confirm_no", language=lang),
                callback_data=no_callback,
            ),
        ]
    ])
