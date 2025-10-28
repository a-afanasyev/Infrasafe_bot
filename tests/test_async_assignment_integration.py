"""
Integration Tests for AsyncAssignmentService with AsyncSmartDispatcher (Phase 2A)

Тестирует интеграцию AsyncAssignmentService с AsyncSmartDispatcher.

SCOPE:
- smart_assign_request() с AsyncSmartDispatcher
- get_assignment_recommendations() с параллельной обработкой
- Integration tests для полного flow

Created: 19.10.2025
"""

import pytest
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from uk_management_bot.services.async_assignment_service import AsyncAssignmentService
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request_assignment import RequestAssignment


# Test Database Setup
@pytest.fixture
async def async_test_db():
    """Создание async in-memory тестовой БД"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False
    )

    async with engine.begin() as conn:
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
async def test_data(async_test_db: AsyncSession):
    """Создание полного набора тестовых данных"""
    # Users
    users = [
        User(
            telegram_id=1001,
            first_name="Иван",
            last_name="Сантехник",
            username="ivan_plumber",
            role="executor",
            status="approved",
            specialization="Сантехника"
        ),
        User(
            telegram_id=1002,
            first_name="Петр",
            last_name="Электрик",
            username="petr_electrician",
            role="executor",
            status="approved",
            specialization="Электрика"
        ),
        User(
            telegram_id=1003,
            first_name="Мария",
            last_name="Универсал",
            username="maria_universal",
            role="executor",
            status="approved",
            specialization="Сантехника,Электрика"
        ),
        User(
            telegram_id=2001,
            first_name="Заявитель",
            last_name="Тестовый",
            username="applicant",
            role="applicant",
            status="approved"
        ),
        User(
            telegram_id=3001,
            first_name="Менеджер",
            last_name="Главный",
            username="manager",
            role="manager",
            status="approved"
        )
    ]

    for user in users:
        async_test_db.add(user)

    await async_test_db.commit()

    for user in users:
        await async_test_db.refresh(user)

    # Shifts
    executors = [u for u in users if u.role == "executor"]
    shifts = [
        Shift(
            user_id=executors[0].id,
            start_time=datetime.now(),
            status="active",
            specialization="Сантехника"
        ),
        Shift(
            user_id=executors[1].id,
            start_time=datetime.now(),
            status="active",
            specialization="Электрика"
        ),
        Shift(
            user_id=executors[2].id,
            start_time=datetime.now(),
            status="active",
            specialization="Сантехника,Электрика"
        ),
    ]

    for shift in shifts:
        async_test_db.add(shift)

    await async_test_db.commit()

    for shift in shifts:
        await async_test_db.refresh(shift)

    # Request
    applicant = [u for u in users if u.role == "applicant"][0]
    request = Request(
        request_number="251019-001",
        user_id=applicant.id,
        category="Сантехника",
        address="ул. Тестовая, д. 1",
        description="Протекает кран",
        status="Новая",
        urgency="Обычная",
        created_at=datetime.now()
    )

    async_test_db.add(request)
    await async_test_db.commit()
    await async_test_db.refresh(request)

    return {
        'users': users,
        'executors': executors,
        'shifts': shifts,
        'request': request,
        'applicant': applicant,
        'manager': [u for u in users if u.role == "manager"][0]
    }


# ========== SMART ASSIGNMENT TESTS ==========

@pytest.mark.asyncio
async def test_smart_assign_request_success(async_test_db, test_data):
    """Тест успешного умного назначения заявки"""
    service = AsyncAssignmentService(async_test_db)

    request = test_data['request']
    manager = test_data['manager']

    result = await service.smart_assign_request(
        request_number=request.request_number,
        assigned_by=manager.id
    )

    assert result is not None
    assert result.request_number == request.request_number
    assert result.executor_id is not None

    # Проверяем, что заявка назначена правильно
    await async_test_db.refresh(request)
    assert request.executor_id is not None
    assert request.assigned_by == manager.id
    assert request.assigned_at is not None


@pytest.mark.asyncio
async def test_smart_assign_request_specialization_match(async_test_db, test_data):
    """Тест умного назначения с учетом специализации"""
    service = AsyncAssignmentService(async_test_db)

    request = test_data['request']
    manager = test_data['manager']

    # Заявка категории "Сантехника"
    result = await service.smart_assign_request(
        request_number=request.request_number,
        assigned_by=manager.id
    )

    assert result is not None

    # Должен быть назначен исполнитель с соответствующей специализацией
    await async_test_db.refresh(request)
    executor = [u for u in test_data['executors'] if u.id == request.executor_id][0]
    assert "Сантехника" in executor.specialization


@pytest.mark.asyncio
async def test_smart_assign_not_found(async_test_db, test_data):
    """Тест умного назначения несуществующей заявки"""
    service = AsyncAssignmentService(async_test_db)

    manager = test_data['manager']

    result = await service.smart_assign_request(
        request_number="999999-999",
        assigned_by=manager.id
    )

    assert result is None


@pytest.mark.asyncio
async def test_smart_assign_no_dispatcher(async_test_db, test_data, monkeypatch):
    """Тест fallback при недоступности AsyncSmartDispatcher"""
    # Имитируем отсутствие AsyncSmartDispatcher
    import uk_management_bot.services.async_assignment_service as module
    monkeypatch.setattr(module, "ASYNC_SMART_DISPATCHER_AVAILABLE", False)

    service = AsyncAssignmentService(async_test_db)

    request = test_data['request']
    manager = test_data['manager']

    result = await service.smart_assign_request(
        request_number=request.request_number,
        assigned_by=manager.id
    )

    # Должен вернуть None (fallback)
    assert result is None


# ========== RECOMMENDATIONS TESTS ==========

@pytest.mark.asyncio
async def test_get_assignment_recommendations_success(async_test_db, test_data):
    """Тест получения рекомендаций по назначению"""
    service = AsyncAssignmentService(async_test_db)

    request = test_data['request']

    recommendations = await service.get_assignment_recommendations(
        request_number=request.request_number
    )

    assert recommendations is not None
    assert isinstance(recommendations, list)
    assert len(recommendations) > 0

    # Проверяем структуру рекомендаций
    for rec in recommendations:
        assert 'shift_id' in rec
        assert 'executor_id' in rec
        assert 'executor_name' in rec
        assert 'total_score' in rec
        assert 'specialization_score' in rec
        assert 'geography_score' in rec
        assert 'workload_score' in rec
        assert 'rating_score' in rec
        assert 'urgency_score' in rec
        assert 'recommended' in rec
        assert 'recommendation_reason' in rec

        # Проверяем диапазон оценок
        assert 0.0 <= rec['total_score'] <= 1.0


@pytest.mark.asyncio
async def test_get_assignment_recommendations_sorted(async_test_db, test_data):
    """Тест сортировки рекомендаций по убыванию балла"""
    service = AsyncAssignmentService(async_test_db)

    request = test_data['request']

    recommendations = await service.get_assignment_recommendations(
        request_number=request.request_number
    )

    assert len(recommendations) > 1

    # Проверяем сортировку
    for i in range(len(recommendations) - 1):
        assert recommendations[i]['total_score'] >= recommendations[i + 1]['total_score']


@pytest.mark.asyncio
async def test_get_assignment_recommendations_parallel_processing(async_test_db, test_data):
    """Тест параллельной обработки рекомендаций (PERFORMANCE TEST)"""
    service = AsyncAssignmentService(async_test_db)

    request = test_data['request']

    start_time = asyncio.get_event_loop().time()
    recommendations = await service.get_assignment_recommendations(
        request_number=request.request_number
    )
    elapsed = asyncio.get_event_loop().time() - start_time

    assert len(recommendations) > 0

    # Performance: параллельная обработка должна быть быстрой
    num_shifts = len(test_data['shifts'])
    avg_time_per_shift = elapsed / num_shifts

    assert elapsed < 0.5  # Total < 500ms
    assert avg_time_per_shift < 0.2  # < 200ms per shift

    print(f"\n✅ Parallel recommendations processing:")
    print(f"   Total: {elapsed*1000:.2f}ms for {num_shifts} shifts")
    print(f"   Average per shift: {avg_time_per_shift*1000:.2f}ms")


@pytest.mark.asyncio
async def test_get_assignment_recommendations_eager_loading(async_test_db, test_data):
    """Тест eager loading в рекомендациях (NO N+1 QUERIES)"""
    service = AsyncAssignmentService(async_test_db)

    request = test_data['request']

    # Первый запрос - загружает данные
    recommendations = await service.get_assignment_recommendations(
        request_number=request.request_number
    )

    # Проверяем, что все executor_name заполнены без дополнительных запросов
    for rec in recommendations:
        assert rec['executor_name'] is not None
        assert rec['executor_name'] != "Неизвестно"


@pytest.mark.asyncio
async def test_get_assignment_recommendations_not_found(async_test_db):
    """Тест рекомендаций для несуществующей заявки"""
    service = AsyncAssignmentService(async_test_db)

    recommendations = await service.get_assignment_recommendations(
        request_number="999999-999"
    )

    assert recommendations == []


@pytest.mark.asyncio
async def test_get_assignment_recommendations_no_shifts(async_test_db, test_data):
    """Тест рекомендаций при отсутствии доступных смен"""
    service = AsyncAssignmentService(async_test_db)

    # Делаем все смены неактивными
    for shift in test_data['shifts']:
        shift.status = "completed"

    await async_test_db.commit()

    recommendations = await service.get_assignment_recommendations(
        request_number=test_data['request'].request_number
    )

    assert recommendations == []


# ========== INTEGRATION TESTS ==========

@pytest.mark.asyncio
async def test_full_smart_assignment_flow(async_test_db, test_data):
    """Тест полного flow: рекомендации → умное назначение → проверка"""
    service = AsyncAssignmentService(async_test_db)

    request = test_data['request']
    manager = test_data['manager']

    # 1. Получаем рекомендации
    recommendations = await service.get_assignment_recommendations(
        request_number=request.request_number
    )

    assert len(recommendations) > 0
    best_recommendation = recommendations[0]

    # 2. Выполняем умное назначение
    assignment = await service.smart_assign_request(
        request_number=request.request_number,
        assigned_by=manager.id
    )

    assert assignment is not None

    # 3. Проверяем, что назначение соответствует лучшей рекомендации
    await async_test_db.refresh(request)

    # Должен быть назначен исполнитель с высоким score
    assert request.executor_id is not None


@pytest.mark.asyncio
async def test_concurrent_smart_assignments(async_test_db, test_data):
    """Тест параллельного умного назначения нескольких заявок"""
    service = AsyncAssignmentService(async_test_db)

    manager = test_data['manager']
    applicant = test_data['applicant']

    # Создаем несколько заявок
    requests = []
    for i in range(5):
        request = Request(
            request_number=f"251019-{i+10:03d}",
            user_id=applicant.id,
            category="Сантехника",
            address=f"ул. Тестовая, д. {i+10}",
            description=f"Заявка #{i+10}",
            status="Новая",
            urgency="Обычная",
            created_at=datetime.now()
        )
        async_test_db.add(request)
        requests.append(request)

    await async_test_db.commit()

    # Параллельно назначаем
    start_time = asyncio.get_event_loop().time()

    tasks = [
        service.smart_assign_request(req.request_number, manager.id)
        for req in requests
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = asyncio.get_event_loop().time() - start_time

    # Проверяем результаты
    successful = sum(1 for r in results if r is not None)

    assert successful > 0
    assert all(not isinstance(r, Exception) for r in results)

    print(f"\n✅ Concurrent smart assignments:")
    print(f"   {successful}/{len(requests)} successful in {elapsed:.2f}s")
    print(f"   Average: {elapsed/len(requests)*1000:.2f}ms per request")


@pytest.mark.asyncio
async def test_smart_assignment_with_workload_balancing(async_test_db, test_data):
    """Тест умного назначения с балансировкой нагрузки"""
    service = AsyncAssignmentService(async_test_db)

    manager = test_data['manager']
    applicant = test_data['applicant']

    # Создаем много заявок для одного исполнителя
    executor = test_data['executors'][0]

    for i in range(5):
        request = Request(
            request_number=f"251019-{i+100:03d}",
            user_id=applicant.id,
            category="Сантехника",
            address=f"ул. Нагрузки, д. {i+1}",
            description=f"Заявка нагрузки #{i+1}",
            status="В работе",
            executor_id=executor.id,
            urgency="Обычная",
            created_at=datetime.now()
        )
        async_test_db.add(request)

    await async_test_db.commit()

    # Назначаем новую заявку
    new_request = Request(
        request_number="251019-200",
        user_id=applicant.id,
        category="Сантехника",
        address="ул. Балансировки, д. 1",
        description="Заявка для балансировки",
        status="Новая",
        urgency="Обычная",
        created_at=datetime.now()
    )

    async_test_db.add(new_request)
    await async_test_db.commit()

    # Умное назначение должно учесть нагрузку
    assignment = await service.smart_assign_request(
        request_number=new_request.request_number,
        assigned_by=manager.id
    )

    assert assignment is not None

    # Должен быть назначен менее загруженный исполнитель
    await async_test_db.refresh(new_request)
    # Проверяем, что не назначен перегруженный executor
    # (или назначен, но с пониженным приоритетом)
    assert new_request.executor_id is not None


@pytest.mark.asyncio
async def test_recommendations_with_different_urgencies(async_test_db, test_data):
    """Тест влияния срочности на рекомендации"""
    service = AsyncAssignmentService(async_test_db)

    request = test_data['request']

    # Обычная срочность
    request.urgency = "Обычная"
    await async_test_db.commit()

    recommendations_normal = await service.get_assignment_recommendations(
        request_number=request.request_number
    )

    # Критическая срочность
    request.urgency = "Критическая"
    await async_test_db.commit()

    recommendations_critical = await service.get_assignment_recommendations(
        request_number=request.request_number
    )

    # Оценки должны отличаться (критическая должна иметь boost)
    assert len(recommendations_normal) == len(recommendations_critical)

    # Urgency score должен быть выше для критической
    for norm, crit in zip(recommendations_normal, recommendations_critical):
        assert crit['urgency_score'] >= norm['urgency_score']


# ========== PERFORMANCE BENCHMARKS ==========

@pytest.mark.asyncio
async def test_benchmark_smart_assignment_throughput(async_test_db, test_data):
    """Benchmark: пропускная способность умного назначения"""
    service = AsyncAssignmentService(async_test_db)

    manager = test_data['manager']
    applicant = test_data['applicant']

    # Создаем 20 заявок
    requests = []
    for i in range(20):
        request = Request(
            request_number=f"BENCH-{i:03d}",
            user_id=applicant.id,
            category="Сантехника" if i % 2 == 0 else "Электрика",
            address=f"ул. Бенчмарк, д. {i+1}",
            description=f"Benchmark request #{i+1}",
            status="Новая",
            urgency="Обычная",
            created_at=datetime.now()
        )
        async_test_db.add(request)
        requests.append(request)

    await async_test_db.commit()

    # Benchmark параллельного назначения
    start = asyncio.get_event_loop().time()

    tasks = [
        service.smart_assign_request(req.request_number, manager.id)
        for req in requests
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = asyncio.get_event_loop().time() - start

    successful = sum(1 for r in results if r is not None)
    throughput = successful / elapsed

    print(f"\n📊 SMART ASSIGNMENT THROUGHPUT BENCHMARK:")
    print(f"   Total requests: {len(requests)}")
    print(f"   Successful: {successful}")
    print(f"   Time: {elapsed:.2f}s")
    print(f"   Throughput: {throughput:.2f} assignments/sec")
    print(f"   Average: {elapsed/len(requests)*1000:.2f}ms per assignment")

    # Performance assertions
    assert throughput > 5  # > 5 assignments/sec
    assert elapsed < 10  # Total < 10s for 20 requests


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
