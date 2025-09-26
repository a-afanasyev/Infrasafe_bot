from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base
from datetime import datetime, timezone
from typing import Optional


class ShiftAssignment(Base):
    """Назначение заявки на конкретную смену"""
    
    __tablename__ = "shift_assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ========== ОСНОВНЫЕ СВЯЗИ ==========
    # Смена, к которой назначена заявка
    shift_id = Column(Integer, ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Заявка, которая назначена на смену
    request_number = Column(String(10), ForeignKey("requests.request_number", ondelete="CASCADE"), nullable=False, index=True)
    
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
    
    @property
    def response_time_minutes(self) -> Optional[int]:
        """Возвращает время отклика в минутах (от назначения до начала)"""
        if not self.started_at:
            return None
        
        delta = self.started_at - self.assigned_at
        return int(delta.total_seconds() / 60)
    
    @property
    def completion_time_minutes(self) -> Optional[int]:
        """Возвращает общее время выполнения в минутах (от назначения до завершения)"""
        if not self.completed_at:
            return None
        
        delta = self.completed_at - self.assigned_at
        return int(delta.total_seconds() / 60)
    
    def calculate_efficiency_score(self) -> float:
        """Рассчитывает общую оценку эффективности назначения"""
        scores = []
        
        # Оценка ИИ (если есть)
        if self.ai_score:
            scores.append(self.ai_score)
        
        # Оценка соответствия специализации
        if self.specialization_match_score:
            scores.append(self.specialization_match_score)
        
        # Географическая оценка
        if self.geographic_score:
            scores.append(self.geographic_score)
        
        # Оценка загруженности
        if self.workload_score:
            scores.append(self.workload_score)
        
        # Оценка качества выполнения
        if self.execution_quality_rating:
            # Конвертируем из 1-5 в 0-100
            quality_score = (self.execution_quality_rating - 1) / 4 * 100
            scores.append(quality_score)
        
        # Штраф за превышение времени
        if self.duration_actual_vs_estimated and self.duration_actual_vs_estimated > 1.2:
            time_penalty = max(0, 100 - (self.duration_actual_vs_estimated - 1) * 50)
            scores.append(time_penalty)
        
        if not scores:
            return 0.0
        
        return sum(scores) / len(scores)
    
    def update_status_with_timestamp(self, new_status: str) -> None:
        """Обновляет статус с автоматическим проставлением временных меток"""
        self.status = new_status
        current_time = datetime.now(timezone.utc)
        
        if new_status == "in_progress" and not self.started_at:
            self.started_at = current_time
            
        elif new_status == "completed" and not self.completed_at:
            self.completed_at = current_time
            
            # Рассчитываем фактическую продолжительность
            if self.started_at:
                delta = current_time - self.started_at
                self.actual_duration = int(delta.total_seconds() / 60)
    
    def validate_assignment(self) -> tuple[bool, str]:
        """Проверяет корректность назначения"""
        # Проверяем, что смена активна
        if hasattr(self, 'shift') and self.shift and self.shift.status not in ["active", "planned"]:
            return False, "Смена не активна"
        
        # Проверяем, что смена не переполнена
        if hasattr(self, 'shift') and self.shift and self.shift.is_full:
            return False, "Смена уже заполнена до максимума"
        
        # Проверяем статус заявки
        if hasattr(self, 'request') and self.request and self.request.status in ["completed", "cancelled"]:
            return False, "Заявка уже завершена или отменена"
        
        return True, "Назначение корректно"