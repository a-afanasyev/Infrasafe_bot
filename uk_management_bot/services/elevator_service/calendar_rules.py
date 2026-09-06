"""Календарные правила графика ТО/освидетельствований и стадии напоминаний.

Все функции принимают ``today``/``now`` параметром — часы не читаются
(бизнес-дата приходит из ``utils/business_time.business_today`` в обёртках).

Стадия напоминания хранится в ДНЯХ последней отправленной стадии
(``*_reminder_stage``: 0 = ничего не отправлено, 30/14/7 = «за N дней»),
а не индексом в списке: список стадий менеджер может менять в конфиге, и
сохранённое значение обязано пережить сжатие/расширение списка.
"""

from calendar import monthrange
from collections.abc import Sequence
from datetime import date, datetime, timedelta

from uk_management_bot.database.models.elevator import OCCURRENCE_STATES

from ._core import (
    ElevatorStateError,
    ElevatorValidationError,
    is_strict_int,
    require_aware,
)

# Диапазоны генератора графика
MIN_EVERY_MONTHS, MAX_EVERY_MONTHS = 1, 24
MIN_OCCURRENCE_COUNT, MAX_OCCURRENCE_COUNT = 1, 36
# Стадии напоминаний по умолчанию: за 30 / 14 / 7 дней до срока
DEFAULT_REMINDER_STAGES: tuple[int, ...] = (30, 14, 7)
MAX_STAGE_DAYS = 365
# Состояния записи графика, закрытые для правок
_FROZEN_STATES = frozenset({"done", "cancelled"})


def _require_int_in_range(value: int, lo: int, hi: int, name: str) -> None:
    if not is_strict_int(value) or not lo <= value <= hi:
        raise ElevatorValidationError(f"{name} должен быть целым в диапазоне {lo}..{hi}")


def _add_months(start: date, months: int) -> date:
    """Сдвинуть дату на ``months`` месяцев; день обрезается по длине месяца."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, monthrange(year, month)[1])
    return date(year, month, day)


def generate_occurrence_dates(start: date, every_months: int, count: int) -> tuple[date, ...]:
    """Даты графика: ``start`` включительно, далее с шагом ``every_months``.

    День исходной даты сохраняется и обрезается по концу месяца без
    накопления (31 янв → 28/29 фев → 31 мар). ``every_months`` 1..24,
    ``count`` 1..36, иначе ``ElevatorValidationError``.
    """
    _require_int_in_range(every_months, MIN_EVERY_MONTHS, MAX_EVERY_MONTHS, "every_months")
    _require_int_in_range(count, MIN_OCCURRENCE_COUNT, MAX_OCCURRENCE_COUNT, "count")
    return tuple(_add_months(start, index * every_months) for index in range(count))


def assert_occurrence_editable(state: str) -> None:
    """``done`` и ``cancelled`` неизменяемы → ``ElevatorStateError``; неизвестное
    состояние → ``ElevatorValidationError``."""
    if state not in OCCURRENCE_STATES:
        raise ElevatorValidationError(f"неизвестное состояние записи графика {state!r}")
    if state in _FROZEN_STATES:
        raise ElevatorStateError(f"запись графика в состоянии {state!r} не редактируется")


def validate_reminder_stages(stages: Sequence[int]) -> tuple[int, ...]:
    """Стадии — непустая строго убывающая последовательность int 1..365.

    Принимается любая ``Sequence`` (list/tuple/range…), кроме ``str``/``bytes``.
    """
    if isinstance(stages, (str, bytes)) or not isinstance(stages, Sequence):
        raise ElevatorValidationError("стадии напоминаний: ожидается список дней")
    values = tuple(stages)
    if not values:
        raise ElevatorValidationError("стадии напоминаний: нужен непустой список дней")
    if not all(is_strict_int(v) and 1 <= v <= MAX_STAGE_DAYS for v in values):
        raise ElevatorValidationError(f"стадии напоминаний: целые дни 1..{MAX_STAGE_DAYS}")
    if any(later >= earlier for earlier, later in zip(values, values[1:])):
        raise ElevatorValidationError("стадии напоминаний должны строго убывать (30, 14, 7)")
    return values


def next_reminder_stage(
    due_on: date,
    today: date,
    last_stage_days: int,
    stages: Sequence[int] = DEFAULT_REMINDER_STAGES,
) -> int | None:
    """Дни новой стадии напоминания или ``None``, если слать нечего.

    ``last_stage_days`` — дни последней отправленной стадии (0 = ничего).
    Возвращается ближайшая к сроку достигнутая стадия — минимальное ``d`` из
    ``stages`` с ``today >= due_on - d`` — если она строго меньше
    ``last_stage_days`` (или ничего ещё не слали). Пропущенные стадии
    схлопываются в одно сообщение (за 5 дней при 0 → 7). Значение
    ``last_stage_days`` вне текущего списка (60 после сжатия) — не ошибка:
    сравнение идёт по дням. После ``due_on`` стадий нет (``is_overdue``).
    """
    valid_stages = validate_reminder_stages(stages)
    if not is_strict_int(last_stage_days) or last_stage_days < 0:
        raise ElevatorValidationError("last_stage_days должен быть неотрицательным целым")
    if today > due_on:
        return None
    reached = [days for days in valid_stages if today >= due_on - timedelta(days=days)]
    if not reached:
        return None
    closest = min(reached)
    if last_stage_days == 0 or closest < last_stage_days:
        return closest
    return None


def is_overdue(due_on: date, today: date, grace_days: int = 7) -> bool:
    """Просрочено, если прошло больше ``grace_days`` после ``due_on`` (с 8-го дня)."""
    if not is_strict_int(grace_days) or grace_days < 0:
        raise ElevatorValidationError("grace_days должен быть неотрицательным целым")
    return (today - due_on).days > grace_days


def should_remind_overdue(
    last_reminded_at: datetime | None, now: datetime, period_days: int = 7
) -> bool:
    """Повтор напоминания о просрочке: никогда не слали → True, иначе раз в период."""
    if not is_strict_int(period_days) or period_days < 1:
        raise ElevatorValidationError("period_days должен быть положительным целым")
    require_aware(now, "now")
    if last_reminded_at is None:
        return True
    require_aware(last_reminded_at, "last_reminded_at")
    return now - last_reminded_at >= timedelta(days=period_days)
