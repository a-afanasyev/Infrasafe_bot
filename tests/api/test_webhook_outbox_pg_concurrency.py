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

# ARCH-010 (доменная фикстура pg_domain_factory ниже):
from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.rating import Rating

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


# ===========================================================================
# ARCH-010: ON CONFLICT-дедуп + конкурентные версии под настоящим Postgres.
# Отдельная фикстура: доменные таблицы (users/yards/buildings/apartments/
# requests/assignments/audit/shifts) в той же temp-схеме — update_building и
# workflow на голом webhook_outbox-харнессе не запускаются.
# ===========================================================================

_DOMAIN_TABLES = [
    User.__table__, Yard.__table__, Building.__table__, Apartment.__table__,
    UserApartment.__table__, Request.__table__, RequestAssignment.__table__,
    AuditLog.__table__, ShiftTemplate.__table__, Shift.__table__,
    Rating.__table__, WebhookOutbox.__table__,
]


@pytest_asyncio.fixture
async def pg_domain_factory(monkeypatch):
    """Как pg_factory, но с полным доменным подмножеством таблиц (ARCH-010)."""
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
                lambda sc: Base.metadata.create_all(
                    sc, tables=_DOMAIN_TABLES, checkfirst=True
                )
            )
    except Exception as exc:  # pragma: no cover - host without reachable PG
        await engine.dispose()
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(webhook_sender.settings, "INFRASAFE_WEBHOOK_ENABLED", True)

    yield factory

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    await engine.dispose()


@pytest.mark.asyncio
async def test_on_conflict_double_enqueue_single_row_pg(pg_domain_factory):
    """ARCH-010 §5: двойной enqueue одного логического события под Postgres —
    ровно одна outbox-строка, без IntegrityError."""
    from uk_management_bot.services.webhook_sender import EventIdentity, queue_webhook

    async with pg_domain_factory() as db:
        for _ in range(2):
            await queue_webhook(
                db, "building.updated", "/api/webhooks/uk/building",
                {"id": 1, "address": "A", "yard_name": "Y"},
                EventIdentity(version=7),
            )
        await db.commit()
        rows = (await db.execute(select(WebhookOutbox))).scalars().all()
    assert len(rows) == 1


async def _seed_building(factory) -> int:
    async with factory() as db:
        db.add(User(id=2, telegram_id=2, first_name="U",
                    roles='["manager"]', active_role="manager",
                    status="approved", language="ru"))
        db.add(Yard(id=1, name="Y", is_active=True, created_by=2))
        db.add(Building(id=1, yard_id=1, address="A0", is_active=True,
                        created_by=2))
        await db.commit()
    return 1


@pytest.mark.asyncio
async def test_concurrent_update_building_serialized_versions(
    pg_domain_factory, monkeypatch
):
    """ARCH-010 §3 (P1-B): два конкурентных update_building сериализуются
    FOR UPDATE'ом — разные версии, разные event_id, payload второго несёт
    СВОИ поля (не stale-поля первого).

    Синхронизация: A захватил лок и запаузен внутри транзакции (в
    enqueue_outbox) → стартует B → B ЖДЁТ на SELECT FOR UPDATE
    (таймаут-проверка) → release → A коммитит → B продолжает."""
    from uk_management_bot.services.addresses import core

    building_id = await _seed_building(pg_domain_factory)

    async def _noop(event, data):
        return None

    monkeypatch.setattr(core, "publish_realtime_after_commit", _noop)

    a_inside = asyncio.Event()
    release_a = asyncio.Event()
    calls = {"n": 0}
    orig_enqueue = core.enqueue_outbox

    async def paced_enqueue(db, *, event, data, identity=None):
        calls["n"] += 1
        if calls["n"] == 1:  # первый — сессия A, пауза ПОД row-lock'ом
            a_inside.set()
            await release_a.wait()
        await orig_enqueue(db, event=event, data=data, identity=identity)

    monkeypatch.setattr(core, "enqueue_outbox", paced_enqueue)

    async def run_update(address: str):
        async with pg_domain_factory() as db:
            await core.update_building(db, building_id, {"address": address})

    task_a = asyncio.create_task(run_update("A1"))
    await asyncio.wait_for(a_inside.wait(), timeout=10)

    task_b = asyncio.create_task(run_update("B1"))
    await asyncio.sleep(0.3)
    assert not task_b.done(), "B должен ждать на SELECT FOR UPDATE, пока A держит лок"

    release_a.set()
    await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=15)

    async with pg_domain_factory() as db:
        bld = await db.get(Building, building_id)
        assert bld.building_version == 2
        assert bld.address == "B1"  # B выиграл вторым, его поля не потеряны
        rows = (await db.execute(
            select(WebhookOutbox).where(WebhookOutbox.event == "building.updated")
        )).scalars().all()
    assert len(rows) == 2
    ids = {r.event_id for r in rows}
    assert len(ids) == 2, "конкурентные версии обязаны дать разные event_id"
    addresses = {r.payload["building"]["address"] for r in rows}
    assert addresses == {"A1", "B1"}, "payload второго несёт свои поля, не stale"


