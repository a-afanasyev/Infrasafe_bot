"""
Integration Tests for AsyncSmartDispatcher (Phase 2A)

Тестирует async AI-алгоритмы назначения заявок с многокритериальной оптимизацией.

SCOPE: Phase 2A async core assignment methods
- auto_assign_request
- calculate_assignment_score
- find_best_shift_for_request
- parallel score calculations

Created: 19.10.2025
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from uk_management_bot.services.async_smart_dispatcher import (
    AsyncSmartDispatcher,
    AssignmentScore,
    AssignmentResult
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User


# Test Database Setup
@pytest.fixture
async def async_test_db():
    """Создание async in-memory тестовой БД"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False
    )

    async with engine.begin() as conn:
        # Import Base after creating engine
        from uk_management_bot.database.models.base import Base
        await conn.run_sync(Base.metadata.create_all)

    AsyncTestSession = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with AsyncTestSession() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def test_users(async_test_db: AsyncSession):
    """Создание тестовых пользователей"""
    users = [
        User(
            telegram_id=1001,
            first_name="Иван",
            last_name="Иванов",
            username="ivan_executor",
            role="executor",
            status="approved",
            specialization="Сантехника"
        ),
        User(
            telegram_id=1002,
            first_name="Петр",
            last_name="Петров",
            username="petr_executor",
            role="executor",
            status="approved",
            specialization="Электрика"
        ),
        User(
            telegram_id=1003,
            first_name="Мария",
            last_name="Сидорова",
            username="maria_executor",
            role="executor",
            status="approved",
            specialization="Сантехника"
        ),
        User(
            telegram_id=2001,
            first_name="Заявитель",
            last_name="Тестовый",
            username="applicant",
            role="applicant",
            status="approved"
        )
    ]

    for user in users:
        async_test_db.add(user)

    await async_test_db.commit()

    # Refresh to get IDs
    for user in users:
        await async_test_db.refresh(user)

    return users


@pytest.fixture
async def test_shifts(async_test_db: AsyncSession, test_users):
    """Создание тестовых смен"""
    executors = [u for u in test_users if u.role == "executor"]

    shifts = [
        Shift(
            user_id=executors[0].id,  # Иван - Сантехника
            start_time=datetime.now(),
            status="active",
            specialization="Сантехника"
        ),
        Shift(
            user_id=executors[1].id,  # Петр - Электрика
            start_time=datetime.now(),
            status="active",
            specialization="Электрика"
        ),
        Shift(
            user_id=executors[2].id,  # Мария - Сантехника
            start_time=datetime.now(),
            status="active",
            specialization="Сантехника"
        ),
    ]

    for shift in shifts:
        async_test_db.add(shift)

    await async_test_db.commit()

    for shift in shifts:
        await async_test_db.refresh(shift)

    return shifts


@pytest.fixture
async def test_request(async_test_db: AsyncSession, test_users):
    """Создание тестовой заявки"""
    applicant = [u for u in test_users if u.role == "applicant"][0]

    request = Request(
        request_number="251019-001",
        user_id=applicant.id,
        category="Сантехника",
        address="ул. Тестовая, д. 1",
        description="Протекает кран на кухне",
        status="Новая",
        urgency="Обычная",
        created_at=datetime.now()
    )

    async_test_db.add(request)
    await async_test_db.commit()
    await async_test_db.refresh(request)

    return request


# ========== UNIT TESTS ==========

@pytest.mark.asyncio
async def test_async_dispatcher_initialization(async_test_db):
    """Тест инициализации AsyncSmartDispatcher"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    assert dispatcher.db is not None
    assert dispatcher.weights['specialization'] == 0.35
    assert dispatcher.weights['geography'] == 0.25
    assert dispatcher.weights['workload'] == 0.20
    assert dispatcher.weights['rating'] == 0.15
    assert dispatcher.weights['urgency'] == 0.05
    assert sum(dispatcher.weights.values()) == 1.0


@pytest.mark.asyncio
async def test_calculate_specialization_score(async_test_db, test_request, test_shifts):
    """Тест расчета оценки соответствия специализации"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    # Exact match
    matching_shift = [s for s in test_shifts if s.specialization == "Сантехника"][0]
    score = await dispatcher._calculate_specialization_score(test_request, matching_shift)
    assert score == 1.0

    # No match
    non_matching_shift = [s for s in test_shifts if s.specialization == "Электрика"][0]
    score = await dispatcher._calculate_specialization_score(test_request, non_matching_shift)
    assert score == 0.3  # Partial match fallback


@pytest.mark.asyncio
async def test_calculate_workload_score(async_test_db, test_shifts):
    """Тест расчета оценки нагрузки исполнителя"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    shift = test_shifts[0]

    # Нет активных заявок - максимальная оценка
    score = await dispatcher._calculate_workload_score(shift)
    assert score == 1.0


@pytest.mark.asyncio
async def test_calculate_urgency_score(async_test_db, test_request):
    """Тест расчета оценки срочности заявки"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    test_request.urgency = "Критическая"
    score = await dispatcher._calculate_urgency_score(test_request)
    assert score == 1.0

    test_request.urgency = "Обычная"
    score = await dispatcher._calculate_urgency_score(test_request)
    assert score == 0.5


