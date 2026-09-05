"""Сервис модуля «Лифты»: реестр, журнал статусов, график ТО, напоминания.

Паттерн material_service: чистое ядро (валидаторы, доступность, календарь,
правила напоминаний, конфиг — Ф2a) + DB-слой (Ф2b): общие строители над
загруженными объектами и тонкие sync-обёртки для бота (``Session``) /
async для API (``AsyncSession``). Сети нет: ``set_status`` возвращает
сообщения, отправляет вызывающий; commit — у вызывающего.

DB-модули: ``reads`` (лифт/журнал/график/заявки), ``registry`` (реестр с
фильтрами и сводка), ``metrics`` (доступность поверх журнала), ``status``,
``recipients``, ``passport``, ``calendar``, ``config``, ``validation_db``
(границы: длины колонок, номер заявки, URL). ``grouping`` (групповая приёмка
через ``run_command_async``) НЕ реэкспортируется — импортировать модулем, иначе
пакет тянет runner/httpx и получает цикл с хендлерами (гейт
``tests/services/test_elevator_service_imports.py``).

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
from .labels import elevator_label
from .reads import (
    count_building_apartments_without_entrance_async,
    count_open_requests_by_elevator_async,
    get_elevator_async,
    get_elevator_including_archived_async,
    get_elevator_including_archived_sync,
    get_elevator_sync,
    get_occurrence_async,
    get_occurrence_sync,
    list_active_for_building_async,
    list_active_for_building_sync,
    list_all_occurrences_async,
    list_events_async,
    list_occurrences_async,
    list_requests_for_elevator_async,
)
from .recipients import (
    Recipient,
    residents_of_entrance_async,
    residents_of_entrance_sync,
)
from .metrics import (
    availability_30d,
    availability_30d_for_page_async,
    date_to_business_midnight_utc,
    status_intervals_async,
)
from .registry import (
    REGISTRY_FLAGS,
    ElevatorCounters,
    ElevatorSummary,
    YardElevatorSummary,
    count_elevator_requests_without_elevator_async,
    count_elevators_async,
    list_elevators_async,
    maintenance_overdue_ids_async,
    summary_async,
)
from .status import (
    build_resident_messages,
    resident_notify_key,
    set_status_async,
    set_status_sync,
)
from .validation_db import (
    MAX_REASON_LEN,
    validate_passport_values,
    validate_reason,
    validate_request_number,
    validate_string_lengths,
    validate_url,
)
from .passport import (
    EDITABLE_FIELDS,
    archive_async,
    archive_sync,
    commission_async,
    commission_sync,
    create_elevator_async,
    create_elevator_sync,
    update_passport_async,
    update_passport_sync,
)
from .calendar import (
    cancel_occurrence_async,
    complete_occurrence_async,
    complete_occurrence_sync,
    create_occurrence_async,
    create_occurrence_sync,
    generate_occurrences_async,
    generate_occurrences_sync,
    reschedule_occurrence_async,
)
from .config import (
    CONFIG_ROW_ID,
    load_config_async,
    load_config_sync,
    resolve_stored_config,
    save_config_async,
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
    "CONFIG_ROW_ID",
    "DEFAULT_ELEVATORS_CONFIG",
    "DEFAULT_REMINDER_STAGES",
    "DOWNTIME_STATUSES",
    "EDITABLE_FIELDS",
    "ELEVATOR_CATEGORY",
    "MAX_REASON_LEN",
    "PASSPORT_REQUIRED_FIELDS",
    "PUBLIC_CODE_MAX_LEN",
    "REGISTRY_FLAGS",
    "ElevatorConflictError",
    "ElevatorCounters",
    "ElevatorNotFoundError",
    "ElevatorServiceError",
    "ElevatorStateError",
    "ElevatorSummary",
    "ElevatorValidationError",
    "Message",
    "Recipient",
    "StatusChange",
    "StatusInterval",
    "YardElevatorSummary",
    "archive_async",
    "archive_sync",
    "assert_occurrence_editable",
    "availability_30d",
    "availability_30d_for_page_async",
    "build_resident_messages",
    "can_set_status",
    "cancel_occurrence_async",
    "commission_async",
    "commission_sync",
    "complete_occurrence_async",
    "complete_occurrence_sync",
    "compute_availability_30d",
    "count_building_apartments_without_entrance_async",
    "count_elevator_requests_without_elevator_async",
    "count_elevators_async",
    "count_open_requests_by_elevator_async",
    "create_elevator_async",
    "create_elevator_sync",
    "create_occurrence_async",
    "create_occurrence_sync",
    "date_to_business_midnight_utc",
    "downtime_threshold_reached",
    "elevator_label",
    "generate_occurrence_dates",
    "generate_occurrences_async",
    "generate_occurrences_sync",
    "generate_public_code",
    "get_elevator_async",
    "get_elevator_including_archived_async",
    "get_elevator_including_archived_sync",
    "get_elevator_sync",
    "get_occurrence_async",
    "get_occurrence_sync",
    "is_overdue",
    "is_strict_int",
    "is_valid_public_code",
    "list_active_for_building_async",
    "list_active_for_building_sync",
    "list_all_occurrences_async",
    "list_elevators_async",
    "list_events_async",
    "list_occurrences_async",
    "list_requests_for_elevator_async",
    "load_config_async",
    "load_config_sync",
    "maintenance_overdue_ids_async",
    "merge_config",
    "next_reminder_stage",
    "require_aware",
    "require_elevator_for_category",
    "reschedule_occurrence_async",
    "resident_notify_key",
    "residents_of_entrance_async",
    "residents_of_entrance_sync",
    "resolve_stored_config",
    "save_config_async",
    "set_status_async",
    "set_status_sync",
    "should_remind_overdue",
    "status_intervals_async",
    "summary_async",
    "unknown_config_keys",
    "update_passport_async",
    "update_passport_sync",
    "validate_passport_required",
    "validate_passport_values",
    "validate_reason",
    "validate_request_number",
    "validate_reminder_stages",
    "validate_status",
    "validate_string_lengths",
    "validate_url",
]
