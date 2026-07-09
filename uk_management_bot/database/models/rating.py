from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base

class Rating(Base):
    __tablename__ = "ratings"

    # Constraints-фаза SSOT (миграция 018): одна оценка на заявку — DB-гарантия
    # идемпотентности приёмки (повторный APPLICANT_ACCEPT не создаст дубль).
    __table_args__ = (
        UniqueConstraint("request_number", name="uq_ratings_request_number"),
    )

    id = Column(Integer, primary_key=True)
    
    # Связь с заявкой
    request_number = Column(String(15), ForeignKey("requests.request_number"), nullable=False, index=True)
    request = relationship("Request", back_populates="ratings")
    
    # Пользователь, оставивший оценку
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user = relationship("User")
    
    # Оценка от 1 до 5
    rating = Column(Integer, nullable=False)
    
    # Текстовый отзыв
    review = Column(Text, nullable=True)
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<Rating(id={self.id}, request_number={self.request_number}, rating={self.rating})>"