@pytest.mark.asyncio
async def test_calculate_assignment_score_parallel(async_test_db, test_request, test_shifts):
    """Тест параллельного расчета всех компонентов оценки (KEY PERFORMANCE TEST)"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    shift = test_shifts[0]  # Сантехника - exact match

    # Измеряем время параллельного расчета
    start_time = asyncio.get_event_loop().time()
    score = await dispatcher.calculate_assignment_score(test_request, shift)
    elapsed = asyncio.get_event_loop().time() - start_time

    # Проверяем структуру результата
    assert isinstance(score, AssignmentScore)
    assert score.shift_id == shift.id
    assert score.request_number == test_request.request_number
    assert 0.0 <= score.total_score <= 1.0

    # Проверяем все компоненты
    assert score.specialization_score == 1.0  # Exact match
    assert 0.0 <= score.geographic_score <= 1.0
    assert 0.0 <= score.workload_score <= 1.0
    assert 0.0 <= score.rating_score <= 1.0
    assert 0.0 <= score.urgency_score <= 1.0

    # Performance assertion: должно быть быстро (< 100ms даже на медленном CI)
    assert elapsed < 0.1

    print(f"✅ Parallel score calculation: {elapsed*1000:.2f}ms")


@pytest.mark.asyncio
async def test_find_best_shift_for_request(async_test_db, test_request, test_shifts):
    """Тест поиска лучшей смены для заявки"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    best_assignment = await dispatcher.find_best_shift_for_request(
        test_request,
        test_shifts
    )

    assert best_assignment is not None
    assert isinstance(best_assignment, AssignmentScore)
    assert best_assignment.total_score > 0

    # Проверяем, что выбрана смена с соответствующей специализацией
    best_shift = [s for s in test_shifts if s.id == best_assignment.shift_id][0]
    assert best_shift.specialization == test_request.category


@pytest.mark.asyncio
async def test_find_best_shift_parallel_processing(async_test_db, test_request, test_shifts):
    """Тест параллельной обработки всех смен (PERFORMANCE TEST)"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    start_time = asyncio.get_event_loop().time()
    best_assignment = await dispatcher.find_best_shift_for_request(
        test_request,
        test_shifts
    )
    elapsed = asyncio.get_event_loop().time() - start_time

    assert best_assignment is not None

    # Performance: параллельная обработка 3 смен должна быть быстрой
    assert elapsed < 0.2

    print(f"✅ Parallel shift processing (3 shifts): {elapsed*1000:.2f}ms")


@pytest.mark.asyncio
async def test_auto_assign_request_success(async_test_db, test_request, test_shifts):
    """Тест успешного автоназначения заявки"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    result = await dispatcher.auto_assign_request(test_request.request_number)

    assert result is not None
    assert isinstance(result, AssignmentResult)
    assert result.success is True
    assert result.request_number == test_request.request_number
    assert result.shift_id is not None
    assert result.score is not None
    assert result.score >= dispatcher.min_assignment_score

    # Проверяем, что заявка действительно назначена
    await async_test_db.refresh(test_request)
    assert test_request.executor_id is not None
    assert test_request.status == "В работе"
    assert test_request.assigned_at is not None


@pytest.mark.asyncio
async def test_auto_assign_request_no_shifts(async_test_db, test_request):
    """Тест автоназначения при отсутствии доступных смен"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    # Нет смен в БД
    result = await dispatcher.auto_assign_request(test_request.request_number)

    assert result is not None
    assert result.success is False
    assert "нет доступных смен" in result.message.lower()


@pytest.mark.asyncio
async def test_auto_assign_request_already_assigned(async_test_db, test_request, test_shifts):
    """Тест автоназначения уже назначенной заявки"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    # Назначаем заявку вручную
    test_request.executor_id = test_shifts[0].user_id
    await async_test_db.commit()

    result = await dispatcher.auto_assign_request(test_request.request_number)

    assert result is not None
    assert result.success is False
    assert "уже назначена" in result.message.lower()


@pytest.mark.asyncio
async def test_auto_assign_request_not_found(async_test_db):
    """Тест автоназначения несуществующей заявки"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    result = await dispatcher.auto_assign_request("999999-999")

    assert result is not None
    assert result.success is False
    assert "не найдена" in result.message.lower()


@pytest.mark.asyncio
async def test_auto_assign_low_score_rejection(async_test_db, test_request, test_shifts):
    """Тест отклонения назначения при низком score"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    # Устанавливаем очень высокий порог
    dispatcher.min_assignment_score = 0.95

    # Категория не совпадает ни с одной сменой
    test_request.category = "НесуществующаяКатегория"
    await async_test_db.commit()

    result = await dispatcher.auto_assign_request(test_request.request_number)

    assert result is not None
    assert result.success is False
    assert "не найдена подходящая смена" in result.message.lower()


# ========== INTEGRATION TESTS ==========

