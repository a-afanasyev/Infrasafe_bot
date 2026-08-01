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
from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG
from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.services.work_report_service import (
    WorkReportPublishError,
    address_looks_like_apartment,
    autopublish_ready_drafts,
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
        self.resolve_stale_calls: list[int] = []
        self.warm_calls: list[list[int]] = []

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

    async def warm_previews(self, media_ids: list[int]) -> dict:
        """Прогрев превью — оптимизация; сага и тик зовут его best-effort."""
        self.warm_calls.append(list(media_ids))
        return {"warmed": len(media_ids), "already_cached": 0, "failed": 0}

    async def resolve_stale_transitions(self, older_than_minutes: int = 15) -> dict:
        """Четвёртое направление сверки — восстановление зависших
        `archiving`/`deleting` на стороне media-service. Здесь только
        фиксируем факт вызова: сама логика переходов живёт в media_service и
        покрыта его собственным сюитом (media_service/test_publication_lock.py)."""
        self.resolve_stale_calls.append(older_than_minutes)
        return {"archiving_reverted": 0, "deleting_finalized": 0}


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
async def test_publish_allowed_without_before_media(db_session):
    """Фото «до» НЕ обязательно (решение владельца 2026-07-25).

    Раньше такой отчёт получал 422 и работа не попадала в ленту вовсе, хотя
    результат был снят. Часто «до» физически нет: житель фотографирует уже
    текущее состояние, исполнитель на аварии не успевает. Витрина показывает
    отсутствующую сторону подписью «нет фото».
    """
    db_session.add(_mk_request("260725-307"))
    report = _mk_report("260725-307", before_media_ids=[], after_media_ids=[2])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    client = FakeMediaClient(by_category={
        "request_photo": [], "completion_photo": [_photo(2)],
    })

    result = await publish_report(db_session, client, report.id, MODERATOR_ID)

    assert result.status == "published"
    assert result.before_media_ids == []
    # Локи берутся только на реально опубликованные байты.
    assert client.acquire_calls == [2]


@pytest.mark.parametrize("before,after,publishable", [
    ([1], [2], True),    # обе стороны — классический «до/после»
    ([], [2], True),     # только результат — «до» не сняли, витрина покажет «нет фото»
    ([1], [], False),    # только «до» — работа не показана, публиковать нечего
    ([], [], False),     # ни одного фото — карточка без единого доказательства
])
@pytest.mark.asyncio
async def test_publish_requires_result_photo_matrix(db_session, before, after, publishable):
    """Полная матрица правила (решение владельца): публикуем при «до+после» и
    при «только после»; отказываем, если фото результата нет — включая случай,
    когда нет ни одного снимка."""
    number = f"260725-m{len(before)}{len(after)}"
    db_session.add(_mk_request(number))
    report = _mk_report(number, before_media_ids=before, after_media_ids=after)
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    client = FakeMediaClient(by_category={
        "request_photo": [_photo(i) for i in before],
        "completion_photo": [_photo(i) for i in after],
    })

    if publishable:
        result = await publish_report(db_session, client, report.id, MODERATOR_ID)
        assert result.status == "published"
    else:
        with pytest.raises(WorkReportPublishError) as exc:
            await publish_report(db_session, client, report.id, MODERATOR_ID)
        assert exc.value.status_code == 422
        assert "result media" in str(exc.value)


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
async def test_unpublish_keeps_lock_shared_with_needs_review_report(db_session):
    """`needs_review` — тоже держатель lock'а (_LOCK_HOLDING_STATUSES).

    Такой отчёт получается автоматической ревокацией, которая в media-service не
    ходит и локи не снимает, а вернуться в ленту он может (unpublish → reopen →
    publish). Значит его байты обязаны оставаться защищёнными от архивации.
    """
    report_a = _mk_report("260725-321-c", status="published", locked_media_ids=[1, 2])
    report_b = _mk_report("260725-321-d", status="needs_review", locked_media_ids=[2])
    db_session.add_all([report_a, report_b])
    await db_session.commit()
    await db_session.refresh(report_a)

    client = FakeMediaClient()
    await unpublish_report(db_session, client, report_a.id, MODERATOR_ID)

    assert 2 not in client.release_calls
    assert 1 in client.release_calls


@pytest.mark.asyncio
async def test_reconcile_does_not_strip_locks_of_needs_review_report(db_session):
    """Регрессия: до включения `needs_review` в _LOCK_HOLDING_STATUSES сверка
    считала его локи осиротевшими и снимала их, оставляя `locked_media_ids`
    лгать о реальном состоянии media-service."""
    report = _mk_report("260725-321-e", status="needs_review", locked_media_ids=[77])
    db_session.add(report)
    await db_session.commit()

    client = FakeMediaClient(list_locks_items=[{"id": 77}])
    result = await reconcile_publication_locks(db_session, client)

    assert result["orphaned_locks_released"] == 0
    assert client.release_calls == []


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
        # AUD6-P2-04: `fresh` ещё в publishing — снятие орфана 99 ОТЛОЖЕНО:
        # «осиротевший» id может оказаться свежевзятым локом саги, чей
        # locked_media_ids ещё не закоммичен (TOCTOU между двумя БД).
        "orphaned_locks_released": 0,
        "orphan_release_deferred": 1,
        "missing_locks_relocked": 1,
        # Четвёртое направление делегировано media-service (см. docstring
        # reconcile_publication_locks) — здесь проверяем только, что оно вызвано
        # с тем же порогом staleness, а не дублируем его логику.
        "stale_transitions": {"archiving_reverted": 0, "deleting_finalized": 0},
    }
    assert client.resolve_stale_calls == [15]

    stale_reloaded = await _reload(db_session, stale.id)
    assert stale_reloaded.status == "pending"
    assert stale_reloaded.locked_media_ids == []

    fresh_reloaded = await _reload(db_session, fresh.id)
    assert fresh_reloaded.status == "publishing"
    assert fresh_reloaded.locked_media_ids == [7]

    published_reloaded = await _reload(db_session, published.id)
    assert published_reloaded.status == "published"
    assert published_reloaded.locked_media_ids == [42]

    # 99 НЕ отпущен (отложен), 5/6 — отпущены пунктом 1 (unstuck stale).
    assert sorted(client.release_calls) == [5, 6]
    assert client.acquire_calls == [42]


