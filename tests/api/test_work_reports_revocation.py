"""Тесты `work_report_service.revoke_stale_publications` (T5).

Опубликованный отчёт, чья заявка ещё существует, но перестала быть eligible
(статус ушёл от Исполнено/Принято, либо возвращена) — снимается в
needs_review с аудит-следом. Заявка, жёстко удалённая целиком — НЕ трогается
(INNER JOIN её естественно исключает): отчёт — бессрочный снимок, обязан
пережить удаление источника.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.services.work_report_service import revoke_stale_publications


def _mk_request(number: str, *, status: str, is_returned: bool = False) -> Request:
    return Request(
        request_number=number,
        user_id=1,
        category="plumbing",
        status=status,
        description="test",
        urgency="low",
        is_returned=is_returned,
    )


def _mk_published_report(number: str) -> WorkReport:
    return WorkReport(
        request_number=number,
        category_key="plumbing",
        address_public="test address",
        performed_at=datetime.now(timezone.utc),
        status="published",
        source="auto",
        published_at=datetime.now(timezone.utc),
    )


async def _audit_rows_for(db, request_number: str):
    rows = (
        await db.execute(
            select(AuditLog).where(AuditLog.action == "work_report.revoked")
        )
    ).scalars().all()
    return [r for r in rows if r.details.get("request_number") == request_number]


@pytest.mark.asyncio
async def test_revokes_report_when_request_cancelled(db_session):
    db_session.add(_mk_request("260725-200", status="Отменена"))
    db_session.add(_mk_published_report("260725-200"))
    await db_session.commit()

    count = await revoke_stale_publications(db_session)

    assert count == 1
    report = (
        await db_session.execute(
            select(WorkReport).where(WorkReport.request_number == "260725-200")
        )
    ).scalar_one()
    assert report.status == "needs_review"
    assert report.reject_reason == "request_no_longer_eligible"
    assert report.state_changed_at is not None

    audit_rows = await _audit_rows_for(db_session, "260725-200")
    assert len(audit_rows) == 1
    assert audit_rows[0].details["request_status"] == "Отменена"
    assert audit_rows[0].details["is_returned"] is False


@pytest.mark.asyncio
async def test_revokes_report_when_request_returned(db_session):
    db_session.add(_mk_request("260725-201", status="Принято", is_returned=True))
    db_session.add(_mk_published_report("260725-201"))
    await db_session.commit()

    count = await revoke_stale_publications(db_session)

    assert count == 1
    report = (
        await db_session.execute(
            select(WorkReport).where(WorkReport.request_number == "260725-201")
        )
    ).scalar_one()
    assert report.status == "needs_review"
    assert report.reject_reason == "request_no_longer_eligible"

    audit_rows = await _audit_rows_for(db_session, "260725-201")
    assert len(audit_rows) == 1
    assert audit_rows[0].details["is_returned"] is True


@pytest.mark.asyncio
async def test_untouched_when_request_still_eligible(db_session):
    db_session.add(_mk_request("260725-202", status="Принято", is_returned=False))
    db_session.add(_mk_published_report("260725-202"))
    await db_session.commit()

    count = await revoke_stale_publications(db_session)

    assert count == 0
    report = (
        await db_session.execute(
            select(WorkReport).where(WorkReport.request_number == "260725-202")
        )
    ).scalar_one()
    assert report.status == "published"
    assert report.reject_reason is None

    assert await _audit_rows_for(db_session, "260725-202") == []


@pytest.mark.asyncio
async def test_untouched_when_underlying_request_hard_deleted(db_session):
    """No FK — a WorkReport can reference a request_number that no longer
    exists in `requests` at all. The INNER JOIN excludes it: no crash, no
    change, no audit log."""
    db_session.add(_mk_published_report("260725-203-ghost"))
    await db_session.commit()

    count = await revoke_stale_publications(db_session)

    assert count == 0
    report = (
        await db_session.execute(
            select(WorkReport).where(WorkReport.request_number == "260725-203-ghost")
        )
    ).scalar_one()
    assert report.status == "published"
    assert report.reject_reason is None

    assert await _audit_rows_for(db_session, "260725-203-ghost") == []


@pytest.mark.asyncio
async def test_ignores_non_published_reports_even_if_request_ineligible(db_session):
    db_session.add(_mk_request("260725-204", status="Отменена"))
    report = _mk_published_report("260725-204")
    report.status = "needs_media"
    db_session.add(report)
    await db_session.commit()

    count = await revoke_stale_publications(db_session)

    assert count == 0
    row = (
        await db_session.execute(
            select(WorkReport).where(WorkReport.request_number == "260725-204")
        )
    ).scalar_one()
    assert row.status == "needs_media"
