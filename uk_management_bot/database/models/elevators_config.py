from sqlalchemy import Column, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from uk_management_bot.database.session import Base


class ElevatorsConfig(Base):
    """Singleton-конфиг модуля «Лифты» (напоминания, публичность, интервалы ТО).

    Всегда одна строка с id=1; схема ``data`` не enforce-ится на уровне БД —
    валидацию и дефолты несёт сервисный слой. Паттерн — клон auto_manager_config.
    """

    __tablename__ = "elevators_config"

    id = Column(Integer, primary_key=True)
    # with_variant → postgresql=JSONB, sqlite=JSON (тест-conftests). ORM==БД.
    data = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    def __repr__(self):
        return f"<ElevatorsConfig(id={self.id}, updated_at={self.updated_at})>"
