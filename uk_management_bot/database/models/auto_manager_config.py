from sqlalchemy import Column, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from uk_management_bot.database.session import Base


class AutoManagerConfig(Base):
    """Singleton-конфиг «автоматического менеджера» (авто-назначение заявок).

    Всегда одна строка с id=1: enabled, режим (rule|ai), временнóе окно и
    лимит обработки за прогон. Редактируется менеджером из бота и дашборда;
    читается шедулер-job'ом каждые 2 минуты. Паттерн — клон board_config.
    """

    __tablename__ = "auto_manager_config"

    id = Column(Integer, primary_key=True)
    # with_variant → postgresql=JSONB, sqlite=JSON (тест-conftests). ORM==БД.
    data = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    def __repr__(self):
        return f"<AutoManagerConfig(id={self.id}, updated_at={self.updated_at})>"
