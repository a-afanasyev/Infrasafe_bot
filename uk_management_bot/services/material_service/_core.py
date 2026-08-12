"""Чистое ядро сервиса материалов: ошибки, DTO, FIFO-математика, валидации.

Block-move из services/material_service.py (AUD5-ARCH-3 волна 9), тела
байт-в-байт. Сюда же shared-строители ``_decrement_batches``/``_build_issue``/
``_build_allocations`` — по графу вызовов их используют ОБА зеркала apply:
``sync_ops._apply_issue`` и ``movements._apply_issue_async``.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

from uk_management_bot.database.models.material import (
    ISSUE_DOC_TYPES,
    MATERIAL_UNITS,
    Material,
    MaterialIssue,
    MaterialIssueAllocation,
    MaterialReceipt,
)

_MONEY = Decimal("0.01")
_QTY = Decimal("0.001")


# ===========================================================================
# Ошибки (роутер мапит: Validation → 422, Conflict/Insufficient → 409, NotFound → 404)
# ===========================================================================

class MaterialServiceError(Exception):
    """База ошибок сервиса материалов."""


class MaterialValidationError(MaterialServiceError):
    """Некорректные входные данные (→ 422)."""


class MaterialNotFoundError(MaterialServiceError):
    """Материал не найден (→ 404)."""


class MaterialConflictError(MaterialServiceError):
    """Нарушение инварианта учёта: дубль имени, повторное сторно и т.п. (→ 409)."""


class RequestNotFoundError(MaterialValidationError):
    """Заявка с указанным номером не существует (→ 422)."""


class InsufficientStockError(MaterialConflictError):
    """Остатка недостаточно для списания (→ 409)."""

    def __init__(self, available: Decimal):
        self.available = available
        super().__init__(f"недостаточно остатка: доступно {available}")


# ===========================================================================
# PURE CORE — без I/O, тестируется юнитами
# ===========================================================================

@dataclass(frozen=True)
class BatchView:
    """Снимок партии для FIFO-аллокации."""

    id: int
    qty_remaining: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class Allocation:
    """Строка списания из конкретной партии."""

    receipt_id: int
    qty: Decimal
    unit_price: Decimal
    amount: Decimal


def money(value: Decimal) -> Decimal:
    """Округлить сумму до 0.01 (ROUND_HALF_UP)."""
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def allocate_fifo(batches: list[BatchView], qty: Decimal) -> list[Allocation]:
    """Разложить списание ``qty`` по партиям в порядке следования (FIFO).

    Args:
        batches: партии с остатком, уже отсортированные (created_at, id).
        qty: количество к списанию (> 0).

    Returns:
        Список аллокаций; суммы округлены до 0.01 per-строка.

    Raises:
        InsufficientStockError: суммарного остатка партий не хватает.
    """
    remaining = qty
    allocations: list[Allocation] = []
    for batch in batches:
        if remaining <= 0:
            break
        if batch.qty_remaining <= 0:
            continue
        take = min(batch.qty_remaining, remaining)
        allocations.append(
            Allocation(
                receipt_id=batch.id,
                qty=take,
                unit_price=batch.unit_price,
                amount=money(take * batch.unit_price),
            )
        )
        remaining -= take
    if remaining > 0:
        available = sum((b.qty_remaining for b in batches), Decimal("0"))
        raise InsufficientStockError(available)
    return allocations


def parse_qty(value) -> Decimal:
    """Провалидировать количество: Decimal > 0, шаг 0.001."""
    try:
        qty = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise MaterialValidationError("количество — не число")
    if qty <= 0:
        raise MaterialValidationError("количество должно быть больше нуля")
    if qty != qty.quantize(_QTY):
        raise MaterialValidationError("количество — не более 3 знаков после запятой")
    return qty


def parse_price(value) -> Decimal:
    """Провалидировать цену: Decimal >= 0, шаг 0.01."""
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise MaterialValidationError("цена — не число")
    if price < 0:
        raise MaterialValidationError("цена не может быть отрицательной")
    return money(price)


def validate_unit(unit: str) -> str:
    if unit not in MATERIAL_UNITS:
        raise MaterialValidationError(
            f"единица измерения должна быть одной из: {', '.join(MATERIAL_UNITS)}"
        )
    return unit


def _validate_issue_target(doc_type: str, request_number: Optional[str],
                           reason: Optional[str]) -> None:
    """Инвариант ck_issues_target + явность doc_type (без вывода по полям)."""
    if doc_type not in ISSUE_DOC_TYPES:
        raise MaterialValidationError(f"недопустимый тип расхода: {doc_type}")
    if doc_type == "request":
        if not request_number:
            raise MaterialValidationError("расход по заявке требует request_number")
        if reason:
            raise MaterialValidationError("reason запрещён при расходе по заявке")
    else:
        if not reason:
            raise MaterialValidationError(f"расход '{doc_type}' требует reason")
        if request_number:
            raise MaterialValidationError(
                f"request_number запрещён при расходе '{doc_type}'"
            )


# ===========================================================================
# Общий apply: чистые шаги (декремент/сборка строк) + тонкие sync/async-зеркала
# (flush — корутина на AsyncSession, поэтому единой функции быть не может)
# ===========================================================================

def _decrement_batches(batches: list[MaterialReceipt],
                       allocations: list[Allocation]) -> None:
    by_id = {b.id: b for b in batches}
    for alloc in allocations:
        receipt = by_id[alloc.receipt_id]
        receipt.qty_remaining = Decimal(str(receipt.qty_remaining)) - alloc.qty


def _build_issue(allocations: list[Allocation], *, material: Material,
                 qty: Decimal, doc_type: str, request_number: Optional[str],
                 reason: Optional[str], created_by: int,
                 reversal_of_receipt_id: Optional[int]) -> MaterialIssue:
    return MaterialIssue(
        material_id=material.id,
        doc_type=doc_type,
        qty=qty,
        total_cost=money(sum((a.amount for a in allocations), Decimal("0"))),
        request_number=request_number,
        reason=reason,
        reversal_of_receipt_id=reversal_of_receipt_id,
        material_name=material.name,
        unit=material.unit,
        created_by=created_by,
    )


def _build_allocations(issue_id: int,
                       allocations: list[Allocation]) -> list[MaterialIssueAllocation]:
    return [
        MaterialIssueAllocation(
            issue_id=issue_id,
            receipt_id=a.receipt_id,
            qty=a.qty,
            unit_price=a.unit_price,
            amount=a.amount,
        )
        for a in allocations
    ]
