"""Read-модель базы авто для реестра (§6.3): ``vehicles`` + связи и зоны правил.

Только чтение. Строки — ``dict`` (колонка марки отдаётся как в БД — ``make``;
переименование в ``brand`` — забота API-слоя).
"""
from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from access_control.repositories.sql_filters import plate_contains_pattern, where_clause

_VEHICLE_COLS = (
    "id, plate_number_original, plate_number_normalized, plate_country, plate_type, "
    "make, model, color, vehicle_class, status, blocked_reason, blocked_by_user_id, "
    "blocked_at"
)


def page_vehicles(
    db: Session,
    *,
    status: str | None = None,
    plate: str | None = None,
    apartment_id: int | None = None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict]]:
    """(total, страница) авто; сортировка ``created_at`` desc, ``id`` desc."""
    conds: list[str] = []
    params: dict = {}
    if status is not None:
        conds.append("v.status = :status")
        params["status"] = status
    if plate:
        conds.append("v.plate_number_normalized ILIKE :plate")
        params["plate"] = plate_contains_pattern(plate)
    if apartment_id is not None:
        conds.append(
            "EXISTS(SELECT 1 FROM vehicle_apartments va "
            "WHERE va.vehicle_id = v.id AND va.apartment_id = :apt)"
        )
        params["apt"] = apartment_id
    where = where_clause(conds)

    total = db.execute(
        text(f"SELECT count(*) FROM vehicles v {where}"), params
    ).scalar_one()
    rows = db.execute(
        text(
            f"SELECT {_VEHICLE_COLS} FROM vehicles v {where} "
            "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).mappings()
    return total, [dict(r) for r in rows]


def get_vehicle(db: Session, vehicle_id: int) -> dict | None:
    """Авто по id либо ``None``."""
    row = db.execute(
        text(f"SELECT {_VEHICLE_COLS} FROM vehicles v WHERE id = :id"),
        {"id": vehicle_id},
    ).mappings().first()
    return dict(row) if row is not None else None


def apartment_links(db: Session, vehicle_ids: list[int]) -> list[dict]:
    """Связи ``vehicle_apartments`` набора авто одним запросом (по id связи)."""
    if not vehicle_ids:
        return []
    rows = db.execute(
        text(
            "SELECT vehicle_id, apartment_id, relation_type, status, valid_from, "
            " valid_until, approved_by_user_id, approved_at "
            "FROM vehicle_apartments WHERE vehicle_id IN :vids ORDER BY id"
        ).bindparams(bindparam("vids", expanding=True)),
        {"vids": vehicle_ids},
    ).mappings()
    return [dict(r) for r in rows]


def rule_zones(db: Session, vehicle_id: int) -> list[dict]:
    """Зоны (id, code, name) активных vehicle-scoped правил доступа авто."""
    rows = db.execute(
        text(
            "SELECT DISTINCT z.id, z.code, z.name FROM access_rules ar "
            "JOIN parking_zones z ON z.id = ar.zone_id "
            "WHERE ar.vehicle_id = :vid AND ar.is_active = true ORDER BY z.id"
        ),
        {"vid": vehicle_id},
    ).mappings()
    return [dict(r) for r in rows]
