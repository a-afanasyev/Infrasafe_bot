from sqlalchemy import Column, Integer, String, BigInteger, DateTime, JSON
from sqlalchemy.sql import func
from uk_management_bot.database.session import Base


class InviteNonce(Base):
    """Tracks invite nonce usage with UNIQUE constraint for atomic deduplication."""

    __tablename__ = "invite_nonces"

    id = Column(Integer, primary_key=True)
    nonce = Column(String(64), nullable=False, unique=True, index=True)
    used_by = Column(BigInteger, nullable=True)
    used_at = Column(DateTime(timezone=True), server_default=func.now())
    invite_payload = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<InviteNonce(id={self.id}, nonce={self.nonce[:8]}..., used_by={self.used_by})>"
