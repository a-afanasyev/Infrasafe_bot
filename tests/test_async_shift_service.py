"""
Integration tests for AsyncShiftService

PHASE 1 TESTING (Day 5)
Comprehensive async testing suite for shift management functionality.
"""

import pytest
from datetime import datetime, timedelta
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from uk_management_bot.database.session import Base
from uk_management_bot.services.async_shift_service import AsyncShiftService
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User


# ========== FIXTURES ==========

@pytest.fixture(scope="function")
async def async_db_engine():
    """Create async test database engine"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture(scope="function")
async def async_db_session(async_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async test database session"""
    async_session_maker = async_sessionmaker(
        async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="function")
async def test_executor(async_db_session: AsyncSession) -> User:
    """Create test executor"""
    executor = User(
        telegram_id=12345,
        username="test_executor",
        first_name="Test",
        last_name="Executor",
        role="executor",
        active_role="executor",
        status="approved"
    )
    async_db_session.add(executor)
    await async_db_session.flush()
    await async_db_session.refresh(executor)
    return executor


@pytest.fixture(scope="function")
async def test_manager(async_db_session: AsyncSession) -> User:
    """Create test manager"""
    manager = User(
        telegram_id=54321,
        username="test_manager",
        first_name="Test",
        last_name="Manager",
        role="manager",
        active_role="manager",
        status="approved"
    )
    async_db_session.add(manager)
    await async_db_session.flush()
    await async_db_session.refresh(manager)
    return manager


@pytest.fixture(scope="function")
async def async_shift_service(async_db_session: AsyncSession) -> AsyncShiftService:
    """Create AsyncShiftService instance"""
    return AsyncShiftService(async_db_session)


# ========== TESTS ==========

@pytest.mark.asyncio
class TestAsyncShiftServiceStartEnd:
    """Test suite for shift start/end operations"""

    async def test_start_shift_success(
        self,
        async_shift_service: AsyncShiftService,
        test_executor: User,
        async_db_session: AsyncSession
    ):
        """Test successful shift start"""
        result = await async_shift_service.start_shift(
            telegram_id=test_executor.telegram_id,
            notes="Starting shift"
        )

        assert result["success"] == True
        assert result["shift"] is not None
        assert result["shift"].user_id == test_executor.id
        assert result["shift"].status == "active"

    async def test_start_shift_multiple_allowed(
        self,
        async_shift_service: AsyncShiftService,
        test_executor: User,
        async_db_session: AsyncSession
    ):
        """Test multiple active shifts allowed (different specializations)"""
        # Start first shift
        result1 = await async_shift_service.start_shift(
            telegram_id=test_executor.telegram_id,
            notes="Shift 1"
        )

        await async_db_session.flush()

        # Start second shift (should be allowed)
        result2 = await async_shift_service.start_shift(
            telegram_id=test_executor.telegram_id,
            notes="Shift 2"
        )

        assert result1["success"] == True
        assert result2["success"] == True

    async def test_end_shift_success(
        self,
        async_shift_service: AsyncShiftService,
        test_executor: User,
        async_db_session: AsyncSession
    ):
        """Test successful shift end"""
        # Start shift
        start_result = await async_shift_service.start_shift(
            telegram_id=test_executor.telegram_id
        )

        await async_db_session.flush()

        # End shift
        end_result = await async_shift_service.end_shift(
            telegram_id=test_executor.telegram_id,
            notes="Shift completed"
        )

        assert end_result["success"] == True
        assert end_result["shift"].status == "completed"
        assert end_result["shift"].end_time is not None

    async def test_end_shift_no_active(
        self,
        async_shift_service: AsyncShiftService,
        test_executor: User
    ):
        """Test ending shift when no active shift exists"""
        result = await async_shift_service.end_shift(
            telegram_id=test_executor.telegram_id
        )

        assert result["success"] == False
        assert "Нет активной смены" in result["message"]


@pytest.mark.asyncio
class TestAsyncShiftServiceForceEnd:
    """Test suite for force end shift operations"""

    async def test_force_end_shift_by_manager(
        self,
        async_shift_service: AsyncShiftService,
        test_executor: User,
        test_manager: User,
        async_db_session: AsyncSession
    ):
        """Test manager can force end executor's shift"""
        # Executor starts shift
        await async_shift_service.start_shift(
            telegram_id=test_executor.telegram_id
        )

        await async_db_session.flush()

        # Manager force ends shift
        result = await async_shift_service.force_end_shift(
            manager_telegram_id=test_manager.telegram_id,
            target_user_telegram_id=test_executor.telegram_id,
            notes="Forced by manager"
        )

        assert result["success"] == True
        assert result["shift"].status == "completed"

    async def test_force_end_requires_manager_role(
        self,
        async_shift_service: AsyncShiftService,
        test_executor: User,
        async_db_session: AsyncSession
    ):
        """Test force end requires manager role"""
        # Create another executor
        executor2 = User(
            telegram_id=99999,
            username="executor2",
            role="executor",
            status="approved"
        )
        async_db_session.add(executor2)
        await async_db_session.flush()

        # Executor starts shift
        await async_shift_service.start_shift(
            telegram_id=test_executor.telegram_id
        )

        await async_db_session.flush()

        # Another executor tries to force end (should fail)
        result = await async_shift_service.force_end_shift(
            manager_telegram_id=executor2.telegram_id,
            target_user_telegram_id=test_executor.telegram_id
        )

        assert result["success"] == False
        assert "права менеджера" in result["message"].lower()


