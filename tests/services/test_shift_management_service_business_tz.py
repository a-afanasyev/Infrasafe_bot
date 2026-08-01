"""ARCH-116: «смены на дату» и «смены за месяц» — бакет по бизнес-дню.

Экран «Расписание» у менеджера спрашивает смены на выбранную дату. Дата в
callback'е — календарная (что человек выбрал в календаре), а бакет считался
`func.date(planned_start_time)`, то есть по UTC-дате инстанта. Смена, которая
для Ташкента начинается 30.07 в 02:00, лежала в 29.07: менеджер, выбрав 30-е,
её не видел, а выбрав 29-е — видел смену «следующего дня».
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.session import Base
from uk_management_bot.services.shift_management_service import ShiftManagementService

CROSSOVER_UTC = datetime(2026, 7, 29, 21, 0, tzinfo=timezone.utc)  # 30.07 02:00 Ташкента

_engine = create_engine("sqlite:///:memory:", echo=False)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


def _shift(db, start_utc: datetime) -> Shift:
    end_utc = start_utc + timedelta(hours=8)
    shift = Shift(user_id=1, status="planned", start_time=start_utc, end_time=end_utc,
                  planned_start_time=start_utc, planned_end_time=end_utc)
    db.add(shift)
    db.commit()
    return shift


class TestGetShiftsForDate:
    def test_crossover_shift_belongs_to_its_business_date(self, db):
        _shift(db, CROSSOVER_UTC)
        assert len(ShiftManagementService(db).get_shifts_for_date(date(2026, 7, 30))) == 1

    def test_crossover_shift_is_not_on_previous_date(self, db):
        _shift(db, CROSSOVER_UTC)
        assert ShiftManagementService(db).get_shifts_for_date(date(2026, 7, 29)) == []

    def test_late_evening_shift_stays_on_its_own_date(self, db):
        """Контроль: смена 23:00 по Ташкенту (18:00Z) остаётся в своём дне."""
        _shift(db, datetime(2026, 7, 30, 18, 0, tzinfo=timezone.utc))
        svc = ShiftManagementService(db)
        assert len(svc.get_shifts_for_date(date(2026, 7, 30))) == 1
        assert svc.get_shifts_for_date(date(2026, 7, 31)) == []


class TestGetShiftsInMonth:
    def test_first_day_of_month_by_business_date(self, db):
        """01.08 02:00 Ташкента = 31.07 21:00Z — это АВГУСТ, не июль."""
        _shift(db, datetime(2026, 7, 31, 21, 0, tzinfo=timezone.utc))
        svc = ShiftManagementService(db)
        assert len(svc.get_shifts_in_month(date(2026, 8, 1))) == 1
        assert svc.get_shifts_in_month(date(2026, 7, 1)) == []

    def test_last_day_of_month_stays_in_month(self, db):
        """Контроль: 31.07 23:00 Ташкента (18:00Z) остаётся в июле."""
        _shift(db, datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc))
        svc = ShiftManagementService(db)
        assert len(svc.get_shifts_in_month(date(2026, 7, 1))) == 1
        assert svc.get_shifts_in_month(date(2026, 8, 1)) == []
