"""Контракт обёртки `check_request_access` (П5).

Файл переписан. Прежняя версия строилась на `AsyncMock(spec=AsyncSession)` с
жёсткой последовательностью `side_effect` и `MagicMock`-заявками: она проверяла
не поведение, а ФОРМУ вызовов. Цена такого теста выяснилась при сведении копий
предиката — смена `scalar_one_or_none()` на `scalars().first()` уронила один
тест и оставила зелёными остальные, хотя проверяли они одно и то же. На
`MagicMock` любое обращение истинно, поэтому «проходит» ещё не значит «проверено».

Здесь остаётся только то, что принадлежит самой обёртке: 404 на несуществующей
заявке, возврат объекта заявки при доступе, 403 при отказе. Матрица правил
доступа живёт отдельно и проверяется на настоящих данных:
  * `uk_management_bot/tests/utils/test_request_access.py` — правила на чистых фактах;
  * `tests/api/test_request_access_parity.py` — обе добычи фактов над БД.
"""
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.api.dependencies_access import check_request_access
from uk_management_bot.database.session import Base
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard  # noqa: F401  (create_all)
from uk_management_bot.database.models.building import Building  # noqa: F401  (create_all)
from uk_management_bot.database.models.apartment import Apartment  # noqa: F401  (create_all)

RN = "260401-001"


@pytest.fixture
def db_file(tmp_path):
    return tmp_path / "access.sqlite3"


@pytest.fixture
def seeded(db_file):
    """Заявка владельца (id=1) и посторонний пользователь (id=2)."""
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        owner = User(telegram_id=7001, roles='["applicant"]', active_role="applicant",
                     first_name="Владелец")
        stranger = User(telegram_id=7002, roles='["applicant"]', active_role="applicant",
                        first_name="Посторонний")
        manager = User(telegram_id=7003, roles='["manager"]', active_role="manager",
                       first_name="Менеджер")
        s.add_all([owner, stranger, manager])
        s.flush()
        s.add(Request(
            request_number=RN, user_id=owner.id, category="Сантехника",
            description="контракт обёртки", status="Новая", source="web", media_files=[],
        ))
        s.commit()
        ids = {"owner": owner.id, "stranger": stranger.id, "manager": manager.id}
    engine.dispose()
    return ids


@pytest_asyncio.fixture
async def session(db_file, seeded):
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_returns_the_request_object_on_access(session, seeded):
    """Обёртка обязана вернуть саму заявку, а не просто «да»."""
    owner = await session.get(User, seeded["owner"])
    result = await check_request_access(RN, session, owner)
    assert isinstance(result, Request)
    assert result.request_number == RN


@pytest.mark.asyncio
async def test_missing_request_is_404_not_403(session, seeded):
    """404 важно отличать от 403: иначе перебором номеров видно, что существует."""
    manager = await session.get(User, seeded["manager"])
    with pytest.raises(HTTPException) as exc:
        await check_request_access("999999-999", session, manager)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_denied_user_gets_403(session, seeded):
    stranger = await session.get(User, seeded["stranger"])
    with pytest.raises(HTTPException) as exc:
        await check_request_access(RN, session, stranger)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_manager_passes_the_wrapper(session, seeded):
    """Контроль: обёртка действительно спрашивает канон, а не отказывает всем."""
    manager = await session.get(User, seeded["manager"])
    result = await check_request_access(RN, session, manager)
    assert result.request_number == RN