@pytest.mark.asyncio
class TestAsyncShiftServiceRetrieval:
    """Test suite for shift retrieval operations"""

    async def test_is_user_in_active_shift(
        self,
        async_shift_service: AsyncShiftService,
        test_executor: User,
        async_db_session: AsyncSession
    ):
        """Test checking if user is in active shift"""
        # No active shift
        is_active = await async_shift_service.is_user_in_active_shift(
            telegram_id=test_executor.telegram_id
        )
        assert is_active == False

        # Start shift
        await async_shift_service.start_shift(
            telegram_id=test_executor.telegram_id
        )

        await async_db_session.flush()

        # Should have active shift
        is_active = await async_shift_service.is_user_in_active_shift(
            telegram_id=test_executor.telegram_id
        )
        assert is_active == True

    async def test_get_active_shift(
        self,
        async_shift_service: AsyncShiftService,
        test_executor: User,
        async_db_session: AsyncSession
    ):
        """Test getting active shift"""
        # Start shift
        start_result = await async_shift_service.start_shift(
            telegram_id=test_executor.telegram_id,
            notes="Test shift"
        )

        await async_db_session.flush()

        # Get active shift
        active_shift = await async_shift_service.get_active_shift(
            telegram_id=test_executor.telegram_id
        )

        assert active_shift is not None
        assert active_shift.id == start_result["shift"].id
        assert active_shift.status == "active"

    async def test_list_shifts_with_filters(
        self,
        async_shift_service: AsyncShiftService,
        test_executor: User,
        async_db_session: AsyncSession
    ):
        """Test listing shifts with various filters"""
        # Create multiple shifts
        for i in range(5):
            await async_shift_service.start_shift(
                telegram_id=test_executor.telegram_id,
                notes=f"Shift {i+1}"
            )
            await async_db_session.flush()

            if i < 3:
                # End first 3 shifts
                await async_shift_service.end_shift(
                    telegram_id=test_executor.telegram_id
                )
                await async_db_session.flush()

        # Get all shifts
        all_shifts = await async_shift_service.list_shifts(
            telegram_id=test_executor.telegram_id,
            limit=10
        )
        assert len(all_shifts) == 5

        # Get only active shifts
        active_shifts = await async_shift_service.list_shifts(
            telegram_id=test_executor.telegram_id,
            status="active"
        )
        assert len(active_shifts) == 2

        # Get only completed shifts
        completed_shifts = await async_shift_service.list_shifts(
            telegram_id=test_executor.telegram_id,
            status="completed"
        )
        assert len(completed_shifts) == 3

    async def test_list_shifts_with_period_filter(
        self,
        async_shift_service: AsyncShiftService,
        test_executor: User,
        async_db_session: AsyncSession
    ):
        """Test listing shifts with period filter"""
        # Create shift
        await async_shift_service.start_shift(
            telegram_id=test_executor.telegram_id
        )

        await async_db_session.flush()

        # Get today's shifts
        today_shifts = await async_shift_service.list_shifts(
            telegram_id=test_executor.telegram_id,
            period="today"
        )

        assert len(today_shifts) >= 1


@pytest.mark.asyncio
class TestAsyncShiftServiceStatistics:
    """Test suite for shift statistics"""

    async def test_get_shift_stats(
        self,
        async_shift_service: AsyncShiftService,
        test_executor: User,
        async_db_session: AsyncSession
    ):
        """Test getting shift statistics"""
        # Create and complete shifts
        for i in range(3):
            await async_shift_service.start_shift(
                telegram_id=test_executor.telegram_id
            )
            await async_db_session.flush()

            if i < 2:
                # Complete 2 shifts
                await async_shift_service.end_shift(
                    telegram_id=test_executor.telegram_id
                )
                await async_db_session.flush()

        # Get statistics
        stats = await async_shift_service.get_shift_stats(
            telegram_id=test_executor.telegram_id
        )

        assert stats["total_shifts"] == 3
        assert stats["active_count"] == 1
        assert stats["total_hours"] >= 0


@pytest.mark.asyncio
class TestAsyncShiftServicePerformance:
    """Test suite for async performance validation"""

    async def test_concurrent_shift_queries(
        self,
        async_shift_service: AsyncShiftService,
        test_executor: User,
        async_db_session: AsyncSession
    ):
        """Test concurrent shift queries (async advantage)"""
        import asyncio

        # Start a shift
        await async_shift_service.start_shift(
            telegram_id=test_executor.telegram_id
        )

        await async_db_session.flush()

        # Execute multiple queries concurrently
        tasks = [
            async_shift_service.is_user_in_active_shift(test_executor.telegram_id),
            async_shift_service.get_active_shift(test_executor.telegram_id),
            async_shift_service.list_shifts(telegram_id=test_executor.telegram_id),
            async_shift_service.get_shift_stats(telegram_id=test_executor.telegram_id)
        ]

        results = await asyncio.gather(*tasks)

        assert results[0] == True  # is_user_in_active_shift
        assert results[1] is not None  # get_active_shift
        assert len(results[2]) >= 1  # list_shifts
        assert results[3]["total_shifts"] >= 1  # get_shift_stats


# ========== RUN TESTS ==========

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
