"""Пороги простоя и конфиг модуля «Лифты» (дефолты + глубокий merge с валидацией).

Конфиг хранится в ``elevators_config.data`` (JSON, одна строка); схему БД не
enforce-ит — её несёт ``merge_config``. Сохранённый конфиг (``stored``)
терпим к неизвестным ключам (остатки старых версий отбрасываются, T3 логирует
их через ``unknown_config_keys``); патч от пользователя (``patch``) строгий.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any

from ._core import ElevatorValidationError, is_strict_int, require_aware
from .calendar_rules import DEFAULT_REMINDER_STAGES, validate_reminder_stages

# Статусы, по которым считается простой (для порогов напоминаний)
DOWNTIME_STATUSES: tuple[str, ...] = ("not_working", "under_repair")
MIN_THRESHOLD_DAYS, MAX_THRESHOLD_DAYS = 1, 365
# Конфиг — плоские секции; глубже 4 уровней = мусор/атака на рекурсию
MAX_CONFIG_DEPTH = 4

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


def downtime_threshold_reached(
    status: str,
    status_since: datetime | None,
    now: datetime,
    thresholds: Mapping[str, int | None],
) -> bool:
    """Достигнут ли порог простоя для напоминания персоналу.

    Пороги — дни по статусу (``{"not_working": 7, "under_repair": None}``);
    ``None``/отсутствие ключа = не напоминать; порог иного типа →
    ``ElevatorValidationError``. Для статусов вне ``DOWNTIME_STATUSES``
    (``working``, ``maintenance``) всегда False.
    """
    require_aware(now, "now")
    if status not in DOWNTIME_STATUSES or status_since is None:
        return False
    threshold = thresholds.get(status)
    if threshold is None:
        return False
    if not is_strict_int(threshold):
        raise ElevatorValidationError(f"порог простоя для {status!r}: ожидается целое или null")
    require_aware(status_since, "status_since")
    return now - status_since >= timedelta(days=threshold)


# ===========================================================================
# merge_config
# ===========================================================================

def _check_depth(depth: int) -> None:
    if depth > MAX_CONFIG_DEPTH:
        raise ElevatorValidationError("слишком глубокая вложенность конфига")


def _thaw(value: Any, depth: int = 1) -> Any:
    """Глубокая копия в plain dict/list (JSON-совместимо, без MappingProxyType)."""
    _check_depth(depth)
    if isinstance(value, Mapping):
        return {key: _thaw(inner, depth + 1) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(inner, depth + 1) for inner in value]
    return value


def _deep_merge(base: dict[str, Any], patch: Mapping[str, Any], depth: int = 1) -> dict[str, Any]:
    """Новый dict: словари сливаются рекурсивно, остальное (в т.ч. списки) заменяется."""
    _check_depth(depth)
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value, depth + 1)
        else:
            result[key] = _thaw(value, depth + 1)
    return result


def unknown_config_keys(stored: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Пути неизвестных ключей сохранённого конфига (``"key"`` / ``"section.key"``).

    Для логирования в T3: ``merge_config`` такие ключи из ``stored`` молча
    отбрасывает.
    """
    if not isinstance(stored, Mapping):
        return ()
    paths: list[str] = []
    for key, value in stored.items():
        default = DEFAULT_ELEVATORS_CONFIG.get(key)
        if key not in DEFAULT_ELEVATORS_CONFIG:
            paths.append(str(key))
        elif isinstance(default, Mapping) and isinstance(value, Mapping):
            paths.extend(f"{key}.{inner}" for inner in value if inner not in default)
    return tuple(paths)


def _prune_unknown(stored: Mapping[str, Any]) -> dict[str, Any]:
    """Новый dict без неизвестных ключей (top-level и внутри известных секций)."""
    pruned: dict[str, Any] = {}
    for key, value in stored.items():
        default = DEFAULT_ELEVATORS_CONFIG.get(key)
        if key not in DEFAULT_ELEVATORS_CONFIG:
            continue
        if isinstance(default, Mapping) and isinstance(value, Mapping):
            pruned[key] = {inner: v for inner, v in value.items() if inner in default}
        else:
            pruned[key] = value
    return pruned


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ElevatorValidationError(f"{name}: ожидается объект")
    return value


def _require_bool(value: Any, name: str) -> None:
    if not isinstance(value, bool):
        raise ElevatorValidationError(f"{name}: ожидается true/false")


def _require_known_keys(section: Mapping[str, Any], allowed: Sequence[str], name: str) -> None:
    unknown = sorted(str(key) for key in set(section) - set(allowed))
    if unknown:
        raise ElevatorValidationError(f"{name}: неизвестные ключи {', '.join(unknown)}")


def _validate_thresholds(section: Any) -> None:
    thresholds = _require_mapping(section, "downtime_threshold_days")
    _require_known_keys(thresholds, DOWNTIME_STATUSES, "downtime_threshold_days")
    for status, days in thresholds.items():
        if days is None:
            continue
        if not is_strict_int(days) or not MIN_THRESHOLD_DAYS <= days <= MAX_THRESHOLD_DAYS:
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

    ``stored`` терпимый: неизвестные ключи (top-level и внутри секций)
    отбрасываются (см. ``unknown_config_keys``), невалидные значения →
    ``ElevatorValidationError``. ``patch`` строгий: неизвестные ключи и
    невалидные значения → ``ElevatorValidationError``. Пороги — int 1..365
    или null; стадии — строго убывающие int ≤ 365; флаги — bool; вложенность
    глубже ``MAX_CONFIG_DEPTH`` запрещена. Возвращает новый plain dict
    (JSON-совместимый), входы не мутируются.
    """
    result = _thaw(DEFAULT_ELEVATORS_CONFIG)
    if stored is not None:
        result = _deep_merge(result, _prune_unknown(_require_mapping(stored, "stored")))
        _validate_config(result)
    if patch is not None:
        result = _deep_merge(result, _require_mapping(patch, "patch"))
        _validate_config(result)
    return result
