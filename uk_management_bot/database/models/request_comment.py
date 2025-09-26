"""
Модель для комментариев к заявкам
Обеспечивает систему комментариев с привязкой к изменениям статуса
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from uk_management_bot.database.session import Base

class RequestComment(Base):
    """Модель комментариев к заявкам"""
    
    __tablename__ = "request_comments"
    
    # Основные поля
    id = Column(Integer, primary_key=True, index=True)
    request_number = Column(String(10), ForeignKey("requests.request_number"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Содержимое комментария
    comment_text = Column(Text, nullable=False)
    comment_type = Column(String(50), nullable=False)  # 'status_change', 'clarification', 'purchase', 'report'
    
    # Контекст комментария (для изменений статуса)
    previous_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=True)
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Связи с другими моделями
    request = relationship("Request", back_populates="comments")
    user = relationship("User")
    
    def __repr__(self):
        return f"<RequestComment(id={self.id}, request_number={self.request_number}, type={self.comment_type})>"
    
    def to_dict(self):
        """Преобразование в словарь для API"""
        return {
            "id": self.id,
            "request_number": self.request_number,
            "user_id": self.user_id,
            "comment_text": self.comment_text,
            "comment_type": self.comment_type,
            "previous_status": self.previous_status,
            "new_status": self.new_status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
