from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ImportBatch(Base):
    __tablename__ = "payment_imports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(200))
    as_of: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="preview")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now,
                                                 server_default=text("CURRENT_TIMESTAMP"))
    created_by: Mapped[str] = mapped_column(String(64))
    invalid: Mapped[int] = mapped_column(Integer, default=0)
    row_count: Mapped[int] = mapped_column(Integer)


class ImportEntry(Base):
    """Строка импорта. `paid_at` вынесен из JSON отдельной колонкой: по нему идёт
    сортировка платежей и отсечение «последних 200» — по дате самого платежа, а не
    по дате пакета, иначе свежий платёж из старой выгрузки отрезался бы."""
    __tablename__ = "payment_import_rows"
    __table_args__ = (Index("ix_payment_import_rows_batch_line", "batch_id", "line"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("payment_imports.id", ondelete="RESTRICT"))
    line: Mapped[int] = mapped_column(Integer)
    account_number: Mapped[str] = mapped_column(String(64), index=True)
    paid_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    data: Mapped[dict] = mapped_column(JSON)
    errors: Mapped[list] = mapped_column(JSON)


class PaymentClaim(Base):
    """Unique active source operation, enforced also for concurrent activations."""
    __tablename__ = "payment_claims"
    __table_args__ = (UniqueConstraint("source", "operation_id", name="uq_payment_source_operation"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("payment_imports.id", ondelete="RESTRICT"), index=True)
    source: Mapped[str] = mapped_column(String(100))
    operation_id: Mapped[str] = mapped_column(String(100))


class AuditEvent(Base):
    __tablename__ = "payment_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("payment_imports.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now,
                                                 server_default=text("CURRENT_TIMESTAMP"))
