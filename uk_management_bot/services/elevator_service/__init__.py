"""Сервис модуля «Лифты»: реестр, журнал статусов, график ТО, напоминания.

Паттерн material_service: чистое ядро (валидаторы, доступность, календарь,
правила напоминаний, конфиг) + тонкие sync/async-обёртки с БД (T3).
В этом пакете (Ф2a) — только чистые функции без сессий и сети.

Инварианты (см. модели database/models/elevator.py):

* Статус лифта меняется только руками персонала через ``set_status`` (T3);
  подсказки из заявок / InfraSafe — источник события, не автосмена.
* Журнал ``elevator_status_events`` append-only; лифт не удаляется, а
  архивируется (``archived_at``).
* ``working`` (как и любой статус) — только после ввода в эксплуатацию:
  до ``is_commissioned`` статус NULL (``can_set_status``).
* Напоминания — идемпотентный тик: у сущности хранится стадия в колонке
  ``*_reminder_stage`` (SmallInteger) со семантикой «ДНИ последней
  отправленной стадии, 0 = ничего не отправлено» (30 → 14 → 7), а не индекс:
  список стадий меняется в конфиге, и сохранённое значение обязано пережить
  сжатие/расширение списка. Пропущенные стадии схлопываются в одно сообщение
  (``next_reminder_stage``); просрочка — с 8-го дня, повтор еженедельно
  (``is_overdue``/``should_remind_overdue``).
* Конфиг ``elevators_config.data``: сохранённый — терпим к неизвестным
  ключам (отбрасываются, ``unknown_config_keys`` для лога), патч — строгий
  (``merge_config``).
* Доступность за 30 дней считается только по времени, когда лифт введён в
  эксплуатацию и не архивирован; пробелы журнала в знаменатель не входят
  (``compute_availability_30d``).
* Заявка категории ``elevator`` обязана нести ``elevator_id`` и
  ``elevator_operational`` (Р11, ``require_elevator_for_category``).
"""

from ._core import (
    ELEVATOR_CATEGORY,
    ElevatorConflictError,
    ElevatorNotFoundError,
    ElevatorServiceError,
    ElevatorStateError,
    ElevatorValidationError,
    Message,
    StatusChange,
    is_strict_int,
    require_aware,
)
from .availability import StatusInterval, compute_availability_30d
from .calendar_rules import (
    DEFAULT_REMINDER_STAGES,
    assert_occurrence_editable,
    generate_occurrence_dates,
    is_overdue,
    next_reminder_stage,
    should_remind_overdue,
    validate_reminder_stages,
)
from .public_code import (
    PUBLIC_CODE_MAX_LEN,
    generate_public_code,
    is_valid_public_code,
)
from .reminder_rules import (
    DEFAULT_ELEVATORS_CONFIG,
    DOWNTIME_STATUSES,
    downtime_threshold_reached,
    merge_config,
    unknown_config_keys,
)
from .validation import (
    PASSPORT_REQUIRED_FIELDS,
    can_set_status,
    require_elevator_for_category,
    validate_passport_required,
    validate_status,
)

__all__ = [
    "DEFAULT_ELEVATORS_CONFIG",
    "DEFAULT_REMINDER_STAGES",
    "DOWNTIME_STATUSES",
    "ELEVATOR_CATEGORY",
    "PASSPORT_REQUIRED_FIELDS",
    "PUBLIC_CODE_MAX_LEN",
    "ElevatorConflictError",
    "ElevatorNotFoundError",
    "ElevatorServiceError",
    "ElevatorStateError",
    "ElevatorValidationError",
    "Message",
    "StatusChange",
    "StatusInterval",
    "assert_occurrence_editable",
    "can_set_status",
    "compute_availability_30d",
    "downtime_threshold_reached",
    "generate_occurrence_dates",
    "generate_public_code",
    "is_overdue",
    "is_strict_int",
    "is_valid_public_code",
    "merge_config",
    "next_reminder_stage",
    "require_aware",
    "require_elevator_for_category",
    "should_remind_overdue",
    "unknown_config_keys",
    "validate_passport_required",
    "validate_reminder_stages",
    "validate_status",
]
