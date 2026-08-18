"""Shift-management handlers — cross-cutting shared layer.

Helpers and the specialization-label map used across the split
shift_management/ submodules. The Router lives in _router.py.
"""


from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from uk_management_bot.constants.specializations import (
    CANONICAL_SPECIALIZATIONS,
    UNIVERSAL_SPECIALIZATION,
    normalize_specialization,
)
from uk_management_bot.database.session import session_scope
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.business_time import business_date_of, fmt_time


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

    ARCH-116: и время, и переход через полночь считаются в бизнес-зоне. По UTC-дате
    смена 01:00→09:00 по Ташкенту получала ложный '+1' (её UTC-даты разные), то
    есть подпись сообщала о переходе, которого пользователь не видит.
    """
    if not end_dt:
        return "—"
    label = fmt_time(end_dt)
    if start_dt:
        days = (business_date_of(end_dt) - business_date_of(start_dt)).days
        if days > 0:
            label += f" +{days}"
    return label


# BUG-169: здесь стоял СВОЙ словарь переводов на legacy-наборе (`electric`,
# `plumbing`, `hvac`, `maintenance`). Шести из девяти канонических позиций в нём
# не было вовсе, а после миграции 010 в БД лежит именно канон — `get(spec, spec)`
# отдавал менеджеру сырой `electrician` в списках смен, карточке назначения и
# аналитике. Дефект был живым на обоих продах.
#
# Второй словарь не нужен изначально: локали бота уже несут блок
# `specializations.*` на весь канон в ru и uz, и он же питает клавиатуры выдачи
# специализаций. Один источник названий — бот и дашборд расходиться не могут.
_SPECIALIZATION_ORDER = {spec: idx for idx, spec in enumerate(CANONICAL_SPECIALIZATIONS)}


def _specialization_label(token: str, language: str) -> str:
    """Название позиции по канон-токену.

    ⚠️ `get_text` на отсутствующем ключе возвращает САМ КЛЮЧ, а не пустую
    строку — без этой проверки менеджер увидел бы `specializations.elevator`,
    что не лучше сырого токена. Ратчет
    `tests/test_bug169_specialization_display.py` держит канон переведённым в
    обоих языках, здесь же — страховка на случай гонки «канон вырос, локаль нет».
    """
    key = f"specializations.{token}"
    label = get_text(key, language=language)
    return token if label == key else label


def translate_specializations(specializations: list, language: str = "ru") -> str:
    """Человеческие названия специализаций через локали бота.

    Нормализация делает вывод устойчивым к тому, что реально лежит в строках:
    legacy-токен (`electric`), канон (`electrician`) и мусор с регистром и
    пробелами приходят из одних и тех же полей. `hvac` разворачивается в две
    позиции — это сторона «умею», где расширение безопасно (см.
    `constants/specializations.normalize_specialization`).

    Неизвестный токен показывается КАК ЕСТЬ (прежнее поведение `get(spec, spec)`):
    подменить его на «Любая» значило бы выдать нераспознанное значение за
    универсальную смену.
    """
    if not specializations:
        return get_text("shift_management.any_specialization", language=language)

    labels: list[str] = []
    seen: set[str] = set()

    for raw in specializations:
        canon = sorted(
            normalize_specialization(raw, side="have"),
            key=_SPECIALIZATION_ORDER.__getitem__,
        )
        if canon:
            for token in canon:
                if token not in seen:
                    seen.add(token)
                    labels.append(_specialization_label(token, language))
            continue

        # Вне канона: wildcard смены — со своим названием, всё прочее — как есть.
        token = raw.strip().lower() if isinstance(raw, str) else str(raw)
        if token == UNIVERSAL_SPECIALIZATION:
            if token not in seen:
                seen.add(token)
                labels.append(_specialization_label(token, language))
        elif str(raw) not in seen:
            seen.add(str(raw))
            labels.append(str(raw))

    return ", ".join(labels)


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
