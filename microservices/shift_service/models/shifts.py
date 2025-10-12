# Shift Models for Shift Service
# UK Management Bot - Shift Service

from datetime import datetime, time
from typing import Optional, List
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, DateTime, Boolean, Integer, Text, ForeignKey,
    Time, JSON, Float, Index, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from . import Base


class ShiftStatus(str, Enum):
    """Shift status enumeration"""
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TRANSFERRED = "transferred"


class ShiftType(str, Enum):
    """Shift type enumeration"""
    REGULAR = "regular"
    OVERTIME = "overtime"
    EMERGENCY = "emergency"
    REPLACEMENT = "replacement"
    TRAINING = "training"


class SpecializationType(str, Enum):
    """Specialization type enumeration - migrated from monolith"""
    PLUMBER = "plumber"
    ELECTRICIAN = "electrician"
    CARPENTER = "carpenter"
    PAINTER = "painter"
    JANITOR = "janitor"
    SECURITY = "security"
    LANDSCAPER = "landscaper"
    MAINTENANCE = "maintenance"
    MANAGER = "manager"
    INSPECTOR = "inspector"
    REPAIR = "repair"
    EMERGENCY = "emergency"


class Shift(Base):
    """
    Core shift model representing individual work shifts
    Migrated from monolith uk_management_bot.database.shifts
    """
    __tablename__ = "shifts"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic shift information
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text)

    # Timing - Actual times
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False, index=True)
    duration_hours = Column(Float, nullable=False)

    # ========== НОВЫЕ ПОЛЯ ПЛАНИРОВАНИЯ ==========
    # Планируемое время смены (из tasks.md:2918-2920)
    planned_start_time = Column(DateTime(timezone=True), nullable=True, comment="Планируемое время начала")
    planned_end_time = Column(DateTime(timezone=True), nullable=True, comment="Планируемое время окончания")

    # Status and type
    status = Column(ENUM(ShiftStatus), nullable=False, default=ShiftStatus.PLANNED, index=True)
    shift_type = Column(ENUM(ShiftType), nullable=False, default=ShiftType.REGULAR)

    # Assignment information
    executor_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # User service reference
    specialization = Column(ENUM(SpecializationType), nullable=False, index=True)

    # ========== НОВЫЕ ПОЛЯ СПЕЦИАЛИЗАЦИИ (tasks.md:2924-2927) ==========
    # Фокус специализации для смены (JSON массив)
    specialization_focus = Column(JSON, nullable=True, comment='Массив специализаций ["electric", "plumbing"]')

    # Зоны покрытия (JSON массив)
    coverage_areas = Column(JSON, nullable=True, comment='Массив зон ["building_A", "yard_1"]')

    # Географическая зона
    geographic_zone = Column(String(100), nullable=True, comment="Географическая зона")

    # Location information
    location = Column(String(300))
    coordinates = Column(JSON)  # {"lat": float, "lng": float}
    address = Column(Text)

    # Requirements and preferences
    requirements = Column(JSON)  # Specific requirements for this shift
    priority = Column(Integer, default=1, index=True)  # 1=low, 2=medium, 3=high, 4=urgent

    # ========== НОВЫЕ ПОЛЯ ПЛАНИРОВАНИЯ НАГРУЗКИ (tasks.md:2929-2932) ==========
    # Максимальное количество заявок на смену
    max_requests = Column(Integer, default=10, nullable=False, comment="Максимум заявок на смену")

    # Текущее количество назначенных заявок
    current_request_count = Column(Integer, default=0, nullable=False, comment="Текущее количество заявок")

    # Template reference
    template_id = Column(UUID(as_uuid=True), ForeignKey("shift_templates.id"), nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=False)  # User service reference

    # ========== РАСШИРЕННЫЕ ПОЛЯ АНАЛИТИКИ (tasks.md:2934-2939) ==========
    # Завершенные заявки за смену
    completed_requests = Column(Integer, default=0, nullable=False, comment="Завершенные заявки")

    # Среднее время выполнения заявки (в минутах)
    average_completion_time = Column(Float, nullable=True, comment="Среднее время выполнения (мин)")

    # Среднее время отклика на заявки (в минутах)
    average_response_time = Column(Float, nullable=True, comment="Среднее время отклика (мин)")

    # Рейтинг качества работы за смену (1.0-5.0)
    completion_rating = Column(Float, nullable=True, comment="Рейтинг качества (1.0-5.0)")

    # Заметки при завершении смены (Bug #18 fix)
    completion_notes = Column(Text, nullable=True, comment="Заметки при завершении смены")

    # Фактическая продолжительность
    actual_duration_hours = Column(Float, nullable=True, comment="Фактическая продолжительность (часы)")

    # Оценка эффективности (0.0-100.0)
    efficiency_score = Column(Float, nullable=True, comment="Эффективность (0-100)")

    # Relationships
    template = relationship("ShiftTemplate", back_populates="shifts")
    assignments = relationship("ShiftAssignment", back_populates="shift", cascade="all, delete-orphan")
    transfers = relationship("ShiftTransfer", back_populates="shift", cascade="all, delete-orphan")

    # Constraints
    __table_args__ = (
        CheckConstraint('start_time < end_time', name='start_before_end'),
        CheckConstraint('duration_hours > 0', name='positive_duration'),
        CheckConstraint('priority >= 1 AND priority <= 4', name='valid_priority'),
        CheckConstraint('completion_rating IS NULL OR (completion_rating >= 1.0 AND completion_rating <= 5.0)',
                       name='valid_rating'),
        CheckConstraint('max_requests >= 0', name='valid_max_requests'),
        CheckConstraint('current_request_count >= 0', name='valid_request_count'),
        CheckConstraint('completed_requests >= 0', name='valid_completed_requests'),
        Index('idx_shifts_executor_date', 'executor_id', 'start_time'),
        Index('idx_shifts_status_priority', 'status', 'priority'),
        Index('idx_shifts_specialization_date', 'specialization', 'start_time'),
        Index('idx_shifts_geographic_zone', 'geographic_zone'),
    )

    def __repr__(self):
        return f"<Shift(id={self.id}, title='{self.title}', status='{self.status}')>"

    # ========== НОВЫЕ МЕТОДЫ МОДЕЛИ (tasks.md:2941-2946) ==========

    @property
    def is_full(self) -> bool:
        """Проверяет, заполнена ли смена до максимума заявок"""
        return self.current_request_count >= self.max_requests

    @property
    def load_percentage(self) -> float:
        """Возвращает процент загруженности смены (0-100)"""
        if self.max_requests == 0:
            return 0.0
        return (self.current_request_count / self.max_requests) * 100.0

    def can_handle_specialization(self, required_specialization: str) -> bool:
        """
        Проверяет, может ли смена обработать заявку с определенной специализацией

        Args:
            required_specialization: Требуемая специализация

        Returns:
            True если смена может обработать специализацию
        """
        if not self.specialization_focus:
            return True  # Универсальная смена

        return (
            required_specialization in self.specialization_focus or
            "universal" in self.specialization_focus
        )

    def can_handle_area(self, area: str) -> bool:
        """
        Проверяет, может ли смена обработать заявку в определенной зоне

        Args:
            area: Зона покрытия

        Returns:
            True если смена покрывает указанную зону
        """
        if not self.coverage_areas:
            return True  # Покрывает все зоны

        return area in self.coverage_areas or "all" in self.coverage_areas


