"""Async data-access service for the shifts/employees API (ARCH-05a, PR-27).

Весь прямой ORM/data-access слой роутера `api/shifts/router.py` вынесен сюда:
запросы (`select`/`db.execute`/`db.scalar`), мутации (`db.add`/`commit`/
`refresh`/`delete`/`flush`) и конструирование ORM-объектов. Роутер остаётся
тонким HTTP-слоем (auth-deps, парсинг запроса, сериализация ответа, HTTP-
исключения для 404/403/409/422).

Функции принимают `db: AsyncSession` + plain-параметры и возвращают ORM-объекты
или примитивы; маппинг в response-схемы и raise HTTPException — в роутере.
AST-гейт `tests/api/test_shifts_router_inventory.py` фиксирует отсутствие
прямого ORM в роутере на нуле.
"""

# AUD5-ARCH-3 волна 5: block-move файла api/shifts/service.py (1100 строк)
# в пакет. Публичный API без изменений — все прежние имена реэкспортируются
# отсюда, dotted-path импортёров (`from uk_management_bot.api.shifts import
# service; service.foo(...)`) сохранён. Тела функций/класса/констант — код
# байт-в-байт по под-модулям: employees / shifts_read / templates /
# transfers / lifecycle / web_transfers.

from .employees import (
    ACTIVE_REQUEST_STATUSES,
    _is_staff,
    activate_employee,
    count_active_requests,
    decline_employee,
    get_employee_with_stats,
    get_user,
    list_employees,
    list_pending_staff,
    set_meter_entry_role,
    set_user_status,
    set_user_verification,
    soft_delete_employee,
)
from .lifecycle import (
    ShiftOverlapError,
    apply_shift_update,
    create_shift,
    delete_shift,
    end_shift,
    find_overlapping_shift_for_update,
    get_shift_for_update,
    lock_user_shift_scope,
)
from .shifts_read import (
    _load_users_for_shifts,
    get_schedule,
    get_shift,
    get_stats,
    list_shifts,
    load_users_map,
)
from .templates import (
    create_shifts_from_template,
    create_template,
    get_active_template,
    get_template,
    list_templates,
    soft_delete_template,
    update_template,
)
from .transfers import (
    approve_transfer,
    cancel_transfer,
    commit_and_refresh_transfer,
    get_transfer_for_update,
    list_transfers,
    reject_transfer,
    resolve_transfer_users,
)
from .web_transfers import (
    REASSIGN_MOVE_STATUSES,
    _move_active_requests_web,
    accept_transfer_web,
    create_transfer_web,
    list_approved_managers,
    list_user_transfers,
    reassign_shift_web,
    reject_transfer_web_by_recipient,
)

__all__ = [
    # employees
    "ACTIVE_REQUEST_STATUSES",
    "_is_staff",
    "activate_employee",
    "count_active_requests",
    "decline_employee",
    "get_employee_with_stats",
    "get_user",
    "list_employees",
    "list_pending_staff",
    "set_meter_entry_role",
    "set_user_status",
    "set_user_verification",
    "soft_delete_employee",
    # lifecycle
    "ShiftOverlapError",
    "apply_shift_update",
    "create_shift",
    "delete_shift",
    "end_shift",
    "find_overlapping_shift_for_update",
    "get_shift_for_update",
    "lock_user_shift_scope",
    # shifts_read
    "_load_users_for_shifts",
    "get_schedule",
    "get_shift",
    "get_stats",
    "list_shifts",
    "load_users_map",
    # templates
    "create_shifts_from_template",
    "create_template",
    "get_active_template",
    "get_template",
    "list_templates",
    "soft_delete_template",
    "update_template",
    # transfers
    "approve_transfer",
    "cancel_transfer",
    "commit_and_refresh_transfer",
    "get_transfer_for_update",
    "list_transfers",
    "reject_transfer",
    "resolve_transfer_users",
    # web_transfers
    "REASSIGN_MOVE_STATUSES",
    "_move_active_requests_web",
    "accept_transfer_web",
    "create_transfer_web",
    "list_approved_managers",
    "list_user_transfers",
    "reassign_shift_web",
    "reject_transfer_web_by_recipient",
]
