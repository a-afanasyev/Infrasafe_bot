"""
Обработчики для управления квартирами (Apartment Management)

Функционал:
- Просмотр списка квартир
- Создание новой квартиры
- Просмотр детальной информации о квартире
- Редактирование квартиры
- Удаление (деактивация) квартиры
- Поиск квартир по номеру или адресу
- Просмотр жителей квартиры

AUD5-ARCH-3 (волна 3): block-move плоского файла в пакет. Порядок импорта
под-модулей = порядок регистрации хендлеров исходника (пересечения
callback-фильтров!), тела функций перенесены байт-в-байт.
"""
from ._router import router
from . import viewing, details, creation, editing, autofill, navigation  # noqa: F401 — регистрация по порядку
from .viewing import (
    show_apartments_list,
    show_apartments_by_building,
    paginate_apartments_by_building,
    start_apartment_search,
    process_apartment_search,
)
from .details import (
    show_apartment_details,
    show_apartment_residents,
)
from .creation import (
    start_apartment_creation,
    process_apartment_building_selection,
    process_apartment_number,
    process_apartment_entrance,
    process_apartment_floor,
    process_apartment_rooms,
    process_apartment_area,
)
from .editing import (
    show_apartment_edit_menu,
    toggle_apartment_status,
    confirm_apartment_deletion,
    delete_apartment,
    start_edit_apartment_area,
    process_new_apartment_area,
)
from .autofill import (
    start_autofill_apartments,
    process_autofill_range,
    confirm_autofill_apartments,
    cancel_autofill_apartments,
    parse_apartment_range,
    format_numbers_preview,
)
from .navigation import (
    _return_to_profile_apartments,
    _return_to_admin_yards,
    cancel_apartment_action,
    cancel_generic_action,
)

__all__ = [
    "router",
    # viewing
    "show_apartments_list",
    "show_apartments_by_building",
    "paginate_apartments_by_building",
    "start_apartment_search",
    "process_apartment_search",
    # details
    "show_apartment_details",
    "show_apartment_residents",
    # creation
    "start_apartment_creation",
    "process_apartment_building_selection",
    "process_apartment_number",
    "process_apartment_entrance",
    "process_apartment_floor",
    "process_apartment_rooms",
    "process_apartment_area",
    # editing
    "show_apartment_edit_menu",
    "toggle_apartment_status",
    "confirm_apartment_deletion",
    "delete_apartment",
    "start_edit_apartment_area",
    "process_new_apartment_area",
    # autofill
    "start_autofill_apartments",
    "process_autofill_range",
    "confirm_autofill_apartments",
    "cancel_autofill_apartments",
    "parse_apartment_range",
    "format_numbers_preview",
    # navigation (BUG-BOT-021 — обратная совместимость импортов)
    "_return_to_profile_apartments",
    "_return_to_admin_yards",
    "cancel_apartment_action",
    "cancel_generic_action",
]
