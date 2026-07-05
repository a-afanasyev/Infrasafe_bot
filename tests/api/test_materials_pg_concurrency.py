"""РЕАЛЬНЫЕ гонки складского учёта против PostgreSQL (паттерн PR-5 outbox).

SQLite не имеет row-locking (FOR UPDATE молча выбрасывается), поэтому здесь
настоящий Postgres и две подлинные гонки:

  (а) два конкурентных списания одной партии — суммарно списано не больше
      остатка, qty_remaining >= 0, инвариант qty_remaining = qty − SUM(alloc);
  (б) два параллельных сторно одного расхода — surplus-партии созданы ровно
      один раз, второй запрос получает MaterialConflictError (лок исходного
      issue FOR UPDATE сериализует проверку «уже сторнирован»).

Изоляция: собственная temp-схема в той же БД (schema_translate_map).
Скип, если DATABASE_URL не Postgres (см. POSTGRES_TEST_URL в conftest).
"""
import asyncio
import os
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from uk_management_bot.database.models.material import (
    Material,
    MaterialIssue,
    MaterialIssueAllocation,
    MaterialReceipt,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services import material_service
from uk_management_bot.services.material_service import (
    InsufficientStockError,
    MaterialConflictError,
)

SCHEMA = "materials_race_test"

_TABLES = [
    User.__table__,
    Material.__table__,
    MaterialReceipt.__table__,
    MaterialIssue.__table__,
    MaterialIssueAllocation.__table__,
]


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
            await conn.run_sync(
                lambda sc: Base.metadata.create_all(sc, tables=_TABLES)
            )
    except Exception as exc:  # pragma: no cover — хост без доступного PG
        await engine.dispose()
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    await engine.dispose()


async def _seed(factory) -> tuple[int, int]:
    """user + материал; партии добавляют сами тесты."""
    async with factory() as db:
        user = User(telegram_id=424242, username="race", first_name="Race",
                    roles='["manager"]', active_role="manager", status="approved")
        db.add(user)
        await db.flush()
        material = Material(name="Гоночный материал", unit="pcs")
        db.add(material)
        await db.flush()
        ids = (user.id, material.id)
        await db.commit()
    return ids


async def _issue(factory, material_id: int, user_id: int, qty: str):
    async with factory() as db:
        try:
            await material_service.issue_material(
                db, material_id=material_id, qty=qty, created_by=user_id,
                doc_type="household", reason="гонка",
            )
            await db.commit()
            return "ok"
        except InsufficientStockError:
            await db.rollback()
            return "insufficient"


@pytest.mark.asyncio
async def test_concurrent_issues_never_oversell(pg_factory):
    user_id, material_id = await _seed(pg_factory)
    async with pg_factory() as db:
        await material_service.create_receipt(
            db, material_id=material_id, qty="10", unit_price="100.00",
            created_by=user_id,
        )
        await db.commit()

    # 7 + 7 > 10 — ровно одно списание обязано отвалиться
    results = await asyncio.gather(
        _issue(pg_factory, material_id, user_id, "7"),
        _issue(pg_factory, material_id, user_id, "7"),
    )
    assert sorted(results) == ["insufficient", "ok"]

    async with pg_factory() as db:
        receipt = (await db.execute(select(MaterialReceipt))).scalar_one()
        remaining = Decimal(str(receipt.qty_remaining))
        assert remaining == Decimal("3")
        allocated = (await db.execute(
            select(func.coalesce(func.sum(MaterialIssueAllocation.qty), 0))
            .where(MaterialIssueAllocation.receipt_id == receipt.id)
        )).scalar_one()
        assert Decimal(str(receipt.qty)) - Decimal(str(allocated)) == remaining


async def _reverse(factory, material_id: int, user_id: int, issue_id: int):
    async with factory() as db:
        try:
            await material_service.adjust(
                db, material_id=material_id, direction="surplus",
                reason="гонка сторно", created_by=user_id,
                reversal_of_issue_id=issue_id,
            )
            await db.commit()
            return "ok"
        except MaterialConflictError:
            await db.rollback()
            return "conflict"


@pytest.mark.asyncio
async def test_concurrent_issue_reversals_single_shot(pg_factory):
    user_id, material_id = await _seed(pg_factory)
    async with pg_factory() as db:
        await material_service.create_receipt(
            db, material_id=material_id, qty="3", unit_price="100.00",
            created_by=user_id,
        )
        await material_service.create_receipt(
            db, material_id=material_id, qty="10", unit_price="150.00",
            created_by=user_id,
        )
        issue = await material_service.issue_material(
            db, material_id=material_id, qty="5", created_by=user_id,
            doc_type="household", reason="исходный расход",
        )
        issue_id = issue.id
        await db.commit()

    results = await asyncio.gather(
        _reverse(pg_factory, material_id, user_id, issue_id),
        _reverse(pg_factory, material_id, user_id, issue_id),
    )
    assert sorted(results) == ["conflict", "ok"]

    async with pg_factory() as db:
        reversal_receipts = (await db.execute(
            select(MaterialReceipt)
            .where(MaterialReceipt.reversal_of_issue_id == issue_id)
            .order_by(MaterialReceipt.unit_price)
        )).scalars().all()
        # партии созданы РОВНО один раз: по одной на каждую цену аллокаций
        assert [(Decimal(str(r.qty)), Decimal(str(r.unit_price)))
                for r in reversal_receipts] == [
            (Decimal("3"), Decimal("100.00")),
            (Decimal("2"), Decimal("150.00")),
        ]
