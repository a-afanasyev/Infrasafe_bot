"""CSV-выгрузки аналитики: принятые заявки и сводка по исполнителям.

Формат — как у склада (`api/materials/router.py`): `;`, BOM для Excel,
`escape_csv_cell` на каждой строке, пришедшей от людей (отчёт, отзыв,
причина, адрес, имя). Заголовки — на русском.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.utils.business_time import fmt_datetime
from uk_management_bot.utils.categories import (
    get_category_display,
    get_urgency_display,
    resolve_category_key,
)
from uk_management_bot.utils.csv_escape import escape_csv_cell

from .executors import (
    RETURNED_BY_BOTH,
    RETURNED_BY_MANAGER,
    RETURNED_BY_RESIDENT,
    AcceptedRequest,
    ExecutorSummary,
    load_accepted,
)

#: Как у склада: больше — уже не выгрузка из дашборда.
EXPORT_LIMIT = 10_000
#: Отчёт исполнителя в ячейке обрезается — полный текст в карточке заявки.
REPORT_MAX_CHARS = 500
#: Карточка заявки в дашборде (SPA под /uk; FRONTEND_URL — bare origin).
DASHBOARD_REQUEST_PATH = "/uk/dashboard?request="

NO_EXECUTOR = "Без исполнителя"

SOURCE_LABELS = {
    "bot": "Бот",
    "twa": "Mini App",
    "group": "Группа",
    "call_center": "Колл-центр",
    "web": "Дашборд",
    "api": "Дашборд",
    "infrasafe": "InfraSafe",
    "inspector": "Обходчик",
    "dispatcher": "Диспетчер",
}
_RETURNED_BY_LABELS = {
    RETURNED_BY_RESIDENT: "Житель",
    RETURNED_BY_MANAGER: "Менеджер",
    RETURNED_BY_BOTH: "Житель и менеджер",
}

COMPLETED_HEADER = [
    "Номер", "Исполнитель", "Категория", "Адрес", "Срочность", "Источник",
    "Создана", "Назначена", "Выполнена", "Принята",
    "Часы работы", "Часы до приёмки", "Норматив, ч", "Просрочена",
    "Оценка", "Отзыв", "Отчёт исполнителя", "Фото работ",
    "Возвращали", "Кто вернул", "Причина возврата", "Материалы, сум", "Ссылка",
]

EXECUTORS_HEADER = [
    "Исполнитель", "Выполнено", "Принято", "С возвратом", "С просрочкой",
    "Среднее время работы, ч", "Среднее до приёмки, ч", "Средняя оценка",
    "Оценок", "В работе сейчас", "Материалы, сум",
]


def source_label(source: Optional[str]) -> str:
    return SOURCE_LABELS.get(source or "", source or "")


def _dt(value: Optional[datetime]) -> str:
    return fmt_datetime(value) if value is not None else ""


def _num(value) -> str:
    """Число для Excel с русской локалью — запятая, «—» для пропуска."""
    if value is None:
        return "—"
    return str(value).replace(".", ",")


def _yes_no(value: Optional[bool]) -> str:
    if value is None:
        return "—"
    return "да" if value else "нет"


def _text(value: Optional[str], limit: Optional[int] = None) -> str:
    text = (value or "").strip()
    if limit is not None and len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return escape_csv_cell(text)


def _request_link(number: str) -> str:
    origin = (settings.FRONTEND_URL or "").rstrip("/")
    return f"{origin}{DASHBOARD_REQUEST_PATH}{number}" if origin else ""


def _render(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(header)
    writer.writerows(rows)
    # utf-8-sig BOM — чтобы Excel открывал кириллицу без танцев
    return "\ufeff" + buf.getvalue()


def completed_row(row: AcceptedRequest, sla_hours: dict, cost: Optional[Decimal]) -> list:
    reasons = {
        RETURNED_BY_RESIDENT: [row.return_reason],
        RETURNED_BY_MANAGER: [row.manager_return_reason],
        RETURNED_BY_BOTH: [row.return_reason, row.manager_return_reason],
    }.get(row.returned_by or "", [])
    reason = " / ".join(r.strip() for r in reasons if r and r.strip())
    return [
        escape_csv_cell(row.request_number),
        _text(row.executor_name or NO_EXECUTOR),
        _text(get_category_display(resolve_category_key(row.category), "ru")),
        _text(row.address),
        _text(get_urgency_display(row.urgency, "ru")),
        _text(source_label(row.source)),
        _dt(row.created_at), _dt(row.assigned_at), _dt(row.executed_at), _dt(row.completed_at),
        _num(row.work_hours), _num(row.to_accept_hours),
        _num(row.sla_limit(sla_hours)), _yes_no(row.is_overdue(sla_hours)),
        _num(row.rating), _text(row.review),
        _text(row.completion_report, REPORT_MAX_CHARS),
        _yes_no(row.has_photos),
        _yes_no(row.returned_by is not None),
        _RETURNED_BY_LABELS.get(row.returned_by or "", ""),
        _text(reason),
        _num(cost),
        _request_link(row.request_number),
    ]


def completed_csv(rows: list[AcceptedRequest], sla_hours: dict, costs: dict[str, Decimal]) -> str:
    return _render(COMPLETED_HEADER, [
        completed_row(r, sla_hours, costs.get(r.request_number)) for r in rows
    ])


def executors_csv(summaries: list[ExecutorSummary]) -> str:
    return _render(EXECUTORS_HEADER, [
        [
            _text(s.name or NO_EXECUTOR), s.executed, s.accepted, s.returned, s.overdue,
            _num(s.avg_work_hours), _num(s.avg_to_accept_hours), _num(s.avg_rating),
            s.ratings_count, s.in_work_now, _num(s.materials_cost),
        ]
        for s in summaries
    ])


async def build_completed_csv(
    db: AsyncSession, first: date, last: date, sla_hours: dict,
    executor_id: Optional[int] = None,
) -> tuple[str, int]:
    """(CSV, число строк) принятых заявок периода — для API и автоотчёта бота."""
    from uk_management_bot.services.material_service import get_requests_material_costs

    rows = await load_accepted(db, first, last, executor_id=executor_id, limit=EXPORT_LIMIT)
    costs = await get_requests_material_costs(db, [r.request_number for r in rows])
    return completed_csv(rows, sla_hours, costs), len(rows)


def export_filename(prefix: str, first: date, last: date, suffix: str = "") -> str:
    tail = f"_{suffix}" if suffix else ""
    return f"{prefix}_{first.isoformat()}_{last.isoformat()}{tail}.csv"
