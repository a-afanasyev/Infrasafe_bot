"""Ошибки work_report_service и статусные константы саги публикации."""

from uk_management_bot.constants.work_reports import LOCK_HOLDING_STATUSES

# ===========================================================================
# Ошибки
# ===========================================================================


class WorkReportServiceError(Exception):
    """База ошибок work_report_service."""


class MediaValidationError(WorkReportServiceError):
    """Media id, явно выбранный человеком, не прошёл проверку по текущим
    метаданным media-service (не относится к заявке/категории, не фото, не
    активен, слишком большой или размер неизвестен).

    Используется там, где выбор сделал человек (ручной PATCH, повторная
    проверка перед публикацией) и тихий дроп был бы неверной реакцией на его
    ошибку. Контраст с `autofill_media` ниже, который молча фильтрует
    автоматически найденных кандидатов."""


class WorkReportPublishError(WorkReportServiceError):
    """Raised by the publication saga (publish/unpublish/reject/reopen) when
    the requested transition can't happen right now. `status_code` carries the
    HTTP semantics a router should use directly — mirrors
    `request_address.AddressResolutionError`'s shape (message + status_code),
    an established pattern in this codebase for service errors a router just
    re-raises as HTTPException.

    404 — the report doesn't exist.
    409 — wrong current status for this transition, OR the underlying request
    stopped being eligible (deleted/status changed/returned) — a conflict with
    current server state, not a defect in the request body.
    422 — the report is missing before/after media, or a media id fails
    re-validation — a defect in what's being published, reachable via manual
    API calls that bypass autofill's own needs_media gating.
    """

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# Статусы, в которых отчёт СЧИТАЕТСЯ держателем publication-lock'ов из своего
# `locked_media_ids`. `needs_review` включён наравне с published/publishing: он
# получается автоматической ревокацией (`revoke_stale_publications`), которая
# не ходит в media-service и локи не снимает, а отчёт может вернуться в ленту
# (unpublish → reopen → publish). Если бы `needs_review` тут не значился,
# `reconcile_publication_locks` счёл бы его локи осиротевшими и снял их, оставив
# `locked_media_ids` лгать о реальном состоянии media-service.
# AUD6-P2-57: значение — из канона constants/work_reports.py.
_LOCK_HOLDING_STATUSES = LOCK_HOLDING_STATUSES
