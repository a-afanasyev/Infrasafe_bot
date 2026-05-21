"""
BUG-BOT-026: Локализованные имена месяцев для RU/UZ UI.

`datetime.strftime('%B')` использует системный локаль (обычно `C`/`en_US`),
давая `May 2026` в русском UI. Эта утилита читает массивы `months.<key>`
из i18n-файлов проекта, чтобы рендерить `Май 2026` / `May 2026` (uz).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Union

from uk_management_bot.utils.helpers import get_text


_MONTH_KEYS = (
    "january", "february", "march", "april",
    "may", "june", "july", "august",
    "september", "october", "november", "december",
)


def localized_month_name(month_index: int, language: str = "ru") -> str:
    """Возвращает локализованное имя месяца по индексу 1..12."""
    if not 1 <= month_index <= 12:
        raise ValueError(f"month_index must be 1..12, got {month_index}")
    key = _MONTH_KEYS[month_index - 1]
    return get_text(f"months.{key}", language=language)


def localized_month_year(dt: Union[date, datetime], language: str = "ru") -> str:
    """`date(2026, 5, 1)` + `ru` → `Май 2026`."""
    name = localized_month_name(dt.month, language=language)
    return f"{name} {dt.year}"
