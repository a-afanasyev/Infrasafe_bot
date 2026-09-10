"""Блокировка периода на время записи показаний и переходов статуса (AUD7-COR-03).

Все писатели (PUT, bulk, import commit, переходы, корректировки) берут
`SELECT … FOR UPDATE` по строке reporting_periods и только потом читают статус.
Порядок захвата единый — по возрастанию month — поэтому взаимных блокировок
между одиночной записью и каскадом корректировки нет. На SQLite (тесты)
FOR UPDATE не компилируется — блокировка становится обычным SELECT'ом,
поведение проверяется на PostgreSQL в tests/test_period_concurrency_pg.py.
Освобождение — commit/rollback запроса; get_db закрывает сессию при ошибке.

Ожидание ограничено `SET LOCAL lock_timeout` (settings.lock_timeout_ms, только
PostgreSQL): писатель, упёршийся в занятый период, получает 55P03, который
app.core.errors отдаёт как 409 period_busy — вместо того, чтобы висеть на
воркере thread-пула. SET LOCAL живёт до конца транзакции, поэтому вызывается
в той же транзакции, что и FOR UPDATE (сессия autobegin'ит на первом execute).
"""

import uuid

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import not_found
from app.models import ReportingPeriod


def _apply_lock_timeout(db: Session) -> None:
    """`SET LOCAL lock_timeout` на текущую транзакцию; на SQLite и при 0 — no-op."""
    if db.get_bind().dialect.name != "postgresql":
        return
    timeout_ms = int(get_settings().lock_timeout_ms)
    if timeout_ms <= 0:
        return
    # SET LOCAL не принимает bind-параметры; int-cast делает подстановку безопасной.
    db.execute(text(f"SET LOCAL lock_timeout = '{timeout_ms}ms'"))


def lock_period(db: Session, tenant_id: uuid.UUID, month: str) -> ReportingPeriod:
    """Период tenant'а за месяц под FOR UPDATE; свежий статус после ожидания блокировки."""
    _apply_lock_timeout(db)
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
    """Период month и все более поздние НЕзакрытые периоды tenant'а, по возрастанию month.

    Для корректировки: каскад пишет в показания последующих периодов, поэтому
    захватываем их все — в том же порядке, что и одиночные писатели. Стартовый
    месяц берётся всегда (корректируют submitted ИЛИ closed период); более поздние
    закрытые пропускаем — каскад в них не пишет, а лишняя блокировка только
    расширяла бы зону конфликта (сек-ревью M-1).
    """
    _apply_lock_timeout(db)
    return list(
        db.execute(
            select(ReportingPeriod)
            .where(
                ReportingPeriod.tenant_id == tenant_id,
                ReportingPeriod.month >= month,
                or_(ReportingPeriod.status != "closed", ReportingPeriod.month == month),
            )
            .order_by(ReportingPeriod.month)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalars()
    )
