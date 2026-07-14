"""Reconciliation act generation: immutable row snapshots + XLSX/CSV/PDF renderers (ТЗ §5.7)."""

import csv
import hashlib
import io
import json
import uuid

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import Export, ExportRow, Meter, Reading, ReportingPeriod
from app.services.readings import get_previous_accepted

BASE_COLUMNS = [
    ("period", "Период"),
    ("provider", "Поставщик"),
    ("provider_account", "Лицевой счёт"),
    ("primary_object", "Основной объект"),
    ("meter_number", "Номер счётчика"),
    ("meter_name", "Наименование счётчика"),
    ("description", "Описание и потребители"),
    ("unit", "Единица измерения"),
    ("previous_value", "Предыдущее показание"),
    ("previous_read_at", "Дата предыдущего показания"),
    ("current_value", "Текущее показание"),
    ("current_read_at", "Дата текущего показания"),
    ("coefficient", "Коэффициент"),
    ("consumption", "Расход"),
    ("note", "Примечание"),
]


def build_rows(db: Session, tenant_id, period: ReportingPeriod, filters: dict) -> list[dict]:
    """One row per meter (never per object)."""
    stmt = (
        select(Reading, Meter)
        .join(Meter, Reading.meter_id == Meter.id)
        .where(Reading.reporting_period_id == period.id, Meter.tenant_id == tenant_id)
        .order_by(Meter.meter_number_normalized)
    )
    if filters.get("provider_id"):
        stmt = stmt.where(Meter.provider_id == uuid.UUID(filters["provider_id"]))
    if filters.get("resource_type"):
        stmt = stmt.where(Meter.resource_type == filters["resource_type"])
    if filters.get("object_id"):
        stmt = stmt.where(Meter.primary_object_id == uuid.UUID(filters["object_id"]))

    rows = []
    for reading, meter in db.execute(stmt).all():
        prev = get_previous_accepted(db, meter.id, period.month)
        consumers = ", ".join(
            link.object.name for link in meter.consumer_links if link.object
        )
        description = meter.description + (f" | Потребители: {consumers}" if consumers else "")
        rows.append(
            {
                "period": period.month,
                "provider": meter.provider.name if meter.provider else "",
                "provider_account": meter.provider_account or "",
                "primary_object": meter.primary_object.name if meter.primary_object else "",
                "meter_number": meter.meter_number,
                "meter_name": meter.name,
                "description": description,
                "unit": meter.unit,
                "previous_value": str(prev.value) if prev and prev.value is not None else "",
                "previous_read_at": prev.read_at.isoformat() if prev and prev.read_at else "",
                "current_value": str(reading.value) if reading.value is not None else "",
                "current_read_at": reading.read_at.isoformat() if reading.read_at else "",
                "coefficient": str(meter.coefficient),
                "consumption": str(reading.consumption) if reading.consumption is not None else "",
                "note": reading.comment or "",
            }
        )
    return rows


def checksum_rows(rows: list[dict]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def snapshot_rows(db: Session, export: Export, rows: list[dict]) -> None:
    for index, data in enumerate(rows):
        db.add(ExportRow(export_id=export.id, row_index=index, data=data))


def render_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([label for _, label in BASE_COLUMNS])
    for row in rows:
        writer.writerow([row.get(key, "") for key, _ in BASE_COLUMNS])
    return buf.getvalue().encode("utf-8-sig")


def render_xlsx(rows: list[dict], title: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append([label for _, label in BASE_COLUMNS])
    for row in rows:
        ws.append([row.get(key, "") for key, _ in BASE_COLUMNS])
    for column_cells in ws.columns:
        width = max(len(str(c.value or "")) for c in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = min(max(width + 2, 10), 50)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_CYRILLIC_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # docker image (fonts-dejavu)
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",  # macOS
    "/Library/Fonts/Arial Unicode.ttf",
)


def _register_cyrillic_font() -> str:
    import os

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "ActPdf" in pdfmetrics.getRegisteredFontNames():
        return "ActPdf"
    for path in _CYRILLIC_FONT_CANDIDATES:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont("ActPdf", path))
            return "ActPdf"
    # COR-07: fail loud — Helvetica silently drops Cyrillic glyphs (all headers are
    # Russian), producing a blank/broken act. Better a clear error than a bad PDF.
    raise ApiError(
        500,
        "pdf_font_missing",
        "На сервере нет шрифта с кириллицей для PDF; используйте XLSX/CSV или установите DejaVu Sans",
    )


def render_pdf(rows: list[dict], title: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font = _register_cyrillic_font()

    pdf_columns = [
        ("meter_number", "Номер"),
        ("meter_name", "Счётчик"),
        ("primary_object", "Объект"),
        ("unit", "Ед."),
        ("previous_value", "Пред."),
        ("current_value", "Тек."),
        ("coefficient", "Коэф."),
        ("consumption", "Расход"),
    ]
    table_data = [[label for _, label in pdf_columns]]
    for row in rows:
        table_data.append([str(row.get(key, "")) for key, _ in pdf_columns])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=15 * mm, bottomMargin=15 * mm)
    style = ParagraphStyle("title", fontName=font, fontSize=14)
    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ]
        )
    )
    doc.build([Paragraph(title, style), Spacer(1, 8 * mm), table])
    return buf.getvalue()


def render(rows: list[dict], fmt: str, title: str) -> tuple[bytes, str]:
    if fmt == "csv":
        return render_csv(rows), "text/csv; charset=utf-8"
    if fmt == "xlsx":
        return (
            render_xlsx(rows, title),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    if fmt == "pdf":
        return render_pdf(rows, title), "application/pdf"
    raise ValueError(f"Неизвестный формат {fmt}")
