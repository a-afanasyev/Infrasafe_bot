"""Роутер складского учёта материалов (/api/v2/materials).

RBAC: все эндпоинты (чтение и запись) — manager | system_admin со статусом
approved (``require_approved_roles``); исполнитель работает через бот
(sync-сервис), API ему не нужен.

Роутер тонкий: вся учётная логика в services/material_service.py, транзакции
и data-access — в api/materials/service.py (AUD5-ARCH-2 волна 2); здесь —
маппинг ошибок сервиса на HTTP-коды (Validation→422, NotFound→404,
Conflict/Insufficient→409).

Статичные пути (/stock, /operations, ...) объявлены ДО /{material_id}.
"""
import csv
import io
from datetime import datetime, time, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_approved_roles
from uk_management_bot.api.materials import service as api_service
from uk_management_bot.api.materials.schemas import (
    AdjustmentCreate,
    AdjustmentOut,
    IssueCard,
    IssueCreate,
    MaterialCard,
    MaterialCreate,
    MaterialUpdate,
    OperationsPage,
    ProcurementOut,
    ReceiptCard,
    ReceiptCreate,
    RequestMaterialsOut,
    StockRow,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.csv_escape import escape_csv_cell
from uk_management_bot.services import material_service
from uk_management_bot.services.material_service import (
    MaterialConflictError,
    MaterialNotFoundError,
    MaterialServiceError,
    MaterialValidationError,
)

router = APIRouter()

_manager_only = require_approved_roles("manager", "system_admin")

_EXPORT_LIMIT = 10_000


def _http_error(exc: MaterialServiceError) -> HTTPException:
    """Маппинг доменных ошибок сервиса на HTTP-коды."""
    if isinstance(exc, MaterialNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, MaterialConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, MaterialValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _date_bounds(date_from: Optional[str], date_to: Optional[str]):
    """YYYY-MM-DD → [начало дня; конец дня] UTC (включительно)."""
    def _parse(value: str, end: bool):
        try:
            day = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=422, detail=f"неверная дата: {value}")
        return datetime.combine(day, time.max if end else time.min, tzinfo=timezone.utc)

    return (
        _parse(date_from, end=False) if date_from else None,
        _parse(date_to, end=True) if date_to else None,
    )


# ── Номенклатура ────────────────────────────────────────────────────

@router.get("", response_model=list[MaterialCard])
async def list_materials(
    q: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    return await api_service.list_material_rows(
        db, q=q, is_active=is_active, limit=limit, offset=offset,
    )


@router.post("", response_model=MaterialCard, status_code=201)
async def create_material(
    body: MaterialCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    try:
        material = await api_service.create_material_tx(
            db, name=body.name, unit=body.unit,
            category=body.category, min_stock=body.min_stock,
        )
    except MaterialServiceError as exc:
        raise _http_error(exc)
    return material


# ── Остатки / журнал / отчёты (статичные пути — ДО /{material_id}) ──

@router.get("/stock", response_model=list[StockRow])
async def get_stock(
    q: Optional[str] = Query(None),
    only_low: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    return await material_service.get_stock(db, q=q, only_low=only_low)


@router.post("/receipts", response_model=ReceiptCard, status_code=201)
async def create_receipt(
    body: ReceiptCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    try:
        receipt = await api_service.create_receipt_tx(
            db, material_id=body.material_id, qty=body.qty,
            unit_price=body.unit_price, created_by=user.id,
            supplier=body.supplier, doc_number=body.doc_number,
            doc_date=body.doc_date, note=body.note,
        )
    except MaterialServiceError as exc:
        raise _http_error(exc)
    return receipt


@router.post("/issues", response_model=IssueCard, status_code=201)
async def create_issue(
    body: IssueCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    try:
        issue = await api_service.create_issue_tx(
            db, material_id=body.material_id, qty=body.qty,
            created_by=user.id, doc_type=body.doc_type,
            request_number=body.request_number, reason=body.reason,
        )
    except MaterialServiceError as exc:
        raise _http_error(exc)
    return issue


@router.post("/adjustments", response_model=AdjustmentOut, status_code=201)
async def create_adjustment(
    body: AdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    try:
        result = await api_service.adjust_tx(
            db, material_id=body.material_id, direction=body.direction,
            reason=body.reason, created_by=user.id,
            qty=body.qty, unit_price=body.unit_price,
            reversal_of_issue_id=body.reversal_of_issue_id,
            reversal_of_receipt_id=body.reversal_of_receipt_id,
        )
    except MaterialServiceError as exc:
        raise _http_error(exc)
    if isinstance(result, list):
        return AdjustmentOut(receipts=result)
    return AdjustmentOut(issue=result)


@router.get("/operations", response_model=OperationsPage)
async def list_operations(
    op_type: Optional[str] = Query(None, pattern="^(receipt|issue)$"),
    material_id: Optional[int] = Query(None),
    request_number: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    dt_from, dt_to = _date_bounds(date_from, date_to)
    return await material_service.list_operations(
        db, op_type=op_type, material_id=material_id,
        request_number=request_number, date_from=dt_from, date_to=dt_to,
        limit=limit, offset=offset,
    )


_OPS_CSV_HEADER = [
    "Тип", "ID", "Дата", "Материал", "Ед.", "Вид документа", "Кол-во",
    "Сумма", "Заявка", "Поставщик", "Причина/примечание",
]

_OP_TYPE_LABELS = {"receipt": "Приход", "issue": "Расход"}


@router.get("/operations/export")
async def export_operations(
    op_type: Optional[str] = Query(None, pattern="^(receipt|issue)$"),
    material_id: Optional[int] = Query(None),
    request_number: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    dt_from, dt_to = _date_bounds(date_from, date_to)
    page = await material_service.list_operations(
        db, op_type=op_type, material_id=material_id,
        request_number=request_number, date_from=dt_from, date_to=dt_to,
        limit=_EXPORT_LIMIT, offset=0,
    )
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(_OPS_CSV_HEADER)
    for op in page["items"]:
        # F-07: пользовательские строки экранируются от Excel formula injection.
        writer.writerow([
            _OP_TYPE_LABELS.get(op["op_type"], op["op_type"]),
            op["id"],
            op["created_at"].isoformat() if op["created_at"] else "",
            escape_csv_cell(op["material_name"]),
            escape_csv_cell(op["unit"]),
            escape_csv_cell(op["doc_type"]),
            op["qty"],
            op["amount"],
            escape_csv_cell(op["request_number"] or ""),
            escape_csv_cell(op["supplier"] or ""),
            escape_csv_cell(op["reason"] or ""),
        ])
    # utf-8-sig BOM — чтобы Excel открывал кириллицу без танцев
    payload = "\ufeff" + buf.getvalue()
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=material_operations.csv"},
    )


@router.get("/by-request/{request_number}", response_model=RequestMaterialsOut)
async def get_request_materials(
    request_number: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    return await material_service.get_request_materials(db, request_number)


@router.get("/procurement", response_model=ProcurementOut)
async def get_procurement(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    return await material_service.get_procurement(db)


_PROC_CSV_HEADER = ["Материал", "Ед.", "Остаток", "Мин. остаток", "Докупить"]


@router.get("/procurement/export")
async def export_procurement(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    data = await material_service.get_procurement(db)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(_PROC_CSV_HEADER)
    for row in data["deficit"]:
        # F-07: название/ед. — пользовательский ввод, экранируем от формул.
        writer.writerow([
            escape_csv_cell(row["name"]),
            escape_csv_cell(row["unit"]),
            row["stock"], row["min_stock"], row["to_buy"],
        ])
    payload = "\ufeff" + buf.getvalue()
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=material_procurement.csv"},
    )


# ── PATCH карточки (динамический путь — ПОСЛЕ статичных) ───────────

@router.patch("/{material_id}", response_model=MaterialCard)
async def update_material(
    material_id: int,
    body: MaterialUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    fields = body.model_dump(exclude_unset=True)
    try:
        material = await api_service.update_material_tx(
            db, material_id,
            name=fields.get("name"),
            unit=fields.get("unit"),
            category=fields.get("category"),
            min_stock=fields["min_stock"] if "min_stock" in fields else ...,
            is_active=fields.get("is_active"),
        )
    except MaterialServiceError as exc:
        raise _http_error(exc)
    return material
