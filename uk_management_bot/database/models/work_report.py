from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from uk_management_bot.constants.work_reports import WORK_REPORT_STATUSES
from uk_management_bot.database.session import Base


class WorkReport(Base):
    """Замороженный снапшот выполненной заявки для публичной ленты «до/после».

    Публикуется на витрину резидентов после модерации менеджером. Две вещи
    здесь неочевидны из самого кода:

    - Нет `ForeignKey` на `requests`: заявку можно жёстко удалить
      (`admin_handler_service.delete_request_cascade`, `request_service.delete_request`),
      а отчёт — бессрочный снапшот и обязан пережить удаление исходной заявки.
      Идемпотентность синхронизации обеспечена через `unique` на `request_number`.
    - Нет столбца `description`: наружу не должно уйти ничего, что не хранится
      явно в этой таблице — контент ленты собирается только из полей ниже.

    Жизненный цикл (реализация состояния — в последующих задачах):
    pending ⇄ needs_media → publishing (transient) → published →
    needs_review (заявка перестала быть eligible после публикации) | rejected
    (ручной снятие с публикации). rejected → pending через reopen. Жёсткого
    удаления в v1 нет.
    """

    __tablename__ = "work_reports"
    __table_args__ = (
        # AUD6-P2-57: список собирается из канона, а не дублируется строкой.
        CheckConstraint(
            "status IN ({})".format(",".join(f"'{s}'" for s in WORK_REPORT_STATUSES)),
            name="ck_work_reports_status"),
        CheckConstraint("source IN ('auto','manual')", name="ck_work_reports_source"),
        Index("ix_work_reports_status_published_at", "status", "published_at"),
    )
    id = Column(Integer, primary_key=True)

    # БЕЗ ForeignKey: заявку можно жёстко удалить (admin_handler_service.delete_request_cascade,
    # request_service.delete_request), а отчёт — бессрочный снапшот и обязан пережить это.
    # UNIQUE — идемпотентность sync. НИКОГДА не отдаётся наружу.
    request_number = Column(String(15), nullable=False, unique=True, index=True)

    category_key   = Column(String(100), nullable=False)   # канон-ключ (resolve_category_key)
    address_public = Column(String(300), nullable=False)   # дом/двор; НИКОГДА не копия Request.address
    # NOT NULL: у «Исполнено» completed_at пуст → COALESCE(completed_at, updated_at, created_at)
    performed_at   = Column(DateTime(timezone=True), nullable=False)

    before_media_ids = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=list)
    after_media_ids  = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=list)
    # [{"id":int,"file_type":"photo","mime":"image/jpeg","size":int}] — снапшот на момент publish,
    # чтобы публичная лента не ходила в media-service вообще.
    media_meta       = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=list)
    # id, на которые ЭТОТ отчёт держит publication-lock. Источник для компенсаций и сверки.
    locked_media_ids = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=list)

    status = Column(String(16), nullable=False, default="pending", server_default="pending", index=True)
    source = Column(String(8),  nullable=False, default="manual",  server_default="manual")
    reject_reason   = Column(String(200), nullable=True)

    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    published_at    = Column(DateTime(timezone=True), nullable=True)
    media_synced_at = Column(DateTime(timezone=True), nullable=True)
    state_changed_at = Column(DateTime(timezone=True), nullable=True)   # для отлова зависшего publishing
    moderated_by    = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    def __repr__(self):
        return f"<WorkReport(id={self.id}, request_number={self.request_number}, status={self.status})>"
