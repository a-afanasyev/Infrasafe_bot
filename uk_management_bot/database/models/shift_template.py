from sqlalchemy import Column, Integer, String, Text, Boolean, JSON, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base


class ShiftTemplate(Base):
    """Шаблон смены для автоматического создания смен"""
    
    __tablename__ = "shift_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ========== ОСНОВНАЯ ИНФОРМАЦИЯ ==========
    # Название шаблона
    name = Column(String(100), nullable=False)
    
    # Описание шаблона
    description = Column(Text, nullable=True)
    
    # ========== ВРЕМЕННЫЕ РАМКИ ==========
    # Час начала смены (0-23)
    start_hour = Column(Integer, nullable=False)
    
    # Минута начала смены (0-59)
    start_minute = Column(Integer, default=0, nullable=False)
    
    # Продолжительность смены в часах
    duration_hours = Column(Integer, default=8, nullable=False)
    
    # ========== ТРЕБОВАНИЯ К ИСПОЛНИТЕЛЯМ ==========
    # Требуемые специализации (JSON массив)
    required_specializations = Column(JSON, nullable=True)  # ["electric", "plumbing"]
    
    # Минимальное количество исполнителей
    min_executors = Column(Integer, default=1, nullable=False)
    
    # Максимальное количество исполнителей
    max_executors = Column(Integer, default=3, nullable=False)
    
    # Максимальное количество заявок на смену по умолчанию
    default_max_requests = Column(Integer, default=10, nullable=False)
    
    # ========== ЗОНЫ ПОКРЫТИЯ ==========
    # Зоны покрытия (JSON массив)
    coverage_areas = Column(JSON, nullable=True)  # ["building_A", "yard_1"]
    
    # Географическая зона
    geographic_zone = Column(String(100), nullable=True)
    
    # Приоритет шаблона (1-5)
    priority_level = Column(Integer, default=1, nullable=False)
    
    # ========== АВТОМАТИЗАЦИЯ ==========
    # Автоматическое создание смен по шаблону
    auto_create = Column(Boolean, default=False, nullable=False)
    
    # Дни недели для автоматического создания (JSON массив)
    # [1,2,3,4,5] = Пн-Пт, [6,7] = Сб-Вс, [1,2,3,4,5,6,7] = Ежедневно
    days_of_week = Column(JSON, nullable=True)
    
    # За сколько дней вперед создавать смены
    advance_days = Column(Integer, default=7, nullable=False)
    
    # ========== ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ ==========
    # Активен ли шаблон
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Тип смены по умолчанию
    default_shift_type = Column(String(50), default="regular", nullable=False)
    
    # Дополнительные настройки в JSON
    settings = Column(JSON, nullable=True)
    
    # ========== СИСТЕМНЫЕ ПОЛЯ ==========
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ========== СВЯЗИ ==========
    # Смены, созданные по этому шаблону
    shifts = relationship("Shift", back_populates="template")
    
    def __repr__(self):
        return f"<ShiftTemplate(id={self.id}, name='{self.name}', auto_create={self.auto_create})>"
    
    @property
    def end_hour(self) -> int:
        """Возвращает час окончания смены"""
        start_minute = self.start_minute or 0
        duration_hours = self.duration_hours or 8
        total_minutes = (self.start_hour * 60 + start_minute) + (duration_hours * 60)
        return (total_minutes // 60) % 24
    
    @property
    def end_minute(self) -> int:
        """Возвращает минуту окончания смены"""
        start_minute = self.start_minute or 0
        duration_hours = self.duration_hours or 8
        total_minutes = (self.start_hour * 60 + start_minute) + (duration_hours * 60)
        return total_minutes % 60
    
    def is_day_included(self, weekday: int) -> bool:
        """Проверяет, включен ли день недели в шаблон (1=понедельник, 7=воскресенье)"""
        if not self.days_of_week:
            return False
        return weekday in self.days_of_week
    
    def matches_specialization(self, specializations: list) -> bool:
        """Проверяет, соответствует ли шаблон требуемым специализациям"""
        if not self.required_specializations:
            return True  # Универсальный шаблон
        
        if not specializations:
            return False
        
        # Проверяем пересечение специализаций
        required_set = set(self.required_specializations)
        available_set = set(specializations)
        
        return bool(required_set.intersection(available_set)) or "universal" in available_set