"""Чистые валидаторы модуля «Лифты»: инвариант Р11, статус, паспорт, состояние.

Проверки, требующие запроса (лифт существует / активен / введён в
эксплуатацию), живут в обёртках T3 — здесь только данные на входе.
"""

from collections.abc import Mapping

from uk_management_bot.database.models.elevator import ELEVATOR_STATUSES

from ._core import (
    ELEVATOR_CATEGORY,
    ElevatorStateError,
    ElevatorValidationError,
    is_strict_int,
)

# Обязательные поля паспорта при создании лифта
PASSPORT_REQUIRED_FIELDS: tuple[str, ...] = (
    "passport_number",
    "manufacturer",
    "serial_number",
    "building_id",
    "entrance_number",
    "elevator_number",
)
# Поля паспорта, обязанные быть положительными int (bool не считается int)
_POSITIVE_INT_FIELDS: frozenset[str] = frozenset(
    {"building_id", "entrance_number", "elevator_number"}
)


def require_elevator_for_category(
    category: str | None,
    elevator_id: int | None,
    elevator_operational: bool | None,
    *,
    enabled: bool,
) -> None:
    """Инвариант Р11: заявка категории «лифт» обязана указывать лифт и его работоспособность.

    ``enabled=False`` (флаг ``ELEVATORS_ENABLED`` выключен) → no-op. Другая
    категория → no-op даже при заполненных полях: лифт у заявки иной
    категории допустим.
    """
    if not enabled or category != ELEVATOR_CATEGORY:
        return
    missing = [
        name
        for name, value in (
            ("elevator_id", elevator_id),
            ("elevator_operational", elevator_operational),
        )
        if value is None
    ]
    if missing:
        raise ElevatorValidationError(
            "для заявки категории «лифт» обязательны поля: " + ", ".join(missing)
        )


def validate_status(status: str) -> str:
    """Нормализовать (strip + lower) и проверить вхождение в ``ELEVATOR_STATUSES``."""
    if not isinstance(status, str):
        raise ElevatorValidationError(f"статус лифта должен быть строкой, получен {type(status).__name__}")
    normalized = status.strip().lower()
    if normalized not in ELEVATOR_STATUSES:
        raise ElevatorValidationError(
            f"неизвестный статус лифта {status!r}; допустимо: {', '.join(ELEVATOR_STATUSES)}"
        )
    return normalized


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_positive_int(value: object) -> bool:
    return is_strict_int(value) and value > 0  # type: ignore[operator]


def validate_passport_required(fields: Mapping[str, object]) -> None:
    """Проверить обязательные поля паспорта лифта.

    Отсутствие ключа / None / пустая строка / пробелы → в списке отсутствующих.
    ``building_id``, ``entrance_number``, ``elevator_number`` — положительные int.
    Одна ошибка со всеми проблемными полями сразу.
    """
    missing = [name for name in PASSPORT_REQUIRED_FIELDS if _is_blank(fields.get(name))]
    not_positive = [
        name
        for name in PASSPORT_REQUIRED_FIELDS
        if name in _POSITIVE_INT_FIELDS
        and name not in missing
        and not _is_positive_int(fields.get(name))
    ]
    problems = []
    if missing:
        problems.append("отсутствуют обязательные поля паспорта: " + ", ".join(missing))
    if not_positive:
        problems.append("должны быть положительными целыми: " + ", ".join(not_positive))
    if problems:
        raise ElevatorValidationError("; ".join(problems))


def can_set_status(new_status: str, *, is_commissioned: bool, archived: bool) -> None:
    """Допустима ли смена статуса по состоянию лифта.

    Архивный лифт → ``ElevatorStateError``. До ввода в эксплуатацию статус
    NULL и любая установка запрещена → ``ElevatorStateError``. Неизвестное имя
    статуса → ``ElevatorValidationError`` (см. ``validate_status``).
    """
    validate_status(new_status)
    if archived:
        raise ElevatorStateError("лифт архивирован: смена статуса недоступна")
    if not is_commissioned:
        raise ElevatorStateError(
            "лифт не введён в эксплуатацию: статус можно задать только после ввода"
        )
