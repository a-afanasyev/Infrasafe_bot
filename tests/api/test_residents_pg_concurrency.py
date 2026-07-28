"""РЕАЛЬНЫЕ гонки раздела «Жители» против PostgreSQL (паттерн test_materials_pg_concurrency).

SQLite не умеет row-locking (`FOR UPDATE` молча выбрасывается) и в тестах живёт
одной сессией на тест, поэтому весь sqlite-сьют мутаций проходит даже при
полностью сломанной сериализации. Здесь настоящий Postgres и две подлинные
гонки, каждая — из реальной жизни, а не из синтетического тайминга:

  (а) два менеджера одновременно подтверждают одну заявку на привязку
      (или менеджер дважды кликнул) — обработать обязан ровно один, второй
      получает конфликт. Иначе в аудите затирается настоящий рецензент, а
      житель получает два уведомления об одном решении;

  (б) два одновременных attach разных квартир одному жителю — инвариант T6
      обязан выстоять: ровно одна основная квартира, а не две.

⚠ Почему одного `SELECT ... FOR UPDATE` мало. Лок строки `users` сериализует
транзакции, но НЕ обновляет уже загруженные объекты: `db.get()` и обычный
`select()` отдают их из identity map вообще без SQL. Значит guard вида
«заявка уже обработана» сверялся бы с состоянием, прочитанным ДО лока, и
пропускал бы второй запрос. Поэтому после лока строки перечитываются с
`populate_existing=True` — эти тесты и стерегут именно это.

Изоляция: собственная temp-схема в той же БД (schema_translate_map).
Скип, если DATABASE_URL не Postgres (см. POSTGRES_TEST_URL в conftest).
"""
import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.session import Base
from uk_management_bot.services.residents import core
from uk_management_bot.services.residents.exceptions import ResidentError

SCHEMA = "residents_race_test"