@pytest.mark.asyncio
async def test_reconcile_releases_orphans_only_without_publishing_in_flight(db_session):
    """AUD6-P2-04, тихий прогон: ни одного отчёта в publishing — настоящий
    орфан снимается, как и раньше."""
    now = datetime.now(timezone.utc)
    published = _mk_report(
        "260725-352", status="published", locked_media_ids=[42],
        state_changed_at=now,
    )
    db_session.add(published)
    await db_session.commit()

    client = FakeMediaClient(list_locks_items=[{"id": 42}, {"id": 99}])
    result = await reconcile_publication_locks(db_session, client)

    assert result["orphaned_locks_released"] == 1
    assert result["orphan_release_deferred"] == 0
    assert client.release_calls == [99]


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


# ===========================================================================
# autopublish_ready_drafts — режим «без модерации»
# ===========================================================================


async def _seed_autopublish(
    db_session, *, enabled: bool, categories: list[str] | None = None
) -> None:
    import copy

    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data["work_reports"]["autopublish"] = enabled
    data["work_reports"]["categories"] = categories if categories is not None else []
    db_session.add(BoardConfig(id=1, data=data, updated_by=None))
    await db_session.commit()


@pytest.mark.asyncio
async def test_autopublish_disabled_is_a_noop(db_session):
    """Дефолт — выключено. Черновик обязан остаться в очереди."""
    await _seed_autopublish(db_session, enabled=False)
    db_session.add(_mk_request("260725-501"))
    report = _mk_report("260725-501")
    db_session.add(report)
    await db_session.commit()

    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1)], "completion_photo": [_photo(2)],
    })
    result = await autopublish_ready_drafts(db_session, client)

    assert result == {
        "published": 0, "left_for_moderation": 0, "skipped_by_category": 0,
        "failed": 0, "enabled": False,
    }
    assert (await _reload(db_session, report.id)).status == "pending"


@pytest.mark.asyncio
async def test_autopublish_publishes_draft_with_both_sides(db_session):
    await _seed_autopublish(db_session, enabled=True)
    db_session.add(_mk_request("260725-502"))
    report = _mk_report("260725-502")
    db_session.add(report)
    await db_session.commit()

    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1)], "completion_photo": [_photo(2)],
    })
    result = await autopublish_ready_drafts(db_session, client, triggered_by=MODERATOR_ID)

    assert result["published"] == 1
    assert result["left_for_moderation"] == 0
    reloaded = await _reload(db_session, report.id)
    assert reloaded.status == "published"
    # Медиа заморожены и залочены — режим не ослабляет ни одну гарантию саги.
    assert sorted(reloaded.locked_media_ids) == [1, 2]
    assert {m["id"] for m in reloaded.media_meta} == {1, 2}


