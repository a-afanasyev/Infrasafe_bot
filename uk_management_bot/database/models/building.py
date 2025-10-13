"""
Модель здания (дома)
"""
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base


class Building(Base):
    """
    Здание (дом) - находится на территории двора
    """
    __tablename__ = "buildings"

    id = Column(Integer, primary_key=True, index=True)
    address = Column(String(300), nullable=False, index=True)  # Полный адрес здания
    yard_id = Column(Integer, ForeignKey("yards.id", ondelete="CASCADE"), nullable=False, index=True)

    # GPS координаты здания для GeoOptimizer
    gps_latitude = Column(Float, nullable=True)
    gps_longitude = Column(Float, nullable=True)

    # Характеристики здания
    entrance_count = Column(Integer, default=1, nullable=False)  # Количество подъездов
    floor_count = Column(Integer, default=1, nullable=False)     # Количество этажей

    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    yard = relationship("Yard", back_populates="buildings")
    apartments = relationship("Apartment", back_populates="building", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])

    @property
    def apartments_count(self) -> int:
        """Количество квартир в здании"""
        return len(self.apartments) if self.apartments else 0

    @property
    def residents_count(self) -> int:
        """Количество жителей в здании (через квартиры)"""
        if not self.apartments:
            return 0

        total = 0
        for apartment in self.apartments:
            if hasattr(apartment, 'user_apartments'):
                # Считаем только подтвержденных жителей
                total += len([ua for ua in apartment.user_apartments if ua.status == 'approved'])

        return total

    def __repr__(self):
        return f"<Building(id={self.id}, address='{self.address}', yard_id={self.yard_id})>"
