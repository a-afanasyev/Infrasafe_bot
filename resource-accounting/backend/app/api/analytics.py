"""Time series and aggregates; shared meters counted only via primary object (ТЗ §5.6)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import ALL_ROLES, require_roles
from app.core.errors import bad_request, not_found
from app.db import get_db
from app.models import Meter, MeterTag, Reading, ReportingPeriod, ResourceObject, User

router = APIRouter(prefix="/analytics", tags=["analytics"])

RANGE_MONTHS = {"6m": 6, "12m": 12, "24m": 24, "all": None}


@router.get("/meters/{meter_id}", response_model=dict)
def meter_series(
    meter_id: uuid.UUID,
    range: str = Query(default="12m"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ALL_ROLES)),
):
    meter = db.get(Meter, meter_id)
    if not meter or meter.tenant_id != user.tenant_id:
        raise not_found("Счётчик")
    if range not in RANGE_MONTHS:
        raise bad_request(f"range должен быть одним из {list(RANGE_MONTHS)}")

    stmt = (
        select(Reading, ReportingPeriod.month)
        .join(ReportingPeriod, Reading.reporting_period_id == ReportingPeriod.id)
        .where(Reading.meter_id == meter.id)
        .order_by(ReportingPeriod.month)
    )
    rows = db.execute(stmt).all()
    limit = RANGE_MONTHS[range]
    if limit:
        rows = rows[-limit:]

    points = []
    for reading, month in rows:
        points.append(
            {
                "month": month,
                "reading": str(reading.value) if reading.value is not None else None,
                "consumption": str(reading.consumption) if reading.consumption is not None else None,
                "status": reading.status,
                "kind": reading.kind,
                "missing": reading.value is None,
            }
        )

    consumptions = [float(p["consumption"]) for p in points if p["consumption"] is not None]

    def avg_last(n: int) -> float | None:
        chunk = consumptions[-n:]
        return round(sum(chunk) / len(chunk), 4) if chunk else None

    change_abs = change_pct = None
    if len(consumptions) >= 2:
        change_abs = round(consumptions[-1] - consumptions[-2], 4)
        if consumptions[-2]:
            change_pct = round(change_abs / consumptions[-2] * 100, 1)

    yoy = None
    if len(points) >= 13 and points[-13]["consumption"] is not None and points[-1]["consumption"] is not None:
        prev_year = float(points[-13]["consumption"])
        current = float(points[-1]["consumption"])
        yoy = {
            "previous_year": prev_year,
            "current": current,
            "change_pct": round((current - prev_year) / prev_year * 100, 1) if prev_year else None,
        }

    return {
        "data": {
            "meter_id": str(meter.id),
            "meter_number": meter.meter_number,
            "unit": meter.unit,
            "points": points,
            "stats": {
                "avg_3m": avg_last(3),
                "avg_6m": avg_last(6),
                "avg_12m": avg_last(12),
                "change_abs": change_abs,
                "change_pct": change_pct,
                "year_over_year": yoy,
            },
        }
    }


@router.get("/meters-sparklines", response_model=dict)
def meters_sparklines(
    months: int = Query(default=6, ge=1, le=24),
    resource_type: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ALL_ROLES)),
):
    """Последние N точек расхода по каждому счётчику одним запросом (для мини-графика
    в таблице). Строки без расхода (база/пропуск) исключаются, поэтому январь-база
    в серию не попадает."""
    stmt = (
        select(Reading.meter_id, ReportingPeriod.month, Reading.consumption)
        .join(ReportingPeriod, Reading.reporting_period_id == ReportingPeriod.id)
        .join(Meter, Reading.meter_id == Meter.id)
        .where(
            ReportingPeriod.tenant_id == user.tenant_id,
            Reading.consumption.is_not(None),
        )
        .order_by(ReportingPeriod.month)
    )
    if resource_type:
        stmt = stmt.where(Meter.resource_type == resource_type)

    by_meter: dict[str, list[dict]] = {}
    for meter_id, month, consumption in db.execute(stmt).all():
        by_meter.setdefault(str(meter_id), []).append(
            {"month": month, "consumption": float(consumption)}
        )
    series = {mid: pts[-months:] for mid, pts in by_meter.items()}
    return {"data": {"months": months, "series": series}}


@router.get("/summary", response_model=dict)
def summary(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    group_by: str = Query(default="primary_object"),
    resource_type: str | None = None,
    provider_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ALL_ROLES)),
):
    if group_by not in ("primary_object", "provider", "resource_type", "month"):
        raise bad_request("group_by: primary_object | provider | resource_type | month")

    stmt = (
        select(
            ReportingPeriod.month,
            Meter.primary_object_id,
            Meter.provider_id,
            Meter.resource_type,
            func.sum(Reading.consumption).label("consumption"),
            func.count(Reading.id).label("readings"),
        )
        .join(Reading, Reading.reporting_period_id == ReportingPeriod.id)
        .join(Meter, Reading.meter_id == Meter.id)
        .where(
            ReportingPeriod.tenant_id == user.tenant_id,
            Reading.consumption.is_not(None),
        )
        .group_by(ReportingPeriod.month, Meter.primary_object_id, Meter.provider_id, Meter.resource_type)
    )
    if date_from:
        stmt = stmt.where(ReportingPeriod.month >= date_from)
    if date_to:
        stmt = stmt.where(ReportingPeriod.month <= date_to)
    if resource_type:
        stmt = stmt.where(Meter.resource_type == resource_type)
    if provider_id:
        stmt = stmt.where(Meter.provider_id == provider_id)
    if tag_id:
        stmt = stmt.where(Meter.id.in_(select(MeterTag.meter_id).where(MeterTag.tag_id == tag_id)))

    rows = db.execute(stmt).all()

    object_names = {
        str(oid): name
        for oid, name in db.execute(
            select(ResourceObject.id, ResourceObject.name).where(ResourceObject.tenant_id == user.tenant_id)
        ).all()
    }

    groups: dict[str, dict] = {}
    for month, object_id, prov_id, res_type, consumption, readings in rows:
        if group_by == "primary_object":
            key, label = str(object_id), object_names.get(str(object_id), "?")
        elif group_by == "provider":
            key, label = str(prov_id) if prov_id else "none", str(prov_id) if prov_id else "Без поставщика"
        elif group_by == "resource_type":
            key, label = res_type, res_type
        else:
            key, label = month, month
        bucket = groups.setdefault(key, {"key": key, "label": label, "consumption": 0.0, "readings": 0, "months": {}})
        bucket["consumption"] = round(bucket["consumption"] + float(consumption), 4)
        bucket["readings"] += readings
        bucket["months"][month] = round(bucket["months"].get(month, 0.0) + float(consumption), 4)

    return {"data": {"group_by": group_by, "groups": sorted(groups.values(), key=lambda g: g["label"])}}