@pytest.mark.asyncio
async def test_autopublish_audit_does_not_claim_human_approval(db_session):
    """Ключевое отличие от ручной публикации: `moderated_by` пуст, действие —
    `work_report.autopublish`, а инициатор режима лежит отдельным ключом. Иначе
    журнал выглядел бы как одобрение содержимого фото человеком."""
    await _seed_autopublish(db_session, enabled=True)
    db_session.add(_mk_request("260725-503"))
    report = _mk_report("260725-503")
    db_session.add(report)
    await db_session.commit()

    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1)], "completion_photo": [_photo(2)],
    })
    await autopublish_ready_drafts(db_session, client, triggered_by=MODERATOR_ID)

    reloaded = await _reload(db_session, report.id)
    assert reloaded.moderated_by is None

    entry = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "work_report.autopublish")
    )).scalars().one()
    assert entry.user_id is None
    assert entry.details["triggered_by"] == MODERATOR_ID
    assert entry.details["request_number"] == "260725-503"


@pytest.mark.asyncio
async def test_autopublish_publishes_draft_without_before_side(db_session):
    """Нет фото «до» — не препятствие: критерий готовности совпадает с
    publish_report (нужен результат), иначе работа не попала бы в ленту вовсе."""
    await _seed_autopublish(db_session, enabled=True)
    db_session.add(_mk_request("260725-504"))
    report = _mk_report("260725-504")
    db_session.add(report)
    await db_session.commit()

    client = FakeMediaClient(by_category={
        "request_photo": [], "completion_photo": [_photo(2)],
    })
    result = await autopublish_ready_drafts(db_session, client)

    assert result["published"] == 1
    assert result["left_for_moderation"] == 0
    assert (await _reload(db_session, report.id)).status == "published"


@pytest.mark.asyncio
async def test_autopublish_leaves_draft_without_result_for_moderation(db_session):
    """«Без модерации» не значит «опубликовать что угодно»: без фото РЕЗУЛЬТАТА
    карточка «работы выполнены» не имеет ни одного доказательства."""
    await _seed_autopublish(db_session, enabled=True)
    db_session.add(_mk_request("260725-505"))
    report = _mk_report("260725-505")
    db_session.add(report)
    await db_session.commit()

    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1)], "completion_photo": [],
    })
    result = await autopublish_ready_drafts(db_session, client)

    assert result["published"] == 0
    assert result["left_for_moderation"] == 1
    assert (await _reload(db_session, report.id)).status == "needs_media"


@pytest.mark.asyncio
async def test_autopublish_skips_ineligible_request_without_failing_batch(db_session):
    """Одна неудача не срывает пакет: заявка, переставшая быть eligible, даёт
    409 внутри publish_report, а следующий отчёт всё равно публикуется."""
    await _seed_autopublish(db_session, enabled=True)
    db_session.add(_mk_request("260725-505", is_returned=True))
    db_session.add(_mk_request("260725-506"))
    bad = _mk_report("260725-505")
    good = _mk_report("260725-506")
    db_session.add_all([bad, good])
    await db_session.commit()

    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1)], "completion_photo": [_photo(2)],
    })
    result = await autopublish_ready_drafts(db_session, client)

    assert result["published"] == 1
    assert result["failed"] == 1
    assert (await _reload(db_session, bad.id)).status == "pending"
    assert (await _reload(db_session, good.id)).status == "published"


@pytest.mark.asyncio
async def test_autopublish_survives_media_service_failure(db_session):
    """Сбой media-service не должен ронять весь пакет (а через него — и весь
    POST /sync, где рядом идут синк и ревокация, к media-service не относящиеся).
    Клиент бросает на любой не-2xx, поэтому перехват здесь широкий."""
    await _seed_autopublish(db_session, enabled=True)
    db_session.add(_mk_request("260725-507"))
    db_session.add(_mk_request("260725-508"))
    broken = _mk_report("260725-507")
    ok = _mk_report("260725-508")
    db_session.add_all([broken, ok])
    await db_session.commit()

    class HalfBrokenClient(FakeMediaClient):
        async def get_request_media(self, request_number, category, limit=50):
            if request_number == "260725-507":
                raise RuntimeError("media-service 404")
            return await super().get_request_media(request_number, category, limit)

    client = HalfBrokenClient(by_category={
        "request_photo": [_photo(1)], "completion_photo": [_photo(2)],
    })
    result = await autopublish_ready_drafts(db_session, client)

    assert result["published"] == 1
    assert result["failed"] == 1
    assert (await _reload(db_session, broken.id)).status == "pending"
    assert (await _reload(db_session, ok.id)).status == "published"


