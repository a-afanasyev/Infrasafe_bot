from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from uk_management_bot.database.session import Base

# APIFE-14: revocation_reason values. Only ROTATED replay triggers family-wide
# revocation; LOGOUT/ADMIN/legacy (NULL) revocations never do.
REASON_ROTATED = "rotated"
REASON_LOGOUT = "logout"
REASON_REUSE = "reuse"
REASON_ADMIN = "admin"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    device_info = Column(Text, nullable=True)
    # APIFE-14: token-family lineage. One family per login; rotation preserves it.
    family_id = Column(String(36), nullable=False, index=True)
    parent_token_id = Column(Integer, ForeignKey('refresh_tokens.id', ondelete='SET NULL'), nullable=True)
    revocation_reason = Column(String(16), nullable=True)

    @property
    def is_valid(self) -> bool:
        from datetime import datetime, timezone
        if self.revoked_at is not None:
            return False
        expires = self.expires_at
        # Postgres returns tz-aware datetimes; SQLite (tests) drops the tzinfo.
        # Treat a naive value as UTC so the comparison never raises TypeError.
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > datetime.now(timezone.utc)
