"""Webhook outbox — transactional outbox pattern for reliable webhook delivery."""
from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, Index, CheckConstraint
from sqlalchemy.sql import func, text
from uk_management_bot.database.session import Base


class WebhookOutbox(Base):
    __tablename__ = "webhook_outbox"

    id = Column(Integer, primary_key=True)
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
    # PR-5 (CODE-01): claim/lease-доставка. Запись клеймится воркером
    # (status='in_flight' + уникальный claim_token + claimed_at), HTTP идёт вне
    # транзакции, финализация — compare-and-set по claim_token. Протухший lease
    # (claimed_at < now()-OUTBOX_LEASE) реклеймится другим воркером.
    claim_token = Column(String(36), nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    # Наблюдаемость crash-loop'ов: число claim'ов (стартов доставки). НЕ участвует
    # в dead-letter — retry-budget расходуют только подтверждённые неуспехи.
    claim_count = Column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        Index("ix_webhook_outbox_status_created", "status", "created_at"),
        # DB-053: горячий путь outbox-процессора — pending-события, oldest-first.
        Index("ix_webhook_outbox_pending", "created_at", postgresql_where=text("status = 'pending'")),
        # PR-5: reclaim-скан протухших in_flight по claimed_at.
        Index("ix_webhook_outbox_in_flight", "claimed_at", postgresql_where=text("status = 'in_flight'")),
        # DB-057: статус — закрытое множество (pending → in_flight → sent/failed).
        CheckConstraint(
            "status IN ('pending', 'in_flight', 'sent', 'failed')",
            name="ck_webhook_outbox_status",
        ),
    )

    def __repr__(self):
        return f"<WebhookOutbox(id={self.id}, event={self.event}, status={self.status})>"
