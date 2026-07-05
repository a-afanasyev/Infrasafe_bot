"""Складской учёт материалов: номенклатура, партии (FIFO), расход, аллокации.

Четыре таблицы модуля «Учёт закупок и движения материальных средств»:

* ``materials`` — номенклатура (name UNIQUE навсегда, soft-delete is_active)
* ``material_receipts`` — приход = партия; immutable кроме qty_remaining
* ``material_issues`` — расход; immutable; request_number БЕЗ FK на requests
  (журнал переживает удаление заявки)
* ``material_issue_allocations`` — FIFO-связка расход↔партия (себестоимость)

Сторно-ссылки образуют цикл FK receipts↔issues, поэтому
``fk_material_receipts_reversal_of_issue`` добавляется ОТДЕЛЬНЫМ шагом после
создания обеих таблиц (в модели — use_alter=True).

Идемпотентность per-object: guard перед каждым create_table, create_index и
create_foreign_key — упавшая посередине миграция при повторе досоздаёт
недостающие объекты (CI = create_all + stamp + upgrade).

Revision ID: 036
Revises: 035
Create Date: 2026-07-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MATERIAL_UNITS = ("pcs", "m", "m2", "l", "kg", "pack", "set")
RECEIPT_DOC_TYPES = ("purchase", "surplus")
ISSUE_DOC_TYPES = ("request", "household", "shortage")


def _tables(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def _indexes(bind, table: str) -> set:
    return {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}


def _fks(bind, table: str) -> set:
    return {fk["name"] for fk in sa.inspect(bind).get_foreign_keys(table)}


def _in_list(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _ensure_index(bind, table: str, name: str, columns, **kw) -> None:
    if name not in _indexes(bind, table):
        op.create_index(name, table, columns, **kw)


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # 1) Номенклатура
    if "materials" not in tables:
        op.create_table(
            "materials",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(200), nullable=False, unique=True),
            sa.Column("unit", sa.String(20), nullable=False),
            sa.Column("category", sa.String(100), nullable=True),
            sa.Column("min_stock", sa.Numeric(12, 3), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                f"unit IN ({_in_list(MATERIAL_UNITS)})", name="ck_materials_unit"
            ),
        )

    # 2) Приход/партии (FK на material_issues добавляется шагом 5 — цикл)
    if "material_receipts" not in _tables(bind):
        op.create_table(
            "material_receipts",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "material_id",
                sa.Integer,
                sa.ForeignKey("materials.id"),
                nullable=False,
            ),
            sa.Column(
                "doc_type", sa.String(20), nullable=False, server_default="purchase"
            ),
            sa.Column("qty", sa.Numeric(12, 3), nullable=False),
            sa.Column("qty_remaining", sa.Numeric(12, 3), nullable=False),
            sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
            sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("supplier", sa.String(200), nullable=True),
            sa.Column("doc_number", sa.String(100), nullable=True),
            sa.Column("doc_date", sa.Date(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("reversal_of_issue_id", sa.Integer, nullable=True),
            sa.Column("material_name", sa.String(200), nullable=False),
            sa.Column("unit", sa.String(20), nullable=False),
            sa.Column(
                "created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint("qty > 0", name="ck_receipts_qty_positive"),
            sa.CheckConstraint(
                "qty_remaining >= 0 AND qty_remaining <= qty",
                name="ck_receipts_remaining_range",
            ),
            sa.CheckConstraint(
                "unit_price >= 0", name="ck_receipts_unit_price_non_negative"
            ),
            sa.CheckConstraint(
                f"doc_type IN ({_in_list(RECEIPT_DOC_TYPES)})",
                name="ck_receipts_doc_type",
            ),
        )

    # 3) Расход (request_number — plain-строка, БЕЗ FK: журнал переживает
    #    удаление заявки через delete_request_cascade/delete_request)
    if "material_issues" not in _tables(bind):
        op.create_table(
            "material_issues",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "material_id",
                sa.Integer,
                sa.ForeignKey("materials.id"),
                nullable=False,
            ),
            sa.Column(
                "doc_type", sa.String(20), nullable=False, server_default="request"
            ),
            sa.Column("qty", sa.Numeric(12, 3), nullable=False),
            sa.Column("total_cost", sa.Numeric(14, 2), nullable=False),
            sa.Column("request_number", sa.String(15), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column(
                "reversal_of_receipt_id",
                sa.Integer,
                sa.ForeignKey("material_receipts.id"),
                nullable=True,
            ),
            sa.Column("material_name", sa.String(200), nullable=False),
            sa.Column("unit", sa.String(20), nullable=False),
            sa.Column(
                "created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint("qty > 0", name="ck_issues_qty_positive"),
            sa.CheckConstraint(
                f"doc_type IN ({_in_list(ISSUE_DOC_TYPES)})",
                name="ck_issues_doc_type",
            ),
            sa.CheckConstraint(
                "(doc_type = 'request' AND request_number IS NOT NULL) "
                "OR (doc_type <> 'request' AND reason IS NOT NULL)",
                name="ck_issues_target",
            ),
        )

    # 4) FIFO-аллокации
    if "material_issue_allocations" not in _tables(bind):
        op.create_table(
            "material_issue_allocations",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "issue_id",
                sa.Integer,
                sa.ForeignKey("material_issues.id"),
                nullable=False,
            ),
            sa.Column(
                "receipt_id",
                sa.Integer,
                sa.ForeignKey("material_receipts.id"),
                nullable=False,
            ),
            sa.Column("qty", sa.Numeric(12, 3), nullable=False),
            sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.CheckConstraint("qty > 0", name="ck_allocations_qty_positive"),
        )

    # 5) Циклический FK receipts→issues — отдельным шагом после обеих таблиц
    if "fk_material_receipts_reversal_of_issue" not in _fks(bind, "material_receipts"):
        op.create_foreign_key(
            "fk_material_receipts_reversal_of_issue",
            "material_receipts",
            "material_issues",
            ["reversal_of_issue_id"],
            ["id"],
        )

    # 6) Индексы — каждый со своим guard'ом (упавший посередине повтор досоздаёт)
    _ensure_index(
        bind, "material_receipts", "ix_material_receipts_material_id", ["material_id"]
    )
    _ensure_index(
        bind, "material_receipts", "ix_material_receipts_created_at", ["created_at"]
    )
    _ensure_index(
        bind,
        "material_receipts",
        "ix_material_receipts_reversal_of_issue_id",
        ["reversal_of_issue_id"],
    )
    _ensure_index(
        bind,
        "material_receipts",
        "ix_material_receipts_fifo",
        ["material_id", "created_at", "id"],
        postgresql_where=sa.text("qty_remaining > 0"),
    )
    _ensure_index(
        bind, "material_issues", "ix_material_issues_material_id", ["material_id"]
    )
    _ensure_index(
        bind,
        "material_issues",
        "ix_material_issues_request_number",
        ["request_number"],
    )
    _ensure_index(
        bind,
        "material_issues",
        "ix_material_issues_material_created",
        ["material_id", "created_at"],
    )
    _ensure_index(
        bind,
        "material_issues",
        "ix_material_issues_reversal_of_receipt_id",
        ["reversal_of_receipt_id"],
    )
    _ensure_index(
        bind, "material_issues", "ix_material_issues_created_at", ["created_at"]
    )
    _ensure_index(
        bind,
        "material_issue_allocations",
        "ix_issue_allocations_issue_id",
        ["issue_id"],
    )
    _ensure_index(
        bind,
        "material_issue_allocations",
        "ix_issue_allocations_receipt_id",
        ["receipt_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    # Сначала разорвать циклический FK, затем таблицы в обратном порядке
    if "material_receipts" in _tables(bind):
        if "fk_material_receipts_reversal_of_issue" in _fks(bind, "material_receipts"):
            op.drop_constraint(
                "fk_material_receipts_reversal_of_issue",
                "material_receipts",
                type_="foreignkey",
            )
    op.execute("DROP TABLE IF EXISTS material_issue_allocations")
    op.execute("DROP TABLE IF EXISTS material_issues")
    op.execute("DROP TABLE IF EXISTS material_receipts")
    op.execute("DROP TABLE IF EXISTS materials")
