"""
Модель связи пользователя с дополнительными дворами

Позволяет жителям создавать заявки в дополнительных дворах помимо их основного двора.
По умолчанию житель имеет доступ только к двору, где находится его квартира.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base


class UserYard(Base):
    """
    Связь пользователя с дополнительными дворами (Many-to-Many)

    Используется для:
    - Управляющих, которые отвечают за несколько дворов
    - Жителей, имеющих несколько квартир в разных дворах
    - Специальных прав доступа к определенным дворам
    """
    __tablename__ = "user_yards"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    yard_id = Column(Integer, ForeignKey("yards.id", ondelete="CASCADE"), nullable=False, index=True)

    # Дополнительная информация
    granted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Кто назначил
    comment = Column(Text, nullable=True)  # Причина назначения

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    user = relationship("User", foreign_keys=[user_id], back_populates="user_yards")
    yard = relationship("Yard", back_populates="user_yards")
    granter = relationship("User", foreign_keys=[granted_by])

    # Уникальность связи пользователь-двор
    __table_args__ = (
        UniqueConstraint('user_id', 'yard_id', name='uix_user_yard'),
    )

    def __repr__(self):
        return f"<UserYard(user_id={self.user_id}, yard_id={self.yard_id})>"
