from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base

class Shift(Base):
    __tablename__ = "shifts"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Исполнитель
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="shifts")
    
    # ========== СУЩЕСТВУЮЩИЕ ПОЛЯ ==========
    # Время смены
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    
    # Статус смены: active, completed, cancelled, planned, paused
    status = Column(String(50), default="active", nullable=False)
    
    # Дополнительная информация
    notes = Column(Text, nullable=True)
    
    # ========== НОВЫЕ ПОЛЯ ПЛАНИРОВАНИЯ ==========
    # Планируемое время смены
    planned_start_time = Column(DateTime(timezone=True), nullable=True)
    planned_end_time = Column(DateTime(timezone=True), nullable=True)
    
    # Связь с шаблоном смены
    shift_template_id = Column(Integer, ForeignKey("shift_templates.id"), nullable=True)
    
    # Тип смены
    shift_type = Column(String(50), default="regular", nullable=True)  # regular, emergency, overtime, maintenance
    
    # ========== НОВЫЕ ПОЛЯ СПЕЦИАЛИЗАЦИИ ==========
    # Фокус специализации для смены (JSON массив)
    specialization_focus = Column(JSON, nullable=True)  # ["electric", "plumbing", "hvac"]
    
    # Зоны покрытия (JSON массив)
    coverage_areas = Column(JSON, nullable=True)  # ["building_A", "yard_1", "parking"]
    
    # Географическая зона
    geographic_zone = Column(String(100), nullable=True)
    
    # ========== НОВЫЕ ПОЛЯ ПЛАНИРОВАНИЯ НАГРУЗКИ ==========
    # Максимальное количество заявок на смену
    max_requests = Column(Integer, default=10, nullable=False)
    
    # Текущее количество назначенных заявок
    current_request_count = Column(Integer, default=0, nullable=False)
    
    # Приоритет смены (1-5, где 5 - высший приоритет)
    priority_level = Column(Integer, default=1, nullable=False)
    
    # ========== НОВЫЕ ПОЛЯ АНАЛИТИКИ ПРОИЗВОДИТЕЛЬНОСТИ ==========
    # Завершенные заявки за смену
    completed_requests = Column(Integer, default=0, nullable=False)
    
    # Среднее время выполнения заявки (в минутах)
    average_completion_time = Column(Float, nullable=True)
    
    # Среднее время отклика на заявки (в минутах)
    average_response_time = Column(Float, nullable=True)
    
    # Оценка эффективности (0.0-100.0)
    efficiency_score = Column(Float, nullable=True)
    
    # Рейтинг качества работы за смену (1.0-5.0)
    quality_rating = Column(Float, nullable=True)
    
    # ========== СИСТЕМНЫЕ ПОЛЯ ==========
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ========== СВЯЗИ ==========
    # Связь с шаблоном смены
    template = relationship("ShiftTemplate", back_populates="shifts")
    
    # Связь с назначениями заявок
    assignments = relationship("ShiftAssignment", back_populates="shift", cascade="all, delete-orphan")

    # Связь с передачами смен
    transfers = relationship("ShiftTransfer", back_populates="shift", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Shift(id={self.id}, user_id={self.user_id}, status={self.status}, type={self.shift_type})>"
    
    @property
    def is_full(self) -> bool:
        """Проверяет, заполнена ли смена до максимума"""
        return self.current_request_count >= self.max_requests
    
    @property
    def load_percentage(self) -> float:
        """Возвращает процент загруженности смены"""
        if self.max_requests == 0:
            return 0.0
        return (self.current_request_count / self.max_requests) * 100.0
    
    @property
    def duration_hours(self) -> float:
        """Возвращает продолжительность смены в часах"""
        if not self.start_time:
            return 0.0
        
        end_time = self.end_time or self.planned_end_time
        if not end_time:
            return 0.0
            
        delta = end_time - self.start_time
        return delta.total_seconds() / 3600.0
    
    def can_handle_specialization(self, required_specialization: str) -> bool:
        """Проверяет, может ли смена обработать заявку с определенной специализацией"""
        if not self.specialization_focus:
            return True  # Универсальная смена
        
        return required_specialization in self.specialization_focus or "universal" in self.specialization_focus
    
    def can_handle_area(self, area: str) -> bool:
        """Проверяет, может ли смена обработать заявку в определенной зоне"""
        if not self.coverage_areas:
            return True  # Покрывает все зоны
        
        return area in self.coverage_areas or "all" in self.coverage_areas
