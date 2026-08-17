"""Единый парсер специализаций — исполнителя, смены и шаблона смены.

Поля исторически хранятся разнородно: JSON-список (`'["plumber","electric"]'`),
CSV (`'plumber,electric'`) либо скаляр-строка (`'plumber'`). Раньше разбор
дублировался по нескольким местам и местами был хрупким (substring-поиск по
JSON-тексту).

Здесь же происходит нормализация к канону (`constants/specializations.py`):
сравнение специализаций строгое, поэтому legacy-токен вроде `electric` или
категорийный `maintenance` иначе не совпал бы ни с чем.
"""

from __future__ import annotations

import json

from uk_management_bot.constants.specializations import (
    UNIVERSAL_SPECIALIZATION,
    normalize_specialization,
)


def _raw_tokens(raw) -> list[str]:
    """Разложить разнородное хранение в список сырых токенов (без нормализации)."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(s).strip() for s in raw if str(s).strip()]
    if not isinstance(raw, str):
        text = str(raw).strip()
        return [text] if text else []
    text = raw.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(s).strip() for s in parsed if str(s).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
    # CSV или скаляр
    return [part.strip() for part in text.split(",") if part.strip()]


def parse_specialization_values(raw, *, side: str = "have",
                                allow_universal: bool = False) -> set[str]:
    """Канонические специализации из сырого значения любого из трёх полей.

    Args:
        side: ``"have"`` (навыки исполнителя) либо ``"need"`` (требование
            смены/шаблона). Влияет только на `hvac` — см. normalize_specialization.
        allow_universal: пропускать ли wildcard `universal` (смены и шаблоны —
            да, исполнитель — нет: это не навык).
    """
    result: set[str] = set()
    for token in _raw_tokens(raw):
        if allow_universal and token.strip().lower() == UNIVERSAL_SPECIALIZATION:
            result.add(UNIVERSAL_SPECIALIZATION)
            continue
        result |= normalize_specialization(token, side=side)
    return result


def parse_specializations(user) -> set[str]:
    """Множество canonical-специализаций исполнителя (`User.specialization`).

    `universal` пропускаем: в этом проекте он живёт и на стороне ИСПОЛНИТЕЛЯ —
    `shift_planning_service` считает такого работника подходящим под любой
    шаблон. Отбросив токен, мы молча лишили бы универсалов работы. Семантику
    не трогаем (BUG-166), только доносим значение до потребителя.
    """
    return parse_specialization_values(
        getattr(user, "specialization", None), side="have", allow_universal=True)


def parse_shift_specs(shift) -> set[str]:
    """Требуемые специализации смены (`Shift.specialization_focus`)."""
    return parse_specialization_values(
        getattr(shift, "specialization_focus", None),
        side="need", allow_universal=True)


def parse_template_specs(template) -> set[str]:
    """Требуемые специализации шаблона (`ShiftTemplate.required_specializations`).

    Отдельная функция, а не переиспользование `parse_shift_specs`: поле у
    шаблона называется иначе, и общий парсер читал бы у него пустоту.
    """
    return parse_specialization_values(
        getattr(template, "required_specializations", None),
        side="need", allow_universal=True)


def has_required_specs(user, shift) -> bool:
    """True, если у исполнителя есть ВСЕ требуемые сменой специализации.

    Единый guard для переназначения смены (REG-02): sync-ядро бота и async-зеркало
    веба (`api/shifts`). Смена без указанных спецификаций — без ограничений.

    ⚠️ Семантика «ВСЕ» (issubset) сохранена байт-в-байт: в проекте она расходится
    с ANY-семантикой `shift_planning_service` (BUG-166). Приводить их к одной
    здесь нельзя — это меняет, кого назначают на смены.

    ⚠️ Токен `universal` в требовании смены НЕ трактуется как «подходит любой»,
    хотя `Shift.can_handle_specialization` и `smart_dispatcher` делают именно
    так. Расхождение реальное, но чинить его здесь нельзя: тогда перевод смены
    и авто-подбор разъедутся ещё сильнее — `scoring.py` и `planning.py` остались
    бы со старым поведением. Пункт BUG-166, чинить всем трём консьюмерам сразу.
    """
    required = parse_shift_specs(shift)
    if not required:
        return True
    return required.issubset(parse_specializations(user))