@pytest.mark.asyncio
async def test_autopublish_skips_report_outside_category_filter(db_session):
    """Черновик мог быть создан ДО того, как категорию убрали из списка (или
    вручную, минуя синк). Без повторной проверки здесь автопубликация уносила бы
    в открытую ленту категорию, которую владелец из ленты уже исключил."""
    await _seed_autopublish(db_session, enabled=True, categories=["cleaning"])
    db_session.add(_mk_request("260725-509"))
    # _mk_report по умолчанию кладёт category_key="plumbing" — вне списка.
    report = _mk_report("260725-509")
    db_session.add(report)
    await db_session.commit()

    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1)], "completion_photo": [_photo(2)],
    })
    result = await autopublish_ready_drafts(db_session, client)

    assert result["published"] == 0
    assert result["skipped_by_category"] == 1
    reloaded = await _reload(db_session, report.id)
    assert reloaded.status == "pending"
    # Медиа даже не подтягивались — до autofill дело не дошло.
    assert reloaded.media_synced_at is None


@pytest.mark.asyncio
async def test_autopublish_publishes_report_inside_category_filter(db_session):
    await _seed_autopublish(db_session, enabled=True, categories=["plumbing", "cleaning"])
    db_session.add(_mk_request("260725-510"))
    report = _mk_report("260725-510")  # plumbing — в списке
    db_session.add(report)
    await db_session.commit()

    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1)], "completion_photo": [_photo(2)],
    })
    result = await autopublish_ready_drafts(db_session, client)

    assert result["published"] == 1
    assert result["skipped_by_category"] == 0
    assert (await _reload(db_session, report.id)).status == "published"


@pytest.mark.asyncio
async def test_autopublish_empty_category_filter_means_no_restriction(db_session):
    """Пустой список = без ограничения (это фильтр, а пустой фильтр ничего не
    отсекает) — та же семантика, что в sync_pending_drafts и в UI."""
    await _seed_autopublish(db_session, enabled=True, categories=[])
    db_session.add(_mk_request("260725-511"))
    report = _mk_report("260725-511")
    db_session.add(report)
    await db_session.commit()

    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1)], "completion_photo": [_photo(2)],
    })
    result = await autopublish_ready_drafts(db_session, client)

    assert result["published"] == 1
    assert result["skipped_by_category"] == 0


@pytest.mark.asyncio
async def test_autopublish_batch_window_not_starved_by_filtered_out_drafts(db_session):
    """Фильтр в SQL, а не в Python после выборки: иначе черновики чужих
    категорий съедали бы окно пакета и подходящий отчёт не публиковался бы
    никогда. Проверяем на окне размером 1."""
    import uk_management_bot.services.work_report_service as svc

    await _seed_autopublish(db_session, enabled=True, categories=["cleaning"])
    # Более старый черновик чужой категории идёт первым по created_at.
    db_session.add(_mk_request("260725-512"))
    db_session.add(_mk_request("260725-513"))
    stale = _mk_report("260725-512")  # plumbing, вне списка
    wanted = _mk_report("260725-513")
    wanted.category_key = "cleaning"
    db_session.add_all([stale, wanted])
    await db_session.commit()

    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1)], "completion_photo": [_photo(2)],
    })
    original_limit = svc._AUTOPUBLISH_BATCH_LIMIT
    svc._AUTOPUBLISH_BATCH_LIMIT = 1
    try:
        result = await autopublish_ready_drafts(db_session, client)
    finally:
        svc._AUTOPUBLISH_BATCH_LIMIT = original_limit

    assert result["published"] == 1
    assert (await _reload(db_session, wanted.id)).status == "published"
    assert (await _reload(db_session, stale.id)).status == "pending"


# ── прогрев превью ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_warms_previews_for_its_media(db_session):
    """Житель часто открывает витрину сразу после публикации, а тик придёт лишь
    через 10 минут — поэтому превью греются в самой публикации."""
    db_session.add(_mk_request("260725-w01"))
    report = _mk_report("260725-w01", before_media_ids=[1, 2], after_media_ids=[10])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    client = FakeMediaClient(by_category={
        "request_photo": [_photo(1), _photo(2)],
        "completion_photo": [_photo(10)],
    })

    await publish_report(db_session, client, report.id, MODERATOR_ID)

    assert client.warm_calls == [[1, 2, 10]]


