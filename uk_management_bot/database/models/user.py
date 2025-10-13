from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    
    # Роль пользователя (историческое поле для совместимости): applicant | executor | manager
    # В новой модели используем поля roles (JSON в TEXT) и active_role
    role = Column(String(50), default="applicant", nullable=False)

    # Новый формат ролей: список ролей в JSON (храним как TEXT для простоты в SQLite)
    # Пример значения: '["applicant", "executor"]'
    roles = Column(Text, nullable=True)

    # Активная роль пользователя: applicant | executor | manager
    active_role = Column(String(50), nullable=True)
    
    # Статус: pending, approved, blocked
    status = Column(String(50), default="pending", nullable=False)
    
    # Язык пользователя
    language = Column(String(10), default="ru", nullable=False)
    
    # Дополнительная информация
    phone = Column(String(20), nullable=True)
    
    # Специализация сотрудника (для исполнителей/менеджеров):
    # JSON строка с массивом специализаций: ["electrician", "plumber", "security"]
    specialization = Column(Text, nullable=True)
    
    # Новые поля для верификации
    verification_status = Column(String(50), default="pending", nullable=False)  # pending, verified, rejected
    verification_notes = Column(Text, nullable=True)  # Комментарии администратора
    verification_date = Column(DateTime(timezone=True), nullable=True)  # Дата верификации
    verified_by = Column(Integer, nullable=True)  # ID администратора, который верифицировал
    
    # Дополнительные поля для проверки
    passport_series = Column(String(10), nullable=True)  # Серия паспорта
    passport_number = Column(String(10), nullable=True)  # Номер паспорта
    birth_date = Column(DateTime(timezone=True), nullable=True)  # Дата рождения
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Обратные связи с указанием foreign_keys
    requests = relationship("Request", back_populates="user", foreign_keys="Request.user_id")
    shifts = relationship("Shift", back_populates="user")
    executed_requests = relationship("Request", foreign_keys="Request.executor_id")
    notifications = relationship("Notification", back_populates="user")
    
    # Новые связи для верификации с указанием foreign_keys
    documents = relationship("UserDocument", back_populates="user", foreign_keys="UserDocument.user_id")
    verifications = relationship("UserVerification", back_populates="user", foreign_keys="UserVerification.user_id")
    access_rights = relationship("AccessRights", back_populates="user", foreign_keys="AccessRights.user_id")

    # Связи для передачи смен
    outgoing_transfers = relationship("ShiftTransfer", foreign_keys="ShiftTransfer.from_executor_id", back_populates="from_executor")
    incoming_transfers = relationship("ShiftTransfer", foreign_keys="ShiftTransfer.to_executor_id", back_populates="to_executor")

    # Связь с квартирами через UserApartment (новая система адресов)
    user_apartments = relationship("UserApartment", back_populates="user", foreign_keys="UserApartment.user_id")

    # Связь с дополнительными дворами через UserYard
    user_yards = relationship("UserYard", back_populates="user", foreign_keys="UserYard.user_id")

    def __repr__(self):
        return (
            f"<User(telegram_id={self.telegram_id}, role={self.role}, "
            f"active_role={self.active_role}, status={self.status})>"
        )
