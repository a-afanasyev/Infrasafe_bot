"""Модели складского учёта материалов (закупки и движение матсредств).

Четыре таблицы одного агрегата:

* ``materials`` — номенклатура (справочник, soft-delete через is_active)
* ``material_receipts`` — приход = партия (FIFO-лот)
* ``material_issues`` — расход (по заявке / хознужды / недостача)
* ``material_issue_allocations`` — FIFO-связка расход↔партия (аудит себестоимости)

Политика учёта:

* Операции append-only: ``material_issues``/``material_issue_allocations``
  полностью immutable; ``material_receipts`` immutable кроме ``qty_remaining``
  (единственное мутируемое поле — декремент при FIFO-списании). Исправление
  ошибок — только сторно со ссылкой ``reversal_of_issue_id`` /
  ``reversal_of_receipt_id`` (см. services/material_service.py).
* ``material_issues.request_number`` — plain-строка БЕЗ FK на requests:
  складской журнал обязан пережить удаление заявки (delete_request_cascade /
  RequestService.delete_request). Существование заявки проверяет сервис при
  создании расхода.
* ``material_name``/``unit`` в операциях — snapshot на момент операции:
  переименование карточки материала не переписывает историю.
* Остатки — агрегат SUM(qty_remaining) по партиям, денормализованной таблицы нет.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from uk_management_bot.database.session import Base

# Канон-ключи единиц измерения (локализация — через get_text/i18n, паттерн urgency)
MATERIAL_UNITS = ("pcs", "m", "m2", "l", "kg", "pack", "set")
# Типы прихода: закупка / излишек инвентаризации либо сторно расхода
RECEIPT_DOC_TYPES = ("purchase", "surplus")
# Типы расхода: на заявку / хознужды / недостача инвентаризации либо сторно прихода
ISSUE_DOC_TYPES = ("request", "household", "shortage")


class Material(Base):
    """Номенклатура материалов.

    ``name`` уникален глобально и навсегда (включая is_active=false):
    один материал = одна карточка с непрерывной историей движений.
    Повтор имени деактивированного → реактивация существующей карточки.
    """

    __tablename__ = "materials"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    unit = Column(String(20), nullable=False)
    category = Column(String(100), nullable=True)
    min_stock = Column(Numeric(12, 3), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    receipts = relationship("MaterialReceipt", back_populates="material")
    issues = relationship("MaterialIssue", back_populates="material")

    __table_args__ = (
        CheckConstraint(
            "unit IN ({})".format(", ".join(f"'{u}'" for u in MATERIAL_UNITS)),
            name="ck_materials_unit",
        ),
    )

    def __repr__(self):
        return f"<Material(id={self.id}, name={self.name!r}, unit={self.unit})>"


class MaterialReceipt(Base):
    """Приход = партия (FIFO-лот).

    Immutable кроме ``qty_remaining`` (декремент при списании).
    ``reversal_of_issue_id`` заполнен, если партия создана сторно расхода
    (одно сторно может создать несколько партий — по одной на каждую цену
    исходных аллокаций, поэтому UNIQUE на поле не вешается).
    """

    __tablename__ = "material_receipts"

    id = Column(Integer, primary_key=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    doc_type = Column(String(20), nullable=False, server_default="purchase")
    qty = Column(Numeric(12, 3), nullable=False)
    qty_remaining = Column(Numeric(12, 3), nullable=False)
    unit_price = Column(Numeric(14, 2), nullable=False)
    total_amount = Column(Numeric(14, 2), nullable=False)
    supplier = Column(String(200), nullable=True)
    doc_number = Column(String(100), nullable=True)
    doc_date = Column(Date, nullable=True)
    note = Column(Text, nullable=True)
    # Циклический FK receipts↔issues: разрубается через use_alter (ALTER TABLE)
    reversal_of_issue_id = Column(
        Integer,
        ForeignKey(
            "material_issues.id",
            use_alter=True,
            name="fk_material_receipts_reversal_of_issue",
        ),
        nullable=True,
    )
    material_name = Column(String(200), nullable=False)
    unit = Column(String(20), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    material = relationship("Material", back_populates="receipts")
    allocations = relationship("MaterialIssueAllocation", back_populates="receipt")

    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_receipts_qty_positive"),
        CheckConstraint(
            "qty_remaining >= 0 AND qty_remaining <= qty",
            name="ck_receipts_remaining_range",
        ),
        CheckConstraint("unit_price >= 0", name="ck_receipts_unit_price_non_negative"),
        CheckConstraint(
            "doc_type IN ({})".format(", ".join(f"'{t}'" for t in RECEIPT_DOC_TYPES)),
            name="ck_receipts_doc_type",
        ),
        Index("ix_material_receipts_material_id", "material_id"),
        Index("ix_material_receipts_created_at", "created_at"),
        Index("ix_material_receipts_reversal_of_issue_id", "reversal_of_issue_id"),
        # FIFO-скан: только партии с остатком (partial — PostgreSQL; на sqlite
        # postgresql_where игнорируется и создаётся обычный индекс — безвредно)
        Index(
            "ix_material_receipts_fifo",
            "material_id",
            "created_at",
            "id",
            postgresql_where=text("qty_remaining > 0"),
        ),
    )

    def __repr__(self):
        return (
            f"<MaterialReceipt(id={self.id}, material_id={self.material_id}, "
            f"qty={self.qty}, remaining={self.qty_remaining})>"
        )


class MaterialIssue(Base):
    """Расход материала. Полностью immutable.

    ``request_number`` — plain-строка без FK (см. docstring модуля).
    ``reversal_of_receipt_id`` заполнен, если расход = сторно прихода
    (адресное списание ровно указанной партии мимо общего FIFO).
    """

    __tablename__ = "material_issues"

    id = Column(Integer, primary_key=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    doc_type = Column(String(20), nullable=False, server_default="request")
    qty = Column(Numeric(12, 3), nullable=False)
    total_cost = Column(Numeric(14, 2), nullable=False)
    request_number = Column(String(15), nullable=True)
    reason = Column(Text, nullable=True)
    reversal_of_receipt_id = Column(
        Integer, ForeignKey("material_receipts.id"), nullable=True
    )
    material_name = Column(String(200), nullable=False)
    unit = Column(String(20), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    material = relationship("Material", back_populates="issues")
    allocations = relationship("MaterialIssueAllocation", back_populates="issue")

    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_issues_qty_positive"),
        CheckConstraint(
            "doc_type IN ({})".format(", ".join(f"'{t}'" for t in ISSUE_DOC_TYPES)),
            name="ck_issues_doc_type",
        ),
        # Расход по заявке обязан иметь номер; прочие типы — причину
        CheckConstraint(
            "(doc_type = 'request' AND request_number IS NOT NULL) "
            "OR (doc_type <> 'request' AND reason IS NOT NULL)",
            name="ck_issues_target",
        ),
        Index("ix_material_issues_material_id", "material_id"),
        Index("ix_material_issues_request_number", "request_number"),
        Index("ix_material_issues_material_created", "material_id", "created_at"),
        Index("ix_material_issues_reversal_of_receipt_id", "reversal_of_receipt_id"),
        Index("ix_material_issues_created_at", "created_at"),
    )

    def __repr__(self):
        return (
            f"<MaterialIssue(id={self.id}, material_id={self.material_id}, "
            f"qty={self.qty}, doc_type={self.doc_type})>"
        )


class MaterialIssueAllocation(Base):
    """FIFO-связка расход↔партия: из какой партии, сколько и почём списано.

    Аудит себестоимости; полностью immutable. Источник остатка — НЕ аллокации,
    а ``material_receipts.qty_remaining`` (инвариант
    ``qty_remaining = qty − SUM(allocations)`` закреплён тестами).
    """

    __tablename__ = "material_issue_allocations"

    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey("material_issues.id"), nullable=False)
    receipt_id = Column(Integer, ForeignKey("material_receipts.id"), nullable=False)
    qty = Column(Numeric(12, 3), nullable=False)
    unit_price = Column(Numeric(14, 2), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)

    issue = relationship("MaterialIssue", back_populates="allocations")
    receipt = relationship("MaterialReceipt", back_populates="allocations")

    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_allocations_qty_positive"),
        Index("ix_issue_allocations_issue_id", "issue_id"),
        Index("ix_issue_allocations_receipt_id", "receipt_id"),
    )

    def __repr__(self):
        return (
            f"<MaterialIssueAllocation(issue_id={self.issue_id}, "
            f"receipt_id={self.receipt_id}, qty={self.qty})>"
        )
