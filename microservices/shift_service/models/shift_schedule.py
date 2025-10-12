# Shift Schedule Model for Shift Service
# UK Management Bot - Shift Service
# Migrated from monolith: uk_management_bot/database/models/shift_schedule.py

from datetime import date, datetime
from typing import Dict, List, Optional
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Date, DateTime, Boolean, Integer, JSON, Float,
    CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from . import Base


class ScheduleStatus(str, Enum):
    """Shift schedule status enumeration"""
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ShiftSchedule(Base):
    """
    Daily shift planning and scheduling model
    Tracks coverage, predictions, and optimization metrics for a specific date

    Migrated from monolith: uk_management_bot/database/models/shift_schedule.py
    """
    __tablename__ = "shift_schedules"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ========== ОСНОВНАЯ ИНФОРМАЦИЯ ==========
    # Дата, на которую создано расписание
    date = Column(Date, nullable=False, unique=True, index=True)

    # ========== ПЛАНИРОВАНИЕ ПОКРЫТИЯ ==========
    # Запланированное покрытие по часам (JSON)
    # Пример: {"09:00": 2, "10:00": 3, "14:00": 2} - количество исполнителей по часам
    planned_coverage = Column(
        JSON,
        nullable=True,
        comment="Planned hourly coverage: {'09:00': 2, '10:00': 3}"
    )

    # Фактическое покрытие по часам (JSON)
    actual_coverage = Column(
        JSON,
        nullable=True,
        comment="Actual hourly coverage: {'09:00': 2, '10:00': 3}"
    )

    # Запланированное покрытие по специализациям (JSON)
    # Пример: {"PLUMBER": 2, "ELECTRICIAN": 1, "MAINTENANCE": 3}
    planned_specialization_coverage = Column(
        JSON,
        nullable=True,
        comment="Planned specialization coverage: {'PLUMBER': 2, 'ELECTRICIAN': 1}"
    )

    # Фактическое покрытие по специализациям (JSON)
    actual_specialization_coverage = Column(
        JSON,
        nullable=True,
        comment="Actual specialization coverage: {'PLUMBER': 2, 'ELECTRICIAN': 1}"
    )

    # ========== ПРОГНОЗЫ И ПЛАНИРОВАНИЕ ==========
    # Прогнозируемое количество заявок на день
    predicted_requests = Column(Integer, nullable=True, comment="Predicted request count")

    # Фактическое количество заявок
    actual_requests = Column(Integer, default=0, nullable=False, comment="Actual request count")

    # Точность прогноза (0.0-100.0)
    prediction_accuracy = Column(
        Float,
        nullable=True,
        comment="Prediction accuracy percentage (0.0-100.0)"
    )

    # Рекомендуемое количество смен
    recommended_shifts = Column(Integer, nullable=True, comment="AI-recommended shift count")

    # Фактическое количество созданных смен
    actual_shifts = Column(Integer, default=0, nullable=False, comment="Actual created shift count")

    # ========== ОПТИМИЗАЦИЯ ==========
    # Оценка оптимальности расписания (0.0-100.0)
    optimization_score = Column(
        Float,
        nullable=True,
        comment="Schedule optimization score (0.0-100.0)"
    )

    # Процент покрытия потребностей (0.0-100.0)
    coverage_percentage = Column(
        Float,
        nullable=True,
        comment="Coverage fulfillment percentage (0.0-100.0)"
    )

    # Балансировка нагрузки между исполнителями (0.0-100.0)
    load_balance_score = Column(
        Float,
        nullable=True,
        comment="Load balance score across executors (0.0-100.0)"
    )

    # ========== ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ ==========
    # Особые условия дня (праздник, выходной, событие)
    # Пример: ["holiday", "event", "maintenance"]
    special_conditions = Column(
        JSON,
        nullable=True,
        comment="Special day conditions: ['holiday', 'event', 'maintenance']"
    )

    # Корректировки от менеджера
    manual_adjustments = Column(
        JSON,
        nullable=True,
        comment="Manager manual adjustments"
    )

    # Комментарии к расписанию
    notes = Column(String(500), nullable=True, comment="Schedule notes")

    # ========== СТАТУС И МЕТАДАННЫЕ ==========
    # Статус расписания
    status = Column(String(50), default=ScheduleStatus.DRAFT, nullable=False, index=True)

    # Кто создал расписание (UUID пользователя из User Service)
    created_by = Column(UUID(as_uuid=True), nullable=True, comment="User service reference")

    # Автоматически ли создано расписание
    auto_generated = Column(Boolean, default=False, nullable=False, comment="AI auto-generated flag")

    # Версия расписания (для отслеживания изменений)
    version = Column(Integer, default=1, nullable=False, comment="Schedule version number")

    # ========== СИСТЕМНЫЕ ПОЛЯ ==========
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Constraints
    __table_args__ = (
        CheckConstraint('predicted_requests >= 0', name='positive_predicted_requests'),
        CheckConstraint('actual_requests >= 0', name='positive_actual_requests'),
        CheckConstraint('recommended_shifts >= 0', name='positive_recommended_shifts'),
        CheckConstraint('actual_shifts >= 0', name='positive_actual_shifts'),
        CheckConstraint(
            'prediction_accuracy IS NULL OR (prediction_accuracy >= 0.0 AND prediction_accuracy <= 100.0)',
            name='valid_prediction_accuracy'
        ),
        CheckConstraint(
            'optimization_score IS NULL OR (optimization_score >= 0.0 AND optimization_score <= 100.0)',
            name='valid_optimization_score'
        ),
        CheckConstraint(
            'coverage_percentage IS NULL OR (coverage_percentage >= 0.0 AND coverage_percentage <= 100.0)',
            name='valid_coverage_percentage'
        ),
        CheckConstraint(
            'load_balance_score IS NULL OR (load_balance_score >= 0.0 AND load_balance_score <= 100.0)',
            name='valid_load_balance_score'
        ),
        Index('idx_shift_schedules_date_status', 'date', 'status'),
        Index('idx_shift_schedules_created_by', 'created_by'),
    )

    def __repr__(self):
        return f"<ShiftSchedule(id={self.id}, date={self.date}, status={self.status})>"

    # ========== COMPUTED PROPERTIES ==========

    @property
    def coverage_gap_percentage(self) -> float:
        """Возвращает процент недопокрытия потребностей (0.0-100.0)"""
        if self.coverage_percentage is None:
            return 0.0
        return max(0.0, 100.0 - self.coverage_percentage)

    @property
    def is_weekend(self) -> bool:
        """Проверяет, является ли дата выходным днем (суббота/воскресенье)"""
        return self.date.weekday() >= 5  # 5=суббота, 6=воскресенье

    @property
    def weekday(self) -> int:
        """Возвращает день недели (1=понедельник, 7=воскресенье)"""
        return self.date.weekday() + 1

    @property
    def is_understaff(self) -> bool:
        """Проверяет, недоукомплектован ли день (покрытие < 80%)"""
        return self.coverage_percentage is not None and self.coverage_percentage < 80.0

    @property
    def is_overstaffed(self) -> bool:
        """Проверяет, переукомплектован ли день (покрытие > 120%)"""
        return self.coverage_percentage is not None and self.coverage_percentage > 120.0

    # ========== HELPER METHODS ==========

    def get_planned_coverage_at_hour(self, hour: int) -> int:
        """
        Возвращает запланированное покрытие на указанный час

        Args:
            hour: Час дня (0-23)

        Returns:
            Количество исполнителей, запланированных на этот час
        """
        if not self.planned_coverage:
            return 0

        hour_key = f"{hour:02d}:00"
        return self.planned_coverage.get(hour_key, 0)

    def get_actual_coverage_at_hour(self, hour: int) -> int:
        """
        Возвращает фактическое покрытие на указанный час

        Args:
            hour: Час дня (0-23)

        Returns:
            Фактическое количество исполнителей на этот час
        """
        if not self.actual_coverage:
            return 0

        hour_key = f"{hour:02d}:00"
        return self.actual_coverage.get(hour_key, 0)

    def calculate_coverage_gap(self) -> Dict[str, int]:
        """
        Рассчитывает разрыв между планируемым и фактическим покрытием

        Returns:
            Словарь {час: недопокрытие} для часов с недопокрытием
            Пример: {"09:00": 2, "14:00": 1} - не хватает 2 исполнителей в 9:00, 1 в 14:00
        """
        gaps = {}

        if not self.planned_coverage or not self.actual_coverage:
            return gaps

        for hour_key in self.planned_coverage.keys():
            planned = self.planned_coverage.get(hour_key, 0)
            actual = self.actual_coverage.get(hour_key, 0)
            gap = planned - actual

            if gap > 0:  # Недопокрытие
                gaps[hour_key] = gap

        return gaps

    def get_gap_hours(self) -> List[int]:
        """
        Возвращает список часов с недопокрытием

        Returns:
            Список часов (0-23) где фактическое покрытие меньше планового
        """
        gaps = self.calculate_coverage_gap()
        return [int(hour_key.split(":")[0]) for hour_key in gaps.keys()]

    def update_actual_coverage_from_shifts(self, shifts: list) -> None:
        """
        Обновляет фактическое покрытие на основе списка смен

        Args:
            shifts: Список объектов Shift для этого дня

        Side Effects:
            Обновляет actual_coverage, actual_specialization_coverage, actual_shifts
        """
        coverage = {}
        specialization_coverage = {}

        for shift in shifts:
            if not shift.start_time:
                continue

            # Покрытие по часам
            start_hour = shift.start_time.hour
            duration = int(shift.duration_hours) if shift.duration_hours else 8

            for hour in range(start_hour, start_hour + duration):
                if hour >= 24:
                    break  # Не выходим за рамки дня

                hour_key = f"{hour:02d}:00"
                coverage[hour_key] = coverage.get(hour_key, 0) + 1

            # Покрытие по специализациям
            if shift.specialization_focus:
                for spec in shift.specialization_focus:
                    specialization_coverage[spec] = specialization_coverage.get(spec, 0) + 1
            else:
                # Если нет specialization_focus, используем основную specialization
                spec_name = shift.specialization.value if hasattr(shift.specialization, 'value') else str(shift.specialization)
                specialization_coverage[spec_name] = specialization_coverage.get(spec_name, 0) + 1

        self.actual_coverage = coverage
        self.actual_specialization_coverage = specialization_coverage
        self.actual_shifts = len(shifts)

    def calculate_optimization_metrics(self) -> Dict[str, float]:
        """
        Рассчитывает метрики оптимизации расписания

        Returns:
            Словарь с метриками: coverage_percentage, prediction_accuracy

        Side Effects:
            Обновляет self.coverage_percentage и self.prediction_accuracy
        """
        metrics = {}

        # Расчет процента покрытия
        if self.planned_coverage and self.actual_coverage:
            total_planned = sum(self.planned_coverage.values())
            total_actual = sum(self.actual_coverage.values())

            if total_planned > 0:
                coverage_percent = min(100.0, (total_actual / total_planned) * 100.0)
                metrics["coverage_percentage"] = coverage_percent
                self.coverage_percentage = coverage_percent

        # Расчет точности прогноза
        if self.predicted_requests and self.actual_requests:
            if self.predicted_requests > 0:
                error_percent = abs(self.predicted_requests - self.actual_requests) / self.predicted_requests * 100.0
                accuracy = 100.0 - error_percent
                metrics["prediction_accuracy"] = max(0.0, accuracy)
                self.prediction_accuracy = max(0.0, accuracy)

        return metrics

    def is_fully_covered(self, min_coverage: float = 100.0) -> bool:
        """
        Проверяет, полностью ли покрыт день

        Args:
            min_coverage: Минимальный процент покрытия для считания "полным" (по умолчанию 100%)

        Returns:
            True если покрытие >= min_coverage
        """
        if self.coverage_percentage is None:
            return False
        return self.coverage_percentage >= min_coverage
