"""
conftest.py for tests/services/ — patches DATABASE_URL to SQLite
before any uk_management_bot modules are imported, avoiding
the need for psycopg2 or a running PostgreSQL instance.
"""
import os

# Force SQLite and DEBUG mode for tests that run outside Docker.
# This MUST happen before any uk_management_bot import triggers
# database/session.py which calls create_engine at import time.
os.environ["DATABASE_URL"] = "sqlite:///test_services.db"
os.environ["DEBUG"] = "true"
os.environ["INVITE_SECRET"] = "test_secret_for_unit_tests"
os.environ["ADMIN_PASSWORD"] = "test_admin_password"


# ---------------------------------------------------------------------------
# Фикстуры модуля «Лифты» (tests/services/test_elevator_service_*.py).
# Импорты моделей — внутри фикстур: env выше обязан отработать до первого
# импорта uk_management_bot.
# ---------------------------------------------------------------------------
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402


@pytest.fixture()
def el_engine():
    """In-memory sqlite со всей схемой Base (общий StaticPool-коннект)."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    import uk_management_bot.database.models  # noqa: F401 — регистрация моделей
    from uk_management_bot.database.session import Base

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def el_factory(el_engine):
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=el_engine, autoflush=False, autocommit=False)


@pytest.fixture()
def el_db(el_factory):
    session = el_factory()
    yield session
    session.close()


@pytest_asyncio.fixture
async def el_async_factory():
    """async_sessionmaker на sqlite+aiosqlite (in-memory, StaticPool) в loop теста
    (паттерн tests/api/conftest.py — без asyncio.run)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    import uk_management_bot.database.models  # noqa: F401
    from uk_management_bot.database.session import Base

    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


class ElevatorSeed:
    """Строители тест-данных лифтового модуля (объекты, не добавленные в сессию)."""

    @staticmethod
    def yard(id: int = 1, name: str = "Двор 1"):
        from uk_management_bot.database.models.yard import Yard

        return Yard(id=id, name=name, is_active=True)

    @staticmethod
    def building(id: int = 1, yard_id: int = 1, address: str = "ул. Мира, д. 5",
                 entrance_count: int = 4, is_active: bool = True):
        from uk_management_bot.database.models.building import Building

        return Building(id=id, yard_id=yard_id, address=address,
                        entrance_count=entrance_count, floor_count=9, is_active=is_active)

    @staticmethod
    def apartment(id: int, building_id: int = 1, number: str | None = None,
                  entrance: int | None = 1, is_active: bool = True):
        from uk_management_bot.database.models.apartment import Apartment

        return Apartment(id=id, building_id=building_id, apartment_number=number or str(id),
                         entrance=entrance, is_active=is_active)

    @staticmethod
    def user(id: int, telegram_id: int | None = None, *, language: str = "ru",
             status: str = "approved", roles: str = '["applicant"]', **extra):
        from uk_management_bot.database.models.user import User

        return User(id=id, telegram_id=telegram_id if telegram_id is not None else 1000 + id,
                    first_name=f"U{id}", roles=roles, active_role="applicant",
                    status=status, language=language, **extra)

    @staticmethod
    def belonging(user_id: int, apartment_id: int, status: str = "approved"):
        from uk_management_bot.database.models.user_apartment import UserApartment

        return UserApartment(user_id=user_id, apartment_id=apartment_id, status=status)

    @staticmethod
    def elevator(id: int | None = None, building_id: int = 1, entrance: int = 1,
                 number: int = 1, *, commissioned: bool = True,
                 status: str | None = "working", public_code: str | None = None, **extra):
        from datetime import date

        from uk_management_bot.database.models.elevator import Elevator

        code = public_code or f"code-{id or 0}-{building_id}-{entrance}-{number}-xxxxxxxx"
        fields = dict(
            building_id=building_id, entrance_number=entrance, elevator_number=number,
            passport_number=f"P-{entrance}{number}", manufacturer="OTIS",
            serial_number=f"S-{entrance}{number}", public_code=code,
            is_commissioned=commissioned,
            commissioned_at=date(2026, 1, 1) if commissioned else None,
            current_status=status if commissioned else None,
        )
        if id is not None:
            fields["id"] = id
        fields.update(extra)
        return Elevator(**fields)


@pytest.fixture()
def el_seed():
    return ElevatorSeed
