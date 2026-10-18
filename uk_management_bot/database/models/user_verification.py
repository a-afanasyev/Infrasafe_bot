"""
Модели для системы верификации пользователей

Содержит модели для:
- Документы пользователей
- Процесс верификации
- Права доступа по уровням
"""

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Enum, ForeignKey, Integer, JSON,
    LargeBinary, String, Text, UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uk_management_bot.database.session import Base
import enum

class DocumentType(enum.Enum):
    """Типы документов для верификации"""
    PASSPORT = "passport"
    PROPERTY_DEED = "property_deed"
    RENTAL_AGREEMENT = "rental_agreement"
    UTILITY_BILL = "utility_bill"
    OTHER = "other"

class VerificationStatus(enum.Enum):
    """Статусы верификации"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REQUESTED = "requested"

class AccessLevel(enum.Enum):
    """Уровни доступа для подачи заявок"""
    APARTMENT = "apartment"  # Квартира (максимум 2 заявителя)
    HOUSE = "house"          # Дом (много квартир)
    YARD = "yard"            # Двор (много домов)

class UserDocument(Base):
    """Модель документов пользователя"""
    __tablename__ = "user_documents"
    
    id = Column(Integer, primary_key=True)
    
    # Связь с пользователем
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user = relationship("User", back_populates="documents", foreign_keys=[user_id])
    
    # Информация о документе
    document_type = Column(Enum(DocumentType), nullable=False)
    # Хранение: либо легаси Telegram file_id, либо зашифрованная тройка в
    # медиа-сервисе (media_id + ключ + uuid для AAD) — см. миграцию 026.
    # Удаление строки уничтожает ключ: blob в канале становится нечитаемым.
    file_id = Column(String(255), nullable=True)
    media_id = Column(Integer, nullable=True)
    encryption_key = Column(LargeBinary, nullable=True)
    document_uuid = Column(String(36), nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    
    # Статус проверки
    verification_status = Column(Enum(VerificationStatus), default=VerificationStatus.PENDING)
    verification_notes = Column(Text, nullable=True)
    
    # Кто проверил документ
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("media_id", name="uq_user_documents_media_id"),
        CheckConstraint(
            "(file_id IS NOT NULL AND file_id <> '' AND media_id IS NULL"
            " AND encryption_key IS NULL AND document_uuid IS NULL)"
            " OR (file_id IS NULL AND media_id IS NOT NULL"
            " AND encryption_key IS NOT NULL AND document_uuid IS NOT NULL)",
            name="ck_user_documents_storage_xor",
        ),
    )

    def __repr__(self):
        return f"<UserDocument(id={self.id}, type={self.document_type}, status={self.verification_status})>"

class UserVerification(Base):
    """Модель процесса верификации пользователя"""
    __tablename__ = "user_verifications"
    
    id = Column(Integer, primary_key=True)
    
    # Связь с пользователем
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user = relationship("User", back_populates="verifications", foreign_keys=[user_id])
    
    # Статус верификации
    status = Column(Enum(VerificationStatus), default=VerificationStatus.PENDING)
    
    # Запросы дополнительной информации
    requested_info = Column(JSON, default=dict)  # {"address": True, "documents": ["passport"]}
    requested_at = Column(DateTime(timezone=True), nullable=True)
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
    # Комментарии администратора
    admin_notes = Column(Text, nullable=True)
    
    # Кто проверил
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<UserVerification(user_id={self.user_id}, status={self.status})>"

class AccessRights(Base):
    """Модель прав доступа для подачи заявок"""
    __tablename__ = "access_rights"
    
    id = Column(Integer, primary_key=True)
    
    # Связь с пользователем
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user = relationship("User", back_populates="access_rights", foreign_keys=[user_id])
    
    # Уровень доступа
    access_level = Column(Enum(AccessLevel), nullable=False)
    
    # Детали доступа
    apartment_number = Column(String(20), nullable=True)  # Для уровня APARTMENT
    house_number = Column(String(20), nullable=True)      # Для уровня HOUSE
    yard_name = Column(String(100), nullable=True)        # Для уровня YARD
    
    # Статус прав
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Кто назначил права
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    granted_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Комментарии
    notes = Column(Text, nullable=True)
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<AccessRights(user_id={self.user_id}, level={self.access_level}, active={self.is_active})>"
