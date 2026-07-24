"""Смоук-тест ORM модели `WorkReport` (T1: миграция + модель, тёмными).

Модель нигде не используется (dark/inactive) — сервисный слой в следующих
задачах. Здесь только проверка, что Base.metadata.create_all собирает таблицу
и что дефолты/констрейнты, заданные в модели, реально применяются на sqlite
(тестовый движок conftest'а).
"""
import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from uk_management_bot.database.models.work_report import WorkReport

pytestmark = pytest.mark.asyncio


def _report(**overrides) -> WorkReport:
    kwargs = dict(
        request_number="260725-001",
        category_key="plumbing",
        address_public="ул. Тестовая, 1",
        performed_at=datetime.datetime(2026, 7, 25, tzinfo=datetime.timezone.utc),
    )
    kwargs.update(overrides)
    return WorkReport(**kwargs)


async def test_roundtrip_with_defaults(db_session):
    db_session.add(_report())
    await db_session.commit()

    row = (await db_session.execute(select(WorkReport))).scalar_one()
    assert row.id is not None
    assert row.request_number == "260725-001"
    assert row.category_key == "plumbing"
    assert row.address_public == "ул. Тестовая, 1"
    assert row.performed_at is not None
    # JSON list defaults
    assert row.before_media_ids == []
    assert row.after_media_ids == []
    assert row.media_meta == []
    assert row.locked_media_ids == []
    # status/source defaults
    assert row.status == "pending"
    assert row.source == "manual"
    assert row.reject_reason is None
    assert row.created_at is not None
    assert row.published_at is None
    assert row.media_synced_at is None
    assert row.state_changed_at is None
    assert row.moderated_by is None


async def test_media_fields_roundtrip_as_json_lists(db_session):
    media_meta = [{"id": 1, "file_type": "photo", "mime": "image/jpeg", "size": 12345}]
    db_session.add(_report(
        request_number="260725-002",
        before_media_ids=[1, 2],
        after_media_ids=[3, 4],
        media_meta=media_meta,
        locked_media_ids=[3, 4],
        status="published",
        source="auto",
    ))
    await db_session.commit()

    row = await db_session.scalar(
        select(WorkReport).where(WorkReport.request_number == "260725-002")
    )
    assert row.before_media_ids == [1, 2]
    assert row.after_media_ids == [3, 4]
    assert row.media_meta == media_meta
    assert row.locked_media_ids == [3, 4]
    assert row.status == "published"
    assert row.source == "auto"


async def test_request_number_unique(db_session):
    db_session.add(_report(request_number="260725-003"))
    await db_session.commit()

    db_session.add(_report(request_number="260725-003"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_status_check_constraint_rejects_unknown_value(db_session):
    db_session.add(_report(request_number="260725-004", status="bogus"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_source_check_constraint_rejects_unknown_value(db_session):
    db_session.add(_report(request_number="260725-005", source="bogus"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
