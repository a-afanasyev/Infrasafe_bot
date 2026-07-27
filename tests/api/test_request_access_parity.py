"""П5 — parity: синхронный и асинхронный сборщики фактов обязаны совпадать.

Условие плана — parity-тест на канон ДО удаления расходящихся копий. Ядро
(`utils/request_access`) покрыто матрицей правил на чистых фактах; здесь
проверяется вторая половина риска: две ДОБЫЧИ фактов над настоящей БД (у бота
синхронная `Session`, у API — `AsyncSession`) на одних и тех же данных дают
одинаковый ответ. Расхождение реализаций, а не правил, стоило прод-дефекта в
PR #259.

БД — один файл sqlite и два движка поверх него, а не общая сессия: так обе
реализации читают буквально одни и те же строки, и сценарий не приходится
сеять дважды. Ничего из предмета не подменяется, обе функции настоящие.
"""
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.models.building import Building
from uk_management_bot.services.request_access import (
    request_access_reason_async,
    request_access_reason_sync,
)

RN = "260801-001"

# ── Сценарии: ожидание записано ЯВНО, а не вычислено тем же кодом — иначе тест
# доказывал бы лишь «две реализации одинаково неправы». ─────────────────────
SCENARIOS = [
    ("посторонний", ["applicant"], None, {}, None),
    ("владелец", ["applicant"], None, {"owner": True}, "owner"),
    ("менеджер чужой заявки", ["manager"], None, {}, "manager"),
    ("менеджер важнее владельца", ["manager"], None, {"owner": True}, "manager"),
    ("исполнитель по executor_id", ["executor"], None, {"executor_id": True},
     "executor_direct"),
    ("исполнитель по индивидуальному назначению", ["executor"], None,
     {"individual": True}, "executor_individual_assignment"),
    ("индивидуальное назначение без смены", ["executor"], None,
     {"individual": True}, "executor_individual_assignment"),
    ("multi-role исполнитель сохраняет доступ", ["applicant", "executor"], None,
     {"individual": True}, "executor_individual_assignment"),
    ("назначение без роли executor не пускает", ["applicant"], None,
     {"individual": True}, None),
    ("группа + смена", ["executor"], '["plumber"]',
     {"group": "plumber", "shift": True}, "executor_group_assignment_on_shift"),
    ("группа без смены", ["executor"], '["plumber"]',
     {"group": "plumber"}, None),
    ("группа, чужая специализация", ["executor"], '["electric"]',
     {"group": "plumber", "shift": True}, None),
    ("группа, CSV-специализации", ["executor"], "electric,plumber",
     {"group": "plumber", "shift": True}, "executor_group_assignment_on_shift"),
    ("сосед на «Исполнено»", ["applicant"], None,
     {"resident": True, "status": "Исполнено"}, "apartment_resident_on_accepted"),
    ("сосед на «В работе» — нет", ["applicant"], None,
     {"resident": True, "status": "В работе"}, None),
    ("неодобренный сосед на «Исполнено» — нет", ["applicant"], None,
     {"resident": True, "approved": False, "status": "Исполнено"}, None),
    ("отменённое назначение не пускает", ["executor"], None,
     {"individual": True, "assignment_active": False}, None),
]
IDS = [s[0] for s in SCENARIOS]


def _seed(sync_session, roles, specialization, plan) -> int:
    """Засеять сценарий синхронно. Возвращает id субъекта."""
    import json

    owner = User(telegram_id=9001, roles='["applicant"]', active_role="applicant",
                 first_name="Владелец")
    # active_role намеренно «applicant» даже там, где проверяется исполнитель:
    # канон обязан смотреть на СОСТАВ ролей, а не на активную (AUD3-14).
    subject = User(telegram_id=9002, roles=json.dumps(roles), active_role="applicant",
                   first_name="Субъект", specialization=specialization)
    sync_session.add_all([owner, subject])
    sync_session.flush()

    apartment_id = None
    if plan.get("resident"):
        # Квартира требует здания, здание — двора: цепочка обязательных FK.
        yard = Yard(name="Двор parity")
        sync_session.add(yard)
        sync_session.flush()
        building = Building(address="ул. Тестовая, 1", yard_id=yard.id)
        sync_session.add(building)
        sync_session.flush()
        apartment = Apartment(building_id=building.id, apartment_number="300")
        sync_session.add(apartment)
        sync_session.flush()
        apartment_id = apartment.id
        sync_session.add(UserApartment(
            user_id=subject.id, apartment_id=apartment_id,
            status="approved" if plan.get("approved", True) else "pending",
        ))

    sync_session.add(RequestModel(
        request_number=RN,
        user_id=subject.id if plan.get("owner") else owner.id,
        category="Сантехника", description="parity",
        status=plan.get("status", "Новая"), source="web", media_files=[],
        apartment_id=apartment_id,
        executor_id=subject.id if plan.get("executor_id") else None,
    ))

    a_status = "active" if plan.get("assignment_active", True) else "cancelled"
    if plan.get("individual"):
        sync_session.add(RequestAssignment(
            request_number=RN, assignment_type="individual",
            executor_id=subject.id, status=a_status, created_by=owner.id,
        ))
    if plan.get("group"):
        sync_session.add(RequestAssignment(
            request_number=RN, assignment_type="group",
            group_specialization=plan["group"], executor_id=None,
            status=a_status, created_by=owner.id,
        ))
    if plan.get("shift"):
        # start_time обязателен по схеме; предикат смотрит только на status,
        # поэтому конкретное время роли не играет — важно, что смена активна.
        sync_session.add(Shift(
            user_id=subject.id, status="active",
            start_time=datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc),
        ))

    sync_session.commit()
    return subject.id


@pytest.fixture
def db_file(tmp_path):
    """Файловая sqlite: её видят и синхронный движок, и асинхронный."""
    return tmp_path / "parity.sqlite3"


@pytest.fixture
def sync_factory(db_file):
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest_asyncio.fixture
async def async_factory(db_file, sync_factory):
    """Зависит от sync_factory: схему создаёт он, порядок важен."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.parametrize("name,roles,spec,plan,expected", SCENARIOS, ids=IDS)
def test_sync_builder_matches_canon(sync_factory, name, roles, spec, plan, expected):
    with sync_factory() as session:
        subject_id = _seed(session, roles, spec, plan)
        subject = session.get(User, subject_id)
        request = session.get(RequestModel, RN)
        assert request_access_reason_sync(session, subject, request) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("name,roles,spec,plan,expected", SCENARIOS, ids=IDS)
async def test_async_builder_matches_canon(
    sync_factory, async_factory, name, roles, spec, plan, expected
):
    with sync_factory() as session:
        subject_id = _seed(session, roles, spec, plan)

    async with async_factory() as session:
        subject = await session.get(User, subject_id)
        request = await session.get(RequestModel, RN)
        assert await request_access_reason_async(session, subject, request) == expected
