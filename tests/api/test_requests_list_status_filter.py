"""GET /api/v2/requests?status=… — фильтр по НЕСКОЛЬКИМ статусам.

TWA исполнителя грузила `limit=50` без фильтра и отбирала активные на клиенте:
при 50+ архивных старые активные выпадали из выборки. Параметр `status`
повторяемый (`status=a&status=b`); одиночный — прежний контракт. Значения
валидируются по канону статусов (422 на неизвестный).
"""
import pytest
import pytest_asyncio

from uk_management_bot.database.models.request import Request
import uk_management_bot.utils.constants as C

LIST_URL = "/api/v2/requests"

ROWS = {
    "260921-001": C.REQUEST_STATUS_NEW,
    "260921-002": C.REQUEST_STATUS_IN_PROGRESS,
    "260921-003": C.REQUEST_STATUS_RETURNED,
    "260921-004": C.REQUEST_STATUS_APPROVED,
    "260921-005": C.REQUEST_STATUS_CANCELLED,
}


@pytest_asyncio.fixture
async def rows(db_session, manager_user):
    db_session.add_all([
        Request(request_number=n, user_id=manager_user.id, category="plumbing",
                description="x", status=st, urgency="low")
        for n, st in ROWS.items()
    ])
    await db_session.commit()


async def _numbers(client, params) -> list[str]:
    r = await client.get(LIST_URL, params=params)
    assert r.status_code == 200, r.text
    return sorted(c["request_number"] for c in r.json())


@pytest.mark.asyncio
async def test_no_status_returns_all(client, rows):
    assert await _numbers(client, {}) == sorted(ROWS)


@pytest.mark.asyncio
async def test_single_status_is_backward_compatible(client, rows):
    assert await _numbers(client, {"status": C.REQUEST_STATUS_NEW}) == ["260921-001"]


@pytest.mark.asyncio
async def test_repeated_status_filters_by_any_of(client, rows):
    params = [("status", C.REQUEST_STATUS_NEW),
              ("status", C.REQUEST_STATUS_IN_PROGRESS),
              ("status", C.REQUEST_STATUS_RETURNED)]
    assert await _numbers(client, params) == ["260921-001", "260921-002", "260921-003"]


@pytest.mark.asyncio
async def test_unknown_status_is_422(client, rows):
    r = await client.get(LIST_URL, params=[("status", C.REQUEST_STATUS_NEW),
                                           ("status", "Bogus")])
    assert r.status_code == 422, r.text
    assert "Bogus" in r.text


# ═══ Фильтр по дате приёмки (переход из аналитики исполнителей) ═══


@pytest.mark.asyncio
async def test_accepted_window_filters_by_business_dates(client, db_session, manager_user):
    from datetime import datetime, timezone

    def utc(*a):
        return datetime(*a, tzinfo=timezone.utc)

    db_session.add_all([
        Request(request_number=n, user_id=manager_user.id, category="plumbing",
                description="x", status=C.REQUEST_STATUS_APPROVED, urgency="low",
                completed_at=ts)
        for n, ts in {
            "261001-001": utc(2026, 10, 1, 5),
            "261031-001": utc(2026, 10, 31, 18, 59),   # 23:59 31.10 Ташкента
            "261031-002": utc(2026, 10, 31, 19, 0),    # 00:00 01.11 Ташкента
            "260930-001": utc(2026, 9, 30, 18, 59),
        }.items()
    ])
    await db_session.commit()
    params = {"accepted_from": "2026-10-01", "accepted_to": "2026-10-31"}
    assert await _numbers(client, params) == ["261001-001", "261031-001"]


@pytest.mark.parametrize("params", [
    {"accepted_from": "2026-10-01"},
    {"accepted_from": "2026-10-31", "accepted_to": "2026-10-01"},
    {"accepted_from": "x", "accepted_to": "2026-10-01"},
])
@pytest.mark.asyncio
async def test_accepted_window_validation(client, params):
    assert (await client.get(LIST_URL, params=params)).status_code == 422
