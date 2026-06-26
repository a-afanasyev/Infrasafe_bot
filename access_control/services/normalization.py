"""Нормализация номеров (§12). Чистая, легко тестируемая функция.

Возвращает иммутабельный ``NormalizedPlate`` с четырьмя полями (§12):
``normalized``, ``recognition_key``, ``country``, ``type``.

Инварианты §12:
* удаляются пробелы и допустимые разделители; буквы — в верхний регистр;
* применяется профиль страны (пилот: UZ + generic);
* кириллические/латинские омоглифы и пары ``O/0``, ``I/1`` НЕ сливаются в
  ``normalized`` (каноническом номере) — скрипт символа сохраняется. Они
  объединяются ТОЛЬКО в ``recognition_key`` для поиска кандидатов (без
  молчаливого слияния и без авто-allow по fuzzy — §12, решение CTO #2).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Профиль страны по умолчанию для пилота (синтетические UZ-номера).
DEFAULT_COUNTRY = "UZ"

# Допустимые разделители, удаляемые из номера (пробелы, дефис, точка, и т.п.).
_SEPARATORS = re.compile(r"[\s\-_.·•]+")

# Кириллические омоглифы → латинские визуальные двойники. Только для
# recognition_key: в normalized кириллица остаётся кириллицей (§12).
_CYRILLIC_TO_LATIN = {
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H",
    "О": "O", "Р": "P", "С": "C", "Т": "T", "У": "Y", "Х": "X",
}

# Складывание пар буква/цифра в каноническую цифру для recognition_key.
# §12 называет именно пары O/0 и I/1 — держим перечень минимальным, чтобы не
# объединять различимые номера сверх требуемого.
_LOOKALIKE_FOLD = {"O": "0", "I": "1"}


@dataclass(frozen=True)
class NormalizedPlate:
    """Результат нормализации номера (§12). Иммутабельный DTO."""

    original: str
    normalized: str
    recognition_key: str
    country: str
    type: str


def _strip_and_upper(value: str) -> str:
    """Убрать разделители, нормализовать Unicode (NFC) и привести к верхнему регистру."""
    nfc = unicodedata.normalize("NFC", value)
    without_sep = _SEPARATORS.sub("", nfc)
    return without_sep.upper()


def _detect_type(normalized: str, country: str) -> str:
    """Определить тип номера по эвристике профиля (§12: обычный/транзит/дипл./иностр.).

    Для пилота достаточно грубой классификации; точные профили вводятся при
    подключении реальных иностранных/транзитных номеров (§17, риск).
    """
    if not normalized:
        return "unknown"
    if country != DEFAULT_COUNTRY:
        return "foreign"
    # UZ-транзит: префикс T; дипломатические серии — отдельный профиль (позже).
    if normalized.startswith("T") and any(ch.isdigit() for ch in normalized):
        return "transit"
    return "standard"


def _recognition_key(normalized: str) -> str:
    """Свернуть омоглифы и пары O/0, I/1 в стабильный ключ поиска кандидатов (§12).

    Кириллица → латиница → складывание визуальных двойников букв в цифры. Это
    ТОЛЬКО для поиска: ``normalized`` сохраняет исходный скрипт и буквы.
    """
    out: list[str] = []
    for ch in normalized:
        latin = _CYRILLIC_TO_LATIN.get(ch, ch)
        out.append(_LOOKALIKE_FOLD.get(latin, latin))
    return "".join(out)


def normalize_plate(
    plate_number_original: str, country: str | None = None
) -> NormalizedPlate:
    """Нормализовать номер (§12).

    Args:
        plate_number_original: исходный номер с камеры/ввода.
        country: код страны; ``None`` → профиль пилота по умолчанию (UZ).

    Returns:
        NormalizedPlate: канонический ``normalized`` (скрипт сохранён),
        ``recognition_key`` (омоглифы свёрнуты), ``country`` и ``type``.
    """
    resolved_country = country or DEFAULT_COUNTRY
    normalized = _strip_and_upper(plate_number_original or "")
    recognition_key = _recognition_key(normalized)
    plate_type = _detect_type(normalized, resolved_country)
    return NormalizedPlate(
        original=plate_number_original,
        normalized=normalized,
        recognition_key=recognition_key,
        country=resolved_country,
        type=plate_type,
    )