@pytest.mark.asyncio
async def test_concurrent_status_transitions_serialized_versions(
    pg_domain_factory, monkeypatch
):
    """ARCH-010 §7: два конкурентных транзишна одной заявки под существующим
    with_for_update. Легальная цепочка: A = MANAGER_ASSIGN (Новая→В работе),
    B = EXECUTOR_COMPLETE (В работе→Выполнена) — B валиден только ПОСЛЕ
    коммита A. Разные status_version, разные event_id, обе строки в outbox."""
    from datetime import datetime, timezone as tz

    import uk_management_bot.services.workflow_runner as wr
    import uk_management_bot.utils.constants as C
    from uk_management_bot.utils.request_workflow import Action, ActionCommand, PrincipalRef

    async with pg_domain_factory() as db:
        db.add(User(id=2, telegram_id=2, first_name="Owner",
                    roles='["applicant"]', active_role="applicant",
                    status="approved", language="ru"))
        db.add(User(id=3, telegram_id=3, first_name="Mgr",
                    roles='["manager"]', active_role="manager",
                    status="approved", language="ru"))
        db.add(User(id=4, telegram_id=4, first_name="Exec",
                    roles='["executor"]', active_role="executor",
                    status="approved", language="ru"))
        db.add(Request(request_number="260723-001", user_id=2, category="c",
                       description="d", urgency="low",
                       status=C.REQUEST_STATUS_NEW))
        # start_time в прошлом: is_on_shift_now сравнивает с naive datetime.now()
        # (см. utils/shifts.py) — «сегодняшняя полночь UTC» может быть ещё будущим.
        db.add(Shift(user_id=4, status="active",
                     start_time=datetime(2026, 6, 10, 8, 0, tzinfo=tz.utc)))
        await db.commit()

    a_inside = asyncio.Event()
    release_a = asyncio.Event()
    calls = {"n": 0}
    orig_emit = wr.emit_request_status_changed

    async def paced_emit(db, request_number, old, new, source, identity=None):
        calls["n"] += 1
        if calls["n"] == 1:  # первый emit — транзакция A, пауза под локом
            a_inside.set()
            await release_a.wait()
        await orig_emit(db, request_number, old, new, source, identity=identity)

    monkeypatch.setattr(wr, "emit_request_status_changed", paced_emit)

    mgr = PrincipalRef(kind="user", user_id=3, source="telegram")
    executor = PrincipalRef(kind="user", user_id=4, source="telegram")

    task_a = asyncio.create_task(wr.run_command_async(
        pg_domain_factory, "260723-001", mgr,
        ActionCommand("a", Action.MANAGER_ASSIGN, {"executor_id": 4})))
    await asyncio.wait_for(a_inside.wait(), timeout=10)

    task_b = asyncio.create_task(wr.run_command_async(
        pg_domain_factory, "260723-001", executor,
        ActionCommand("b", Action.EXECUTOR_COMPLETE,
                      {"completion_report": "done"})))
    await asyncio.sleep(0.3)
    assert not task_b.done(), "B должен ждать на with_for_update, пока A держит лок"

    release_a.set()
    await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=15)

    async with pg_domain_factory() as db:
        req = (await db.execute(
            select(Request).where(Request.request_number == "260723-001")
        )).scalar_one()
        assert req.status == C.REQUEST_STATUS_EXECUTED
        assert req.status_version == 2
        rows = (await db.execute(
            select(WebhookOutbox).where(
                WebhookOutbox.event == "request.status_changed")
        )).scalars().all()
    assert len(rows) == 2
    assert len({r.event_id for r in rows}) == 2
