"""Consumption calculation and reading validation (ТЗ §5.4)."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict
from app.models import AnomalyRule, Meter, Reading, ReadingRevision, ReportingPeriod
from app.models.base import utcnow
from app.schemas.readings import ReadingIn

EDITABLE_PERIOD_STATUSES = ("open", "review")


def period_month_bounds(month: str) -> tuple[date, date]:
    year, mon = int(month[:4]), int(month[5:7])
    first = date(year, mon, 1)
    last = (date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)) - timedelta(days=1)
    return first, last


def get_previous_accepted(db: Session, meter_id: uuid.UUID, month: str) -> Reading | None:
    """Latest ACCEPTED reading in an earlier period ('YYYY-MM' sorts lexicographically).

    COR-02: only ok/warning readings count as a baseline — a reading that failed
    validation (status='error') keeps its raw value on the row but must never
    become the base for the next month's consumption.
    """
    stmt = (
        select(Reading)
        .join(ReportingPeriod, Reading.reporting_period_id == ReportingPeriod.id)
        .where(
            Reading.meter_id == meter_id,
            Reading.value.is_not(None),
            Reading.status.in_(("ok", "warning")),
            ReportingPeriod.month < month,
        )
        .order_by(ReportingPeriod.month.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def compute_consumption(
    previous: Decimal | None, current: Decimal, coefficient: Decimal, kind: str, max_digits: int | None
) -> Decimal:
    if previous is None or kind == "replacement":
        # First reading of a meter (or a fresh device): no prior baseline, consumption = current value
        return (current * coefficient).quantize(Decimal("0.0001"))
    if kind == "rollover":
        if not max_digits:
            raise bad_request("Для rollover требуется заданная разрядность счётчика")
        capacity = Decimal(10) ** max_digits
        return ((capacity - previous + current) * coefficient).quantize(Decimal("0.0001"))
    return ((current - previous) * coefficient).quantize(Decimal("0.0001"))


def get_recent_consumptions(db: Session, meter_id: uuid.UUID, month: str, window: int) -> list[Decimal]:
    stmt = (
        select(Reading.consumption)
        .join(ReportingPeriod, Reading.reporting_period_id == ReportingPeriod.id)
        .where(
            Reading.meter_id == meter_id,
            Reading.consumption.is_not(None),
            ReportingPeriod.month < month,
        )
        .order_by(ReportingPeriod.month.desc())
        .limit(window)
    )
    return [row[0] for row in db.execute(stmt).all()]


def check_anomaly(
    db: Session, meter: Meter, month: str, consumption: Decimal
) -> str | None:
    """Return a warning message if consumption violates configured thresholds."""
    rule = db.execute(
        select(AnomalyRule).where(
            AnomalyRule.tenant_id == meter.tenant_id, AnomalyRule.resource_type == meter.resource_type
        )
    ).scalar_one_or_none()
    if not rule:
        return None
    if rule.abs_threshold is not None and consumption > rule.abs_threshold:
        return f"Расход {consumption} превышает абсолютный порог {rule.abs_threshold}"
    history = get_recent_consumptions(db, meter.id, month, rule.avg_window_months)
    if history:
        last = history[0]
        if rule.pct_change_threshold is not None and last > 0:
            change_pct = abs(consumption - last) / last * 100
            if change_pct > rule.pct_change_threshold:
                return f"Изменение к прошлому месяцу {change_pct:.0f}% превышает порог {rule.pct_change_threshold}%"
        avg = sum(history) / len(history)
        if rule.avg_deviation_pct is not None and avg > 0:
            deviation_pct = abs(consumption - avg) / avg * 100
            if deviation_pct > rule.avg_deviation_pct:
                return (
                    f"Отклонение от среднего за {len(history)} мес. {deviation_pct:.0f}% "
                    f"превышает порог {rule.avg_deviation_pct}%"
                )
    return None


def evaluate_value(
    db: Session,
    meter: Meter,
    month: str,
    previous_value: Decimal | None,
    value: Decimal,
    read_at: date | None,
    kind: str,
) -> tuple[Decimal | None, str, str | None]:
    """Single source of truth for reading validation (ТЗ §5.4).

    Returns (consumption, status, validation_message). Shared by direct input,
    corrections and forward recompute so all three enforce identical rules.
    """
    errors: list[str] = []

    if value < 0:
        errors.append("Показание не может быть отрицательным")
    if meter.max_digits and value >= Decimal(10) ** meter.max_digits:
        errors.append(f"Показание превышает разрядность прибора ({meter.max_digits} знаков)")

    if read_at is not None:
        today = date.today()
        first, last = period_month_bounds(month)
        if read_at > max(today, last) + timedelta(days=1):
            errors.append("Дата снятия не может быть существенно позже текущей даты")
        if not (first - timedelta(days=15) <= read_at <= last + timedelta(days=15)):
            errors.append("Дата снятия вне допустимого окна периода")

    if previous_value is not None and value < previous_value and kind == "normal":
        errors.append(
            f"Показание {value} меньше предыдущего {previous_value}; "
            "укажите причину: rollover, replacement или correction"
        )

    if errors:
        return None, "error", "; ".join(errors)

    consumption = compute_consumption(previous_value, value, meter.coefficient, kind, meter.max_digits)
    warning = check_anomaly(db, meter, month, consumption)
    if warning:
        return consumption, "warning", warning
    return consumption, "ok", None


def validate_and_fill(db: Session, meter: Meter, period: ReportingPeriod, data: ReadingIn, reading: Reading) -> None:
    """Apply ТЗ §5.4 rules; sets value/consumption/status/validation_message on the reading."""
    reading.kind = data.kind
    reading.missing_reason = data.missing_reason
    reading.comment = data.comment
    reading.photo_file_id = data.photo_file_id

    prev = get_previous_accepted(db, meter.id, period.month)
    reading.previous_value = prev.value if prev else None

    if data.value is None:
        if not data.missing_reason:
            raise bad_request("Отсутствие показания требует причины (нет доступа, неисправность, замена, другое)")
        reading.value = None
        reading.read_at = None
        reading.consumption = None
        reading.status = "missing"
        reading.validation_message = None
        return

    today = date.today()
    first, last = period_month_bounds(period.month)
    # Default: today clamped into the period (entering a past/future month defaults to that month)
    read_at = data.read_at or min(max(today, first), last)
    reading.value = data.value
    reading.read_at = read_at

    consumption, status, message = evaluate_value(
        db, meter, period.month, reading.previous_value, data.value, read_at, data.kind
    )
    reading.consumption = consumption
    reading.status = status
    reading.validation_message = message


def upsert_reading(
    db: Session, meter: Meter, period: ReportingPeriod, data: ReadingIn, actor
) -> Reading:
    """Idempotent draft save: one live row per meter+period (ТЗ §7.3)."""
    if period.status not in EDITABLE_PERIOD_STATUSES:
        raise conflict(
            f"Период {period.month} в статусе {period.status}: прямое редактирование запрещено, создайте корректировку"
        )
    if meter.status != "active":
        raise bad_request(f"Счётчик {meter.meter_number} не активен")

    reading = db.execute(
        select(Reading).where(Reading.meter_id == meter.id, Reading.reporting_period_id == period.id)
    ).scalar_one_or_none()
    old_value = reading.value if reading else None
    if reading is None:
        reading = Reading(
            tenant_id=meter.tenant_id,
            meter_id=meter.id,
            reporting_period_id=period.id,
            created_by=actor.id if actor else None,
        )
        db.add(reading)

    validate_and_fill(db, meter, period, data, reading)
    reading.updated_by = actor.id if actor else None
    try:
        db.flush()
    except IntegrityError:
        # COR-05: concurrent first-insert lost the race on uq_readings_meter_period → 409, not 500.
        db.rollback()
        raise conflict(f"Показание для {meter.meter_number} за {period.month} уже вводится другим запросом")

    if old_value != reading.value:
        db.add(
            ReadingRevision(
                reading_id=reading.id,
                old_value=old_value,
                new_value=reading.value,
                kind=data.kind,
                reason=data.comment,
                actor_id=actor.id if actor else None,
                actor_name=actor.display_name if actor else None,
                created_at=utcnow(),
            )
        )
    return reading


def recompute_forward(db: Session, meter: Meter, from_month: str) -> int:
    """After a correction, recompute consumption of later readings in non-closed periods."""
    stmt = (
        select(Reading, ReportingPeriod)
        .join(ReportingPeriod, Reading.reporting_period_id == ReportingPeriod.id)
        .where(Reading.meter_id == meter.id, ReportingPeriod.month > from_month)
        .order_by(ReportingPeriod.month)
    )
    updated = 0
    for reading, period in db.execute(stmt).all():
        if period.status == "closed" or reading.value is None:
            continue
        prev = get_previous_accepted(db, meter.id, period.month)
        reading.previous_value = prev.value if prev else None
        # COR-03: recompute status/anomaly too, not just the number — a new base
        # can turn a previously-ok reading into a decrease/anomaly and vice versa.
        consumption, status, message = evaluate_value(
            db, meter, period.month, reading.previous_value, reading.value, reading.read_at, reading.kind
        )
        reading.consumption = consumption
        reading.status = status
        reading.validation_message = message
        updated += 1
    return updated


def apply_correction(
    db: Session, reading: Reading, new_value: Decimal, reason: str, kind: str, actor
) -> Reading:
    """Correction of a submitted/closed reading: revision trail + forward recompute (ТЗ §5.4)."""
    meter: Meter = reading.meter
    period: ReportingPeriod = reading.period
    old_value = reading.value

    db.add(
        ReadingRevision(
            reading_id=reading.id,
            old_value=old_value,
            new_value=new_value,
            kind=kind,
            reason=reason,
            actor_id=actor.id if actor else None,
            actor_name=actor.display_name if actor else None,
            created_at=utcnow(),
        )
    )
    reading.value = new_value
    reading.kind = kind
    prev = get_previous_accepted(db, meter.id, period.month)
    reading.previous_value = prev.value if prev else None
    # COR-01: run the correction through the same validation as direct input —
    # an over-capacity or anomalous correction must not be silently accepted as ok.
    consumption, status, message = evaluate_value(
        db, meter, period.month, reading.previous_value, new_value, reading.read_at, kind
    )
    reading.consumption = consumption
    reading.status = status
    reading.validation_message = (
        f"Корректировка: {reason}" if message is None else f"Корректировка: {reason} — {message}"
    )
    reading.updated_by = actor.id if actor else None
    recompute_forward(db, meter, period.month)
    return reading
