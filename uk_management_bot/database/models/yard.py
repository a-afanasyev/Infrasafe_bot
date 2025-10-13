"""
Модель двора (Yard) для справочника адресов
"""
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base


class Yard(Base):
    """
    Двор - территория управляющей компании

    Двор объединяет несколько домов, которые физически разделены дорогами или другими объектами.
    Используется для:
    - Организации территориальной структуры
    - Распределения исполнителей по зонам
    - Оптимизации маршрутов
    """
    __tablename__ = "yards"

    # Основные поля
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)

    # GPS координаты центра двора для GeoOptimizer
    gps_latitude = Column(Float, nullable=True)
    gps_longitude = Column(Float, nullable=True)

    # Статус
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    buildings = relationship("Building", back_populates="yard", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])
    user_yards = relationship("UserYard", back_populates="yard")

    def __repr__(self):
        return f"<Yard(id={self.id}, name='{self.name}', buildings={len(self.buildings)})>"

    @property
    def buildings_count(self):
        """Количество домов в дворе"""
        return len(self.buildings) if self.buildings else 0

    @property
    def active_buildings_count(self):
        """Количество активных домов"""
        return sum(1 for b in self.buildings if b.is_active) if self.buildings else 0
