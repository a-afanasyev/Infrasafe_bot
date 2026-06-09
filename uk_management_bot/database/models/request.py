from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON, Boolean, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base
from uk_management_bot.services.request_number_service import RequestNumberService

class Request(Base):
    __tablename__ = "requests"

    # Инвариант дискриминатор↔FK (план «Обходчик»). Толерантен к address_type IS
    # NULL (немигрированные/legacy строки и существующие тест-фикстуры проходят);
    # как только уровень задан — ровно один соответствующий FK заполнен, прочие
    # NULL. Прод-миграция дополнительно навешивает NOT NULL на address_type.
    __table_args__ = (
        CheckConstraint(
            "address_type IS NULL OR ("
            " (address_type = 'apartment' AND apartment_id IS NOT NULL AND building_id IS NULL AND yard_id IS NULL)"
            " OR (address_type = 'building' AND building_id IS NOT NULL AND apartment_id IS NULL AND yard_id IS NULL)"
            " OR (address_type = 'yard' AND yard_id IS NOT NULL AND apartment_id IS NULL AND building_id IS NULL)"
            " OR (address_type = 'legacy' AND apartment_id IS NULL AND building_id IS NULL AND yard_id IS NULL)"
            ")",
            name="ck_requests_address_type_fk",
        ),
    )

    # НОВЫЙ PRIMARY KEY - номер заявки в формате YYMMDD-NNN
    request_number = Column(String(15), primary_key=True, index=True)
    
    # Связь с пользователем (заявителем)
    # DB-050/052: index — заявки часто фильтруются/джойнятся по заявителю.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user = relationship("User", back_populates="requests", foreign_keys=[user_id])

    # Основная информация о заявке
    category = Column(String(100), nullable=False)
    # DB-050: index — Kanban/аналитика фильтруют по статусу.
    status = Column(String(50), default="Новая", nullable=False, index=True)
    address = Column(Text, nullable=True)  # Legacy: сохраняем для старых заявок, но делаем nullable
    description = Column(Text, nullable=False)
    apartment = Column(String(20), nullable=True)  # Legacy: заменено на apartment_id
    urgency = Column(String(20), default="low", nullable=False)  # канон-ключ (TASK 17)
    source = Column(String(20), default='bot', nullable=True)

    # Новая система адресов: связь с квартирой из справочника
    apartment_id = Column(Integer, ForeignKey("apartments.id"), nullable=True, index=True)

    # 3-уровневый структурированный адрес (план «Обходчик», 2026-06):
    # заявка может быть привязана к двору / дому / квартире. Ровно один из
    # apartment_id/building_id/yard_id заполнен (кроме legacy), уровень фиксирует
    # дискриминатор address_type. Инвариант (тип↔FK) — CHECK в миграции.
    # FK ON DELETE RESTRICT: SET NULL обнулил бы FK при сохранённом address_type
    # → нарушение CHECK; от каскадного удаления защищает purge-гард (addresses).
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="RESTRICT"), nullable=True, index=True)
    yard_id = Column(Integer, ForeignKey("yards.id", ondelete="RESTRICT"), nullable=True, index=True)
    address_type = Column(String(20), nullable=True)  # legacy|yard|building|apartment
    building_obj = relationship("Building", foreign_keys=[building_id])
    yard_obj = relationship("Yard", foreign_keys=[yard_id])

    # Медиафайлы (JSON массив с file_ids)
    media_files = Column(JSON, default=list)
    
    # Исполнитель (если назначен)
    # DB-050/052: index — выборка заявок исполнителя ("мои заявки").
    executor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
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

    # Поля для системы приёмки заявок
    is_returned = Column(Boolean, default=False, nullable=False)  # Флаг возвращенной заявки
    return_reason = Column(Text, nullable=True)  # Причина возврата от заявителя
    return_media = Column(JSON, default=list)  # Медиафайлы при возврате
    returned_at = Column(DateTime(timezone=True), nullable=True)  # Время возврата
    returned_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Кто вернул

    # Поля для подтверждения менеджером
    manager_confirmed = Column(Boolean, default=False, nullable=False)  # Подтверждено менеджером
    manager_confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Кто подтвердил
    manager_confirmed_at = Column(DateTime(timezone=True), nullable=True)  # Когда подтверждено
    manager_confirmation_notes = Column(Text, nullable=True)  # Комментарии менеджера при подтверждении

    # Системные поля
    # DB-050: index — сортировка/диапазоны по дате создания (ленты, аналитика).
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Обратные связи
    ratings = relationship("Rating", back_populates="request")
    comments = relationship("RequestComment", back_populates="request")
    assignments = relationship("RequestAssignment", back_populates="request")

    # Связь с квартирой из справочника адресов
    apartment_obj = relationship("Apartment", back_populates="requests")
    
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
