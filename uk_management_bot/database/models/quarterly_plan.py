from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float, JSON, Date
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base
from datetime import date
from typing import Dict, List, Any, Optional


class QuarterlyPlan(Base):
    """Модель квартального плана смен."""
    
    __tablename__ = "quarterly_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Основная информация о плане
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)  # 1, 2, 3, 4
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    # Создатель плана
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    creator = relationship("User", foreign_keys=[created_by])
    
    # Статус плана
    status = Column(String(50), default="draft", nullable=False)  # draft, active, archived, cancelled
    
    # Конфигурация плана
    specializations = Column(JSON, nullable=True)  # ["electric", "plumbing", "security"]
    coverage_24_7 = Column(Boolean, default=False, nullable=False)
    load_balancing_enabled = Column(Boolean, default=True, nullable=False)
    auto_transfers_enabled = Column(Boolean, default=True, nullable=False)
    notifications_enabled = Column(Boolean, default=True, nullable=False)
    
    # Метрики планирования
    total_shifts_planned = Column(Integer, default=0, nullable=False)
    total_hours_planned = Column(Float, default=0.0, nullable=False)
    coverage_percentage = Column(Float, default=0.0, nullable=False)  # Процент покрытия времени
    
    # Статистика конфликтов
    total_conflicts = Column(Integer, default=0, nullable=False)
    resolved_conflicts = Column(Integer, default=0, nullable=False)
    pending_conflicts = Column(Integer, default=0, nullable=False)
    
    # Дополнительные настройки (JSON)
    settings = Column(JSON, nullable=True)
    
    # Заметки и комментарии
    notes = Column(Text, nullable=True)
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    activated_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    
    # Связи
    schedules = relationship("QuarterlyShiftSchedule", back_populates="quarterly_plan", cascade="all, delete-orphan")
    conflicts = relationship("PlanningConflict", back_populates="quarterly_plan", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<QuarterlyPlan(id={self.id}, {self.year}Q{self.quarter}, status={self.status})>"
    
    @property
    def quarter_name(self) -> str:
        """Возвращает название квартала."""
        quarter_names = {
            1: "I квартал",
            2: "II квартал", 
            3: "III квартал",
            4: "IV квартал"
        }
        return quarter_names.get(self.quarter, f"{self.quarter} квартал")
    
    @property
    def period_display(self) -> str:
        """Возвращает отображаемый период."""
        return f"{self.quarter_name} {self.year}"
    
    @property
    def is_active(self) -> bool:
        """Проверяет, активен ли план."""
        return self.status == "active"
    
    @property
    def is_current(self) -> bool:
        """Проверяет, текущий ли это план (по датам)."""
        today = date.today()
        return self.start_date <= today <= self.end_date
    
    @property
    def conflict_resolution_percentage(self) -> float:
        """Возвращает процент разрешенных конфликтов."""
        if self.total_conflicts == 0:
            return 100.0
        return (self.resolved_conflicts / self.total_conflicts) * 100.0
    
    def get_specializations_list(self) -> List[str]:
        """Возвращает список специализаций."""
        return self.specializations if self.specializations else []
    
    def add_specialization(self, specialization: str) -> None:
        """Добавляет специализацию в план."""
        current = self.get_specializations_list()
        if specialization not in current:
            current.append(specialization)
            self.specializations = current
    
    def remove_specialization(self, specialization: str) -> None:
        """Удаляет специализацию из плана."""
        current = self.get_specializations_list()
        if specialization in current:
            current.remove(specialization)
            self.specializations = current
    
    def get_settings(self) -> Dict[str, Any]:
        """Возвращает настройки плана."""
        return self.settings if self.settings else {}
    
    def update_setting(self, key: str, value: Any) -> None:
        """Обновляет настройку плана."""
        current_settings = self.get_settings()
        current_settings[key] = value
        self.settings = current_settings


class QuarterlyShiftSchedule(Base):
    """Модель запланированной смены в квартальном плане."""
    
    __tablename__ = "quarterly_shift_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Связь с квартальным планом
    quarterly_plan_id = Column(Integer, ForeignKey("quarterly_plans.id"), nullable=False)
    quarterly_plan = relationship("QuarterlyPlan", back_populates="schedules")
    
    # Запланированное время
    planned_date = Column(Date, nullable=False)
    planned_start_time = Column(DateTime(timezone=True), nullable=False)
    planned_end_time = Column(DateTime(timezone=True), nullable=False)
    
    # Назначенный исполнитель
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    
    # Специализация смены
    specialization = Column(String(100), nullable=False)
    
    # Тип расписания
    schedule_type = Column(String(50), nullable=False)  # duty_24_3, workday_5_2, shift_2_2, flexible
    
    # Статус запланированной смены
    status = Column(String(50), default="planned", nullable=False)  # planned, confirmed, cancelled, completed
    
    # Связь с фактической сменой
    actual_shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)
    actual_shift = relationship("Shift", foreign_keys=[actual_shift_id])
    
    # Конфигурация смены
    shift_config = Column(JSON, nullable=True)  # Дополнительные настройки
    
    # Зоны покрытия
    coverage_areas = Column(JSON, nullable=True)
    
    # Приоритет
    priority = Column(Integer, default=1, nullable=False)
    
    # Заметки
    notes = Column(Text, nullable=True)
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<ShiftSchedule(id={self.id}, date={self.planned_date}, specialization={self.specialization})>"
    
    @property
    def duration_hours(self) -> float:
        """Возвращает продолжительность запланированной смены в часах."""
        delta = self.planned_end_time - self.planned_start_time
        return delta.total_seconds() / 3600.0
    
    @property
    def is_confirmed(self) -> bool:
        """Проверяет, подтверждена ли смена."""
        return self.status == "confirmed"
    
    @property
    def is_completed(self) -> bool:
        """Проверяет, завершена ли смена."""
        return self.status == "completed" and self.actual_shift_id is not None
    
    def get_config(self) -> Dict[str, Any]:
        """Возвращает конфигурацию смены."""
        return self.shift_config if self.shift_config else {}
    
    def update_config(self, key: str, value: Any) -> None:
        """Обновляет конфигурацию смены."""
        current_config = self.get_config()
        current_config[key] = value
        self.shift_config = current_config