@pytest.mark.asyncio
async def test_multiple_concurrent_assignments(async_test_db, test_users, test_shifts):
    """Тест параллельного назначения нескольких заявок (CONCURRENCY TEST)"""
    applicant = [u for u in test_users if u.role == "applicant"][0]

    # Создаем 10 заявок
    requests = []
    for i in range(10):
        request = Request(
            request_number=f"251019-{i:03d}",
            user_id=applicant.id,
            category="Сантехника",
            address=f"ул. Тестовая, д. {i+1}",
            description=f"Заявка #{i+1}",
            status="Новая",
            urgency="Обычная",
            created_at=datetime.now()
        )
        async_test_db.add(request)
        requests.append(request)

    await async_test_db.commit()

    # Параллельно назначаем все заявки
    dispatcher = AsyncSmartDispatcher(async_test_db)

    start_time = asyncio.get_event_loop().time()

    tasks = [
        dispatcher.auto_assign_request(req.request_number)
        for req in requests
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = asyncio.get_event_loop().time() - start_time

    # Проверяем результаты
    successful = sum(1 for r in results if isinstance(r, AssignmentResult) and r.success)

    assert successful > 0  # Хотя бы одна должна быть назначена
    assert all(not isinstance(r, Exception) for r in results)  # Нет исключений

    # Performance: параллельная обработка должна быть эффективной
    avg_time_per_request = elapsed / len(requests)
    assert avg_time_per_request < 0.5  # < 500ms per request

    print(f"✅ Concurrent assignments: {successful}/{len(requests)} successful in {elapsed:.2f}s")
    print(f"   Average per request: {avg_time_per_request*1000:.2f}ms")


@pytest.mark.asyncio
async def test_score_calculation_consistency(async_test_db, test_request, test_shifts):
    """Тест консистентности расчета оценок"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    shift = test_shifts[0]

    # Вычисляем score несколько раз
    scores = []
    for _ in range(5):
        score = await dispatcher.calculate_assignment_score(test_request, shift)
        scores.append(score.total_score)

    # Все оценки должны быть идентичны (детерминированный алгоритм)
    assert len(set(scores)) == 1


@pytest.mark.asyncio
async def test_weighted_score_calculation(async_test_db, test_request, test_shifts):
    """Тест правильности взвешенного расчета оценки"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    shift = test_shifts[0]
    score = await dispatcher.calculate_assignment_score(test_request, shift)

    # Вручную пересчитываем взвешенную сумму
    expected_total = (
        score.specialization_score * dispatcher.weights['specialization'] +
        score.geographic_score * dispatcher.weights['geography'] +
        score.workload_score * dispatcher.weights['workload'] +
        score.rating_score * dispatcher.weights['rating'] +
        score.urgency_score * dispatcher.weights['urgency']
    )

    # Должно совпадать с точностью до погрешности float
    assert abs(score.total_score - expected_total) < 0.001


@pytest.mark.asyncio
async def test_assignment_with_high_workload(async_test_db, test_request, test_shifts, test_users):
    """Тест назначения при высокой нагрузке исполнителей"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    # Создаем много активных заявок для одного исполнителя
    executor = test_shifts[0].user_id

    for i in range(10):
        request = Request(
            request_number=f"251019-{i+100:03d}",
            user_id=test_users[-1].id,
            category="Сантехника",
            address=f"ул. Нагрузки, д. {i+1}",
            description=f"Нагрузочная заявка #{i+1}",
            status="В работе",
            executor_id=executor,
            urgency="Обычная",
            created_at=datetime.now()
        )
        async_test_db.add(request)

    await async_test_db.commit()

    # Назначаем новую заявку
    result = await dispatcher.auto_assign_request(test_request.request_number)

    # Должна назначиться на менее загруженного исполнителя
    assert result.success is True
    assert result.shift_id != test_shifts[0].id  # Не на перегруженного


# ========== PERFORMANCE BENCHMARKS ==========

@pytest.mark.asyncio
async def test_performance_benchmark_single_assignment(async_test_db, test_request, test_shifts):
    """Benchmark: время одного назначения"""
    dispatcher = AsyncSmartDispatcher(async_test_db)

    # Warm-up
    await dispatcher.auto_assign_request(test_request.request_number)

    # Reset
    test_request.executor_id = None
    test_request.status = "Новая"
    await async_test_db.commit()

    # Benchmark
    iterations = 10
    times = []

    for _ in range(iterations):
        test_request.executor_id = None
        test_request.status = "Новая"
        await async_test_db.commit()

        start = asyncio.get_event_loop().time()
        await dispatcher.auto_assign_request(test_request.request_number)
        elapsed = asyncio.get_event_loop().time() - start

        times.append(elapsed)

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    print(f"\n📊 PERFORMANCE BENCHMARK: Single Assignment")
    print(f"   Average: {avg_time*1000:.2f}ms")
    print(f"   Min: {min_time*1000:.2f}ms")
    print(f"   Max: {max_time*1000:.2f}ms")

    # Performance assertions
    assert avg_time < 0.5  # Average < 500ms
    assert max_time < 1.0  # Max < 1s


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
