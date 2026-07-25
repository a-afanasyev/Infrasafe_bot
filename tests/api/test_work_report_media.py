"""Тесты `work_report_service.autofill_media` / `validate_media_ids` (T5).

`autofill_media` молча фильтрует автоматически найденных кандидатов (не
человеческий выбор); `validate_media_ids` на тех же условиях REJECTS явный
выбор человека. Единый `FakeMediaClient` — простая замена httpx-клиента,
никакой реальной сети.
"""
from datetime import datetime, timezone

import pytest

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.services.work_report_service import (
    MAX_MEDIA_PER_SIDE,
    MediaValidationError,
    autofill_media,
    validate_media_ids,
)


def _photo(id_, *, file_type="photo", status="active", file_size=1024):
    return {"id": id_, "file_type": file_type, "status": status, "file_size": file_size}


class FakeMediaClient:
    """Заглушка media_client: `get_request_media(request_number, category, limit)`
    возвращает предзаданный список по категории, игнорируя request_number."""

    def __init__(self, by_category: dict[str, list[dict]]):
        self._by_category = by_category
        self.calls: list[tuple[str, str, int]] = []

    async def get_request_media(self, request_number: str, category: str, limit: int = 50):
        self.calls.append((request_number, category, limit))
        return self._by_category.get(category, [])


def _mk_report(status: str = "pending") -> WorkReport:
    return WorkReport(
        id=1,
        request_number="260725-001",
        category_key="plumbing",
        address_public="test",
        performed_at=datetime.now(timezone.utc),
        before_media_ids=[],
        after_media_ids=[],
        media_meta=[],
        locked_media_ids=[],
        status=status,
        source="auto",
    )


# ── autofill_media: filtering ───────────────────────────────────────


@pytest.mark.asyncio
async def test_autofill_filters_non_photo_inactive_oversized_and_unknown_size():
    oversized = settings.PUBLIC_MEDIA_MAX_BYTES + 1
    client = FakeMediaClient({
        "request_photo": [
            _photo(1),
            _photo(2, file_type="video"),
            _photo(3, status="archived"),
            _photo(4, file_size=oversized),
            _photo(5, file_size=None),
        ],
        "completion_photo": [_photo(10)],
    })
    report = _mk_report()

    result = await autofill_media(None, client, report)

    assert result.before_media_ids == [1]
    assert result.after_media_ids == [10]


@pytest.mark.asyncio
async def test_autofill_caps_at_max_media_per_side_keeping_first_n():
    items = [_photo(i) for i in range(1, 10)]  # 9 eligible items
    client = FakeMediaClient({"request_photo": items, "completion_photo": items})
    report = _mk_report()

    result = await autofill_media(None, client, report)

    assert result.before_media_ids == [1, 2, 3, 4]
    assert result.after_media_ids == [1, 2, 3, 4]
    assert len(result.before_media_ids) == MAX_MEDIA_PER_SIDE


@pytest.mark.asyncio
async def test_autofill_fetch_limit_is_larger_than_cap():
    client = FakeMediaClient({"request_photo": [], "completion_photo": []})
    report = _mk_report()

    await autofill_media(None, client, report)

    for _, _, limit in client.calls:
        assert limit == MAX_MEDIA_PER_SIDE * 4


# ── autofill_media: status flips ────────────────────────────────────


@pytest.mark.asyncio
async def test_autofill_flips_pending_to_needs_media_when_one_side_empty():
    client = FakeMediaClient({"request_photo": [_photo(1)], "completion_photo": []})
    report = _mk_report(status="pending")

    result = await autofill_media(None, client, report)

    assert result.status == "needs_media"


@pytest.mark.asyncio
async def test_autofill_flips_needs_media_back_to_pending_when_both_sides_filled():
    client = FakeMediaClient({"request_photo": [_photo(1)], "completion_photo": [_photo(2)]})
    report = _mk_report(status="needs_media")

    result = await autofill_media(None, client, report)

    assert result.status == "pending"


@pytest.mark.parametrize("status", ["publishing", "published", "needs_review", "rejected"])
@pytest.mark.asyncio
async def test_autofill_leaves_other_statuses_alone_even_if_media_empty(status):
    client = FakeMediaClient({"request_photo": [], "completion_photo": []})
    report = _mk_report(status=status)

    result = await autofill_media(None, client, report)

    assert result.status == status


@pytest.mark.asyncio
async def test_autofill_sets_media_synced_at():
    client = FakeMediaClient({"request_photo": [_photo(1)], "completion_photo": [_photo(2)]})
    report = _mk_report()
    report.media_synced_at = None

    result = await autofill_media(None, client, report)

    assert result.media_synced_at is not None


@pytest.mark.asyncio
async def test_autofill_does_not_trust_preexisting_state():
    """Always re-fetches from media-service — stale ids on `report` before
    the call must be fully replaced, not merged."""
    client = FakeMediaClient({"request_photo": [_photo(99)], "completion_photo": [_photo(98)]})
    report = _mk_report()
    report.before_media_ids = [1, 2, 3]
    report.after_media_ids = [4, 5, 6]

    result = await autofill_media(None, client, report)

    assert result.before_media_ids == [99]
    assert result.after_media_ids == [98]


# ── validate_media_ids ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_passes_silently_when_everything_valid():
    client = FakeMediaClient({
        "request_photo": [_photo(1), _photo(2)],
        "completion_photo": [_photo(3)],
    })

    await validate_media_ids(client, "260725-001", [1, 2], [3])  # no raise


@pytest.mark.asyncio
async def test_validate_raises_on_id_from_different_request_or_category():
    client = FakeMediaClient({"request_photo": [_photo(1)], "completion_photo": [_photo(3)]})

    with pytest.raises(MediaValidationError):
        await validate_media_ids(client, "260725-001", [999], [3])


@pytest.mark.asyncio
async def test_validate_raises_on_non_photo():
    client = FakeMediaClient({"request_photo": [_photo(1, file_type="video")], "completion_photo": []})

    with pytest.raises(MediaValidationError):
        await validate_media_ids(client, "260725-001", [1], [])


@pytest.mark.asyncio
async def test_validate_raises_on_inactive():
    client = FakeMediaClient({"request_photo": [_photo(1, status="archived")], "completion_photo": []})

    with pytest.raises(MediaValidationError):
        await validate_media_ids(client, "260725-001", [1], [])


@pytest.mark.asyncio
async def test_validate_raises_on_missing_file_size():
    client = FakeMediaClient({"request_photo": [_photo(1, file_size=None)], "completion_photo": []})

    with pytest.raises(MediaValidationError):
        await validate_media_ids(client, "260725-001", [1], [])


@pytest.mark.asyncio
async def test_validate_raises_on_oversized_file():
    oversized = settings.PUBLIC_MEDIA_MAX_BYTES + 1
    client = FakeMediaClient({"request_photo": [_photo(1, file_size=oversized)], "completion_photo": []})

    with pytest.raises(MediaValidationError):
        await validate_media_ids(client, "260725-001", [1], [])


@pytest.mark.asyncio
async def test_validate_checks_after_side_independently():
    client = FakeMediaClient({"request_photo": [_photo(1)], "completion_photo": [_photo(2, file_type="video")]})

    with pytest.raises(MediaValidationError):
        await validate_media_ids(client, "260725-001", [1], [2])
