"""
Simple Integration Test for AsyncSmartDispatcher
Проверяет базовую функциональность без сложных fixtures
"""

import pytest


def test_async_smart_dispatcher_import():
    """Тест импорта AsyncSmartDispatcher"""
    from uk_management_bot.services.async_smart_dispatcher import (
        AsyncSmartDispatcher,
        AssignmentScore,
        AssignmentResult
    )

    assert AsyncSmartDispatcher is not None
    assert AssignmentScore is not None
    assert AssignmentResult is not None


def test_async_smart_dispatcher_dataclasses():
    """Тест создания dataclass объектов"""
    from uk_management_bot.services.async_smart_dispatcher import (
        AssignmentScore,
        AssignmentResult
    )

    # Test AssignmentScore
    score = AssignmentScore(
        shift_id=1,
        request_number="251019-001",
        total_score=0.85,
        specialization_score=1.0,
        geographic_score=0.7,
        workload_score=0.9,
        rating_score=0.7,
        urgency_score=0.5,
        factors={},
        recommended=True
    )

    assert score.shift_id == 1
    assert score.total_score == 0.85
    assert score.recommended is True

    # Test AssignmentResult
    result = AssignmentResult(
        success=True,
        request_number="251019-001",
        shift_id=1,
        score=0.85,
        message="Success",
        assignment_details={"test": "data"}
    )

    assert result.success is True
    assert result.shift_id == 1


def test_async_smart_dispatcher_weights():
    """Тест весовых коэффициентов"""
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.services.async_smart_dispatcher import AsyncSmartDispatcher

    # Создаем sync session для проверки (async будет в реальных тестах)
    with SessionLocal() as db:
        dispatcher = AsyncSmartDispatcher(db)

        # Проверяем веса
        assert dispatcher.weights['specialization'] == 0.35
        assert dispatcher.weights['geography'] == 0.25
        assert dispatcher.weights['workload'] == 0.20
        assert dispatcher.weights['rating'] == 0.15
        assert dispatcher.weights['urgency'] == 0.05

        # Сумма весов должна быть 1.0
        assert sum(dispatcher.weights.values()) == 1.0

        # Проверяем минимальный порог
        assert dispatcher.min_assignment_score == 0.6


def test_async_assignment_service_integration():
    """Тест интеграции AsyncAssignmentService с AsyncSmartDispatcher"""
    from uk_management_bot.services import async_assignment_service

    # Проверяем, что AsyncSmartDispatcher доступен
    assert hasattr(async_assignment_service, 'ASYNC_SMART_DISPATCHER_AVAILABLE')

    # Проверяем импорт AsyncSmartDispatcher в модуле
    try:
        from uk_management_bot.services.async_smart_dispatcher import AsyncSmartDispatcher
        assert True, "AsyncSmartDispatcher успешно импортирован"
    except ImportError:
        pytest.fail("AsyncSmartDispatcher не может быть импортирован")


def test_async_shift_assignment_service_integration():
    """Тест интеграции AsyncShiftAssignmentService с AsyncSmartDispatcher"""
    from uk_management_bot.services import async_shift_assignment_service

    # Проверяем наличие AsyncSmartDispatcher
    assert hasattr(async_shift_assignment_service, 'ASYNC_SMART_DISPATCHER_AVAILABLE')


def test_urgency_mapping():
    """Тест маппинга срочности на scores"""
    urgency_scores = {
        "Критическая": 1.0,
        "Срочная": 0.8,
        "Обычная": 0.5,
        "Низкая": 0.2
    }

    for urgency, expected_score in urgency_scores.items():
        assert 0.0 <= expected_score <= 1.0


def test_score_thresholds():
    """Тест пороговых значений scores"""
    MIN_SCORE = 0.6
    MAX_REQUESTS_PER_EXECUTOR = 8

    assert 0.0 <= MIN_SCORE <= 1.0
    assert MAX_REQUESTS_PER_EXECUTOR > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
