"""PR-5 — РЕАЛЬНАЯ гонка двух конкурентных воркеров против PostgreSQL.

SQLite не имеет row-locking (SQLAlchemy молча выбрасывает FOR UPDATE), поэтому
этот файл гоняет claim/lease-машину против настоящего Postgres:

  * медленный получатель НЕ блокирует второй воркер — пока worker A держит
    свои claims в HTTP-фазе, worker B клеймит и доставляет ДРУГИЕ записи;
  * каждый event_id доставлен ровно один раз (claims дизъюнктны);
  * reclaim после lease работает и под Postgres.

Изоляция: собственная temp-схема (pr5_outbox_test) в той же БД — таблицы
создаются schema_translate_map'ом, живой бот/обвязка работают в public и не
видят тестовые строки. Скип, если DATABASE_URL не Postgres / недоступен
(локальный хост вне контейнера). В CI backend-tests Postgres-сервис есть.
"""
import asyncio
import os
import uuid
from collections import Counter

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from uk_management_bot.database.models.webhook_outbox import WebhookOutbox
from uk_management_bot.services import webhook_sender

SCHEMA = "pr5_outbox_test"

# ЛОВУШКА import-order: tests/services/conftest.py при старте сессии
# перетирает os.environ["DATABASE_URL"] на sqlite. Настоящий postgres-URL
# сохранён в POSTGRES_TEST_URL conftest'ом tests/api (грузится первым при
# каноническом `pytest tests/api tests/services`); можно задать и снаружи.


def _pg_url() -> str | None:
    url = os.getenv("POSTGRES_TEST_URL", "")
    if not url.startswith("postgresql"):
        return None
    return url.replace("postgresql://", "postgresql+asyncpg://")


@pytest_asyncio.fixture
async def pg_factory(monkeypatch):
    """Session factory на temp-схеме Postgres; skip без Postgres."""
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
            await conn.run_sync(
                lambda sc: WebhookOutbox.__table__.create(sc, checkfirst=True)
            )
    except Exception as exc:  # pragma: no cover - host without reachable PG
        await engine.dispose()
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    monkeypatch.setattr("uk_management_bot.database.session.AsyncSessionLocal", factory)
    monkeypatch.setattr(webhook_sender.settings, "INFRASAFE_WEBHOOK_ENABLED", True)
    monkeypatch.setattr(webhook_sender.settings, "INFRASAFE_WEBHOOK_URL", "http://infrasafe.test")
    monkeypatch.setattr(webhook_sender.settings, "INFRASAFE_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setattr(webhook_sender.settings, "INFRASAFE_USE_NEXT_SECRET", False)

    yield factory

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    await engine.dispose()


async def _seed(factory, n: int) -> None:
    async with factory() as db:
        for i in range(n):
            db.add(WebhookOutbox(
                event_id=str(uuid.uuid4()),  # varchar(36) — без префиксов
                event="building.created",
                endpoint="/api/webhooks/uk/building",
                payload={"event": "building.created", "i": i},
                status="pending",
            ))
        await db.commit()


@pytest.mark.asyncio
async def test_slow_receiver_does_not_block_second_worker(pg_factory, monkeypatch):
    """Worker A висит в HTTP (медленный получатель) → worker B параллельно
    клеймит и доставляет другие записи, не дожидаясь A (CODE-01 закрыт:
    раньше лок A держал весь батч, и B пропускал ВСЁ)."""
    delivered = Counter()
    a_started = asyncio.Event()
    release_a = asyncio.Event()
    call_no = 0

    async def fake_send(url, payload, secret, client):
        nonlocal call_no
        call_no += 1
        delivered[payload["i"]] += 1
        if call_no == 1:  # первый вызов worker'а A — «зависший» получатель
            a_started.set()
            await release_a.wait()
        return (True, "", False, 0)

    monkeypatch.setattr(webhook_sender, "send_webhook", fake_send)
    monkeypatch.setattr(webhook_sender.settings, "INFRASAFE_OUTBOX_CLAIM_BATCH", 5)
    monkeypatch.setattr(webhook_sender.settings, "INFRASAFE_OUTBOX_CONCURRENCY", 1)

    await _seed(pg_factory, 10)

    worker_a = asyncio.create_task(webhook_sender.process_outbox())
    await asyncio.wait_for(a_started.wait(), timeout=10)

    # A висит в HTTP со своим claim-батчем. B должен пройти СЕЙЧАС.
    worker_b = asyncio.create_task(webhook_sender.process_outbox())
    await asyncio.wait_for(worker_b, timeout=15)

    async with pg_factory() as db:
        sent_by_b = (await db.execute(
            select(WebhookOutbox).where(WebhookOutbox.status == "sent")
        )).scalars().all()
    # B доставил свои записи, пока A ещё держит первый claim в полёте.
    assert len(sent_by_b) >= 5, "second worker was blocked by the slow receiver"

    release_a.set()
    await asyncio.wait_for(worker_a, timeout=15)

    # Exactly-once: ни одна запись не доставлена дважды.
    assert all(count == 1 for count in delivered.values()), delivered
    async with pg_factory() as db:
        records = (await db.execute(select(WebhookOutbox))).scalars().all()
    assert len(records) == 10
    assert all(r.status == "sent" for r in records)
    assert all(r.attempts == 0 for r in records)


@pytest.mark.asyncio
async def test_two_workers_drain_disjoint_slices(pg_factory, monkeypatch):
    """Два воркера одновременно: суммарно каждый event ровно один раз."""
    delivered = Counter()

    async def fake_send(url, payload, secret, client):
        await asyncio.sleep(0.01)  # дать второму воркеру шанс на пересечение
        delivered[payload["i"]] += 1
        return (True, "", False, 0)

    monkeypatch.setattr(webhook_sender, "send_webhook", fake_send)
    monkeypatch.setattr(webhook_sender.settings, "INFRASAFE_OUTBOX_CLAIM_BATCH", 5)

    await _seed(pg_factory, 30)

    await asyncio.wait_for(asyncio.gather(
        webhook_sender.process_outbox(),
        webhook_sender.process_outbox(),
    ), timeout=30)

    assert sum(delivered.values()) == 30
    assert all(count == 1 for count in delivered.values()), delivered


@pytest.mark.asyncio
async def test_reclaim_after_lease_under_postgres(pg_factory, monkeypatch):
    """Протухший in_flight (упавший воркер) реклеймится и доставляется."""
    from datetime import datetime, timedelta, timezone

    async def fake_send(url, payload, secret, client):
        return (True, "", False, 0)

    monkeypatch.setattr(webhook_sender, "send_webhook", fake_send)
    lease = webhook_sender.settings.INFRASAFE_OUTBOX_LEASE_SECONDS

    async with pg_factory() as db:
        db.add(WebhookOutbox(
            event_id="pg-stale-1",
            event="building.created",
            endpoint="/api/webhooks/uk/building",
            payload={"event": "building.created", "i": 0},
            status="in_flight",
            claim_token=str(uuid.uuid4()),
            claimed_at=datetime.now(timezone.utc) - timedelta(seconds=lease + 60),
            claim_count=1,
        ))
        await db.commit()

    await webhook_sender.process_outbox()

    async with pg_factory() as db:
        rec = (await db.execute(
            select(WebhookOutbox).where(WebhookOutbox.event_id == "pg-stale-1")
        )).scalar_one()
    assert rec.status == "sent"
    assert rec.claim_count == 2
    assert rec.attempts == 0
