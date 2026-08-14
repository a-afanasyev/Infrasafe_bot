"""
Пакет управления статусами заявок — живой путь «Закуп».

BUG-137: FSM-флоу смены статусов (status_flow/completion/confirmation/
availability + клавиатуры keyboards/request_status.py) ретайрен — из 11
хендлеров в проде жил ровно один: ``handle_materials_input`` (message-хендлер
на стейте ``RequestStatusStates.waiting_for_materials``; вход — менеджерский
«Закуп» ``purchase_<NNN>`` в handlers/admin/actions.py).

AUD3-07 (канон B1/B4): DB-фаза хендлера — цельный sync unit-of-work
(``_apply_purchase`` в ``_units``) в worker-потоке через ``run_db``; наружу
DTO, рендер — по ним. Хендлер НЕ объявляет параметр ``db`` (гейт:
tests/services/test_aud337_async_handlers_gate.py); тестовый seam —
keyword-only ``_db``.
"""

from ._router import router
from . import executor_actions  # noqa: F401,E402 — регистрация message-хендлера
from ._units import (
    _ActiveRow,
    _PurchaseOutcome,
    _apply_purchase,
)
from .executor_actions import handle_materials_input

__all__ = [
    "router",
    # DTO / sync-юниты (AUD3-07)
    "_ActiveRow",
    "_PurchaseOutcome",
    "_apply_purchase",
    # executor_actions
    "handle_materials_input",
]