class ShiftTemplate(Base):
    """
    Shift template model for recurring shift patterns
    Supports the 5 predefined templates from the monolith
    """
    __tablename__ = "shift_templates"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Template information
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text)

    # Timing patterns
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    duration_hours = Column(Float, nullable=False)

    # Days of week (JSON array: [1,2,3,4,5] for Mon-Fri)
    days_of_week = Column(JSON, nullable=False)

    # Requirements
    specialization = Column(ENUM(SpecializationType), nullable=False)
    max_executors = Column(Integer, default=1)

    # Template configuration
    is_active = Column(Boolean, default=True, index=True)
    auto_assign = Column(Boolean, default=False)

    # Recurrence rules
    recurrence_pattern = Column(JSON)  # Complex recurrence rules

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(UUID(as_uuid=True), nullable=False)

    # Relationships
    shifts = relationship("Shift", back_populates="template")

    # Constraints
    __table_args__ = (
        CheckConstraint('start_time < end_time', name='template_start_before_end'),
        CheckConstraint('duration_hours > 0', name='template_positive_duration'),
        CheckConstraint('max_executors > 0', name='template_positive_executors'),
    )

    def __repr__(self):
        return f"<ShiftTemplate(id={self.id}, name='{self.name}', specialization='{self.specialization}')>"


class ShiftAssignment(Base):
    """
    Shift assignment tracking model
    Handles assignment history and changes
    """
    __tablename__ = "shift_assignments"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # References
    shift_id = Column(UUID(as_uuid=True), ForeignKey("shifts.id"), nullable=False, index=True)
    executor_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # User service reference

    # Assignment details
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    assigned_by = Column(UUID(as_uuid=True), nullable=False)  # User service reference

    # Assignment method
    assignment_method = Column(String(50), nullable=False)  # manual, ai, auto, transfer
    confidence_score = Column(Float)  # AI assignment confidence
    notes = Column(Text, nullable=True)  # Assignment notes/reason

    # Status tracking
    is_active = Column(Boolean, default=True, index=True)
    unassigned_at = Column(DateTime(timezone=True))
    unassigned_by = Column(UUID(as_uuid=True))
    unassignment_reason = Column(Text)

    # Performance tracking
    acceptance_time = Column(DateTime(timezone=True))  # When executor accepted
    start_time = Column(DateTime(timezone=True))  # When executor started work
    completion_time = Column(DateTime(timezone=True))  # When executor completed

    # Relationships
    shift = relationship("Shift", back_populates="assignments")

    # Constraints
    __table_args__ = (
        Index('idx_assignments_shift_active', 'shift_id', 'is_active'),
        Index('idx_assignments_executor_date', 'executor_id', 'assigned_at'),
    )

    def __repr__(self):
        return f"<ShiftAssignment(id={self.id}, shift_id={self.shift_id}, executor_id={self.executor_id})>"