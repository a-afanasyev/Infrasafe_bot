"""
Модель связи пользователя и квартиры с модерацией
"""
import enum
from typing import Optional

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base


class UserApartmentStatus(str, enum.Enum):
    """REFACTOR-089: канонические статусы модерации связи пользователь-квартира.

    `str`-подкласс → wire-совместим со строковой колонкой `status`: член равен
    своему значению ('approved' и т.п.), SQLAlchemy биндит value, поэтому
    сравнения/записи дают те же строки, что и раньше.
    """
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class UserApartment(Base):
    """
    Связь пользователя с квартирой (Many-to-Many с модерацией)

    Статусы:
    - pending: Заявка на рассмотрении
    - approved: Подтверждено администратором
    - rejected: Отклонено администратором
    """
    __tablename__ = "user_apartments"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    apartment_id = Column(Integer, ForeignKey("apartments.id", ondelete="CASCADE"), nullable=False, index=True)

    # Модерация
    status = Column(String(20), default=UserApartmentStatus.PENDING.value, nullable=False, index=True)  # pending, approved, rejected
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Комментарий от администратора
    admin_comment = Column(Text, nullable=True)

    # Является ли пользователь владельцем (или только проживающим)
    is_owner = Column(Boolean, default=False, nullable=False)

    # Основная квартира (для пользователей с несколькими квартирами)
    is_primary = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    user = relationship("User", foreign_keys=[user_id], back_populates="user_apartments")
    apartment = relationship("Apartment", back_populates="user_apartments")
    reviewer = relationship("User", foreign_keys=[reviewed_by])

    # Уникальность связи пользователь-квартира
    __table_args__ = (
        UniqueConstraint('user_id', 'apartment_id', name='uix_user_apartment'),
    )

    @property
    def is_pending(self) -> bool:
        """Заявка на рассмотрении"""
        return self.status == UserApartmentStatus.PENDING

    @property
    def is_approved(self) -> bool:
        """Заявка подтверждена"""
        return self.status == UserApartmentStatus.APPROVED

    @property
    def is_rejected(self) -> bool:
        """Заявка отклонена"""
        return self.status == UserApartmentStatus.REJECTED

    def approve(self, reviewer_id: int, comment: Optional[str] = None):
        """Подтвердить связь"""
        self.status = UserApartmentStatus.APPROVED.value
        self.reviewed_by = reviewer_id
        self.reviewed_at = func.now()
        if comment:
            self.admin_comment = comment

    def reject(self, reviewer_id: int, comment: Optional[str] = None):
        """Отклонить связь"""
        self.status = UserApartmentStatus.REJECTED.value
        self.reviewed_by = reviewer_id
        self.reviewed_at = func.now()
        if comment:
            self.admin_comment = comment

    def __repr__(self):
        return f"<UserApartment(user_id={self.user_id}, apartment_id={self.apartment_id}, status='{self.status}')>"