class PlanningConflict(Base):
    """Модель конфликтов планирования."""
    
    __tablename__ = "planning_conflicts"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Связь с квартальным планом
    quarterly_plan_id = Column(Integer, ForeignKey("quarterly_plans.id"), nullable=False)
    quarterly_plan = relationship("QuarterlyPlan", back_populates="conflicts")
    
    # Тип конфликта
    conflict_type = Column(String(100), nullable=False)  # overlap, overload, unavailable, coverage_gap
    
    # Статус конфликта
    status = Column(String(50), default="pending", nullable=False)  # pending, resolved, ignored
    
    # Участвующие объекты
    involved_schedule_ids = Column(JSON, nullable=True)  # ID запланированных смен
    involved_user_ids = Column(JSON, nullable=True)     # ID пользователей
    
    # Детали конфликта
    conflict_time = Column(DateTime(timezone=True), nullable=True)
    conflict_date = Column(Date, nullable=True)
    conflict_details = Column(JSON, nullable=True)
    
    # Описание конфликта
    description = Column(Text, nullable=True)
    
    # Предлагаемые решения
    suggested_resolutions = Column(JSON, nullable=True)
    
    # Примененное решение
    applied_resolution = Column(JSON, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolver = relationship("User", foreign_keys=[resolved_by])
    
    # Приоритет конфликта
    priority = Column(Integer, default=1, nullable=False)  # 1=низкий, 5=критический
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<PlanningConflict(id={self.id}, type={self.conflict_type}, status={self.status})>"
    
    @property
    def is_resolved(self) -> bool:
        """Проверяет, разрешен ли конфликт."""
        return self.status == "resolved"
    
    @property
    def is_critical(self) -> bool:
        """Проверяет, критичный ли конфликт."""
        return self.priority >= 4
    
    def get_involved_schedule_ids(self) -> List[int]:
        """Возвращает список ID участвующих расписаний."""
        return self.involved_schedule_ids if self.involved_schedule_ids else []
    
    def get_involved_user_ids(self) -> List[int]:
        """Возвращает список ID участвующих пользователей."""
        return self.involved_user_ids if self.involved_user_ids else []
    
    def get_conflict_details(self) -> Dict[str, Any]:
        """Возвращает детали конфликта."""
        return self.conflict_details if self.conflict_details else {}
    
    def get_suggested_resolutions(self) -> List[Dict[str, Any]]:
        """Возвращает предлагаемые решения."""
        return self.suggested_resolutions if self.suggested_resolutions else []
    
    def add_suggested_resolution(self, resolution: Dict[str, Any]) -> None:
        """Добавляет предлагаемое решение."""
        current = self.get_suggested_resolutions()
        current.append(resolution)
        self.suggested_resolutions = current