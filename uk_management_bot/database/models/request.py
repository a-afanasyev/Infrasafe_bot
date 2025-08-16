from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database.session import Base

class Request(Base):
    __tablename__ = "requests"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Связь с пользователем (заявителем)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="requests", foreign_keys=[user_id])
    
    # Основная информация о заявке
    category = Column(String(100), nullable=False)
    status = Column(String(50), default="Новая", nullable=False)
    address = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    apartment = Column(String(20), nullable=True)
    urgency = Column(String(20), default="Обычная", nullable=False)
    
    # Медиафайлы (JSON массив с file_ids)
    media_files = Column(JSON, default=list)
    
    # Исполнитель (если назначен)
    executor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    executor = relationship("User", foreign_keys=[executor_id])
    
    # Дополнительная информация
    notes = Column(Text, nullable=True)
    completion_report = Column(Text, nullable=True)
    completion_media = Column(JSON, default=list)
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Обратные связи
    ratings = relationship("Rating", back_populates="request")
    
    def __repr__(self):
        return f"<Request(id={self.id}, category={self.category}, status={self.status})>"