@pytest.mark.asyncio
async def test_publish_survives_failing_warm(db_session):
    """Прогрев — оптимизация: его сбой не имеет права откатить публикацию."""
    db_session.add(_mk_request("260725-w02"))
    report = _mk_report("260725-w02", before_media_ids=[1], after_media_ids=[10])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    class WarmBroken(FakeMediaClient):
        async def warm_previews(self, media_ids):
            raise RuntimeError("media-service down")

    client = WarmBroken(by_category={
        "request_photo": [_photo(1)],
        "completion_photo": [_photo(10)],
    })

    result = await publish_report(db_session, client, report.id, MODERATOR_ID)

    assert result.status == "published"


@pytest.mark.asyncio
async def test_warm_recent_previews_covers_published_only(db_session):
    """Догрев в тике берёт только опубликованные — черновики в ленту не идут,
    греть их нечего."""
    from uk_management_bot.services.work_report_service import warm_recent_previews

    published = _mk_report("260725-w03", status="published", before_media_ids=[10],
                           after_media_ids=[11])
    published.published_at = datetime.now(timezone.utc)
    db_session.add(published)
    db_session.add(_mk_report("260725-w04", status="pending", before_media_ids=[20],
                              after_media_ids=[21]))
    await db_session.commit()
    client = FakeMediaClient()

    await warm_recent_previews(db_session, client)

    assert client.warm_calls == [[10, 11]]


@pytest.mark.asyncio
async def test_warm_recent_previews_noop_without_published(db_session):
    from uk_management_bot.services.work_report_service import warm_recent_previews

    client = FakeMediaClient()
    assert await warm_recent_previews(db_session, client) == {}
    assert client.warm_calls == []


@pytest.mark.asyncio
async def test_warm_is_chunked_to_survive_client_timeout(db_session):
    """Прогрев дробится на пачки.

    Регрессия profk: 48 id одним запросом — это ~70 с скачиваний, а у клиента
    media-service таймаут 30 с, и прогрев не срабатывал вовсе (в логах пустая
    ошибка ReadTimeout).
    """
    from uk_management_bot.services.work_report_service import (
        _WARM_CHUNK, warm_recent_previews,
    )

    now = datetime.now(timezone.utc)
    for i in range(6):
        r = _mk_report(f"260725-c{i:02d}", status="published",
                       before_media_ids=[i * 2 + 1], after_media_ids=[i * 2 + 2])
        r.published_at = now
        db_session.add(r)
    await db_session.commit()
    client = FakeMediaClient()

    result = await warm_recent_previews(db_session, client)

    assert len(client.warm_calls) > 1, "12 id должны уйти несколькими пачками"
    assert all(len(c) <= _WARM_CHUNK for c in client.warm_calls)
    # Ни один id не потерян и не продублирован.
    flat = [m for c in client.warm_calls for m in c]
    assert sorted(flat) == list(range(1, 13))
    assert result["warmed"] == 12


@pytest.mark.asyncio
async def test_failed_chunk_is_counted_not_hidden(db_session):
    """Сбой пачки не должен выглядеть как успех: клиент глотает исключение и
    возвращает пустой dict, поэтому пустой ответ считаем провалом всей пачки."""
    from uk_management_bot.services.work_report_service import warm_recent_previews

    r = _mk_report("260725-c99", status="published", before_media_ids=[1],
                   after_media_ids=[2])
    r.published_at = datetime.now(timezone.utc)
    db_session.add(r)
    await db_session.commit()

    class WarmSilentlyFails(FakeMediaClient):
        async def warm_previews(self, media_ids):
            self.warm_calls.append(list(media_ids))
            return {}

    result = await warm_recent_previews(db_session, WarmSilentlyFails())

    assert result == {"warmed": 0, "already_cached": 0, "failed": 2}


@pytest.mark.asyncio
async def test_publish_compensates_on_transport_failure_during_validate(db_session):
    """AUD6-P1-3: валидация теперь идёт ПОСЛЕ флипа в publishing (сеть — без
    row-лока). Любой сбой шага, включая транспортный, обязан откатить отчёт в
    pending: ни один publication-lock ещё не взят, и парковать отчёт в
    publishing до reconcile незачем. Исходное исключение — наружу как есть."""
    db_session.add(_mk_request("260725-390"))
    report = _mk_report("260725-390", before_media_ids=[1], after_media_ids=[2])
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    class TransportDownClient(FakeMediaClient):
        async def get_request_media(self, request_number, category=None, limit=50):
            raise RuntimeError("media-service unreachable")

    with pytest.raises(RuntimeError, match="unreachable"):
        await publish_report(db_session, TransportDownClient(), report.id, MODERATOR_ID)

    await db_session.refresh(report)
    assert report.status == "pending", "транспортный сбой не должен парковать в publishing"
    assert report.locked_media_ids == []
