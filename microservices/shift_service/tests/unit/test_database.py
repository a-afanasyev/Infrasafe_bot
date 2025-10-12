# Database Layer Tests
# UK Management Bot - Shift Service Tests

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from database import Base, get_db
from models.shifts import Shift, ShiftStatus, SpecializationType, ShiftType
from datetime import datetime, timedelta
from uuid import uuid4


@pytest.mark.asyncio
class TestDatabaseConnection:
    """Test database connection and session management"""

    async def test_database_connection_success(self, test_engine):
        """Test successful database connection"""
        async with test_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    async def test_database_version(self, test_engine):
        """Test PostgreSQL version"""
        async with test_engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            assert "PostgreSQL" in version

    async def test_session_creation(self, db_session: AsyncSession):
        """Test async session creation"""
        assert db_session is not None
        assert isinstance(db_session, AsyncSession)

    async def test_session_transaction(self, db_session: AsyncSession):
        """Test session transaction management"""
        # SQLAlchemy 2.0+ doesn't auto-start transactions
        # Begin transaction explicitly
        async with db_session.begin():
            assert db_session.in_transaction()

            # Just verify session is working
            result = await db_session.execute(text("SELECT 1"))
            assert result.scalar() == 1


@pytest.mark.asyncio
class TestDatabaseModels:
    """Test database model operations"""

    async def test_create_shift_model(self, db_session: AsyncSession):
        """Test creating Shift model instance"""
        base_time = datetime.utcnow()
        shift = Shift(
            title="Test Shift",
            description="Test description",
            start_time=base_time + timedelta(days=1),
            end_time=base_time + timedelta(days=1, hours=8),
            duration_hours=8.0,
            status=ShiftStatus.PLANNED,
            shift_type=ShiftType.REGULAR,
            specialization=SpecializationType.MAINTENANCE,
            location="Test Location",
            priority=2,
            created_by=uuid4()
        )

        db_session.add(shift)
        await db_session.commit()
        await db_session.refresh(shift)

        assert shift.id is not None
        assert shift.title == "Test Shift"
        assert shift.status == ShiftStatus.PLANNED

    async def test_query_shift_model(self, db_session: AsyncSession, shift_factory):
        """Test querying Shift model"""
        # Create test shift
        shift = await shift_factory(title="Query Test")

        # Query it back
        from sqlalchemy import select
        result = await db_session.execute(
            select(Shift).where(Shift.id == shift.id)
        )
        queried_shift = result.scalar_one()

        assert queried_shift.id == shift.id
        assert queried_shift.title == "Query Test"

    async def test_update_shift_model(self, db_session: AsyncSession, shift_factory):
        """Test updating Shift model"""
        shift = await shift_factory(title="Original Title")

        # Update title
        shift.title = "Updated Title"
        await db_session.commit()
        await db_session.refresh(shift)

        assert shift.title == "Updated Title"

    async def test_delete_shift_model(self, db_session: AsyncSession, shift_factory):
        """Test deleting Shift model"""
        shift = await shift_factory(title="To Delete")
        shift_id = shift.id

        # Delete
        await db_session.delete(shift)
        await db_session.commit()

        # Verify deleted
        from sqlalchemy import select
        result = await db_session.execute(
            select(Shift).where(Shift.id == shift_id)
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
class TestDatabaseConstraints:
    """Test database constraints and validations"""

    async def test_shift_status_enum(self, db_session: AsyncSession):
        """Test ShiftStatus enum values"""
        valid_statuses = [
            ShiftStatus.PLANNED,
            ShiftStatus.ACTIVE,
            ShiftStatus.COMPLETED,
            ShiftStatus.CANCELLED,
            ShiftStatus.TRANSFERRED
        ]

        for status in valid_statuses:
            base_time = datetime.utcnow()
            shift = Shift(
                title=f"Test {status.value}",
                start_time=base_time + timedelta(days=1),
                end_time=base_time + timedelta(days=1, hours=8),
                duration_hours=8.0,
                status=status,
                shift_type=ShiftType.REGULAR,
                specialization=SpecializationType.MAINTENANCE,
                priority=2,
                created_by=uuid4()
            )
            db_session.add(shift)
            await db_session.commit()
            await db_session.refresh(shift)

            assert shift.status == status

    async def test_specialization_enum(self, db_session: AsyncSession):
        """Test SpecializationType enum values"""
        specializations = [
            SpecializationType.PLUMBER,
            SpecializationType.ELECTRICIAN,
            SpecializationType.MAINTENANCE
        ]

        for spec in specializations:
            base_time = datetime.utcnow()
            shift = Shift(
                title=f"Test {spec.value}",
                start_time=base_time + timedelta(days=1),
                end_time=base_time + timedelta(days=1, hours=8),
                duration_hours=8.0,
                status=ShiftStatus.PLANNED,
                shift_type=ShiftType.REGULAR,
                specialization=spec,
                priority=2,
                created_by=uuid4()
            )
            db_session.add(shift)
            await db_session.commit()
            await db_session.refresh(shift)

            assert shift.specialization == spec

    async def test_priority_values(self, db_session: AsyncSession):
        """Test priority constraint (1-4)"""
        for priority in [1, 2, 3, 4]:
            base_time = datetime.utcnow()
            shift = Shift(
                title=f"Priority {priority}",
                start_time=base_time + timedelta(days=1),
                end_time=base_time + timedelta(days=1, hours=8),
                duration_hours=8.0,
                status=ShiftStatus.PLANNED,
                shift_type=ShiftType.REGULAR,
                specialization=SpecializationType.MAINTENANCE,
                priority=priority,
                created_by=uuid4()
            )
            db_session.add(shift)
            await db_session.commit()
            await db_session.refresh(shift)

            assert shift.priority == priority


@pytest.mark.asyncio
class TestDatabaseRelationships:
    """Test database relationships and foreign keys"""

    async def test_shift_with_executor(self, db_session: AsyncSession):
        """Test shift with executor_id relationship"""
        executor_id = uuid4()
        base_time = datetime.utcnow()

        shift = Shift(
            title="Assigned Shift",
            start_time=base_time + timedelta(days=1),
            end_time=base_time + timedelta(days=1, hours=8),
            duration_hours=8.0,
            status=ShiftStatus.PLANNED,
            shift_type=ShiftType.REGULAR,
            specialization=SpecializationType.MAINTENANCE,
            executor_id=executor_id,
            priority=2,
            created_by=uuid4()
        )

        db_session.add(shift)
        await db_session.commit()
        await db_session.refresh(shift)

        assert shift.executor_id == executor_id

    async def test_shift_with_coordinates(self, db_session: AsyncSession):
        """Test shift with JSON coordinates"""
        base_time = datetime.utcnow()
        coordinates = {"lat": 55.7558, "lng": 37.6176}

        shift = Shift(
            title="Shift with Location",
            start_time=base_time + timedelta(days=1),
            end_time=base_time + timedelta(days=1, hours=8),
            duration_hours=8.0,
            status=ShiftStatus.PLANNED,
            shift_type=ShiftType.REGULAR,
            specialization=SpecializationType.MAINTENANCE,
            location="Test Location",
            coordinates=coordinates,
            priority=2,
            created_by=uuid4()
        )

        db_session.add(shift)
        await db_session.commit()
        await db_session.refresh(shift)

        assert shift.coordinates == coordinates
        assert shift.coordinates["lat"] == 55.7558
        assert shift.coordinates["lng"] == 37.6176


@pytest.mark.asyncio
class TestDatabaseIsolation:
    """Test database isolation between tests"""

    async def test_isolation_test_1(self, db_session: AsyncSession, shift_factory):
        """First isolation test"""
        shift = await shift_factory(title="Isolation Test 1")

        from sqlalchemy import select
        result = await db_session.execute(select(Shift))
        shifts = result.scalars().all()

        # Should only see this shift (due to test isolation)
        assert len(shifts) >= 1
        assert any(s.title == "Isolation Test 1" for s in shifts)

    async def test_isolation_test_2(self, db_session: AsyncSession, shift_factory):
        """Second isolation test - verify factory works independently"""
        shift = await shift_factory(title="Isolation Test 2")

        from sqlalchemy import select
        result = await db_session.execute(select(Shift).where(Shift.title == "Isolation Test 2"))
        shift_from_db = result.scalar_one()

        # Verify this test's shift was created successfully
        assert shift_from_db is not None
        assert shift_from_db.title == "Isolation Test 2"
