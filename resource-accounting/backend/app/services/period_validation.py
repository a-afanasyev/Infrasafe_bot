"""Единый критерий готовности ведомости к подтверждению (AUD7-COR-02).

`validate` показывает его пользователю, `submit` — применяет. Раньше submit
проверял только ошибки и предупреждения без комментария, а полноту (все
активные счётчики имеют строку) считал только validate — пустая/частичная
ведомость утверждалась.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Meter, Reading, ReportingPeriod

NOT_ENTERED_MESSAGE = "Показание не введено"
WARNING_NO_COMMENT_MESSAGE = "Предупреждение без комментария"


@dataclass(frozen=True)
class PeriodSummary:
    active_meters: int
    entered: int
    not_entered_meters: tuple[tuple[uuid.UUID, str], ...]  # (meter_id, meter_number), без строки
    by_status: dict[str, int]
    warnings_without_comment: tuple[tuple[uuid.UUID, str | None], ...]  # (meter_id, message)
    errors: tuple[tuple[uuid.UUID, str | None], ...]  # (meter_id, message)

    @property
    def not_entered(self) -> int:
        return len(self.not_entered_meters)

    @property
    def can_submit(self) -> bool:
        return not self.errors and not self.warnings_without_comment and self.not_entered == 0

    def blocking_details(self) -> list[dict]:
        """Единый формат details для 409: что именно мешает подтверждению."""
        return (
            [{"meter_id": str(mid), "status": "error", "message": msg} for mid, msg in self.errors]
            + [
                {"meter_id": str(mid), "status": "warning", "message": msg or WARNING_NO_COMMENT_MESSAGE}
                for mid, msg in self.warnings_without_comment
            ]
            + [
                {"meter_id": str(mid), "status": "not_entered", "message": NOT_ENTERED_MESSAGE}
                for mid, _number in self.not_entered_meters
            ]
        )


def summarize_period(db: Session, tenant_id: uuid.UUID, period: ReportingPeriod) -> PeriodSummary:
    """Считает полноту строго по пересечению множеств активных счётчиков и строк
    периода (AUD6-P2-09: строки архивированных счётчиков остаются в периоде и не
    должны ни уводить not_entered в минус, ни завышать entered)."""
    active = db.execute(
        select(Meter.id, Meter.meter_number)
        .where(Meter.tenant_id == tenant_id, Meter.status == "active")
        .order_by(Meter.meter_number_normalized)
    ).all()
    active_by_id = {row.id: row.meter_number for row in active}
    readings = db.execute(select(Reading).where(Reading.reporting_period_id == period.id)).scalars().all()

    by_status: dict[str, int] = {}
    warnings: list[tuple[uuid.UUID, str | None]] = []
    errors: list[tuple[uuid.UUID, str | None]] = []
    entered: set[uuid.UUID] = set()
    for r in readings:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        if r.status == "warning" and not r.comment:
            warnings.append((r.meter_id, r.validation_message))
        if r.status == "error":
            errors.append((r.meter_id, r.validation_message))
        if r.meter_id in active_by_id:
            entered.add(r.meter_id)
    not_entered = tuple((mid, number) for mid, number in active_by_id.items() if mid not in entered)
    return PeriodSummary(
        active_meters=len(active_by_id),
        entered=len(entered),
        not_entered_meters=not_entered,
        by_status=by_status,
        warnings_without_comment=tuple(warnings),
        errors=tuple(errors),
    )