_TABLES = [
    User.__table__,
    Yard.__table__,
    Building.__table__,
    Apartment.__table__,
    UserApartment.__table__,
    AuditLog.__table__,
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
            await conn.run_sync(lambda sc: Base.metadata.create_all(sc, tables=_TABLES))
    except Exception as exc:  # pragma: no cover — хост без доступного PG
        await engine.dispose()
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    await engine.dispose()


async def _seed(factory) -> dict:
    """Менеджер, житель, двор/дом и две квартиры."""
    async with factory() as db:
        manager = User(telegram_id=515151, first_name="М", roles='["manager"]',
                       active_role="manager", status="approved")
        resident = User(telegram_id=515152, first_name="Ж", roles='["applicant"]',
                        active_role="applicant", status="approved", language="ru")
        db.add_all([manager, resident])
        yard = Yard(name="Гоночный двор")
        db.add(yard)
        await db.flush()
        bld = Building(address="Гоночная 1", yard_id=yard.id)
        db.add(bld)
        await db.flush()
        apt1 = Apartment(building_id=bld.id, apartment_number="101")
        apt2 = Apartment(building_id=bld.id, apartment_number="102")
        db.add_all([apt1, apt2])
        await db.flush()
        ids = {
            "manager_id": manager.id, "resident_id": resident.id,
            "apt1": apt1.id, "apt2": apt2.id,
        }
        await db.commit()
    return ids


async def _approve_binding(factory, resident_id: int, ua_id: int, actor_id: int) -> str:
    async with factory() as db:
        try:
            await core.approve_binding(
                db, resident_id=resident_id, ua_id=ua_id, actor_id=actor_id,
            )
            return "ok"
        except Exception as exc:                       # noqa: BLE001
            await db.rollback()
            if isinstance(exc, ResidentError) or "уже обработана" in str(exc):
                return "conflict"
            raise


async def _attach(factory, resident_id: int, apartment_id: int, actor_id: int) -> str:
    async with factory() as db:
        try:
            await core.attach_apartment(
                db, resident_id=resident_id, apartment_id=apartment_id,
                actor_id=actor_id, is_primary=True,
            )
            return "ok"
        except Exception:                              # noqa: BLE001
            await db.rollback()
            return "failed"


@pytest.fixture
def no_realtime(monkeypatch):
    """Redis в тестовом контейнере нет — публикация не должна шуметь."""
    async def _skip(*_args, **_kwargs):
        return None
    monkeypatch.setattr(
        "uk_management_bot.services.residents.core.publish_realtime_after_commit", _skip,
    )


@pytest.mark.asyncio
async def test_binding_is_reread_after_lock(pg_factory):
    """Ядро дефекта: после лока guard обязан видеть СВЕЖЕЕ состояние привязки.

    Расстановка ровно как при двойном клике: сессия B читает заявку (pending),
    другая сессия подтверждает её и коммитит, B читает снова — и обязана
    увидеть approved. На `db.get()` второе чтение возвращало устаревший
    pending прямо из identity map, без единого SQL-запроса, и guard «заявка
    уже обработана» не срабатывал: второй менеджер затирал рецензента, житель
    получал два уведомления об одном решении.
    """
    ids = await _seed(pg_factory)
    async with pg_factory() as db:
        ua = UserApartment(user_id=ids["resident_id"], apartment_id=ids["apt1"],
                           status="pending")
        db.add(ua)
        await db.flush()
        ua_id = ua.id
        await db.commit()

    session_b = pg_factory()
    try:
        before = await core._require_binding(session_b, ids["resident_id"], ua_id)
        assert before.status == "pending"

        async with pg_factory() as session_a:
            row = await session_a.get(UserApartment, ua_id)
            row.status = "approved"
            row.reviewed_by = ids["manager_id"]
            await session_a.commit()

        await core._lock_resident(session_b, ids["resident_id"])
        after = await core._require_binding(session_b, ids["resident_id"], ua_id)
        assert after.status == "approved", (
            "после лока прочитано устаревшее состояние — guard'ы не сработают"
        )
    finally:
        await session_b.close()


@pytest.mark.asyncio
async def test_resident_is_reread_after_lock(pg_factory):
    """То же для аккаунта: повторный approve обязан увидеть уже одобренного."""
    ids = await _seed(pg_factory)
    async with pg_factory() as db:
        u = await db.get(User, ids["resident_id"])
        u.status = "pending"
        await db.commit()

    session_b = pg_factory()
    try:
        # ВАЖНО: первое чтение БЕЗ лока — иначе B держала бы FOR UPDATE на той
        # самой строке, которую сейчас обновит A, и тест встал бы в дедлок.
        before = await core._require_resident(session_b, ids["resident_id"])
        assert before.status == "pending"

        async with pg_factory() as session_a:
            row = await session_a.get(User, ids["resident_id"])
            row.status = "approved"
            await session_a.commit()

        after = await core._lock_and_require_resident(session_b, ids["resident_id"])
        assert after.status == "approved"
    finally:
        await session_b.close()


@pytest.mark.asyncio
async def test_concurrent_approve_processes_the_request_once(pg_factory, no_realtime):
    """Дым-тест поверх реальных эндпоинт-функций: подтверждение ровно одно."""
    ids = await _seed(pg_factory)
    async with pg_factory() as db:
        ua = UserApartment(user_id=ids["resident_id"], apartment_id=ids["apt1"],
                           status="pending")
        db.add(ua)
        await db.flush()
        ua_id = ua.id
        await db.commit()

    results = await asyncio.gather(
        _approve_binding(pg_factory, ids["resident_id"], ua_id, ids["manager_id"]),
        _approve_binding(pg_factory, ids["resident_id"], ua_id, ids["manager_id"]),
    )
    assert sorted(results) == ["conflict", "ok"], results

    async with pg_factory() as db:
        audits = (await db.execute(
            select(AuditLog).where(AuditLog.action == "resident_binding_approved")
        )).scalars().all()
        assert len(audits) == 1


@pytest.mark.asyncio
async def test_concurrent_attach_keeps_exactly_one_primary(pg_factory, no_realtime):
    """T6 под конкуренцией: две основные квартиры недопустимы."""
    ids = await _seed(pg_factory)

    await asyncio.gather(
        _attach(pg_factory, ids["resident_id"], ids["apt1"], ids["manager_id"]),
        _attach(pg_factory, ids["resident_id"], ids["apt2"], ids["manager_id"]),
    )

    async with pg_factory() as db:
        bindings = (await db.execute(
            select(UserApartment).where(UserApartment.user_id == ids["resident_id"])
        )).scalars().all()
        primaries = [b for b in bindings if b.is_primary]
        assert len(primaries) == 1, (
            f"основных квартир: {len(primaries)} при {len(bindings)} привязках"
        )
