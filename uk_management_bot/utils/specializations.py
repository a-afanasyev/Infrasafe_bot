"""Единый парсер специализаций исполнителя.

`User.specialization` исторически хранится разнородно: JSON-список
(`'["plumber","electric"]'`), CSV (`'plumber,electric'`) либо скаляр-строка
(`'plumber'`). Раньше парсинг дублировался по нескольким местам и местами был
хрупким (substring-поиск по JSON-тексту). Эта функция — единый канонический
парсер; используется и в snapshot-раннере (ActorContext.specializations), и в
пул-запросе/автоназначении.
"""

from __future__ import annotations

import json


def parse_specializations(user) -> set[str]:
    """Множество canonical-специализаций исполнителя (без пустых значений)."""
    raw = getattr(user, "specialization", None)
    if not raw:
        return set()
    if isinstance(raw, (list, tuple, set)):
        return {str(s).strip() for s in raw if str(s).strip()}
    if not isinstance(raw, str):
        text = str(raw).strip()
        return {text} if text else set()
    text = raw.strip()
    if not text:
        return set()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return {str(s).strip() for s in parsed if str(s).strip()}
        except (json.JSONDecodeError, TypeError):
            pass
    # CSV или скаляр
    return {part.strip() for part in text.split(",") if part.strip()}


def parse_shift_specs(shift) -> set[str]:
    """Множество требуемых специализаций смены (``Shift.specialization_focus``).

    Хранится разнородно (JSON-список / список / скаляр), как и у пользователя —
    разбираем тем же каноном.
    """
    raw = getattr(shift, "specialization_focus", None)
    if not raw:
        return set()
    if isinstance(raw, (list, tuple, set)):
        return {str(s).strip() for s in raw if str(s).strip()}
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return set()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return {str(s).strip() for s in parsed if str(s).strip()}
            except (json.JSONDecodeError, TypeError):
                pass
        return {part.strip() for part in text.split(",") if part.strip()}
    text = str(raw).strip()
    return {text} if text else set()


def has_required_specs(user, shift) -> bool:
    """True, если у исполнителя есть ВСЕ требуемые сменой специализации.

    Единый guard для переназначения смены (REG-02): sync-ядро бота и async-зеркало
    веба (`api/shifts`). Смена без указанных спецификаций — без ограничений.
    Зеркалит инлайн-проверку `handlers/shift_management.py` (КРИТИЧЕСКАЯ ПРОВЕРКА
    СООТВЕТСТВИЯ СПЕЦИАЛИЗАЦИЙ), но через канонические парсеры.
    """
    required = parse_shift_specs(shift)
    if not required:
        return True
    return required.issubset(parse_specializations(user))
