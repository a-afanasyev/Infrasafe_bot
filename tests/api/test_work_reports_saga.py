"""Тесты публикационной саги `work_report_service` (T6):
`publish_report` / `unpublish_report` / `reject_report` / `reopen_report` /
`reconcile_publication_locks` — координация между БД бота (`work_reports`) и
отдельной БД media-service БЕЗ two-phase commit.

`FakeMediaClient` — та же простая замена httpx-клиента, что и в
`test_work_report_media.py` (T5), расширенная методами захвата/снятия лока и
инвентаризации, нужными саге.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.services.work_report_service import (
    WorkReportPublishError,
    address_looks_like_apartment,
    publish_report,
    reconcile_publication_locks,
    reject_report,
    reopen_report,
    unpublish_report,
)

MODERATOR_ID = 777


def _photo(id_, *, file_type="photo", status="active", file_size=1024, mime_type="image/jpeg"):
    return {
        "id": id_,
        "file_type": file_type,
        "status": status,
        "file_size": file_size,
        "mime_type": mime_type,
    }


class FakeMediaClient:
    """Заглушка media_client для саги: get_request_media (T5-паттерн) +
    acquire/release publication lock + list_publication_locks.

    `acquire_fail_at_call` — 1-indexed номер ВЫЗОВА acquire_publication_lock
    (по порядку, не по media_id), который должен вернуть False — так тест
    может сымитировать "3-й из 4 вызовов провалился" независимо от того,
    какой конкретно media_id пришёл третьим.
    `acquire_fail_media_ids` — альтернативно, провалить конкретные id.
    """

    def __init__(
        self,
        by_category: dict[str, list[dict]] | None = None,
        acquire_fail_at_call: int | None = None,
        acquire_fail_media_ids: set[int] | None = None,
        list_locks_items: list[dict] | None = None,
        release_raises: bool = False,
    ):
        self._by_category = by_category or {}
        self.acquire_calls: list[int] = []
        self.release_calls: list[int] = []
        self._acquire_fail_at_call = acquire_fail_at_call
        self._acquire_fail_media_ids = acquire_fail_media_ids or set()
        self._list_locks_items = list_locks_items if list_locks_items is not None else []
        self._release_raises = release_raises

    async def get_request_media(self, request_number: str, category: str, limit: int = 50):
        return self._by_category.get(category, [])

    async def acquire_publication_lock(self, media_id: int) -> bool:
        self.acquire_calls.append(media_id)
        if self._acquire_fail_at_call is not None and len(self.acquire_calls) == self._acquire_fail_at_call:
            return False
        if media_id in self._acquire_fail_media_ids:
            return False
        return True

    async def release_publication_lock(self, media_id: int) -> bool:
        self.release_calls.append(media_id)
        if self._release_raises:
            raise RuntimeError("media-service unreachable")
        return True

    async def list_publication_locks(self, limit: int = 200, offset: int = 0) -> dict:
        items = self._list_locks_items[offset : offset + limit]
        return {
            "items": items,
            "total": len(self._list_locks_items),
            "limit": limit,
            "offset": offset,
        }


class RaisingReleaseClient:
    """Минимальный клиент, у которого release_publication_lock всегда падает —
    для проверки, что unpublish_report фиксирует статус в БД ДО релиза."""

    async def release_publication_lock(self, media_id: int) -> bool:
        raise RuntimeError("media-service unreachable")


def _mk_request(number: str, *, status: str = "Исполнено", is_returned: bool = False) -> Request:
    return Request(
        request_number=number,
        user_id=1,
        category="plumbing",
        status=status,
        description="test",
        urgency="low",
        is_returned=is_returned,
    )


def _mk_report(
    number: str,
    *,
    status: str = "pending",
    address_public: str = "ул. Ленина, 5 (Двор Гагарина)",
    before_media_ids: list[int] | None = None,
    after_media_ids: list[int] | None = None,
    locked_media_ids: list[int] | None = None,
    state_changed_at=None,
) -> WorkReport:
    return WorkReport(
        request_number=number,
        category_key="plumbing",
        address_public=address_public,
        performed_at=datetime.now(timezone.utc),
        before_media_ids=before_media_ids or [],
        after_media_ids=after_media_ids or [],
        media_meta=[],
        locked_media_ids=locked_media_ids or [],
        status=status,
        source="auto",
        state_changed_at=state_changed_at,
    )


async def _reload(db, report_id: int) -> WorkReport:
    return (
        await db.execute(select(WorkReport).where(WorkReport.id == report_id))
    ).scalar_one()


async def _audit_rows(db, action: str, report_id: int):
    rows = (await db.execute(select(AuditLog).where(AuditLog.action == action))).scalars().all()
    return [r for r in rows if r.details.get("report_id") == report_id]


# ===========================================================================
# publish_report
# ===========================================================================


@pytest.mark.asyncio
async def test_publish_happy_path(db_session):
    db_session.add(_mk_request("260725-300"))
    report = _mk_report("260725-300", before_media_ids=[1, 2], after_media_ids=[10, 11])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1), _photo(2)],
        "completion_photo": [_photo(10), _photo(11)],
    })

    result = await publish_report(db_session, client, report.id, MODERATOR_ID)

    assert result.status == "published"
    assert result.published_at is not None
    assert result.moderated_by == MODERATOR_ID
    assert result.locked_media_ids == [1, 2, 10, 11]
    assert result.media_meta == [
        {"id": 1, "file_type": "photo", "mime": "image/jpeg", "size": 1024},
        {"id": 2, "file_type": "photo", "mime": "image/jpeg", "size": 1024},
        {"id": 10, "file_type": "photo", "mime": "image/jpeg", "size": 1024},
        {"id": 11, "file_type": "photo", "mime": "image/jpeg", "size": 1024},
    ]
    assert client.acquire_calls == [1, 2, 10, 11]

    rows = await _audit_rows(db_session, "work_report.publish", report.id)
    assert len(rows) == 1
    assert rows[0].user_id == MODERATOR_ID
    assert rows[0].details["before_ids"] == [1, 2]
    assert rows[0].details["after_ids"] == [10, 11]


@pytest.mark.asyncio
async def test_publish_404_missing_report(db_session):
    client = FakeMediaClient()
    with pytest.raises(WorkReportPublishError) as exc_info:
        await publish_report(db_session, client, 999999, MODERATOR_ID)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_publish_409_wrong_starting_status(db_session):
    db_session.add(_mk_request("260725-301"))
    report = _mk_report("260725-301", status="published", before_media_ids=[1], after_media_ids=[2])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    with pytest.raises(WorkReportPublishError) as exc_info:
        await publish_report(db_session, FakeMediaClient(), report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 409
    assert "pending" in exc_info.value.message


@pytest.mark.asyncio
async def test_publish_409_request_status_changed_away(db_session):
    db_session.add(_mk_request("260725-302", status="Новая"))
    report = _mk_report("260725-302", before_media_ids=[1], after_media_ids=[2])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    with pytest.raises(WorkReportPublishError) as exc_info:
        await publish_report(db_session, FakeMediaClient(), report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 409
    assert "eligible" in exc_info.value.message


@pytest.mark.asyncio
async def test_publish_409_request_is_returned(db_session):
    db_session.add(_mk_request("260725-303", status="Исполнено", is_returned=True))
    report = _mk_report("260725-303", before_media_ids=[1], after_media_ids=[2])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    with pytest.raises(WorkReportPublishError) as exc_info:
        await publish_report(db_session, FakeMediaClient(), report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_publish_409_request_hard_deleted(db_session):
    # No Request row at all for this request_number.
    report = _mk_report("260725-304-ghost", before_media_ids=[1], after_media_ids=[2])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    with pytest.raises(WorkReportPublishError) as exc_info:
        await publish_report(db_session, FakeMediaClient(), report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_publish_409_address_looks_like_apartment(db_session):
    db_session.add(_mk_request("260725-305"))
    report = _mk_report(
        "260725-305",
        address_public="ул. Ленина, 5, кв. 42",
        before_media_ids=[1],
        after_media_ids=[2],
    )
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    with pytest.raises(WorkReportPublishError) as exc_info:
        await publish_report(db_session, FakeMediaClient(), report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 409
    assert "address" in exc_info.value.message


@pytest.mark.asyncio
async def test_publish_409_empty_address(db_session):
    db_session.add(_mk_request("260725-306"))
    report = _mk_report("260725-306", address_public="", before_media_ids=[1], after_media_ids=[2])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    with pytest.raises(WorkReportPublishError) as exc_info:
        await publish_report(db_session, FakeMediaClient(), report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_publish_422_missing_before_media(db_session):
    db_session.add(_mk_request("260725-307"))
    report = _mk_report("260725-307", before_media_ids=[], after_media_ids=[2])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    with pytest.raises(WorkReportPublishError) as exc_info:
        await publish_report(db_session, FakeMediaClient(), report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_publish_422_missing_after_media(db_session):
    db_session.add(_mk_request("260725-308"))
    report = _mk_report("260725-308", before_media_ids=[1], after_media_ids=[])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    with pytest.raises(WorkReportPublishError) as exc_info:
        await publish_report(db_session, FakeMediaClient(), report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_publish_422_validate_media_ids_rejects_stale_id(db_session):
    db_session.add(_mk_request("260725-309"))
    report = _mk_report("260725-309", before_media_ids=[999], after_media_ids=[2])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1)],  # 999 is not among them
        "completion_photo": [_photo(2)],
    })

    with pytest.raises(WorkReportPublishError) as exc_info:
        await publish_report(db_session, client, report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_publish_compensates_on_partial_lock_failure(db_session):
    """3rd of 4 acquire_publication_lock calls fails → first 2 locks released,
    locked_media_ids reset, status reverted to pending, 409 raised."""
    db_session.add(_mk_request("260725-310"))
    report = _mk_report("260725-310", before_media_ids=[1, 2], after_media_ids=[10, 11])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    client = FakeMediaClient(
        by_category={
            "request_photo": [_photo(1), _photo(2)],
            "completion_photo": [_photo(10), _photo(11)],
        },
        acquire_fail_at_call=3,
    )

    with pytest.raises(WorkReportPublishError) as exc_info:
        await publish_report(db_session, client, report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 409

    assert client.acquire_calls == [1, 2, 10]
    assert client.release_calls == [1, 2]

    reloaded = await _reload(db_session, report.id)
    assert reloaded.status == "pending"
    assert reloaded.locked_media_ids == []


@pytest.mark.asyncio
async def test_publish_second_concurrent_call_sees_409(db_session):
    """Real cross-connection row locking isn't practically testable against
    sqlite (FOR UPDATE is a no-op there). A same-connection sequential call
    proves the second attempt correctly observes the already-transitioned
    status and is rejected with 409 — an acceptable substitute per the task
    spec."""
    db_session.add(_mk_request("260725-311"))
    report = _mk_report("260725-311", before_media_ids=[1], after_media_ids=[2])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1)],
        "completion_photo": [_photo(2)],
    })

    first = await publish_report(db_session, client, report.id, MODERATOR_ID)
    assert first.status == "published"

    with pytest.raises(WorkReportPublishError) as exc_info:
        await publish_report(db_session, client, report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 409


# ===========================================================================
# unpublish_report
# ===========================================================================


@pytest.mark.asyncio
async def test_unpublish_releases_unshared_locks(db_session):
    report = _mk_report("260725-320", status="published", locked_media_ids=[1, 2])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    client = FakeMediaClient()
    result = await unpublish_report(db_session, client, report.id, MODERATOR_ID, reason="test reason")

    assert result.status == "rejected"
    assert result.reject_reason == "test reason"
    assert result.locked_media_ids == []
    assert sorted(client.release_calls) == [1, 2]

    rows = await _audit_rows(db_session, "work_report.unpublish", report.id)
    assert len(rows) == 1
    assert rows[0].details["reason"] == "test reason"


@pytest.mark.asyncio
async def test_unpublish_does_not_release_lock_shared_with_another_live_report(db_session):
    report_a = _mk_report("260725-321-a", status="published", locked_media_ids=[1, 2])
    report_b = _mk_report("260725-321-b", status="published", locked_media_ids=[2, 3])
    db_session.add_all([report_a, report_b])
    await db_session.commit()
    await db_session.refresh(report_a)

    client = FakeMediaClient()
    await unpublish_report(db_session, client, report_a.id, MODERATOR_ID)

    # id 2 shared with still-published report_b — must NOT be released.
    assert 2 not in client.release_calls
    # id 1 unique to report_a — must be released.
    assert 1 in client.release_calls


@pytest.mark.asyncio
async def test_unpublish_needs_review_to_rejected(db_session):
    report = _mk_report("260725-322", status="needs_review", locked_media_ids=[5])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    client = FakeMediaClient()
    result = await unpublish_report(db_session, client, report.id, MODERATOR_ID)

    assert result.status == "rejected"
    assert client.release_calls == [5]


@pytest.mark.asyncio
async def test_unpublish_404_missing_report(db_session):
    with pytest.raises(WorkReportPublishError) as exc_info:
        await unpublish_report(db_session, FakeMediaClient(), 999999, MODERATOR_ID)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_unpublish_409_wrong_status(db_session):
    report = _mk_report("260725-323", status="pending")
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    with pytest.raises(WorkReportPublishError) as exc_info:
        await unpublish_report(db_session, FakeMediaClient(), report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_unpublish_commits_status_before_releasing_locks(db_session):
    """DB-side hide must be durable even if the release step blows up
    afterwards — ordering is: commit rejected status FIRST, unlock SECOND."""
    report = _mk_report("260725-324", status="published", locked_media_ids=[1])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    with pytest.raises(RuntimeError):
        await unpublish_report(db_session, RaisingReleaseClient(), report.id, MODERATOR_ID)

    reloaded = await _reload(db_session, report.id)
    assert reloaded.status == "rejected"
    assert reloaded.locked_media_ids == []


# ===========================================================================
# reject_report
# ===========================================================================


@pytest.mark.asyncio
async def test_reject_pending_to_rejected(db_session):
    report = _mk_report("260725-330", status="pending")
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    result = await reject_report(db_session, report.id, MODERATOR_ID, "not suitable")

    assert result.status == "rejected"
    assert result.reject_reason == "not suitable"
    assert result.moderated_by == MODERATOR_ID

    rows = await _audit_rows(db_session, "work_report.reject", report.id)
    assert len(rows) == 1
    assert rows[0].details["reason"] == "not suitable"


@pytest.mark.asyncio
async def test_reject_needs_media_to_rejected(db_session):
    report = _mk_report("260725-331", status="needs_media")
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    result = await reject_report(db_session, report.id, MODERATOR_ID, "reason")
    assert result.status == "rejected"


@pytest.mark.asyncio
async def test_reject_404_missing_report(db_session):
    with pytest.raises(WorkReportPublishError) as exc_info:
        await reject_report(db_session, 999999, MODERATOR_ID, "reason")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_reject_409_wrong_status(db_session):
    report = _mk_report("260725-332", status="published")
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    with pytest.raises(WorkReportPublishError) as exc_info:
        await reject_report(db_session, report.id, MODERATOR_ID, "reason")
    assert exc_info.value.status_code == 409


# ===========================================================================
# reopen_report
# ===========================================================================


@pytest.mark.asyncio
async def test_reopen_rejected_to_pending(db_session):
    report = _mk_report("260725-340", status="rejected")
    report.reject_reason = "old reason"
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    result = await reopen_report(db_session, report.id, MODERATOR_ID)

    assert result.status == "pending"
    assert result.reject_reason is None

    rows = await _audit_rows(db_session, "work_report.reopen", report.id)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_reopen_404_missing_report(db_session):
    with pytest.raises(WorkReportPublishError) as exc_info:
        await reopen_report(db_session, 999999, MODERATOR_ID)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_reopen_409_wrong_status(db_session):
    report = _mk_report("260725-341", status="pending")
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    with pytest.raises(WorkReportPublishError) as exc_info:
        await reopen_report(db_session, report.id, MODERATOR_ID)
    assert exc_info.value.status_code == 409


# ===========================================================================
# reconcile_publication_locks
# ===========================================================================


@pytest.mark.asyncio
async def test_reconcile_all_three_directions(db_session):
    now = datetime.now(timezone.utc)

    stale = _mk_report(
        "260725-350-stale", status="publishing", locked_media_ids=[5, 6],
        state_changed_at=now - timedelta(minutes=20),
    )
    fresh = _mk_report(
        "260725-350-fresh", status="publishing", locked_media_ids=[7],
        state_changed_at=now - timedelta(minutes=5),
    )
    published = _mk_report(
        "260725-350-pub", status="published", locked_media_ids=[42],
        state_changed_at=now,
    )
    db_session.add_all([stale, fresh, published])
    await db_session.commit()
    await db_session.refresh(stale)
    await db_session.refresh(fresh)
    await db_session.refresh(published)

    # Inventory: 7 (covered by `fresh`, left alone), 99 (orphaned — no report
    # references it). 42 is deliberately ABSENT (missing → re-acquire).
    client = FakeMediaClient(list_locks_items=[{"id": 7}, {"id": 99}])

    result = await reconcile_publication_locks(db_session, client)

    assert result == {
        "unstuck_publishing": 1,
        "orphaned_locks_released": 1,
        "missing_locks_relocked": 1,
    }

    stale_reloaded = await _reload(db_session, stale.id)
    assert stale_reloaded.status == "pending"
    assert stale_reloaded.locked_media_ids == []

    fresh_reloaded = await _reload(db_session, fresh.id)
    assert fresh_reloaded.status == "publishing"
    assert fresh_reloaded.locked_media_ids == [7]

    published_reloaded = await _reload(db_session, published.id)
    assert published_reloaded.status == "published"
    assert published_reloaded.locked_media_ids == [42]

    assert sorted(client.release_calls) == [5, 6, 99]
    assert client.acquire_calls == [42]


@pytest.mark.asyncio
async def test_reconcile_tolerates_reacquire_failure(db_session):
    now = datetime.now(timezone.utc)
    published = _mk_report(
        "260725-351", status="published", locked_media_ids=[77],
        state_changed_at=now,
    )
    db_session.add(published)
    await db_session.commit()
    await db_session.refresh(published)

    client = FakeMediaClient(list_locks_items=[], acquire_fail_media_ids={77})

    result = await reconcile_publication_locks(db_session, client)

    assert result["missing_locks_relocked"] == 0
    assert 77 in client.acquire_calls

    reloaded = await _reload(db_session, published.id)
    assert reloaded.status == "published"
    assert reloaded.locked_media_ids == [77]


# ===========================================================================
# address_looks_like_apartment
# ===========================================================================


@pytest.mark.parametrize("address,expected", [
    ("ул. X, д. 5, кв. 42", True),
    ("ул. X, д. 5", False),
    ("Двор Гагарина", False),
    ("квартал 3", False),
    ("ул. X, кв42", True),
    ("ул. X, Кв. 7", True),
])
def test_address_looks_like_apartment(address, expected):
    assert address_looks_like_apartment(address) == expected
