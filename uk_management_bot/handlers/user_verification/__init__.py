"""
Обработчики для системы верификации пользователей

Содержит обработчики для:
- Управления верификацией пользователей
- Запроса дополнительной информации
- Проверки документов
- Управления правами доступа

AUD3-07 (канон B1/B4): DB-фаза каждого хендлера — цельный sync unit-of-work
(`_load_*`/`_apply_*`/`_collect_*` ниже), исполняемый в worker-потоке через
``run_db``. Сессия живёт только внутри юнита; наружу выходят DTO (dataclass'ы),
рендеринг текста — по ним. Сеть (Telegram-отправки, media-cleanup) — вне
юнитов, на event loop. Хендлеры НЕ объявляют параметр ``db`` (иначе aiogram DI
инъецирует middleware-сессию, и запрос исполняется на loop; гейт:
tests/services/test_aud337_async_handlers_gate.py). Тестовый seam —
keyword-only ``_db``: с ним юнит исполняется синхронно на переданной сессии.

AUD5-ARCH-3 (волна 11, block-move): плоский Router-файл
handlers/user_verification.py разбит на пакет; тела перенесены байт-в-байт.
Публичный API сохранён: ``router`` (main.py) + хендлеры и sync-юниты/DTO,
импортируемые тестами. Порядок импорта под-модулей = порядок регистрации
хендлеров исходника (``_units`` регистраций не несёт).
"""
from ._router import router
from . import panel, documents, info_requests, document_review, access_decision  # noqa: F401 — регистрация по порядку
from ._units import (
    _AccessRightRow,
    _ApartmentRow,
    _DocumentRow,
    _UserCard,
    _approve_user_db,
    _create_request_and_collect_notify,
    _document_row,
    _load_access_rights_card,
    _load_document,
    _load_documents_page,
    _load_user_card,
    _load_verification_stats,
    _purge_user_documents,
    _reject_user_db,
    _verify_document,
)
from .panel import show_verification_panel, show_user_verification
from .documents import (
    request_additional_info,
    view_user_documents,
    download_user_document,
)
from .info_requests import select_info_type, process_request_comment
from .document_review import verify_document, approve_document, reject_document
from .access_decision import (
    manage_access_rights,
    approve_user_verification,
    reject_user_verification,
)

__all__ = [
    "router",
    # DTO / sync-юниты (AUD3-07)
    "_AccessRightRow",
    "_ApartmentRow",
    "_DocumentRow",
    "_UserCard",
    "_approve_user_db",
    "_create_request_and_collect_notify",
    "_document_row",
    "_load_access_rights_card",
    "_load_document",
    "_load_documents_page",
    "_load_user_card",
    "_load_verification_stats",
    "_purge_user_documents",
    "_reject_user_db",
    "_verify_document",
    # panel
    "show_verification_panel",
    "show_user_verification",
    # documents
    "request_additional_info",
    "view_user_documents",
    "download_user_document",
    # info_requests
    "select_info_type",
    "process_request_comment",
    # document_review
    "verify_document",
    "approve_document",
    "reject_document",
    # access_decision
    "manage_access_rights",
    "approve_user_verification",
    "reject_user_verification",
]
