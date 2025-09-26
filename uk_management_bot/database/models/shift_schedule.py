from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, JSON, Float, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base
from datetime import date
from typing import Dict, Any, Optional


class ShiftSchedule(Base):
    """Планирование и расписание смен на конкретную дату"""
    
    __tablename__ = "shift_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ========== ОСНОВНАЯ ИНФОРМАЦИЯ ==========
    # Дата, на которую создано расписание
    date = Column(Date, nullable=False, unique=True, index=True)
    
    # ========== ПЛАНИРОВАНИЕ ПОКРЫТИЯ ==========
    # Запланированное покрытие по часам (JSON)
    # Пример: {"09:00": 2, "10:00": 3, "14:00": 2} - количество исполнителей по часам
    planned_coverage = Column(JSON, nullable=True)
    
    # Фактическое покрытие по часам (JSON)
    actual_coverage = Column(JSON, nullable=True)
    
    # Запланированное покрытие по специализациям (JSON)
    # Пример: {"electric": 2, "plumbing": 1, "universal": 3}
    planned_specialization_coverage = Column(JSON, nullable=True)
    
    # Фактическое покрытие по специализациям (JSON)
    actual_specialization_coverage = Column(JSON, nullable=True)
    
    # ========== ПРОГНОЗЫ И ПЛАНИРОВАНИЕ ==========
    # Прогнозируемое количество заявок на день
    predicted_requests = Column(Integer, nullable=True)
    
    # Фактическое количество заявок
    actual_requests = Column(Integer, default=0, nullable=False)
    
    # Точность прогноза (0.0-100.0)
    prediction_accuracy = Column(Float, nullable=True)
    
    # Рекомендуемое количество смен
    recommended_shifts = Column(Integer, nullable=True)
    
    # Фактическое количество созданных смен
    actual_shifts = Column(Integer, default=0, nullable=False)
    
    # ========== ОПТИМИЗАЦИЯ ==========
    # Оценка оптимальности расписания (0.0-100.0)
    optimization_score = Column(Float, nullable=True)
    
    # Процент покрытия потребностей (0.0-100.0)
    coverage_percentage = Column(Float, nullable=True)
    
    # Балансировка нагрузки между исполнителями (0.0-100.0)
    load_balance_score = Column(Float, nullable=True)
    
    # ========== ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ ==========
    # Особые условия дня (праздник, выходной, событие)
    special_conditions = Column(JSON, nullable=True)  # ["holiday", "event", "maintenance"]
    
    # Корректировки от менеджера
    manual_adjustments = Column(JSON, nullable=True)
    
    # Комментарии к расписанию
    notes = Column(String(500), nullable=True)
    
    # ========== СТАТУС И МЕТАДАННЫЕ ==========
    # Статус расписания: draft, active, completed, archived
    status = Column(String(50), default="draft", nullable=False)
    
    # Кто создал расписание (ID пользователя)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Автоматически ли создано расписание
    auto_generated = Column(Boolean, default=False, nullable=False)
    
    # Версия расписания (для отслеживания изменений)
    version = Column(Integer, default=1, nullable=False)
    
    # ========== СИСТЕМНЫЕ ПОЛЯ ==========
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ========== СВЯЗИ ==========
    # Пользователь, создавший расписание
    creator = relationship("User")
    
    def __repr__(self):
        return f"<ShiftSchedule(id={self.id}, date={self.date}, status={self.status})>"
    
    @property
    def coverage_gap_percentage(self) -> float:
        """Возвращает процент недопокрытия потребностей"""
        if self.coverage_percentage is None:
            return 0.0
        return max(0.0, 100.0 - self.coverage_percentage)
    
    @property
    def is_weekend(self) -> bool:
        """Проверяет, является ли дата выходным днем"""
        return self.date.weekday() >= 5  # 5=суббота, 6=воскресенье
    
    @property
    def weekday(self) -> int:
        """Возвращает день недели (1=понедельник, 7=воскресенье)"""
        return self.date.weekday() + 1
    
    def get_planned_coverage_at_hour(self, hour: int) -> int:
        """Возвращает запланированное покрытие на указанный час"""
        if not self.planned_coverage:
            return 0
        
        hour_key = f"{hour:02d}:00"
        return self.planned_coverage.get(hour_key, 0)
    
    def get_actual_coverage_at_hour(self, hour: int) -> int:
        """Возвращает фактическое покрытие на указанный час"""
        if not self.actual_coverage:
            return 0
        
        hour_key = f"{hour:02d}:00"
        return self.actual_coverage.get(hour_key, 0)
    
    def calculate_coverage_gap(self) -> Dict[str, int]:
        """Рассчитывает разрыв между планируемым и фактическим покрытием"""
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
    
    def update_actual_coverage(self, shifts: list) -> None:
        """Обновляет фактическое покрытие на основе списка смен"""
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
                specialization_coverage["universal"] = specialization_coverage.get("universal", 0) + 1
        
        self.actual_coverage = coverage
        self.actual_specialization_coverage = specialization_coverage
        self.actual_shifts = len(shifts)
    
    def calculate_optimization_metrics(self) -> Dict[str, float]:
        """Рассчитывает метрики оптимизации расписания"""
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
            accuracy = 100.0 - abs(self.predicted_requests - self.actual_requests) / self.predicted_requests * 100.0
            metrics["prediction_accuracy"] = max(0.0, accuracy)
            self.prediction_accuracy = max(0.0, accuracy)
        
        return metrics