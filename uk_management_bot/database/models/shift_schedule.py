from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, JSON, Float, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base


class ShiftSchedule(Base):
    """Планирование и расписание смен на конкретную дату"""
    
    __tablename__ = "shift_schedules"
    
    id = Column(Integer, primary_key=True)
    
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
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
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
    def weekday(self) -> int:
        """Возвращает день недели (1=понедельник, 7=воскресенье)"""
        return self.date.weekday() + 1
