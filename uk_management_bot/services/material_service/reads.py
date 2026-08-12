"""Async-чтение (API): остатки, журнал операций, отчёты.

Block-move из services/material_service.py (AUD5-ARCH-3 волна 9), тела
байт-в-байт.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.material import (
    Material,
    MaterialIssue,
    MaterialReceipt,
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.utils.sql_search import (
    ci_contains,
    escape_like as _escape_like,
    is_postgres,
)

from ._core import money
from ._sa import sa_false, sa_literal, sa_null_str

# ===========================================================================
# ASYNC — чтение (остатки, журнал, отчёты)
# ===========================================================================

async def get_stock(db: AsyncSession, *, q: Optional[str] = None,
                    only_low: bool = False) -> list[dict]:
    """Остатки по материалам: qty + сумма по ценам партий + флаг low_stock."""
    stock = func.coalesce(func.sum(MaterialReceipt.qty_remaining), 0)
    value = func.coalesce(
        func.sum(MaterialReceipt.qty_remaining * MaterialReceipt.unit_price), 0
    )
    query = (
        select(
            Material.id,
            Material.name,
            Material.unit,
            Material.category,
            Material.min_stock,
            Material.is_active,
            stock.label("stock"),
            value.label("stock_value"),
        )
        .outerjoin(
            MaterialReceipt,
            (MaterialReceipt.material_id == Material.id)
            & (MaterialReceipt.qty_remaining > 0),
        )
        .where(Material.is_active.is_(True))
        .group_by(
            Material.id, Material.name, Material.unit,
            Material.category, Material.min_stock, Material.is_active,
        )
        .order_by(Material.name)
    )
    if q:
        query = query.where(
            ci_contains(
                Material.name, f"%{_escape_like(q)}%", is_postgres=is_postgres(db),
            )
        )
    rows = (await db.execute(query)).all()
    result = []
    for r in rows:
        stock_qty = Decimal(str(r.stock))
        min_stock = Decimal(str(r.min_stock)) if r.min_stock is not None else None
        low = min_stock is not None and stock_qty < min_stock
        if only_low and not low:
            continue
        result.append(
            {
                "material_id": r.id,
                "name": r.name,
                "unit": r.unit,
                "category": r.category,
                "min_stock": min_stock,
                "stock": stock_qty,
                "stock_value": money(Decimal(str(r.stock_value))),
                "low_stock": low,
            }
        )
    return result


async def list_operations(db: AsyncSession, *, op_type: Optional[str] = None,
                          material_id: Optional[int] = None,
                          request_number: Optional[str] = None,
                          date_from=None, date_to=None,
                          limit: int = 50, offset: int = 0) -> dict:
    """Журнал операций: UNION ALL приход+расход, новые сверху."""
    receipts_q = select(
        sa_literal("receipt").label("op_type"),
        MaterialReceipt.id.label("id"),
        MaterialReceipt.material_id.label("material_id"),
        MaterialReceipt.material_name.label("material_name"),
        MaterialReceipt.unit.label("unit"),
        MaterialReceipt.doc_type.label("doc_type"),
        MaterialReceipt.qty.label("qty"),
        MaterialReceipt.total_amount.label("amount"),
        sa_null_str().label("request_number"),
        MaterialReceipt.supplier.label("supplier"),
        MaterialReceipt.note.label("reason"),
        MaterialReceipt.created_by.label("created_by"),
        MaterialReceipt.created_at.label("created_at"),
    )
    issues_q = select(
        sa_literal("issue").label("op_type"),
        MaterialIssue.id.label("id"),
        MaterialIssue.material_id.label("material_id"),
        MaterialIssue.material_name.label("material_name"),
        MaterialIssue.unit.label("unit"),
        MaterialIssue.doc_type.label("doc_type"),
        MaterialIssue.qty.label("qty"),
        MaterialIssue.total_cost.label("amount"),
        MaterialIssue.request_number.label("request_number"),
        sa_null_str().label("supplier"),
        MaterialIssue.reason.label("reason"),
        MaterialIssue.created_by.label("created_by"),
        MaterialIssue.created_at.label("created_at"),
    )
    if material_id is not None:
        receipts_q = receipts_q.where(MaterialReceipt.material_id == material_id)
        issues_q = issues_q.where(MaterialIssue.material_id == material_id)
    if date_from is not None:
        receipts_q = receipts_q.where(MaterialReceipt.created_at >= date_from)
        issues_q = issues_q.where(MaterialIssue.created_at >= date_from)
    if date_to is not None:
        receipts_q = receipts_q.where(MaterialReceipt.created_at <= date_to)
        issues_q = issues_q.where(MaterialIssue.created_at <= date_to)
    if request_number:
        # Приход не привязан к заявкам — остаются только расходы
        receipts_q = receipts_q.where(sa_false())
        issues_q = issues_q.where(MaterialIssue.request_number == request_number)
    if op_type == "receipt":
        issues_q = issues_q.where(sa_false())
    elif op_type == "issue":
        receipts_q = receipts_q.where(sa_false())

    from sqlalchemy import union_all

    union = union_all(receipts_q, issues_q).subquery()
    total = (
        await db.execute(select(func.count()).select_from(union))
    ).scalar_one()
    rows = (
        await db.execute(
            select(union)
            .order_by(union.c.created_at.desc(), union.c.op_type, union.c.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = [dict(r._mapping) for r in rows]
    return {"total": total, "items": items}


async def get_request_materials(db: AsyncSession, request_number: str) -> dict:
    """Списания по заявке + суммарная себестоимость.

    Полностью сторнированные расходы (есть surplus-партии с
    ``reversal_of_issue_id``) помечаются ``is_reversed`` и НЕ входят в
    ``total_cost`` — сторно = «материал не израсходован», карточка заявки
    не должна показывать отменённую себестоимость как использованную.
    """
    rows = (
        (
            await db.execute(
                select(MaterialIssue)
                .where(
                    MaterialIssue.request_number == request_number,
                    MaterialIssue.doc_type == "request",
                )
                .order_by(MaterialIssue.created_at)
            )
        )
        .scalars()
        .all()
    )
    reversed_ids: set[int] = set()
    if rows:
        reversed_ids = {
            r[0]
            for r in (
                await db.execute(
                    select(MaterialReceipt.reversal_of_issue_id.distinct()).where(
                        MaterialReceipt.reversal_of_issue_id.in_(
                            [i.id for i in rows]
                        )
                    )
                )
            ).all()
        }
    total = Decimal("0")
    for issue in rows:
        issue.is_reversed = issue.id in reversed_ids  # динамический атрибут для схемы
        if not issue.is_reversed:
            total += Decimal(str(issue.total_cost))
    return {"request_number": request_number, "items": rows, "total_cost": money(total)}


async def get_procurement(db: AsyncSession) -> dict:
    """Список «на закуп»: дефицит по min_stock + открытые заявки в статусе «Закуп»."""
    from uk_management_bot.database.models.user import User
    from uk_management_bot.utils.constants import REQUEST_STATUS_PURCHASE

    deficit = [
        {
            "material_id": row["material_id"],
            "name": row["name"],
            "unit": row["unit"],
            "stock": row["stock"],
            "min_stock": row["min_stock"],
            "to_buy": row["min_stock"] - row["stock"],
        }
        for row in await get_stock(db, only_low=True)
    ]
    requests = (
        await db.execute(
            select(
                Request.request_number,
                Request.requested_materials,
                Request.executor_id,
                User.first_name,
                User.last_name,
            )
            .outerjoin(User, User.id == Request.executor_id)
            .where(Request.status == REQUEST_STATUS_PURCHASE)
            .order_by(Request.created_at.desc())
        )
    ).all()
    open_purchase_requests = [
        {
            "request_number": r.request_number,
            "requested_materials": r.requested_materials,
            "executor_name": (
                " ".join(p for p in (r.first_name, r.last_name) if p) or None
            ),
        }
        for r in requests
    ]
    return {"deficit": deficit, "open_purchase_requests": open_purchase_requests}
