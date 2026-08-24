"""Жизненный цикл смен по расписанию (решение владельца 2026-08-24).

Живой дефект profk: сотрудники стоят в расписании (status='planned', окно
наступило), но все потребители «кто на смене» требуют 'active', а переход
planned→active не делал никто — заявки в смене не приходили, профиль
показывал «без смены». Кнопка «Начать смену» при этом плодила ad-hoc-дубль
вместо активации запланированной.

Два фикса под тестами:
1. Джоба shift_scheduler: planned в окне → active; active с истёкшим
   end_time → completed (ad-hoc с NULL end не трогается).
2. start_shift: активирует запланированную смену в окне, ad-hoc — только
   когда запланированной нет.
"""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.datetime_utils import utc_now

TELEGRAM_ID = 555


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SF = sessionmaker(bind=engine)
    # Джоба открывает СВОЮ сессию через глобальную фабрику — подменяем её.
    import uk_management_bot.utils.shift_scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "SessionLocal", SF)
    session = SF()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _user(db):
    user = User(telegram_id=TELEGRAM_ID, roles='["executor"]',
                active_role="executor", status="approved", language="ru")
    db.add(user)
    db.commit()
    return user


def _shift(db, user_id, *, status, start_delta_min, end_delta_min=None):
    now = utc_now()
    shift = Shift(
        user_id=user_id,
        status=status,
        start_time=now + timedelta(minutes=start_delta_min),
        end_time=(now + timedelta(minutes=end_delta_min))
        if end_delta_min is not None else None,
    )
    db.add(shift)
    db.commit()
    return shift


def _run_job(db):
    from uk_management_bot.utils.shift_scheduler import ShiftScheduler
    scheduler = ShiftScheduler.__new__(ShiftScheduler)  # без запуска apscheduler
    return scheduler._activate_scheduled_shifts_sync()


class TestActivationJob:
    def test_planned_in_window_becomes_active(self, db):
        user = _user(db)
        shift = _shift(db, user.id, status="planned",
                       start_delta_min=-60, end_delta_min=+120)
        activated, completed = _run_job(db)
        db.expire_all()
        assert (activated, completed) == (1, 0)
        assert shift.status == "active"

    def test_future_planned_untouched(self, db):
        user = _user(db)
        shift = _shift(db, user.id, status="planned",
                       start_delta_min=+30, end_delta_min=+120)
        activated, _ = _run_job(db)
        db.expire_all()
        assert activated == 0
        assert shift.status == "planned"

    def test_unassigned_planned_untouched(self, db):
        _user(db)
        shift = _shift(db, None, status="planned",
                       start_delta_min=-60, end_delta_min=+120)
        activated, _ = _run_job(db)
        db.expire_all()
        assert activated == 0
        assert shift.status == "planned"

    def test_expired_active_becomes_completed(self, db):
        user = _user(db)
        shift = _shift(db, user.id, status="active",
                       start_delta_min=-600, end_delta_min=-10)
        _, completed = _run_job(db)
        db.expire_all()
        assert completed == 1
        assert shift.status == "completed"

    def test_adhoc_active_null_end_untouched(self, db):
        """Ad-hoc смену («Начать смену», end_time NULL) завершает человек."""
        user = _user(db)
        shift = _shift(db, user.id, status="active", start_delta_min=-600)
        _, completed = _run_job(db)
        db.expire_all()
        assert completed == 0
        assert shift.status == "active"

    def test_expired_planned_not_activated(self, db):
        """Окно прошло целиком — активировать вчерашнюю смену нельзя."""
        user = _user(db)
        shift = _shift(db, user.id, status="planned",
                       start_delta_min=-600, end_delta_min=-60)
        activated, _ = _run_job(db)
        db.expire_all()
        assert activated == 0
        assert shift.status == "planned"

    def test_on_shift_predicate_after_activation(self, db):
        """Сквозной смысл фикса: после джобы сотрудник «на смене»."""
        from uk_management_bot.utils.shifts import is_on_shift_now_sync
        user = _user(db)
        _shift(db, user.id, status="planned",
               start_delta_min=-60, end_delta_min=+120)
        assert is_on_shift_now_sync(db, user.id) is False
        _run_job(db)
        assert is_on_shift_now_sync(db, user.id) is True


class TestStartShiftActivatesPlanned:
    def _service(self, db):
        from uk_management_bot.services.shift_service import ShiftService
        return ShiftService(db)

    def test_button_activates_planned_instead_of_adhoc(self, db):
        user = _user(db)
        planned = _shift(db, user.id, status="planned",
                         start_delta_min=-60, end_delta_min=+120)
        result = self._service(db).start_shift(TELEGRAM_ID, notes="вышел")
        assert result["success"] is True
        assert result["shift"].id == planned.id, "не должен плодить ad-hoc-дубль"
        assert result["shift"].status == "active"
        assert "вышел" in (result["shift"].notes or "")
        assert db.query(Shift).count() == 1

    def test_button_creates_adhoc_when_no_planned(self, db):
        """Регресс: без запланированной смены — прежний ad-hoc путь."""
        _user(db)
        result = self._service(db).start_shift(TELEGRAM_ID)
        assert result["success"] is True
        assert result["shift"].status == "active"
        assert result["shift"].end_time is None

    def test_future_planned_does_not_block_adhoc(self, db):
        """Смена завтра не активируется досрочно — создаётся ad-hoc."""
        user = _user(db)
        planned = _shift(db, user.id, status="planned",
                         start_delta_min=+300, end_delta_min=+600)
        result = self._service(db).start_shift(TELEGRAM_ID)
        assert result["success"] is True
        assert result["shift"].id != planned.id
        db.expire_all()
        assert planned.status == "planned"
