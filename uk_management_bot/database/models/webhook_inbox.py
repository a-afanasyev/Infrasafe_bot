"""Webhook inbox — inbound webhook record (InfraSafe → UK).

Durable dedup (unique event_id) + audit. Mirrors WebhookOutbox. Written by the
FIX-007 inbound handler; one row per received event.
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON, Text
from sqlalchemy.sql import func
from uk_management_bot.database.session import Base


class WebhookInbox(Base):
    __tablename__ = "webhook_inbox"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    event = Column(String(50), nullable=False, index=True)
    source_ip = Column(String(45), nullable=True)
    payload = Column(JSON, nullable=False)
    # accepted — request created; ignored — non-alert.created event; rejected — error
    outcome = Column(String(20), nullable=False)
    request_number = Column(String(15), nullable=True)
    error = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<WebhookInbox(id={self.id}, event={self.event}, outcome={self.outcome})>"
