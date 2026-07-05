"""Pydantic-схемы модуля складского учёта материалов (/api/v2/materials).

Числа — Decimal (деньги 0.01, количество 0.001); глубокие валидации
(шаг, положительность, инварианты сторно) выполняет сервис
services/material_service.py — схемы держат только форму запроса.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel


# ── Номенклатура ────────────────────────────────────────────────────

class MaterialCreate(BaseModel):
    name: str
    unit: str
    category: Optional[str] = None
    min_stock: Optional[Decimal] = None


class MaterialUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    min_stock: Optional[Decimal] = None
    is_active: Optional[bool] = None


class MaterialCard(BaseModel):
    id: int
    name: str
    unit: str
    category: Optional[str] = None
    min_stock: Optional[Decimal] = None
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Операции ────────────────────────────────────────────────────────

class ReceiptCreate(BaseModel):
    material_id: int
    qty: Decimal
    unit_price: Decimal
    supplier: Optional[str] = None
    doc_number: Optional[str] = None
    doc_date: Optional[date] = None
    note: Optional[str] = None


class IssueCreate(BaseModel):
    material_id: int
    qty: Decimal
    # doc_type явный, не выводится по наличию полей (решение владельца);
    # 'shortage' через этот эндпоинт недоступен — только adjustments
    doc_type: Literal["request", "household"]
    request_number: Optional[str] = None
    reason: Optional[str] = None


class AdjustmentCreate(BaseModel):
    """Два взаимоисключающих режима: инвентаризация (qty обязателен) или
    сторно (qty запрещён — объём берётся из исходной операции)."""

    material_id: int
    direction: Literal["surplus", "shortage"]
    reason: str
    qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    reversal_of_issue_id: Optional[int] = None
    reversal_of_receipt_id: Optional[int] = None


class ReceiptCard(BaseModel):
    id: int
    material_id: int
    doc_type: str
    qty: Decimal
    qty_remaining: Decimal
    unit_price: Decimal
    total_amount: Decimal
    supplier: Optional[str] = None
    doc_number: Optional[str] = None
    doc_date: Optional[date] = None
    note: Optional[str] = None
    reversal_of_issue_id: Optional[int] = None
    material_name: str
    unit: str
    created_by: int
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class IssueCard(BaseModel):
    id: int
    material_id: int
    doc_type: str
    qty: Decimal
    total_cost: Decimal
    request_number: Optional[str] = None
    reason: Optional[str] = None
    reversal_of_receipt_id: Optional[int] = None
    material_name: str
    unit: str
    created_by: int
    created_at: Optional[datetime] = None
    # Заполняется только отчётом by-request: расход полностью сторнирован
    # (не входит в total_cost отчёта)
    is_reversed: bool = False

    model_config = {"from_attributes": True}


class AdjustmentOut(BaseModel):
    """Результат корректировки: созданные операции (сторно расхода может
    создать несколько партий — по одной на каждую цену исходных аллокаций)."""

    receipts: List[ReceiptCard] = []
    issue: Optional[IssueCard] = None


# ── Чтение: остатки, журнал, отчёты ─────────────────────────────────

class StockRow(BaseModel):
    material_id: int
    name: str
    unit: str
    category: Optional[str] = None
    min_stock: Optional[Decimal] = None
    stock: Decimal
    stock_value: Decimal
    low_stock: bool


class OperationRow(BaseModel):
    op_type: Literal["receipt", "issue"]
    id: int
    material_id: int
    material_name: str
    unit: str
    doc_type: str
    qty: Decimal
    amount: Decimal
    request_number: Optional[str] = None
    supplier: Optional[str] = None
    reason: Optional[str] = None
    created_by: int
    created_at: Optional[datetime] = None


class OperationsPage(BaseModel):
    total: int
    items: List[OperationRow]


class RequestMaterialsOut(BaseModel):
    request_number: str
    items: List[IssueCard]
    total_cost: Decimal


class ProcurementRow(BaseModel):
    material_id: int
    name: str
    unit: str
    stock: Decimal
    min_stock: Decimal
    to_buy: Decimal


class OpenPurchaseRequest(BaseModel):
    request_number: str
    requested_materials: Optional[str] = None
    executor_name: Optional[str] = None


class ProcurementOut(BaseModel):
    deficit: List[ProcurementRow]
    open_purchase_requests: List[OpenPurchaseRequest]
