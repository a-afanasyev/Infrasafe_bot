from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database.session import Base

class Rating(Base):
    __tablename__ = "ratings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Связь с заявкой
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False)
    request = relationship("Request", back_populates="ratings")
    
    # Пользователь, оставивший оценку
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User")
    
    # Оценка от 1 до 5
    rating = Column(Integer, nullable=False)
    
    # Текстовый отзыв
    review = Column(Text, nullable=True)
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<Rating(id={self.id}, request_id={self.request_id}, rating={self.rating})>"
