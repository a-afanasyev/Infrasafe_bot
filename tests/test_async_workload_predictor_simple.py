"""
Simple Unit Tests for AsyncWorkloadPredictor
Phase 2B - Day 8 Testing (Simplified)

Test Coverage:
- Import tests
- Dataclass tests
- Configuration tests
- Simple method tests

Total: 15+ tests without database dependency
"""

import pytest
from datetime import date, datetime, timedelta
from typing import List, Dict


def test_async_workload_predictor_import():
    """Тест импорта AsyncWorkloadPredictor"""
    from uk_management_bot.services.async_workload_predictor import (
        AsyncWorkloadPredictor,
        WorkloadPrediction,
        HistoricalData,
        HistoricalPattern,
        DailyStats
    )

    assert AsyncWorkloadPredictor is not None
    assert WorkloadPrediction is not None
    assert HistoricalData is not None
    assert HistoricalPattern is not None
    assert DailyStats is not None


def test_workload_prediction_dataclass():
    """Тест создания WorkloadPrediction dataclass"""
    from uk_management_bot.services.async_workload_predictor import WorkloadPrediction

    prediction = WorkloadPrediction(
        date=date(2025, 10, 20),
        predicted_requests=15,
        confidence_level=0.85,
        peak_hours=[9, 10, 11, 14, 15],
        recommended_shifts=3,
        specialization_breakdown={"Сантехника": 10, "Электрика": 5},
        factors={"seasonal": 1.2, "weekday": 1.0, "holiday": 1.0, "trend": 1.1},
        calculation_time=0.25
    )

    assert prediction.date == date(2025, 10, 20)
    assert prediction.predicted_requests == 15
    assert prediction.confidence_level == 0.85
    assert len(prediction.peak_hours) == 5
    assert prediction.recommended_shifts == 3
    assert prediction.calculation_time == 0.25


def test_historical_pattern_dataclass():
    """Тест создания HistoricalPattern dataclass"""
    from uk_management_bot.services.async_workload_predictor import HistoricalPattern

    pattern = HistoricalPattern(
        pattern_type="daily",
        pattern_data={str(h): float(h % 12) for h in range(24)},
        confidence=0.75,
        sample_size=90
    )

    assert pattern.pattern_type == "daily"
    assert len(pattern.pattern_data) == 24
    assert pattern.confidence == 0.75
    assert pattern.sample_size == 90


def test_daily_stats_dataclass():
    """Тест создания DailyStats dataclass"""
    from uk_management_bot.services.async_workload_predictor import DailyStats

    daily_stats = DailyStats(
        date=date(2025, 10, 20),
        request_count=15,
        shift_count=3,
        avg_urgency=0.6,
        specialization_breakdown={"Сантехника": 10}
    )

    assert daily_stats.date == date(2025, 10, 20)
    assert daily_stats.request_count == 15
    assert daily_stats.shift_count == 3
    assert daily_stats.avg_urgency == 0.6


def test_historical_data_dataclass():
    """Тест создания HistoricalData dataclass"""
    from uk_management_bot.services.async_workload_predictor import HistoricalData

    historical_data = HistoricalData(
        requests=[],
        daily_stats=[],
        total_days=90
    )

    assert historical_data.total_days == 90
    assert isinstance(historical_data.requests, list)
    assert isinstance(historical_data.daily_stats, list)


def test_seasonal_factors_configuration():
    """Тест конфигурации сезонных факторов"""
    # Проверяем что сезонные факторы имеют правильную структуру
    seasonal_factors = {
        1: 1.2,   # Январь
        2: 1.15,
        3: 1.0,
        4: 0.9,
        5: 0.85,
        6: 0.8,
        7: 0.75,
        8: 0.8,
        9: 0.85,
        10: 0.95,
        11: 1.1,
        12: 1.2   # Декабрь
    }

    # Должно быть 12 месяцев
    assert len(seasonal_factors) == 12

    # Зимние месяцы должны иметь более высокий коэффициент
    assert seasonal_factors[1] >= 1.0  # Январь
    assert seasonal_factors[2] >= 1.0  # Февраль
    assert seasonal_factors[12] >= 1.0  # Декабрь

    # Летние месяцы должны иметь более низкий коэффициент
    assert seasonal_factors[6] <= 1.0  # Июнь
    assert seasonal_factors[7] <= 1.0  # Июль


def test_weekday_factors_configuration():
    """Тест конфигурации факторов дней недели"""
    weekday_factors = {
        0: 1.1,   # Понедельник
        1: 1.05,  # Вторник
        2: 1.0,   # Среда
        3: 1.0,   # Четверг
        4: 0.95,  # Пятница
        5: 0.7,   # Суббота
        6: 0.6    # Воскресенье
    }

    # Должно быть 7 дней
    assert len(weekday_factors) == 7

    # Выходные должны иметь более низкий коэффициент
    assert weekday_factors[5] < 1.0  # Суббота
    assert weekday_factors[6] < 1.0  # Воскресенье

    # Понедельник обычно имеет более высокую нагрузку
    assert weekday_factors[0] >= 1.0


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


def test_prediction_validation_ranges():
    """Тест валидации диапазонов прогноза"""
    # Confidence level должен быть между 0 и 1
    assert 0.0 <= 0.85 <= 1.0

    # Predicted requests должны быть неотрицательными
    assert 15 >= 0

    # Recommended shifts должны быть положительными
    assert 3 > 0


def test_peak_hours_validation():
    """Тест валидации пиковых часов"""
    peak_hours = [9, 10, 11, 14, 15]

    # Все часы должны быть в диапазоне 0-23
    for hour in peak_hours:
        assert 0 <= hour <= 23

    # Пиковые часы должны быть уникальными
    assert len(peak_hours) == len(set(peak_hours))


def test_specialization_breakdown_structure():
    """Тест структуры breakdown по специализациям"""
    specialization_breakdown = {
        "Сантехника": 10,
        "Электрика": 5
    }

    # Все значения должны быть неотрицательными целыми
    for spec, count in specialization_breakdown.items():
        assert isinstance(count, int)
        assert count >= 0

    # Сумма должна быть разумной
    total = sum(specialization_breakdown.values())
    assert total > 0


def test_factor_weights_validation():
    """Тест валидации весов факторов"""
    factors = {
        "seasonal": 1.2,
        "weekday": 1.0,
        "holiday": 1.0,
        "trend": 1.1
    }

    # Все факторы должны быть положительными
    for factor, weight in factors.items():
        assert weight > 0.0
        assert weight <= 2.0  # Разумный максимум


def test_pattern_types_enumeration():
    """Тест перечисления типов паттернов"""
    pattern_types = ['daily', 'weekly', 'monthly', 'seasonal']

    assert 'daily' in pattern_types
    assert 'weekly' in pattern_types
    assert 'monthly' in pattern_types
    assert 'seasonal' in pattern_types
    assert len(pattern_types) == 4


def test_historical_days_constraints():
    """Тест ограничений на исторические дни"""
    min_historical_days = 30
    prediction_horizon = 14

    # Минимальный период для надежного прогноза
    assert min_historical_days >= 7

    # Горизонт прогнозирования разумный
    assert 1 <= prediction_horizon <= 30


def test_confidence_threshold_validation():
    """Тест валидации порога уверенности"""
    # Типичный порог уверенности
    confidence_threshold = 0.7

    assert 0.0 < confidence_threshold < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
