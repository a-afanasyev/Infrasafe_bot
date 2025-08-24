"""
Модель уведомлений

Содержит модель для:
- Уведомления пользователей
- История уведомлений
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base


class Notification(Base):
    """Модель уведомлений"""
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Связь с пользователем
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="notifications")
    
    # Тип уведомления
    notification_type = Column(String(50), nullable=False)
    
    # Заголовок и содержание
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    
    # Статус уведомления
    is_read = Column(Boolean, default=False)
    is_sent = Column(Boolean, default=False)
    
    # Дополнительные данные
    meta_data = Column(JSON, default=dict)
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<Notification(id={self.id}, type={self.notification_type}, user_id={self.user_id})>"
