"""Гонки правок паспорта дома — только реальный PostgreSQL.

sqlite-тесты (tests/services/test_building_passport_service.py) проверяют
правила, но блокировка строки паспорта под параллельными запросами там не
работает. Здесь запросы идут разными соединениями к DATABASE_URL бота.

Данные — с id из диапазона 99xxxx; teardown удаляет всё. Таблиц модуля нет
(миграция 036 не применена) — тест пропускается.
"""
import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.building_passport import (
    BuildingPassport,
    BuildingPassportEvent,
    BuildingPassportRevision,
)
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.building_passport import service as svc
from uk_management_bot.services.building_passport import validation
from uk_management_bot.services.building_passport.service import Actor, PassportError

YARD = BUILDING = 990101
ENGINEER, MANAGER = Actor(None, "PG инженер"), Actor(None, "PG менеджер")


def _async_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("postgres-only concurrency test (DATABASE_URL not postgres)")
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


async def _wipe(factory) -> None:
    async with factory() as db:
        ids = select(BuildingPassport.id).where(BuildingPassport.building_id == BUILDING)
        await db.execute(delete(BuildingPassportEvent).where(BuildingPassportEvent.passport_id.in_(ids)))
        await db.execute(delete(BuildingPassportRevision).where(BuildingPassportRevision.passport_id.in_(ids)))
        await db.execute(delete(BuildingPassport).where(BuildingPassport.building_id == BUILDING))
        await db.execute(delete(Building).where(Building.id == BUILDING))
        await db.execute(delete(Yard).where(Yard.id == YARD))
        await db.commit()


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(_async_url(), pool_size=8, max_overflow=4)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        if (await db.execute(text("SELECT to_regclass('building_passports')"))).scalar() is None:
            await engine.dispose()
            pytest.skip("таблиц модуля «Паспорт дома» нет — миграция 036 не применена")
    await _wipe(maker)
    async with maker() as db:
        db.add(Yard(id=YARD, name=f"passport-pg-{YARD}", is_active=True))
        await db.flush()
        db.add(Building(id=BUILDING, yard_id=YARD, address="passport-pg", entrance_count=1,
                        floor_count=9, is_active=True))
        await db.commit()
    try:
        yield maker
    finally:
        await _wipe(maker)
        await engine.dispose()


async def _run(factory, call) -> str:
    """Один запрос в своей транзакции: «ok» или код отказа."""
    async with factory() as db:
        try:
            await call(db)
        except PassportError as exc:
            await db.rollback()
            return exc.code
        await db.commit()
        return "ok"


def _patch(expected: int, **kw):
    return lambda db: svc.patch(db, BUILDING, ENGINEER, expected_version=expected, **kw)


async def _view(factory) -> dict:
    async with factory() as db:
        return await svc.view(db, BUILDING)


async def _complete(factory) -> int:
    assert await _run(factory, _patch(0, meta={"inspection_date": "2026-11-20"})) == "ok"
    view = await _view(factory)
    groups = validation._groups()
    assert await _run(factory, _patch(
        view["version"],
        unknown={k: "нет документов" for k in view["missing"] if k not in groups},
        absent={k: True for k in view["missing"] if k in groups})) == "ok"
    return (await _view(factory))["version"]


@pytest.mark.asyncio
async def test_first_writes_race_leaves_one_passport(factory):
    results = await asyncio.gather(*[
        _run(factory, _patch(0, values={key: value}))
        for key, value in (("floors", 9), ("built_year", 2019), ("entrances", 4))])
    assert "ok" in results and set(results) <= {"ok", "stale"}, results
    async with factory() as db:
        count = (await db.execute(select(func.count(BuildingPassport.id)).where(
            BuildingPassport.building_id == BUILDING))).scalar_one()
    assert count == 1
    assert (await _view(factory))["version"] == results.count("ok")


@pytest.mark.asyncio
async def test_parallel_edits_of_different_fields_both_pass(factory):
    assert await _run(factory, _patch(0, values={"floors": 9})) == "ok"
    results = await asyncio.gather(
        _run(factory, _patch(1, values={"built_year": 2019})),
        _run(factory, _patch(1, values={"cadastre_no": "10:08:01"})))
    assert results == ["ok", "ok"]
    view = await _view(factory)
    assert view["version"] == 3
    assert (view["values"]["built_year"], view["values"]["cadastre_no"]) == (2019, "10:08:01")


@pytest.mark.asyncio
async def test_parallel_edits_of_the_same_field_one_is_stale(factory):
    assert await _run(factory, _patch(0, values={"floors": 9})) == "ok"
    results = await asyncio.gather(*[_run(factory, _patch(1, values={"floors": n})) for n in (10, 11, 12)])
    assert sorted(results) == ["ok", "stale", "stale"], results
    view = await _view(factory)
    assert view["version"] == 2 and view["values"]["floors"] == (10, 11, 12)[results.index("ok")]


@pytest.mark.asyncio
async def test_edit_racing_with_signing_never_lands_in_the_revision(factory):
    version = await _complete(factory)
    assert await _run(factory, lambda db: svc.set_status(
        db, BUILDING, ENGINEER, status="filled", expected_version=version)) == "ok"
    version = (await _view(factory))["version"]

    signed, edited = await asyncio.gather(
        _run(factory, lambda db: svc.set_status(
            db, BUILDING, MANAGER, status="signed", expected_version=version, can_sign=True)),
        _run(factory, _patch(version, values={"floors": 77})))
    # Побеждает ровно одна: либо подпись (правка видит «подписан»), либо правка (подпись устарела).
    assert (signed, edited) in {("ok", "signed"), ("stale", "ok")}, (signed, edited)

    async with factory() as db:
        revisions = await svc.revisions(db, BUILDING)
        if signed == "ok":
            assert len(revisions) == 1
            assert (await svc.revision(db, BUILDING, 1))["values"].get("floors") != 77
        else:
            assert revisions == []
