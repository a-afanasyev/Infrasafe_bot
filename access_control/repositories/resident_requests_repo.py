"""Read-модель заявок жителей на постоянный автомобиль (``resident_access_requests``).

Только чтение (реестр менеджера, §6.3). У таблицы нет ``zone_id`` (DATA_MODEL_PILOT).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.repositories.sql_filters import where_clause

_REQUEST_COLS = (
    "id, apartment_id, created_by_user_id, vehicle_id, "
    " plate_number_original, plate_number_normalized, relation_type, status, "
    " reviewed_by_user_id, reviewed_at, review_comment, created_at "
)


def page_requests(
    db: Session,
    *,
    status: str | None = None,
    apartment_id: int | None = None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict]]:
    """(total, страница) заявок; сортировка ``created_at`` desc, ``id`` desc."""
    conds: list[str] = []
    params: dict = {}
    if status is not None:
        conds.append("status = :status")
        params["status"] = status
    if apartment_id is not None:
        conds.append("apartment_id = :apt")
        params["apt"] = apartment_id
    where = where_clause(conds)

    total = db.execute(
        text(f"SELECT count(*) FROM resident_access_requests {where}"), params
    ).scalar_one()
    rows = db.execute(
        text(
            f"SELECT {_REQUEST_COLS} FROM resident_access_requests {where} "
            "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).mappings()
    return total, [dict(r) for r in rows]


def get_request(db: Session, request_id: int) -> dict | None:
    """Заявка по id либо ``None``."""
    row = db.execute(
        text(f"SELECT {_REQUEST_COLS} FROM resident_access_requests WHERE id = :id"),
        {"id": request_id},
    ).mappings().first()
    return dict(row) if row is not None else None
