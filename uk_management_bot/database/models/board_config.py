from sqlalchemy import Column, Integer, DateTime, JSON
from sqlalchemy.sql import func

from uk_management_bot.database.session import Base


class BoardConfig(Base):
    """Singleton-конфиг публичной витрины resident-board.

    Всегда одна строка с id=1: порядок блоков, наименование УК, контакты,
    данные бота, объявления и часы работы. Редактируется менеджером.
    """

    __tablename__ = "board_config"

    id = Column(Integer, primary_key=True)
    data = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, nullable=True)

    def __repr__(self):
        return f"<BoardConfig(id={self.id}, updated_at={self.updated_at})>"
