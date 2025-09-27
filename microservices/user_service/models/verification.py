# Verification Models for User Service
# UK Management Bot - User Service

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from .user import Base

class UserVerification(Base):
    """User verification requests and process"""
    __tablename__ = "user_verifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)

    # Verification details
    verification_type = Column(String(50), nullable=False, index=True)  # identity/address/phone/email
    status = Column(String(50), default='pending', nullable=False, index=True)  # pending/approved/rejected/in_review

    # Request details
    requested_by = Column(Integer, nullable=True)  # Admin user ID who requested
    verified_by = Column(Integer, nullable=True)  # Admin user ID who verified
    verification_data = Column(JSONB, nullable=True)  # Requested/provided information
    notes = Column(Text, nullable=True)  # Admin notes

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Optional expiration

    # Relationships
    user = relationship("User", back_populates="verifications")
    documents = relationship("UserDocument", back_populates="verification", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<UserVerification(id={self.id}, user_id={self.user_id}, type={self.verification_type}, status={self.status})>"

class UserDocument(Base):
    """User uploaded documents for verification"""
    __tablename__ = "user_documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    verification_id = Column(Integer, ForeignKey('user_verifications.id'), nullable=True, index=True)

    # Document details
    document_type = Column(String(50), nullable=False, index=True)  # passport/utility_bill/photo/id_card
    file_url = Column(String(500), nullable=False)  # URL from Media Service
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)

    # Verification status
    is_verified = Column(Boolean, default=False, nullable=False)
    verified_by = Column(Integer, nullable=True)  # Admin user ID who verified
    verification_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="documents")
    verification = relationship("UserVerification", back_populates="documents")

    def __repr__(self):
        return f"<UserDocument(id={self.id}, user_id={self.user_id}, type={self.document_type}, verified={self.is_verified})>"