"""Фасад-реэкспорт пакета `services/work_reports/` (AUD6-P2-56).

Код разнесён по модулям пакета — см. карту в
`uk_management_bot/services/work_reports/__init__.py`:

* ``errors.py`` — `WorkReportServiceError`, `MediaValidationError`,
  `WorkReportPublishError`, `_LOCK_HOLDING_STATUSES`;
* ``addressing.py`` — `derive_public_address`, `address_looks_like_apartment`;
* ``media_selection.py`` — `fetch_media_selection`, `apply_media_selection`,
  `autofill_media`, `validate_media_ids`;
* ``sync.py`` — `sync_pending_drafts`, `revoke_stale_publications`;
* ``saga.py`` — `publish_report`, `unpublish_report`, `reject_report`,
  `reopen_report`;
* ``previews.py`` — `warm_report_previews`, `warm_recent_previews`;
* ``autopublish.py`` — `autopublish_ready_drafts`;
* ``reconcile.py`` — `reconcile_publication_locks`.

Этот модуль остаётся ЕДИНСТВЕННОЙ публичной точкой входа: колл-сайты и тесты
импортируют отсюда и monkeypatch-ят атрибуты по имени этого модуля
(`monkeypatch.setattr("uk_management_bot.services.work_report_service.X", ...)`).
Чтобы такие патчи продолжали действовать, межмодульные вызовы ВНУТРИ пакета
тоже идут через этот фасад (см. `_svc()` в модулях пакета) — не заменяйте их
на прямые импорты между модулями.
"""

from uk_management_bot.services.work_reports.addressing import (
    _APARTMENT_MARKER_PATTERN,
    address_looks_like_apartment,
    derive_public_address,
)
from uk_management_bot.services.work_reports.autopublish import (
    _AUTOPUBLISH_BATCH_LIMIT,
    _AUTOPUBLISH_TIME_BUDGET_SECONDS,
    autopublish_ready_drafts,
)
from uk_management_bot.services.work_reports.errors import (
    _LOCK_HOLDING_STATUSES,
    MediaValidationError,
    WorkReportPublishError,
    WorkReportServiceError,
)
from uk_management_bot.services.work_reports.media_selection import (
    _AUTOFILL_FETCH_LIMIT,
    _VALIDATE_FETCH_LIMIT,
    MAX_MEDIA_PER_SIDE,
    _filter_and_cap,
    apply_media_selection,
    autofill_media,
    fetch_media_selection,
    validate_media_ids,
)
from uk_management_bot.services.work_reports.previews import (
    _WARM_CHUNK,
    _WARM_SWEEP_LIMIT,
    _warm_in_chunks,
    warm_recent_previews,
    warm_report_previews,
)
from uk_management_bot.services.work_reports.reconcile import (
    _RECONCILE_STALE_MINUTES,
    reconcile_publication_locks,
)
from uk_management_bot.services.work_reports.saga import (
    _load_report_for_update,
    publish_report,
    reject_report,
    reopen_report,
    unpublish_report,
)
from uk_management_bot.services.work_reports.sync import (
    _SYNC_CANDIDATE_LIMIT,
    _SYNC_CIRCUIT_BREAKER_LIMIT,
    _SYNC_MAX_BACKFILL_DAYS,
    _sync_insert_stmt,
    revoke_stale_publications,
    sync_pending_drafts,
)

__all__ = [
    # errors.py
    "WorkReportServiceError",
    "MediaValidationError",
    "WorkReportPublishError",
    "_LOCK_HOLDING_STATUSES",
    # addressing.py
    "derive_public_address",
    "address_looks_like_apartment",
    "_APARTMENT_MARKER_PATTERN",
    # media_selection.py
    "MAX_MEDIA_PER_SIDE",
    "_AUTOFILL_FETCH_LIMIT",
    "_VALIDATE_FETCH_LIMIT",
    "_filter_and_cap",
    "fetch_media_selection",
    "apply_media_selection",
    "autofill_media",
    "validate_media_ids",
    # sync.py
    "_SYNC_CANDIDATE_LIMIT",
    "_SYNC_CIRCUIT_BREAKER_LIMIT",
    "_SYNC_MAX_BACKFILL_DAYS",
    "_sync_insert_stmt",
    "sync_pending_drafts",
    "revoke_stale_publications",
    # saga.py
    "_load_report_for_update",
    "publish_report",
    "unpublish_report",
    "reject_report",
    "reopen_report",
    # previews.py
    "warm_report_previews",
    "warm_recent_previews",
    "_warm_in_chunks",
    "_WARM_SWEEP_LIMIT",
    "_WARM_CHUNK",
    # autopublish.py
    "autopublish_ready_drafts",
    "_AUTOPUBLISH_BATCH_LIMIT",
    "_AUTOPUBLISH_TIME_BUDGET_SECONDS",
    # reconcile.py
    "reconcile_publication_locks",
    "_RECONCILE_STALE_MINUTES",
]
