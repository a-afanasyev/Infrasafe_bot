"""SSOT статусов визуального отчёта «до/после» (AUD6-P2-57).

Словарь статусов существовал ЧЕТЫРЬМЯ рукописными копиями: CheckConstraint
модели, Literal роутера, _MEDIA_EDITABLE_STATUSES и _LOCK_HOLDING_STATUSES —
тот же класс дрейфа, что уже стрелял со списком access-domain таблиц
(4 копии, PR #265). Канон живёт здесь; Literal роутера остаётся литеральным
(статическая типизация не собирается из кортежа) — его согласованность
держит гейт tests/api/test_work_report_status_ssot.py.
"""

WORK_REPORT_STATUSES: tuple[str, ...] = (
    "pending",
    "needs_media",
    "publishing",
    "published",
    "needs_review",
    "rejected",
)

# Статусы, в которых менять состав медиа осмысленно: отчёт ещё не в саге
# публикации и не опубликован.
MEDIA_EDITABLE_STATUSES: tuple[str, ...] = ("pending", "needs_media")

# Статусы-держатели publication-lock'ов в media-service: их locked_media_ids
# считаются «покрытыми» при сверке (reconcile_publication_locks).
LOCK_HOLDING_STATUSES: tuple[str, ...] = ("published", "publishing", "needs_review")
