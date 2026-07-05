"""Сервис складского учёта материалов (закупки и движение матсредств).

Паттерн workflow_runner: чистое ядро (``allocate_fifo``, валидации) + тонкие
sync/async-обёртки. FIFO-математика одна на оба пути.

Инварианты (см. модели database/models/material.py):

* issues/allocations полностью immutable; receipts immutable кроме
  ``qty_remaining``. Исправления — только сторно (полное, однократное,
  со ссылкой на исходную операцию).
* Отрицательные остатки запрещены: нехватка → ``InsufficientStockError``.
* Конкурентность: партии лочатся ``with_for_update()`` со стабильным
  ``ORDER BY created_at, id`` (нет дедлоков); на sqlite (тесты) FOR UPDATE
  молча опускается — как в остальном репо.
* Commit — у вызывающего (sync-путь бота добавляет RequestComment в той же
  сессии; async-путь коммитит в API-роутере).
"""

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.material import (
    ISSUE_DOC_TYPES,
    MATERIAL_UNITS,
    RECEIPT_DOC_TYPES,
    Material,
    MaterialIssue,
    MaterialIssueAllocation,
    MaterialReceipt,
)
from uk_management_bot.database.models.request import Request

logger = logging.getLogger(__name__)

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


def guard_executor_issue(db: Session, *, request_number: str,
                         telegram_id: int):
    """Guard списания исполнителем (ARCH-01: ORM вне хендлера).

    Returns:
        (request, user, err_key): err_key — ключ локали при отказе, иначе None.
        Проверки: заявка существует; статус «В работе»; актор — назначенный
        исполнитель заявки.
    """
    from uk_management_bot.database.models.user import User
    from uk_management_bot.utils.constants import REQUEST_STATUS_IN_PROGRESS

    request = (db.query(Request)
               .filter(Request.request_number == request_number).first())
    if request is None:
        return None, None, "errors.request_not_found"
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user is None:
        return request, None, "common.user_not_found"
    if request.status != REQUEST_STATUS_IN_PROGRESS:
        return request, user, "materials.issue.wrong_status"
    if request.executor_id != user.id:
        return request, user, "materials.issue.not_executor"
    return request, user, None


def issue_material_with_comment(db: Session, *, material_id: int, qty,
                                created_by: int, request_number: str,
                                comment_text: str) -> MaterialIssue:
    """Бот-путь: списание + RequestComment(type='material') + commit —
    ОДНА транзакция (упало что-то одно → откатилось всё).

    Отдельная обёртка поверх чистого ``issue_material_sync`` (тот комментариев
    не пишет и не коммитит — его использует и API-паритет тестов).
    """
    from uk_management_bot.database.models.request_comment import RequestComment

    try:
        issue = issue_material_sync(
            db, material_id=material_id, qty=qty, created_by=created_by,
            doc_type="request", request_number=request_number,
        )
        db.add(RequestComment(
            request_number=request_number,
            user_id=created_by,
            comment_text=comment_text,
            comment_type="material",
        ))
        db.commit()
        return issue
    except Exception:
        db.rollback()
        raise


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


async def create_material(db: AsyncSession, *, name: str, unit: str,
                          category: Optional[str] = None,
                          min_stock=None) -> Material:
    """Создать карточку материала. name UNIQUE навсегда (409 при дубле)."""
    name = (name or "").strip()
    if not name:
        raise MaterialValidationError("название обязательно")
    validate_unit(unit)
    if min_stock is not None:
        min_stock = parse_qty(min_stock)
    existing = (
        await db.execute(select(Material).where(Material.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        raise MaterialConflictError(
            f"материал «{name}» уже существует (id={existing.id}"
            f"{', деактивирован — реактивируйте' if not existing.is_active else ''})"
        )
    material = Material(name=name, unit=unit, category=category, min_stock=min_stock)
    db.add(material)
    await db.flush()
    return material


async def update_material(db: AsyncSession, material_id: int, *,
                          name: Optional[str] = None,
                          category: Optional[str] = None,
                          min_stock=..., is_active: Optional[bool] = None,
                          unit: Optional[str] = None) -> Material:
    """PATCH карточки. unit менять запрещено при наличии движений.

    Переименование НЕ переписывает историю: журнал хранит snapshot material_name.
    """
    material = (
        await db.execute(select(Material).where(Material.id == material_id))
    ).scalar_one_or_none()
    if material is None:
        raise MaterialNotFoundError(f"материал {material_id} не найден")
    if unit is not None and unit != material.unit:
        validate_unit(unit)
        has_moves = (
            await db.execute(
                select(MaterialReceipt.id)
                .where(MaterialReceipt.material_id == material_id)
                .limit(1)
            )
        ).first() is not None
        if has_moves:
            raise MaterialConflictError(
                "единицу измерения нельзя менять: по материалу есть движения"
            )
        material.unit = unit
    if name is not None:
        name = name.strip()
        if not name:
            raise MaterialValidationError("название не может быть пустым")
        if name != material.name:
            dup = (
                await db.execute(
                    select(Material.id).where(
                        Material.name == name, Material.id != material_id
                    )
                )
            ).first()
            if dup is not None:
                raise MaterialConflictError(f"материал «{name}» уже существует")
            material.name = name
    if category is not None:
        material.category = category or None
    if min_stock is not ...:
        material.min_stock = parse_qty(min_stock) if min_stock is not None else None
    if is_active is not None:
        material.is_active = is_active
    await db.flush()
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
        query = query.where(Material.name.ilike(f"%{_escape_like(q)}%", escape="\\"))
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
    """Списания по заявке + суммарная себестоимость."""
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
    total = money(sum((Decimal(str(i.total_cost)) for i in rows), Decimal("0")))
    return {"request_number": request_number, "items": rows, "total_cost": total}


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


# ===========================================================================
# SQL-хелперы
# ===========================================================================

def _escape_like(value: str) -> str:
    """Экранировать спецсимволы LIKE (паттерн api/shifts/service.py)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def sa_literal(value: str):
    from sqlalchemy import literal
    return literal(value)


def sa_null_str():
    from sqlalchemy import cast, null, String
    return cast(null(), String)


def sa_false():
    from sqlalchemy import false
    return false()
