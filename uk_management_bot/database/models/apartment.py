"""
Модель квартиры
"""
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base


class Apartment(Base):
    """
    Квартира - находится в здании
    """
    __tablename__ = "apartments"

    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False, index=True)
    apartment_number = Column(String(20), nullable=False, index=True)  # Номер квартиры

    # Характеристики квартиры
    entrance = Column(Integer, nullable=True)  # Номер подъезда
    floor = Column(Integer, nullable=True)     # Этаж
    rooms_count = Column(Integer, nullable=True)     # Количество комнат
    area = Column(Float, nullable=True)  # Площадь квартиры (кв.м)

    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    building = relationship("Building", back_populates="apartments")
    user_apartments = relationship("UserApartment", back_populates="apartment", cascade="all, delete-orphan")
    requests = relationship("Request", back_populates="apartment_obj")
    creator = relationship("User", foreign_keys=[created_by])

    # Уникальность номера квартиры в рамках здания
    __table_args__ = (
        UniqueConstraint('building_id', 'apartment_number', name='uix_building_apartment'),
    )

    @property
    def full_address(self) -> str:
        """Полный адрес квартиры включая здание и двор"""
        if self.building:
            address_parts = [self.building.address]
            if self.apartment_number:
                address_parts.append(f"кв. {self.apartment_number}")
            return ", ".join(address_parts)
        return f"Квартира {self.apartment_number}"

    @property
    def residents_count(self) -> int:
        """Количество подтвержденных жителей"""
        if not self.user_apartments:
            return 0
        return len([ua for ua in self.user_apartments if ua.status == 'approved'])

    @property
    def pending_requests_count(self) -> int:
        """Количество заявок на подтверждение"""
        if not self.user_apartments:
            return 0
        return len([ua for ua in self.user_apartments if ua.status == 'pending'])

    def __repr__(self):
        return f"<Apartment(id={self.id}, building_id={self.building_id}, number='{self.apartment_number}')>"
