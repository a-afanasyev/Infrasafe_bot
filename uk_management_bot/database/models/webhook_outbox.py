"""Webhook outbox — transactional outbox pattern for reliable webhook delivery."""
from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, Index
from sqlalchemy.sql import func
from uk_management_bot.database.session import Base


class WebhookOutbox(Base):
    __tablename__ = "webhook_outbox"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(36), nullable=False, unique=True, index=True)
    event = Column(String(50), nullable=False, index=True)
    endpoint = Column(String(200), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending", server_default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    last_error = Column(Text, nullable=True)
    retry_after = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_webhook_outbox_status_created", "status", "created_at"),
    )

    def __repr__(self):
        return f"<WebhookOutbox(id={self.id}, event={self.event}, status={self.status})>"
