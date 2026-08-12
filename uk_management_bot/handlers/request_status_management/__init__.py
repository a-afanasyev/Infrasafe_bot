"""
Обработчики для управления статусами заявок
Обеспечивает функциональность изменения статусов заявок с комментариями

AUD3-07 (канон B1/B4): DB-фаза каждого хендлера — цельный sync unit-of-work
(`_load_*`/`_apply_*` ниже) в worker-потоке через ``run_db``; наружу DTO,
рендер — по ним. Хендлеры НЕ объявляют параметр ``db`` (гейт:
tests/services/test_aud337_async_handlers_gate.py); тестовый seam —
keyword-only ``_db``. Сервисы (RequestService/CommentService) sync и коммитят
сами — безопасны в thread-сессии (прецедент B4/AuthService).
"""

from ._router import router
from . import status_flow  # noqa: F401,E402 — регистрация по порядку исходника
from . import executor_actions  # noqa: F401,E402
from . import completion  # noqa: F401,E402
from ._units import (
    _ActiveRow,
    _PurchaseOutcome,
    _apply_completion,
    _apply_purchase,
    _apply_status_change,
    _has_role,
    _load_confirmation_context,
    _load_status_change_context,
    _notify_request_completed,
    _request_exists,
    _take_to_work,
)
from .availability import get_available_statuses, get_comment_prompt
from .confirmation import show_status_confirmation
from .status_flow import (
    handle_status_change_start,
    handle_status_selection,
    handle_comment_input,
    handle_status_confirmation,
    handle_status_cancellation,
)
from .executor_actions import (
    handle_take_to_work,
    handle_purchase_materials,
    handle_materials_input,
)
from .completion import (
    handle_complete_work,
    handle_completion_report_media,
    handle_completion_report_input,
)

__all__ = [
    "router",
    # DTO / sync-юниты (AUD3-07)
    "_ActiveRow",
    "_PurchaseOutcome",
    "_apply_completion",
    "_apply_purchase",
    "_apply_status_change",
    "_has_role",
    "_load_confirmation_context",
    "_load_status_change_context",
    "_notify_request_completed",
    "_request_exists",
    "_take_to_work",
    # вспомогательные функции
    "get_available_statuses",
    "get_comment_prompt",
    "show_status_confirmation",
    # status_flow
    "handle_status_change_start",
    "handle_status_selection",
    "handle_comment_input",
    "handle_status_confirmation",
    "handle_status_cancellation",
    # executor_actions
    "handle_take_to_work",
    "handle_purchase_materials",
    "handle_materials_input",
    # completion
    "handle_complete_work",
    "handle_completion_report_media",
    "handle_completion_report_input",
]
