from sqlalchemy import Column, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from uk_management_bot.database.session import Base


class BoardConfig(Base):
    """Singleton-конфиг публичной витрины resident-board.

    Всегда одна строка с id=1: порядок блоков, наименование УК, контакты,
    данные бота, объявления и часы работы. Редактируется менеджером.
    """

    __tablename__ = "board_config"

    id = Column(Integer, primary_key=True)
    # Прод-БД: jsonb (миграция 021). with_variant → postgresql=JSONB, sqlite=JSON
    # (тест-conftests на sqlite). Контракт ORM==БД (PRC-05).
    data = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # DB-054: FK на users (ON DELETE SET NULL) + индекс — было голым Integer.
    updated_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    def __repr__(self):
        return f"<BoardConfig(id={self.id}, updated_at={self.updated_at})>"
