"""Пороги простоя и конфиг модуля «Лифты» (дефолты + глубокий merge с валидацией).

Конфиг хранится в ``elevators_config.data`` (JSON, одна строка); схему БД не
enforce-ит — её несёт ``merge_config``.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any

from ._core import ElevatorValidationError, require_aware
from .calendar_rules import DEFAULT_REMINDER_STAGES, validate_reminder_stages

# Статусы, по которым считается простой (для порогов напоминаний)
DOWNTIME_STATUSES: tuple[str, ...] = ("not_working", "under_repair")
MIN_THRESHOLD_DAYS, MAX_THRESHOLD_DAYS = 1, 365

_RESIDENT_NOTIFICATION_KEYS = ("repair_started", "maintenance_started", "back_in_service")
_STAFF_REMINDER_KINDS = ("maintenance", "certification", "contract")

DEFAULT_ELEVATORS_CONFIG: Mapping[str, Any] = MappingProxyType(
    {
        "module_public": False,
        "downtime_threshold_days": MappingProxyType({"not_working": 7, "under_repair": None}),
        "resident_notifications": MappingProxyType(
            {key: True for key in _RESIDENT_NOTIFICATION_KEYS}
        ),
        "staff_reminders": MappingProxyType(
            {
                **{kind: DEFAULT_REMINDER_STAGES for kind in _STAFF_REMINDER_KINDS},
                "overdue_weekly": True,
            }
        ),
    }
)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def downtime_threshold_reached(
    status: str,
    status_since: datetime | None,
    now: datetime,
    thresholds: Mapping[str, int | None],
) -> bool:
    """Достигнут ли порог простоя для напоминания персоналу.

    Пороги — дни по статусу (``{"not_working": 7, "under_repair": None}``);
    ``None``/отсутствие ключа = не напоминать. Для статусов вне
    ``DOWNTIME_STATUSES`` (``working``, ``maintenance``) всегда False.
    """
    require_aware(now, "now")
    if status not in DOWNTIME_STATUSES or status_since is None:
        return False
    threshold = thresholds.get(status)
    if threshold is None:
        return False
    require_aware(status_since, "status_since")
    return now - status_since >= timedelta(days=threshold)


# ===========================================================================
# merge_config
# ===========================================================================

def _thaw(value: Any) -> Any:
    """Глубокая копия в plain dict/list (JSON-совместимо, без MappingProxyType)."""
    if isinstance(value, Mapping):
        return {key: _thaw(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(inner) for inner in value]
    return value


def _deep_merge(base: dict[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    """Новый dict: словари сливаются рекурсивно, остальное (в т.ч. списки) заменяется."""
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = _thaw(value)
    return result


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ElevatorValidationError(f"{name}: ожидается объект")
    return value


def _require_bool(value: Any, name: str) -> None:
    if not isinstance(value, bool):
        raise ElevatorValidationError(f"{name}: ожидается true/false")


def _require_known_keys(section: Mapping[str, Any], allowed: Sequence[str], name: str) -> None:
    unknown = sorted(set(section) - set(allowed))
    if unknown:
        raise ElevatorValidationError(f"{name}: неизвестные ключи {', '.join(unknown)}")


def _validate_thresholds(section: Any) -> None:
    thresholds = _require_mapping(section, "downtime_threshold_days")
    _require_known_keys(thresholds, DOWNTIME_STATUSES, "downtime_threshold_days")
    for status, days in thresholds.items():
        if days is None:
            continue
        if not _is_int(days) or not MIN_THRESHOLD_DAYS <= days <= MAX_THRESHOLD_DAYS:
            raise ElevatorValidationError(
                f"downtime_threshold_days.{status}: целое {MIN_THRESHOLD_DAYS}..{MAX_THRESHOLD_DAYS} или null"
            )


def _validate_resident_notifications(section: Any) -> None:
    flags = _require_mapping(section, "resident_notifications")
    _require_known_keys(flags, _RESIDENT_NOTIFICATION_KEYS, "resident_notifications")
    for key, value in flags.items():
        _require_bool(value, f"resident_notifications.{key}")


def _validate_staff_reminders(section: Any) -> None:
    reminders = _require_mapping(section, "staff_reminders")
    _require_known_keys(
        reminders, (*_STAFF_REMINDER_KINDS, "overdue_weekly"), "staff_reminders"
    )
    for kind in _STAFF_REMINDER_KINDS:
        if kind in reminders:
            validate_reminder_stages(reminders[kind])
    if "overdue_weekly" in reminders:
        _require_bool(reminders["overdue_weekly"], "staff_reminders.overdue_weekly")


def _validate_config(config: Mapping[str, Any]) -> None:
    _require_known_keys(config, tuple(DEFAULT_ELEVATORS_CONFIG), "конфиг лифтов")
    _require_bool(config["module_public"], "module_public")
    _validate_thresholds(config["downtime_threshold_days"])
    _validate_resident_notifications(config["resident_notifications"])
    _validate_staff_reminders(config["staff_reminders"])


def merge_config(stored: Mapping[str, Any] | None, patch: Mapping[str, Any] | None) -> dict[str, Any]:
    """Конфиг = дефолты ← ``stored`` ← ``patch`` (глубокий merge) + валидация.

    Возвращает новый plain dict (JSON-совместимый), входы не мутируются.
    Пороги — int 1..365 или null; стадии — строго убывающие int ≤ 365;
    флаги — bool; неизвестные ключи запрещены → ``ElevatorValidationError``.
    """
    result = _thaw(DEFAULT_ELEVATORS_CONFIG)
    for layer, name in ((stored, "stored"), (patch, "patch")):
        if layer is not None:
            result = _deep_merge(result, _require_mapping(layer, name))
    _validate_config(result)
    return result
