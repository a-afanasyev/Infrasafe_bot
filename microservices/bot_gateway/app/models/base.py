"""
Bot Gateway Service - Base Model
UK Management Bot

Base model with common fields for all tables.
"""

from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column, declarative_base

Base = declarative_base()


class BaseModel(Base):
    """
    Abstract base model with common fields.

    All models inherit from this to get:
    - UUID primary key
    - created_at timestamp
    - updated_at timestamp
    """

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
