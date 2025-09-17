from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base
from uk_management_bot.services.request_number_service import RequestNumberService

class Request(Base):
    __tablename__ = "requests"
    
    # НОВЫЙ PRIMARY KEY - номер заявки в формате YYMMDD-NNN
    request_number = Column(String(10), primary_key=True, index=True)
    
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
    
    # Новые поля для назначений
    assignment_type = Column(String(20), nullable=True)  # 'group' или 'individual'
    assigned_group = Column(String(100), nullable=True)  # специализация группы
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Новые поля для материалов и отчетов
    purchase_materials = Column(Text, nullable=True)  # материалы для закупки (старое поле)
    requested_materials = Column(Text, nullable=True)  # запрошенные материалы от исполнителя
    manager_materials_comment = Column(Text, nullable=True)  # комментарии менеджера к списку
    purchase_history = Column(Text, nullable=True)  # история закупок (для сохранения при смене статуса)
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Обратные связи
    ratings = relationship("Rating", back_populates="request")
    comments = relationship("RequestComment", back_populates="request")
    assignments = relationship("RequestAssignment", back_populates="request")
    
    def __repr__(self):
        return f"<Request(request_number={self.request_number}, category={self.category}, status={self.status})>"
    
    @classmethod
    def generate_request_number(cls, db_session, creation_date=None):
        """
        Генерирует уникальный номер для новой заявки
        
        Args:
            db_session: Сессия базы данных
            creation_date: Дата создания (по умолчанию - сегодня)
            
        Returns:
            Уникальный номер заявки в формате YYMMDD-NNN
        """
        return RequestNumberService.generate_next_number(creation_date, db_session)
    
    def format_number_for_display(self):
        """
        Форматирует номер заявки для отображения пользователю
        
        Returns:
            Отформатированная строка номера
        """
        return RequestNumberService.format_for_display(self.request_number)
