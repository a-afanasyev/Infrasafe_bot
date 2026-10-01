"""Доступ к ``access_passes``: атомарный расход въезда временного пропуска (§10.3)
и read-модель пропусков для реестра (§6.2)."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.domain.enums import PassStatus
from access_control.repositories.sql_filters import where_clause

_PASS_COLS = (
    "id, pass_type, apartment_id, created_by_user_id, zone_id, "
    " plate_number_original, plate_number_normalized, valid_from, valid_until, "
    " max_entries, used_entries, status, source, created_at "
)


def consume_taxi_entry(db: Session, pass_id: int) -> bool:
    """Атомарно израсходовать один въезд taxi-pass (§10.3).

    ``UPDATE ... SET used_entries = used_entries + 1 WHERE id = :p AND
    used_entries < max_entries``. Возвращает True при успехе (выделена ёмкость),
    False — если лимит уже исчерпан. При достижении max — статус 'used'.
    """
    updated = db.execute(
        text(
            "UPDATE access_passes "
            "SET used_entries = used_entries + 1, "
            "    status = CASE WHEN used_entries + 1 >= max_entries "
            "                  THEN :used ELSE status END "
            "WHERE id = :p AND used_entries < max_entries"
        ),
        {"p": pass_id, "used": PassStatus.USED.value},
    )
    return updated.rowcount == 1


def page_passes(
    db: Session,
    *,
    pass_type: str | None = None,
    status: str | None = None,
    apartment_id: int | None = None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict]]:
    """(total, страница) пропусков; сортировка ``created_at`` desc, ``id`` desc."""
    conds: list[str] = []
    params: dict = {}
    if pass_type is not None:
        conds.append("pass_type = :pass_type")
        params["pass_type"] = pass_type
    if status is not None:
        conds.append("status = :status")
        params["status"] = status
    if apartment_id is not None:
        conds.append("apartment_id = :apt")
        params["apt"] = apartment_id
    where = where_clause(conds)

    total = db.execute(
        text(f"SELECT count(*) FROM access_passes {where}"), params
    ).scalar_one()
    rows = db.execute(
        text(
            f"SELECT {_PASS_COLS} FROM access_passes {where} "
            "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).mappings()
    return total, [dict(r) for r in rows]


def get_pass(db: Session, pass_id: int) -> dict | None:
    """Пропуск по id либо ``None``."""
    row = db.execute(
        text(f"SELECT {_PASS_COLS} FROM access_passes WHERE id = :id"),
        {"id": pass_id},
    ).mappings().first()
    return dict(row) if row is not None else None
