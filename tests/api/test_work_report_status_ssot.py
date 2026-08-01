"""AUD6-P2-57: словарь статусов отчёта — один канон, четыре бывшие копии.

CheckConstraint модели и служебные кортежи собираются из
constants/work_reports.py по построению; Literal роутера обязан оставаться
литеральным (статическая типизация) — его равенство канону держит этот гейт.
Тот же класс дрейфа уже стрелял со списком access-domain таблиц (PR #265).
"""
import re
from typing import get_args

from uk_management_bot.api.work_reports.router import ReportStatus
from uk_management_bot.constants.work_reports import (
    LOCK_HOLDING_STATUSES,
    MEDIA_EDITABLE_STATUSES,
    WORK_REPORT_STATUSES,
)
from uk_management_bot.database.models.work_report import WorkReport


def test_router_literal_matches_canon():
    assert set(get_args(ReportStatus)) == set(WORK_REPORT_STATUSES)


def test_model_check_constraint_matches_canon():
    ck = next(
        c for c in WorkReport.__table__.constraints
        if getattr(c, "name", None) == "ck_work_reports_status"
    )
    quoted = set(re.findall(r"'([a-z_]+)'", str(ck.sqltext)))
    assert quoted == set(WORK_REPORT_STATUSES)


def test_subsets_stay_inside_canon():
    assert set(MEDIA_EDITABLE_STATUSES) <= set(WORK_REPORT_STATUSES)
    assert set(LOCK_HOLDING_STATUSES) <= set(WORK_REPORT_STATUSES)
    # Дизайн-инварианты, на которые опираются сага и роутер:
    assert "publishing" not in MEDIA_EDITABLE_STATUSES
    assert "publishing" in LOCK_HOLDING_STATUSES
