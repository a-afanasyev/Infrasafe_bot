"""Блокировка периода на время записи показаний и переходов статуса (AUD7-COR-03).

Все писатели (PUT, bulk, import commit, переходы, корректировки) берут
`SELECT … FOR UPDATE` по строке reporting_periods и только потом читают статус.
Порядок захвата единый — по возрастанию month — поэтому взаимных блокировок
между одиночной записью и каскадом корректировки нет. На SQLite (тесты)
FOR UPDATE не компилируется — блокировка становится обычным SELECT'ом,
поведение проверяется на PostgreSQL в tests/test_period_concurrency_pg.py.
Освобождение — commit/rollback запроса; get_db закрывает сессию при ошибке.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.models import ReportingPeriod


def lock_period(db: Session, tenant_id: uuid.UUID, month: str) -> ReportingPeriod:
    """Период tenant'а за месяц под FOR UPDATE; свежий статус после ожидания блокировки."""
    row = db.execute(
        select(ReportingPeriod)
        .where(ReportingPeriod.tenant_id == tenant_id, ReportingPeriod.month == month)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        raise not_found(f"Период {month}")
    return row


def lock_periods_from(db: Session, tenant_id: uuid.UUID, month: str) -> list[ReportingPeriod]:
    """Период month и все более поздние периоды tenant'а, по возрастанию month.

    Для корректировки: каскад пишет в показания последующих периодов, поэтому
    захватываем их все — в том же порядке, что и одиночные писатели.
    """
    return list(
        db.execute(
            select(ReportingPeriod)
            .where(ReportingPeriod.tenant_id == tenant_id, ReportingPeriod.month >= month)
            .order_by(ReportingPeriod.month)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalars()
    )
