"""A9-P2-1 / A9-P2-18 — маркер фото заявки под НАСТОЯЩЕЙ конкуренцией (Postgres).

SQLite не знает row-lock'ов (FOR UPDATE там no-op), поэтому гонку двух
загрузок в одну заявку честно проверить можно только на Postgres. Сценарий
повторяет эндпоинт: каждая «загрузка» — своя сессия, в которой гейт доступа
(`check_request_access`) уже загрузил `Request` в identity map, и только потом
`_append_media_marker` берёт строку `FOR UPDATE`. Без `populate_existing`
вторая сессия дождалась бы лока, но ORM отдал бы ей устаревший `media_files`
из identity map — и маркер первой загрузки был бы затёрт.

Скип и изоляция — как у образца `test_webhook_outbox_pg_concurrency.py`:
URL из POSTGRES_TEST_URL (его выставляет conftest tests/api из DATABASE_URL),
собственная temp-схема; без Postgres — skip. В CI backend-tests Postgres есть.
"""
import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import uk_management_bot.api.main  # noqa: F401  # регистрирует все модели в Base.metadata
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base

SCHEMA = "a9_media_marker_test"
RN = "260922-801"


def _pg_url() -> str | None:
    url = os.getenv("POSTGRES_TEST_URL", "")
    if not url.startswith("postgresql"):
        return None
    return url.replace("postgresql://", "postgresql+asyncpg://")


@pytest_asyncio.fixture
async def pg_factory():
    url = _pg_url()
    if url is None:
        pytest.skip("DATABASE_URL is not PostgreSQL — real-race suite skipped")

    engine = create_async_engine(
        url,
        execution_options={"schema_translate_map": {None: SCHEMA}},
        pool_size=10,
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
            await conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
            await conn.run_sync(lambda sc: Base.metadata.create_all(sc, checkfirst=True))
    except Exception as exc:  # pragma: no cover - host without reachable PG
        await engine.dispose()
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    await engine.dispose()


async def _seed(factory) -> User:
    async with factory() as db:
        manager = User(telegram_id=801, first_name="Mgr", roles='["manager"]',
                       active_role="manager", status="approved", language="ru")
        db.add(manager)
        await db.flush()
        db.add(Request(request_number=RN, user_id=manager.id, category="c",
                       description="d", urgency="low", status="Новая",
                       media_files=[]))
        await db.commit()
        return manager


@pytest.mark.asyncio
async def test_two_concurrent_uploads_keep_both_markers(pg_factory):
    from uk_management_bot.api.dependencies_access import check_request_access
    from uk_management_bot.api.routes.media_proxy import _append_media_marker

    manager = await _seed(pg_factory)
    both_loaded = asyncio.Event()
    loaded_count = 0

    async def upload(media_id: int) -> None:
        nonlocal loaded_count
        async with pg_factory() as db:
            # Как в эндпоинте: гейт загрузил строку, ссылка жива до записи.
            request = await check_request_access(RN, db, manager)
            loaded_count += 1
            if loaded_count == 2:
                both_loaded.set()
            # Обе сессии прочитали media_files=[] ДО того, как кто-то записал.
            await asyncio.wait_for(both_loaded.wait(), timeout=10)
            await _append_media_marker(db, RN, media_id, "photo")
            assert request is not None

    await asyncio.wait_for(asyncio.gather(upload(1), upload(2)), timeout=20)

    async with pg_factory() as db:
        row = (await db.execute(select(Request).where(Request.request_number == RN))).scalar_one()
    assert sorted(m["media_id"] for m in row.media_files) == [1, 2], row.media_files
