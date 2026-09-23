from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base
from datetime import datetime, timezone
from typing import Optional


class ShiftAssignment(Base):
    """Назначение заявки на конкретную смену"""
    
    __tablename__ = "shift_assignments"
    
    id = Column(Integer, primary_key=True)
    
    # ========== ОСНОВНЫЕ СВЯЗИ ==========
    # Смена, к которой назначена заявка
    shift_id = Column(Integer, ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Заявка, которая назначена на смену
    request_number = Column(String(15), ForeignKey("requests.request_number", ondelete="CASCADE"), nullable=False, index=True)
    
    # ========== ПРИОРИТИЗАЦИЯ И ПЛАНИРОВАНИЕ ==========
    # Приоритет назначения (1-5, где 5 - высший приоритет)
    assignment_priority = Column(Integer, default=1, nullable=False)
    
    # Ожидаемая продолжительность выполнения (в минутах)
    estimated_duration = Column(Integer, nullable=True)
    
    # Порядок выполнения в рамках смены
    assignment_order = Column(Integer, nullable=True)
    
    # ========== ML-ОПТИМИЗАЦИЯ И ОЦЕНКИ ==========
    # Оценка качества назначения от ИИ (0.0-100.0)
    ai_score = Column(Float, nullable=True)
    
    # Уровень уверенности в назначении (0.0-1.0)
    confidence_level = Column(Float, nullable=True)
    
    # Оценка соответствия специализации (0.0-100.0)
    specialization_match_score = Column(Float, nullable=True)
    
    # Географическая оценка (расстояние, логистика) (0.0-100.0)
    geographic_score = Column(Float, nullable=True)
    
    # Оценка загруженности исполнителя (0.0-100.0)
    workload_score = Column(Float, nullable=True)
    
    # ========== СТАТУС И ВЫПОЛНЕНИЕ ==========
    # Статус назначения: assigned, accepted, rejected, in_progress, completed, cancelled
    status = Column(String(50), default="assigned", nullable=False)
    
    # Автоматическое ли назначение (ИИ vs ручное)
    auto_assigned = Column(Boolean, default=False, nullable=False)
    
    # Подтверждено ли исполнителем
    confirmed_by_executor = Column(Boolean, default=False, nullable=False)
    
    # ========== ВРЕМЕННЫЕ МЕТКИ ==========
    # Время назначения
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Время начала выполнения
    started_at = Column(DateTime(timezone=True), nullable=True)
    
    # Время завершения
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Планируемое время начала
    planned_start_at = Column(DateTime(timezone=True), nullable=True)
    
    # Планируемое время завершения
    planned_completion_at = Column(DateTime(timezone=True), nullable=True)
    
    # ========== ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ ==========
    # Причина назначения/переназначения
    assignment_reason = Column(String(200), nullable=True)
    
    # Комментарии к назначению
    notes = Column(Text, nullable=True)
    
    # Дополнительные инструкции для исполнителя
    executor_instructions = Column(Text, nullable=True)
    
    # ========== РЕЗУЛЬТАТЫ ВЫПОЛНЕНИЯ ==========
    # Фактическая продолжительность выполнения (в минутах)
    actual_duration = Column(Integer, nullable=True)
    
    # Оценка качества выполнения (1.0-5.0)
    execution_quality_rating = Column(Float, nullable=True)
    
    # Были ли проблемы при выполнении
    had_issues = Column(Boolean, default=False, nullable=False)
    
    # Описание проблем (если были)
    issues_description = Column(Text, nullable=True)
    
    # ========== СИСТЕМНЫЕ ПОЛЯ ==========
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ========== СВЯЗИ ==========
    # Связь со сменой
    shift = relationship("Shift", back_populates="assignments")
    
    # Связь с заявкой
    request = relationship("Request")
    
    def __repr__(self):
        return f"<ShiftAssignment(id={self.id}, shift_id={self.shift_id}, request_number={self.request_number}, status={self.status})>"
    
    @property
    def is_overdue(self) -> bool:
        """Проверяет, просрочено ли назначение"""
        if not self.planned_completion_at:
            return False
        
        if self.status in ["completed", "cancelled"]:
            return False
        
        return datetime.now(timezone.utc) > self.planned_completion_at
    
    @property
    def duration_actual_vs_estimated(self) -> Optional[float]:
        """Возвращает отношение фактического времени к планируемому"""
        if not self.actual_duration or not self.estimated_duration:
            return None
        
        return self.actual_duration / self.estimated_duration
