"""
Detailed shift interface ("📋 Мои смены") — schedule, stats, time tracking.

Uses: Shift.planned_start_time, Shift.planned_end_time (planned times)
Related: shifts.py handles the operational menu ("🔄 Смена")

AUD3-37 (вариант (б), волна B1): DB-фаза каждого хендлера — цельный sync
unit-of-work (`_load_*`/`_start_shift`/`_end_shift` в ``_units``), исполняемый
в worker-потоке через ``run_db``. Сессия живёт только внутри юнита; наружу
выходят DTO (``_ShiftRow``/``_TransferRow``) — рендеринг и клавиатуры работают
по ним duck-typed. Хендлеры НЕ объявляют параметр ``db``: иначе aiogram DI
снова инъецировал бы middleware-сессию, и запрос исполнялся бы на event loop
(гейт: tests/services/test_aud337_async_handlers_gate.py). Тестовый seam —
keyword-only ``_db`` (aiogram это имя не инъецирует: ключа "_db" в data нет),
с ним юнит исполняется синхронно на переданной сессии.

AUD5-ARCH-3 (волна 7, block-move): плоский Router-файл handlers/my_shifts.py
разбит на пакет; тела перенесены байт-в-байт. Публичный API сохранён:
``router`` (main.py) + хендлеры и sync-юниты/DTO, импортируемые тестами.
Порядок импорта под-модулей = порядок регистрации хендлеров исходника
(``_units`` регистраций не несёт).
"""
from ._router import router
from . import menu, viewing, lifecycle, history, transfers  # noqa: F401 — регистрация по порядку
from ._units import (
    MY_SHIFTS_TEXTS,
    _ShiftRow,
    _TransferRow,
    _end_shift,
    _load_current_shifts,
    _load_my_transfers,
    _load_shift_details,
    _load_shift_history,
    _load_transfer_menu_counts,
    _load_transferable_shifts,
    _load_week_shifts,
    _resolve_user_id,
    _shift_row,
    _start_shift,
    _transfer_row,
)
from .menu import cmd_my_shifts, handle_my_shifts_button
from .viewing import handle_current_shifts, handle_week_schedule, handle_shift_details
from .lifecycle import handle_start_shift, handle_end_shift
from .history import handle_shift_history, handle_back_to_my_shifts
from .transfers import (
    handle_shift_transfer_menu,
    handle_initiate_transfer,
    handle_view_my_transfers,
)

__all__ = [
    "router",
    # sync-юниты / DTO / константа (AUD3-37)
    "MY_SHIFTS_TEXTS",
    "_ShiftRow",
    "_TransferRow",
    "_end_shift",
    "_load_current_shifts",
    "_load_my_transfers",
    "_load_shift_details",
    "_load_shift_history",
    "_load_transfer_menu_counts",
    "_load_transferable_shifts",
    "_load_week_shifts",
    "_resolve_user_id",
    "_shift_row",
    "_start_shift",
    "_transfer_row",
    # menu
    "cmd_my_shifts",
    "handle_my_shifts_button",
    # viewing
    "handle_current_shifts",
    "handle_week_schedule",
    "handle_shift_details",
    # lifecycle
    "handle_start_shift",
    "handle_end_shift",
    # history
    "handle_shift_history",
    "handle_back_to_my_shifts",
    # transfers
    "handle_shift_transfer_menu",
    "handle_initiate_transfer",
    "handle_view_my_transfers",
]
