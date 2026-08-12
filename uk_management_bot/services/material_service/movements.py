"""Async-движения (API): приход, FIFO-списание, корректировки и сторно.

Block-move из services/material_service.py (AUD5-ARCH-3 волна 9), тела
байт-в-байт. ``_apply_issue_async`` и ``_get_active_material`` живут здесь:
по графу вызовов их используют только ``create_receipt``/``issue_material``/
``_reverse_receipt`` этого модуля.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.material import (
    RECEIPT_DOC_TYPES,
    Material,
    MaterialIssue,
    MaterialIssueAllocation,
    MaterialReceipt,
)
from uk_management_bot.database.models.request import Request

from ._core import (
    Allocation,
    BatchView,
    MaterialConflictError,
    MaterialNotFoundError,
    MaterialValidationError,
    RequestNotFoundError,
    _build_allocations,
    _build_issue,
    _decrement_batches,
    _validate_issue_target,
    allocate_fifo,
    money,
    parse_price,
    parse_qty,
)

async def _apply_issue_async(db: AsyncSession, batches: list[MaterialReceipt],
                             allocations: list[Allocation], *, material: Material,
                             qty: Decimal, doc_type: str,
                             request_number: Optional[str],
                             reason: Optional[str], created_by: int,
                             reversal_of_receipt_id: Optional[int] = None
                             ) -> MaterialIssue:
    """Async-зеркало _apply_issue (различие только в await flush)."""
    _decrement_batches(batches, allocations)
    issue = _build_issue(
        allocations, material=material, qty=qty, doc_type=doc_type,
        request_number=request_number, reason=reason, created_by=created_by,
        reversal_of_receipt_id=reversal_of_receipt_id,
    )
    db.add(issue)
    await db.flush()
    for row in _build_allocations(issue.id, allocations):
        db.add(row)
    await db.flush()
    return issue


# ===========================================================================
# ASYNC (API)
# ===========================================================================

async def _get_active_material(db: AsyncSession, material_id: int) -> Material:
    material = (
        await db.execute(select(Material).where(Material.id == material_id))
    ).scalar_one_or_none()
    if material is None:
        raise MaterialNotFoundError(f"материал {material_id} не найден")
    if not material.is_active:
        raise MaterialValidationError(f"материал «{material.name}» деактивирован")
    return material


async def create_receipt(db: AsyncSession, *, material_id: int, qty, unit_price,
                         created_by: int, supplier: Optional[str] = None,
                         doc_number: Optional[str] = None, doc_date=None,
                         note: Optional[str] = None,
                         doc_type: str = "purchase",
                         reversal_of_issue_id: Optional[int] = None) -> MaterialReceipt:
    """Оприходовать партию (закупка или surplus-корректировка)."""
    if doc_type not in RECEIPT_DOC_TYPES:
        raise MaterialValidationError(f"недопустимый тип прихода: {doc_type}")
    qty = parse_qty(qty)
    unit_price = parse_price(unit_price)
    material = await _get_active_material(db, material_id)
    receipt = MaterialReceipt(
        material_id=material.id,
        doc_type=doc_type,
        qty=qty,
        qty_remaining=qty,
        unit_price=unit_price,
        total_amount=money(qty * unit_price),
        supplier=supplier,
        doc_number=doc_number,
        doc_date=doc_date,
        note=note,
        reversal_of_issue_id=reversal_of_issue_id,
        material_name=material.name,
        unit=material.unit,
        created_by=created_by,
    )
    db.add(receipt)
    await db.flush()
    return receipt


async def issue_material(db: AsyncSession, *, material_id: int, qty,
                         created_by: int, doc_type: str = "request",
                         request_number: Optional[str] = None,
                         reason: Optional[str] = None,
                         _reversal_of_receipt_id: Optional[int] = None
                         ) -> MaterialIssue:
    """Списать материал (FIFO) — async-путь API. Commit у вызывающего."""
    qty = parse_qty(qty)
    _validate_issue_target(doc_type, request_number, reason)
    material = await _get_active_material(db, material_id)
    if doc_type == "request":
        exists = (
            await db.execute(
                select(Request.request_number).where(
                    Request.request_number == request_number
                )
            )
        ).first()
        if exists is None:
            raise RequestNotFoundError(f"заявка {request_number} не найдена")

    batches = (
        (
            await db.execute(
                select(MaterialReceipt)
                .where(
                    MaterialReceipt.material_id == material_id,
                    MaterialReceipt.qty_remaining > 0,
                )
                .order_by(MaterialReceipt.created_at, MaterialReceipt.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    allocations = allocate_fifo(
        [BatchView(b.id, Decimal(str(b.qty_remaining)), Decimal(str(b.unit_price)))
         for b in batches],
        qty,
    )
    return await _apply_issue_async(
        db, list(batches), allocations,
        material=material, qty=qty, doc_type=doc_type,
        request_number=request_number, reason=reason, created_by=created_by,
        reversal_of_receipt_id=_reversal_of_receipt_id,
    )


async def adjust(db: AsyncSession, *, material_id: int, direction: str,
                 reason: str, created_by: int, qty=None, unit_price=None,
                 reversal_of_issue_id: Optional[int] = None,
                 reversal_of_receipt_id: Optional[int] = None):
    """Корректировка: инвентаризация (qty обязателен) или сторно (qty запрещён).

    Режимы (взаимоисключающие, см. план):
      * surplus без ссылок — инвентаризационный излишек (qty + unit_price?)
      * shortage без ссылок — инвентаризационная недостача (qty, через FIFO)
      * surplus + reversal_of_issue_id — полное однократное сторно расхода:
        по одной surplus-партии на каждую цену исходных аллокаций
      * shortage + reversal_of_receipt_id — сторно нетронутого прихода:
        адресное списание ровно указанной партии (мимо общего FIFO)

    Returns:
        list[MaterialReceipt] | MaterialIssue — созданные операции.
    """
    if direction not in ("surplus", "shortage"):
        raise MaterialValidationError("direction должен быть surplus или shortage")
    if not (reason or "").strip():
        raise MaterialValidationError("reason обязателен для корректировки")
    if reversal_of_issue_id is not None and reversal_of_receipt_id is not None:
        raise MaterialValidationError("допустима только одна reversal-ссылка")

    is_reversal = (
        reversal_of_issue_id is not None or reversal_of_receipt_id is not None
    )
    if is_reversal and qty is not None:
        raise MaterialValidationError(
            "qty запрещён при сторно: объём берётся из исходной операции"
        )
    # Матрица полей: unit_price имеет смысл ТОЛЬКО у инвентаризационного
    # излишка; при shortage цена считается FIFO, при сторно — из исходной
    # операции. Несовместимое поле не игнорируем молча — 422.
    if unit_price is not None and (is_reversal or direction == "shortage"):
        raise MaterialValidationError(
            "unit_price допустим только при инвентаризационном излишке (surplus)"
        )
    if not is_reversal and qty is None:
        raise MaterialValidationError("qty обязателен для инвентаризационной корректировки")

    if reversal_of_issue_id is not None:
        if direction != "surplus":
            raise MaterialValidationError(
                "reversal_of_issue_id допустим только при direction=surplus"
            )
        return await _reverse_issue(
            db, material_id=material_id, issue_id=reversal_of_issue_id,
            reason=reason, created_by=created_by,
        )

    if reversal_of_receipt_id is not None:
        if direction != "shortage":
            raise MaterialValidationError(
                "reversal_of_receipt_id допустим только при direction=shortage"
            )
        return await _reverse_receipt(
            db, material_id=material_id, receipt_id=reversal_of_receipt_id,
            reason=reason, created_by=created_by,
        )

    # Инвентаризация
    if direction == "surplus":
        receipt = await create_receipt(
            db, material_id=material_id, qty=qty,
            unit_price=unit_price if unit_price is not None else Decimal("0"),
            created_by=created_by, note=reason, doc_type="surplus",
        )
        return [receipt]
    return await issue_material(
        db, material_id=material_id, qty=qty, created_by=created_by,
        doc_type="shortage", reason=reason,
    )


async def _reverse_issue(db: AsyncSession, *, material_id: int, issue_id: int,
                         reason: str, created_by: int) -> list[MaterialReceipt]:
    """Полное однократное сторно расхода: surplus-партия на каждую цену аллокаций.

    Гонка «однократности»: UNIQUE не годится (несколько партий на одно сторно) →
    лок исходного issue FOR UPDATE, затем проверка отсутствия партий с этим
    reversal_of_issue_id, затем вставка. Параллельный запрос сериализуется
    на локе и получает 409.
    """
    issue = (
        await db.execute(
            select(MaterialIssue)
            .where(MaterialIssue.id == issue_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if issue is None:
        raise MaterialValidationError(f"расход {issue_id} не найден")
    if issue.material_id != material_id:
        raise MaterialConflictError(
            "material_id не совпадает с материалом сторнируемого расхода"
        )
    already = (
        await db.execute(
            select(MaterialReceipt.id)
            .where(MaterialReceipt.reversal_of_issue_id == issue_id)
            .limit(1)
        )
    ).first()
    if already is not None:
        raise MaterialConflictError(f"расход {issue_id} уже сторнирован")

    allocations = (
        (
            await db.execute(
                select(MaterialIssueAllocation)
                .where(MaterialIssueAllocation.issue_id == issue_id)
                .order_by(MaterialIssueAllocation.id)
            )
        )
        .scalars()
        .all()
    )
    if not allocations:
        raise MaterialConflictError(f"у расхода {issue_id} нет аллокаций")

    # Партионная точность: группируем по цене, НЕ усредняем
    by_price: dict[Decimal, Decimal] = {}
    for alloc in allocations:
        price = Decimal(str(alloc.unit_price))
        by_price[price] = by_price.get(price, Decimal("0")) + Decimal(str(alloc.qty))

    receipts = []
    for price, qty in by_price.items():
        receipts.append(
            await create_receipt(
                db, material_id=material_id, qty=qty, unit_price=price,
                created_by=created_by, note=reason, doc_type="surplus",
                reversal_of_issue_id=issue_id,
            )
        )
    return receipts


async def _reverse_receipt(db: AsyncSession, *, material_id: int,
                           receipt_id: int, reason: str,
                           created_by: int) -> MaterialIssue:
    """Сторно нетронутого прихода: адресное списание ровно указанной партии.

    НЕ через общий FIFO — иначе тихо списалась бы чужая (более старая) партия.
    Гонку закрывает лок партии: конкурирующее списание/сторно меняет
    qty_remaining → проверка qty_remaining == qty не проходит → 409.
    """
    receipt = (
        await db.execute(
            select(MaterialReceipt)
            .where(MaterialReceipt.id == receipt_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if receipt is None:
        raise MaterialValidationError(f"приход {receipt_id} не найден")
    if receipt.material_id != material_id:
        raise MaterialConflictError(
            "material_id не совпадает с материалом сторнируемого прихода"
        )
    if Decimal(str(receipt.qty_remaining)) != Decimal(str(receipt.qty)):
        raise MaterialConflictError(
            "партия уже частично списана или сторнирована — сторно прихода невозможно"
        )
    material = (
        await db.execute(select(Material).where(Material.id == material_id))
    ).scalar_one()

    qty = Decimal(str(receipt.qty))
    unit_price = Decimal(str(receipt.unit_price))
    allocation = Allocation(
        receipt_id=receipt.id, qty=qty, unit_price=unit_price,
        amount=money(qty * unit_price),
    )
    return await _apply_issue_async(
        db, [receipt], [allocation],
        material=material, qty=qty, doc_type="shortage",
        request_number=None, reason=reason, created_by=created_by,
        reversal_of_receipt_id=receipt_id,
    )
