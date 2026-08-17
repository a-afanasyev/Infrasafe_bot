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


def raw_specialization_tokens(raw) -> list[str]:
    """Разложить разнородное хранение в список сырых токенов (без нормализации).

    Публичная: по ней отличают «требования нет» от «требование есть, но не
    резолвится» (`matches_raw_requirement`), и по ней же показывают человеку
    то, что реально записано, когда канон ничего не узнал.
    """
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
    for token in raw_specialization_tokens(raw):
        if allow_universal and token.strip().lower() == UNIVERSAL_SPECIALIZATION:
            result.add(UNIVERSAL_SPECIALIZATION)
            continue
        result |= normalize_specialization(token, side=side)
    return result


def parse_specializations(user) -> set[str]:
    """Множество canonical-специализаций исполнителя (`User.specialization`).

    `universal` пропускаем: он живёт и на стороне ИСПОЛНИТЕЛЯ и означает
    «умеет всё» (`matches_required_specs`). Отбросив токен здесь, мы молча
    лишили бы универсалов работы.
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


def matches_required_specs(user_specs: set[str], required: set[str]) -> bool:
    """Единственный ответ проекта на «подходит ли исполнитель под требование».

    BUG-166: этот вопрос решался девятью разными способами — где-то нужны были
    ВСЕ специализации требования (`issubset`), где-то ЛЮБАЯ (`intersection`),
    а токен `universal` трактовался тремя способами сразу. Две проверки жили в
    одном файле (`handlers/shift_management/assignment_b.py`) и противоречили
    друг другу: список кандидатов предлагал исполнителя, а гвард назначения
    отказывал ему «отсутствуют специализации».

    Правила (решение владельца 2026-08-17):

    1. Пустое требование не ограничивает никого.
    2. `universal` в ТРЕБОВАНИИ = «подойдёт кто угодно».
    3. `universal` у ИСПОЛНИТЕЛЯ = «умеет всё».
    4. Иначе достаточно ОДНОГО совпадения: фокус смены — это «что смена
       покрывает», а не «чем один человек обязан владеть одновременно».
       Заявка и так попадает на смену, если её специализация ЕСТЬ в фокусе
       (`Shift.can_handle_specialization`), поэтому электрик на смене
       «электрика + сантехника» ведёт ровно электрические заявки.

    Оба множества обязаны быть УЖЕ каноническими: нормализация асимметрична по
    сторонам «умею»/«требуется» (см. `normalize_specialization`), и предикат не
    может выбрать сторону за вызывающего — для этого есть `parse_*`.
    """
    if not required:
        return True
    if UNIVERSAL_SPECIALIZATION in required:
        return True
    if UNIVERSAL_SPECIALIZATION in user_specs:
        return True
    return bool(required & user_specs)


def matches_raw_requirement(user_specs: set[str], raw_requirement) -> bool:
    """`matches_required_specs`, но требование берётся СЫРЫМ из БД.

    Единственное место, где решается разница между «требования нет» и
    «требование указано, но не резолвится в канон». Разница неочевидна и стоит
    дорого: если сравнивать с пустотой уже РАСПАРСЕННЫЙ набор, смена или
    шаблон с опечаткой в специализации молча становится «без ограничений» и
    начинает подходить всем. До перехода на канон сравнение шло по сырому
    списку, и такая строка не подходила никому.

    Поэтому здесь fail-closed: нераспознанное требование не пропускает никого.
    Записать его можно — валидатор канона стоит только на create-боди
    (`api/shifts/schemas.py`), PATCH пишет что дали.

    ⚠️ Миграция 010 для того же состояния данных выбрала ПРОТИВОПОЛОЖНОЕ:
    нерезолвимый фокус она записала как `NULL`, то есть «универсальная смена
    вместо не принимающей ничего». Противоречия нет: там разовое приведение
    существующих строк под присмотром, здесь — рантайм-вердикт по строке,
    которую менеджер видит в интерфейсе заполненной.
    """
    required = parse_specialization_values(
        raw_requirement, side="need", allow_universal=True)
    if required:
        return matches_required_specs(user_specs, required)
    return not raw_specialization_tokens(raw_requirement)


def has_required_specs(user, shift) -> bool:
    """Подходит ли исполнитель под требования смены (`specialization_focus`).

    Единый guard для переназначения смены (REG-02): sync-ядро бота и async-зеркало
    веба (`api/shifts`). Семантика — `matches_required_specs`.
    """
    return matches_raw_requirement(
        parse_specializations(user), getattr(shift, "specialization_focus", None))


def has_required_template_specs(user, template) -> bool:
    """То же для шаблона смены (`required_specializations`).

    Отдельная функция, а не флаг у `has_required_specs`: поле у шаблона
    называется иначе, и общий парсер читал бы у него пустоту — то есть «нет
    требований» вместо реальных.
    """
    return matches_raw_requirement(
        parse_specializations(user), getattr(template, "required_specializations", None))
