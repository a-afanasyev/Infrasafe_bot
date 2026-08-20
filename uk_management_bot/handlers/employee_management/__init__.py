"""Обработчики управления сотрудниками (AUD5-ARCH-3: разбит god-файл на под-домены).

Публичный API сохранён: ``router`` (main.py) + хендлеры и sync-юниты/DTO,
импортируемые тестами. Порядок импорта под-модулей = порядок регистрации
хендлеров (фильтры взаимно непересекающиеся, порядок безопасен).
"""
from ._router import router
from . import panels, lists, moderation, editing, roles_specs  # noqa: F401 — регистрация по порядку
from ._units import (
    _EmployeeRow,
    _apply_role_change,
    _apply_specialization_change,
    _employee_row,
    _format_employee_name,
    _load_detailed_spec_stats,
    _load_employee,
    _load_employee_stats,
    _load_employees_page,
    _moderate_employee,
    _return_to_employee_info,
    _search_employees,
    _update_employee_phone,
)
from .panels import (
    back_to_admin_panel,
    back_to_main_panel,
    no_action_handler,
    show_employee_management_panel,
    show_employee_stats,
)
from .lists import (
    handle_employee_search_query,
    show_employee_actions,
    show_employee_list,
    start_employee_search,
)
from .moderation import (
    approve_employee,
    block_employee,
    delete_employee,
    reject_employee,
    unblock_employee,
)
from .editing import (
    edit_employee_entry,
    edit_employee_phone,
    process_employee_phone_edit,
)
from .roles_specs import (
    cancel_roles_editing,
    cancel_specializations_editing,
    change_employee_role,
    change_employee_specialization,
    process_role_change_comment,
    process_specialization_change_comment,
    save_employee_roles,
    save_employee_specializations,
    show_employee_specializations_management,
    toggle_role,
    toggle_specialization,
)

__all__ = [
    "router",
    # sync-юниты / DTO / хелперы (AUD3-37)
    "_EmployeeRow",
    "_apply_role_change",
    "_apply_specialization_change",
    "_employee_row",
    "_format_employee_name",
    "_load_detailed_spec_stats",
    "_load_employee",
    "_load_employee_stats",
    "_load_employees_page",
    "_moderate_employee",
    "_return_to_employee_info",
    "_search_employees",
    "_update_employee_phone",
    # panels
    "back_to_admin_panel",
    "back_to_main_panel",
    "no_action_handler",
    "show_employee_management_panel",
    "show_employee_stats",
    # lists
    "handle_employee_search_query",
    "show_employee_actions",
    "show_employee_list",
    "start_employee_search",
    # moderation
    "approve_employee",
    "block_employee",
    "delete_employee",
    "reject_employee",
    "unblock_employee",
    # editing
    "edit_employee_entry",
    "edit_employee_phone",
    "process_employee_phone_edit",
    # roles_specs
    "cancel_roles_editing",
    "cancel_specializations_editing",
    "change_employee_role",
    "change_employee_specialization",
    "process_role_change_comment",
    "process_specialization_change_comment",
    "save_employee_roles",
    "save_employee_specializations",
    "show_employee_specializations_management",
    "toggle_role",
    "toggle_specialization",
]
