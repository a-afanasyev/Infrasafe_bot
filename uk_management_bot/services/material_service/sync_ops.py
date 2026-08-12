"""Sync-слой (бот): выборки для клавиатур и FIFO-списание в сессии бота.

Block-move из services/material_service.py (AUD5-ARCH-3 волна 9), тела
байт-в-байт.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from uk_management_bot.database.models.material import (
    Material,
    MaterialIssue,
    MaterialReceipt,
)
from uk_management_bot.database.models.request import Request

from ._core import (
    Allocation,
    BatchView,
    MaterialNotFoundError,
    MaterialValidationError,
    RequestNotFoundError,
    _build_allocations,
    _build_issue,
    _decrement_batches,
    _validate_issue_target,
    allocate_fifo,
    parse_qty,
)

# ===========================================================================
# SYNC (бот)
# ===========================================================================

def _get_active_material_sync(db: Session, material_id: int) -> Material:
    material = db.query(Material).filter(Material.id == material_id).first()
    if material is None:
        raise MaterialNotFoundError(f"материал {material_id} не найден")
    if not material.is_active:
        raise MaterialValidationError(f"материал «{material.name}» деактивирован")
    return material


def list_materials_with_stock(db: Session) -> list[dict]:
    """Активные материалы с остатком > 0 (для клавиатуры бота)."""
    stock = func.coalesce(func.sum(MaterialReceipt.qty_remaining), 0)
    rows = (
        db.query(Material.id, Material.name, Material.unit, stock.label("stock"))
        .join(MaterialReceipt, MaterialReceipt.material_id == Material.id)
        .filter(Material.is_active.is_(True), MaterialReceipt.qty_remaining > 0)
        .group_by(Material.id, Material.name, Material.unit)
        .order_by(Material.name)
        .all()
    )
    return [
        {"id": r.id, "name": r.name, "unit": r.unit, "stock": Decimal(str(r.stock))}
        for r in rows
    ]


def get_material_stock_sync(db: Session, material_id: int) -> Decimal:
    """Текущий остаток материала (без лока — для отображения)."""
    stock = (
        db.query(func.coalesce(func.sum(MaterialReceipt.qty_remaining), 0))
        .filter(MaterialReceipt.material_id == material_id)
        .scalar()
    )
    return Decimal(str(stock))


def issue_material_sync(db: Session, *, material_id: int, qty,
                        created_by: int, doc_type: str = "request",
                        request_number: Optional[str] = None,
                        reason: Optional[str] = None) -> MaterialIssue:
    """Списать материал (FIFO) — sync-путь бота.

    Лочит партии FOR UPDATE, аллоцирует, декрементирует qty_remaining,
    пишет issue+allocations. Commit НЕ делает — вызывающий хендлер добавляет
    RequestComment в той же сессии и коммитит один раз (атомарность).
    """
    qty = parse_qty(qty)
    _validate_issue_target(doc_type, request_number, reason)
    material = _get_active_material_sync(db, material_id)
    if doc_type == "request":
        exists = (
            db.query(Request.request_number)
            .filter(Request.request_number == request_number)
            .first()
        )
        if exists is None:
            raise RequestNotFoundError(f"заявка {request_number} не найдена")

    batches = (
        db.query(MaterialReceipt)
        .filter(
            MaterialReceipt.material_id == material_id,
            MaterialReceipt.qty_remaining > 0,
        )
        .order_by(MaterialReceipt.created_at, MaterialReceipt.id)
        .with_for_update()
        .all()
    )
    allocations = allocate_fifo(
        [BatchView(b.id, Decimal(str(b.qty_remaining)), Decimal(str(b.unit_price)))
         for b in batches],
        qty,
    )
    return _apply_issue(
        db, batches, allocations,
        material=material, qty=qty, doc_type=doc_type,
        request_number=request_number, reason=reason, created_by=created_by,
    )


def _apply_issue(db: Session, batches: list[MaterialReceipt],
                 allocations: list[Allocation], *, material: Material,
                 qty: Decimal, doc_type: str, request_number: Optional[str],
                 reason: Optional[str], created_by: int,
                 reversal_of_receipt_id: Optional[int] = None) -> MaterialIssue:
    """Sync-apply: декремент партий + insert issue/allocations (без commit)."""
    _decrement_batches(batches, allocations)
    issue = _build_issue(
        allocations, material=material, qty=qty, doc_type=doc_type,
        request_number=request_number, reason=reason, created_by=created_by,
        reversal_of_receipt_id=reversal_of_receipt_id,
    )
    db.add(issue)
    db.flush()
    for row in _build_allocations(issue.id, allocations):
        db.add(row)
    db.flush()
    return issue
