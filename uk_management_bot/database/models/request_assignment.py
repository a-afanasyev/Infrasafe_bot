"""
Модель для назначений заявок
Обеспечивает систему назначения заявок группам и конкретным исполнителям
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from uk_management_bot.database.session import Base

class RequestAssignment(Base):
    """Модель назначений заявок"""
    
    __tablename__ = "request_assignments"
    
    # Основные поля
    id = Column(Integer, primary_key=True, index=True)
    request_number = Column(String(10), ForeignKey("requests.request_number"), nullable=False)
    
    # Тип назначения
    assignment_type = Column(String(20), nullable=False)  # 'group' или 'individual'
    
    # Для группового назначения
    group_specialization = Column(String(100), nullable=True)
    
    # Для индивидуального назначения
    executor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Статус назначения
    status = Column(String(20), default="active")  # 'active', 'cancelled', 'completed'
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Связи с другими моделями
    request = relationship("Request", back_populates="assignments")
    executor = relationship("User", foreign_keys=[executor_id])
    creator = relationship("User", foreign_keys=[created_by])
    
    def __repr__(self):
        return f"<RequestAssignment(id={self.id}, request_number={self.request_number}, type={self.assignment_type})>"
    
    def to_dict(self):
        """Преобразование в словарь для API"""
        return {
            "id": self.id,
            "request_number": self.request_number,
            "assignment_type": self.assignment_type,
            "group_specialization": self.group_specialization,
            "executor_id": self.executor_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by
        }
    
    @property
    def is_group_assignment(self):
        """Проверка, является ли назначение групповым"""
        return self.assignment_type == "group"
    
    @property
    def is_individual_assignment(self):
        """Проверка, является ли назначение индивидуальным"""
        return self.assignment_type == "individual"
    
    @property
    def is_active(self):
        """Проверка, активно ли назначение"""
        return self.status == "active"
