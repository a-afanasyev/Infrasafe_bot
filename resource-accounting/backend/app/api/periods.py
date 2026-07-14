"""Reporting periods, worksheet, readings input, corrections (ТЗ §5.4)."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import (
    ALL_ROLES,
    OPERATOR_ROLES,
    READING_ENTRY_ROLES,
    REVIEWER_ROLES,
    STAFF_ROLES,
    WORKSHEET_READ_ROLES,
    require_roles,
)
from app.core.deps import (
    correlation_id as _cid,
)
from app.core.errors import bad_request, conflict, not_found
from app.db import get_db
from app.models import AnomalyRule, Meter, Reading, ReportingPeriod, User
from app.schemas.readings import (
    AnomalyRuleIn,
    AnomalyRuleOut,
    BulkReadingsIn,
    CorrectionIn,
    PeriodCreate,
    PeriodOut,
    ReadingIn,
    ReadingOut,
    WorksheetOut,
    WorksheetRow,
)
from app.services.readings import apply_correction, get_previous_accepted, upsert_reading

router = APIRouter(tags=["periods"])

STATUS_FLOW = {
    "open": ("review",),
    "review": ("open", "submitted"),
    "submitted": ("closed",),
    "closed": (),
}


def get_period_or_404(db: Session, user: User, month: str) -> ReportingPeriod:
    row = db.execute(
        select(ReportingPeriod).where(
            ReportingPeriod.tenant_id == user.tenant_id, ReportingPeriod.month == month
        )
    ).scalar_one_or_none()
    if not row:
        raise not_found(f"Период {month}")
    return row


def _transition(db: Session, request: Request, user: User, month: str, target: str) -> ReportingPeriod:
    period = get_period_or_404(db, user, month)
    if target not in STATUS_FLOW[period.status]:
        raise conflict(f"Переход {period.status} → {target} недопустим")
    before = {"status": period.status}
    period.status = target
    write_audit(db, user=user, entity_type="period", entity_id=period.id, action=f"status_{target}",
                before=before, after={"status": target}, correlation_id=_cid(request))
    db.commit()
    return period


@router.get("/periods", response_model=dict)
def list_periods(db: Session = Depends(get_db), user: User = Depends(require_roles(*WORKSHEET_READ_ROLES))):
    rows = db.execute(
        select(ReportingPeriod)
        .where(ReportingPeriod.tenant_id == user.tenant_id)
        .order_by(ReportingPeriod.month.desc())
    ).scalars().all()
    return {"data": [PeriodOut.model_validate(r).model_dump(mode="json") for r in rows]}


@router.post("/periods", response_model=dict, status_code=201)
def create_period(
    payload: PeriodCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATOR_ROLES)),
):
    existing = db.execute(
        select(ReportingPeriod).where(
            ReportingPeriod.tenant_id == user.tenant_id, ReportingPeriod.month == payload.month
        )
    ).scalar_one_or_none()
    if existing:
        raise conflict(f"Период {payload.month} уже существует")
    period = ReportingPeriod(tenant_id=user.tenant_id, month=payload.month, status="open")
    db.add(period)
    db.flush()
    write_audit(db, user=user, entity_type="period", entity_id=period.id, action="create",
                after={"month": period.month}, correlation_id=_cid(request))
    db.commit()
    return {"data": PeriodOut.model_validate(period).model_dump(mode="json")}


@router.get("/periods/{month}/worksheet", response_model=dict)
def worksheet(
    month: str,
    resource_type: str | None = None,
    object_id: uuid.UUID | None = None,
    provider_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*WORKSHEET_READ_ROLES)),
):
    period = get_period_or_404(db, user, month)
    stmt = select(Meter).where(Meter.tenant_id == user.tenant_id, Meter.status == "active")
    if resource_type:
        stmt = stmt.where(Meter.resource_type == resource_type)
    if object_id:
        stmt = stmt.where(Meter.primary_object_id == object_id)
    if provider_id:
        stmt = stmt.where(Meter.provider_id == provider_id)
    meters = db.execute(stmt.order_by(Meter.meter_number_normalized)).scalars().all()

    readings = {
        r.meter_id: r
        for r in db.execute(
            select(Reading).where(Reading.reporting_period_id == period.id)
        ).scalars().all()
    }

    rows = []
    for meter in meters:
        prev = get_previous_accepted(db, meter.id, month)
        reading = readings.get(meter.id)
        rows.append(
            WorksheetRow(
                meter_id=meter.id,
                meter_number=meter.meter_number,
                meter_name=meter.name,
                resource_type=meter.resource_type,
                unit=meter.unit,
                description=meter.description,
                primary_object_id=meter.primary_object_id,
                primary_object_name=meter.primary_object.name if meter.primary_object else "",
                consumers=[
                    link.object.name + (f" — {link.description}" if link.description else "")
                    for link in meter.consumer_links
                    if link.object
                ],
                provider_name=meter.provider.name if meter.provider else None,
                coefficient=meter.coefficient,
                previous_value=prev.value if prev else None,
                previous_read_at=prev.read_at if prev else None,
                reading=ReadingOut.model_validate(reading) if reading else None,
            )
        )
    return {"data": WorksheetOut(period=PeriodOut.model_validate(period), rows=rows).model_dump(mode="json")}


@router.put("/meters/{meter_id}/readings/{month}", response_model=dict)
def put_reading(
    meter_id: uuid.UUID,
    month: str,
    payload: ReadingIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READING_ENTRY_ROLES)),
):
    period = get_period_or_404(db, user, month)
    meter = db.get(Meter, meter_id)
    if not meter or meter.tenant_id != user.tenant_id:
        raise not_found("Счётчик")
    reading = upsert_reading(db, meter, period, payload, user)
    write_audit(db, user=user, entity_type="reading", entity_id=reading.id, action="upsert",
                after={"meter": meter.meter_number, "month": month,
                       "value": str(reading.value) if reading.value is not None else None},
                correlation_id=_cid(request))
    db.commit()
    return {"data": ReadingOut.model_validate(reading).model_dump(mode="json")}


@router.post("/periods/{month}/readings/bulk", response_model=dict)
def bulk_readings(
    month: str,
    payload: BulkReadingsIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READING_ENTRY_ROLES)),
):
    """Transactional batch save: all valid selected rows or none (ТЗ §9)."""
    period = get_period_or_404(db, user, month)
    results = []
    for item in payload.items:
        meter = db.get(Meter, item.meter_id)
        if not meter or meter.tenant_id != user.tenant_id:
            db.rollback()
            raise not_found(f"Счётчик {item.meter_id}")
        reading = upsert_reading(db, meter, period, ReadingIn(**item.model_dump(exclude={"meter_id"})), user)
        results.append(reading)
    write_audit(db, user=user, entity_type="period", entity_id=period.id, action="bulk_readings",
                after={"month": month, "count": len(results)}, correlation_id=_cid(request))
    db.commit()
    return {"data": [ReadingOut.model_validate(r).model_dump(mode="json") for r in results]}


@router.post("/periods/{month}/validate", response_model=dict)
def validate_period(
    month: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*STAFF_ROLES)),
):
    """Summary of problems that block confirmation."""
    period = get_period_or_404(db, user, month)
    meters_count = db.execute(
        select(Meter.id).where(Meter.tenant_id == user.tenant_id, Meter.status == "active")
    ).scalars().all()
    readings = db.execute(
        select(Reading).where(Reading.reporting_period_id == period.id)
    ).scalars().all()
    by_status: dict[str, int] = {}
    warnings_without_comment = []
    errors = []
    for r in readings:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        if r.status == "warning" and not r.comment:
            warnings_without_comment.append(str(r.meter_id))
        if r.status == "error":
            errors.append({"meter_id": str(r.meter_id), "message": r.validation_message})
    missing_input = len(meters_count) - len(readings)
    return {
        "data": {
            "period": PeriodOut.model_validate(period).model_dump(mode="json"),
            "active_meters": len(meters_count),
            "entered": len(readings),
            "not_entered": missing_input,
            "by_status": by_status,
            "warnings_without_comment": warnings_without_comment,
            "errors": errors,
            "can_submit": not errors and not warnings_without_comment and missing_input == 0,
        }
    }


@router.post("/periods/{month}/move-to-review", response_model=dict)
def move_to_review(
    month: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATOR_ROLES)),
):
    period = _transition(db, request, user, month, "review")
    return {"data": PeriodOut.model_validate(period).model_dump(mode="json")}


@router.post("/periods/{month}/reopen", response_model=dict)
def reopen(
    month: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*REVIEWER_ROLES)),
):
    period = _transition(db, request, user, month, "open")
    return {"data": PeriodOut.model_validate(period).model_dump(mode="json")}


@router.post("/periods/{month}/submit", response_model=dict)
def submit(
    month: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*REVIEWER_ROLES)),
):
    """review → submitted: blocked while errors or uncommented warnings remain."""
    period = get_period_or_404(db, user, month)
    if period.status != "review":
        raise conflict(f"Подтвердить можно только период в статусе review (сейчас {period.status})")
    readings = db.execute(select(Reading).where(Reading.reporting_period_id == period.id)).scalars().all()
    problems = [r for r in readings if r.status == "error" or (r.status == "warning" and not r.comment)]
    if problems:
        raise conflict(
            "Есть ошибки или предупреждения без комментария",
            details=[{"meter_id": str(r.meter_id), "status": r.status, "message": r.validation_message}
                     for r in problems],
        )
    period = _transition(db, request, user, month, "submitted")
    return {"data": PeriodOut.model_validate(period).model_dump(mode="json")}


@router.post("/periods/{month}/close", response_model=dict)
def close_period(
    month: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*REVIEWER_ROLES)),
):
    period = _transition(db, request, user, month, "closed")
    return {"data": PeriodOut.model_validate(period).model_dump(mode="json")}


@router.post("/readings/{reading_id}/corrections", response_model=dict)
def create_correction(
    reading_id: uuid.UUID,
    payload: CorrectionIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*REVIEWER_ROLES)),
):
    reading = db.get(Reading, reading_id)
    if not reading or reading.tenant_id != user.tenant_id:
        raise not_found("Показание")
    if reading.period.status in ("open", "review"):
        raise bad_request("Период ещё редактируется: измените показание напрямую")
    old_value = reading.value  # COR-04: capture the true previous value before it is overwritten
    apply_correction(db, reading, payload.new_value, payload.reason, payload.kind, user)
    write_audit(db, user=user, entity_type="reading", entity_id=reading.id, action="correction",
                before={"value": str(old_value) if old_value is not None else None},
                after={"value": str(reading.value), "reason": payload.reason},
                correlation_id=_cid(request))
    db.commit()
    return {"data": ReadingOut.model_validate(reading).model_dump(mode="json")}


# --- Anomaly rules (admin) ---
@router.get("/anomaly-rules", response_model=dict)
def list_anomaly_rules(db: Session = Depends(get_db), user: User = Depends(require_roles(*ALL_ROLES))):
    rows = db.execute(select(AnomalyRule).where(AnomalyRule.tenant_id == user.tenant_id)).scalars().all()
    return {"data": [AnomalyRuleOut.model_validate(r).model_dump(mode="json") for r in rows]}


@router.put("/anomaly-rules", response_model=dict)
def upsert_anomaly_rule(
    payload: AnomalyRuleIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("resource_admin")),
):
    row = db.execute(
        select(AnomalyRule).where(
            AnomalyRule.tenant_id == user.tenant_id, AnomalyRule.resource_type == payload.resource_type
        )
    ).scalar_one_or_none()
    if row is None:
        row = AnomalyRule(tenant_id=user.tenant_id, resource_type=payload.resource_type)
        db.add(row)
    row.abs_threshold = payload.abs_threshold
    row.pct_change_threshold = payload.pct_change_threshold
    row.avg_window_months = payload.avg_window_months
    row.avg_deviation_pct = payload.avg_deviation_pct
    db.flush()
    write_audit(db, user=user, entity_type="anomaly_rule", entity_id=row.id, action="upsert",
                after=payload.model_dump(mode="json"), correlation_id=_cid(request))
    db.commit()
    return {"data": AnomalyRuleOut.model_validate(row).model_dump(mode="json")}
