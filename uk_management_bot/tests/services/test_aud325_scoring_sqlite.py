"""AUD3-25: SQL-фильтры скоринга на РЕАЛЬНОЙ sqlite-сессии.

Соседний ``test_shift_assignment_service.py`` мокает всю цепочку
``db.query().filter().count()`` — сами предикаты (чей user_id, какие статусы,
какое окно дат, условия перекрытия) на моках не исполняются и не могут
упасть. Здесь те же методы ``ScoringEngine`` гоняются против настоящих строк:
предмет — SQL-предикат, а не арифметика поверх подменённых count'ов.

Харнесс-факт (ARCH-116): sqlite роняет tzinfo при bind, но фильтр
``col >= lo AND col < hi`` с aware-UTC границами ведёт себя как на Postgres,
а naive из чтения трактуется business_time-каноном как UTC — поэтому
бизнес-окна (`business_days_window`) проверяемы без Postgres.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

EXEC_ID, OTHER_ID = 1, 2

# Полдень UTC — далеко от полуночных краёв бизнес-зоны (UTC+5): смена не
# уползает в соседнюю бизнес-дату.
BASE = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db():
    from uk_management_bot.database.session import Base
    import uk_management_bot.database.models  # noqa: F401 — все таблицы

    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    from uk_management_bot.database.models.user import User
    for uid, tg in ((EXEC_ID, 100), (OTHER_ID, 200)):
        session.add(User(id=uid, telegram_id=tg, roles='["executor"]',
                         status="approved", specialization='["plumber"]'))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _engine(db):
    from uk_management_bot.services.shift_assignment_service.scoring import (
        ScoringEngine,
    )
    return ScoringEngine(db, {})


def _shift(db, *, user_id=EXEC_ID, start=BASE, hours=8, status="planned",
           specs=None):
    from uk_management_bot.database.models.shift import Shift

    row = Shift(user_id=user_id, status=status,
                start_time=start, planned_start_time=start,
                planned_end_time=start + timedelta(hours=hours),
                specialization_focus=specs)
    db.add(row)
    db.commit()
    return row


_request_seq = iter(range(100, 1000))


def _request(db, *, executor_id=EXEC_ID, status="В работе"):
    from uk_management_bot.database.models.request import Request

    row = Request(request_number=f"260910-{next(_request_seq)}",
                  user_id=OTHER_ID, executor_id=executor_id,
                  category="plumbing", description="d", address="Дом 1",
                  status=status)
    db.add(row)
    db.commit()
    return row


# Текущая смена, для которой считается скоринг: персистится обязательно —
# фильтр `Shift.id != shift.id` с транзиентным id=None дал бы `!= NULL`,
# то есть ЛОЖЬ на каждой строке, и запрос перекрытий ослеп бы молча.
@pytest.fixture()
def current(db):
    return _shift(db, specs=["plumber"])


class TestWorkloadFilters:
    def test_counts_only_this_executors_planned_and_active(self, db, current):
        from uk_management_bot.database.models.user import User

        _shift(db, start=BASE + timedelta(days=1))                    # planned ✓
        _shift(db, start=BASE + timedelta(days=2), status="active")   # active ✓
        _shift(db, start=BASE + timedelta(days=3), status="cancelled")  # ✗
        _shift(db, start=BASE + timedelta(days=4), status="completed")  # ✗
        _shift(db, start=BASE + timedelta(days=1), user_id=OTHER_ID)    # чужая ✗

        score = _engine(db)._calculate_workload_score(
            current, db.get(User, EXEC_ID))
        # current + 2 = 3 смены в окне; заявок нет.
        assert score == pytest.approx(((7 - 3) / 7 + 1.0) / 2)

    def test_week_window_excludes_far_shifts(self, db, current):
        from uk_management_bot.database.models.user import User

        _shift(db, start=BASE - timedelta(days=10))  # вне окна ±7 бизнес-дней
        _shift(db, start=BASE + timedelta(days=10))  # вне окна

        score = _engine(db)._calculate_workload_score(
            current, db.get(User, EXEC_ID))
        # В окне только сама current.
        assert score == pytest.approx(((7 - 1) / 7 + 1.0) / 2)

    def test_request_status_and_executor_filters(self, db, current):
        from uk_management_bot.database.models.user import User

        _request(db, status="В работе")
        _request(db, status="Закуп")
        _request(db, status="Новая")       # не активная ✗
        _request(db, status="Исполнено")   # не активная ✗
        _request(db, executor_id=OTHER_ID, status="В работе")  # чужая ✗

        # request_number уникален — перезапишем на честные
        score = _engine(db)._calculate_workload_score(
            current, db.get(User, EXEC_ID))
        assert score == pytest.approx(((7 - 1) / 7 + (10 - 2) / 10) / 2)


class TestAvailabilityFilters:
    def test_same_spec_overlap_blocks(self, db, current):
        from uk_management_bot.database.models.user import User

        _shift(db, start=BASE + timedelta(hours=2), specs=["plumber"])
        assert _engine(db)._calculate_availability_score(
            current, db.get(User, EXEC_ID)) == 0.0

    def test_different_spec_overlap_allowed_with_penalty(self, db, current):
        from uk_management_bot.database.models.user import User

        _shift(db, start=BASE + timedelta(hours=2), specs=["electrician"])
        assert _engine(db)._calculate_availability_score(
            current, db.get(User, EXEC_ID)) == 0.8

    def test_cancelled_overlap_is_ignored(self, db, current):
        from uk_management_bot.database.models.user import User

        _shift(db, start=BASE + timedelta(hours=2), specs=["plumber"],
               status="cancelled")
        assert _engine(db)._calculate_availability_score(
            current, db.get(User, EXEC_ID)) == 1.0

    def test_other_users_overlap_is_ignored(self, db, current):
        from uk_management_bot.database.models.user import User

        _shift(db, start=BASE + timedelta(hours=2), specs=["plumber"],
               user_id=OTHER_ID)
        assert _engine(db)._calculate_availability_score(
            current, db.get(User, EXEC_ID)) == 1.0

    def test_short_rest_before_shift_lowers_score(self, db, current):
        from uk_management_bot.database.models.user import User

        # Заканчивается за 4 часа до начала current (отдых < 8ч).
        _shift(db, start=BASE - timedelta(hours=12), hours=8)
        assert _engine(db)._calculate_availability_score(
            current, db.get(User, EXEC_ID)) == 0.7

    def test_enough_rest_keeps_full_availability(self, db, current):
        from uk_management_bot.database.models.user import User

        # Заканчивается за 9 часов до начала current.
        _shift(db, start=BASE - timedelta(hours=17), hours=8)
        assert _engine(db)._calculate_availability_score(
            current, db.get(User, EXEC_ID)) == 1.0

    def test_completed_shift_counts_for_rest_check(self, db, current):
        from uk_management_bot.database.models.user import User

        # Отдых считает и completed-смены (фильтр шире, чем у перекрытий).
        _shift(db, start=BASE - timedelta(hours=12), hours=8,
               status="completed")
        assert _engine(db)._calculate_availability_score(
            current, db.get(User, EXEC_ID)) == 0.7


class TestConflictPenalties:
    def test_five_shifts_in_window_add_penalty(self, db, current):
        from uk_management_bot.database.models.user import User

        for d in (1, 2, -1, -2):  # + current = 5 в окне ±3 бизнес-дней
            _shift(db, start=BASE + timedelta(days=d))
        assert _engine(db)._calculate_conflict_penalties(
            current, db.get(User, EXEC_ID)) == pytest.approx(0.3)

    def test_four_shifts_no_penalty(self, db, current):
        from uk_management_bot.database.models.user import User

        for d in (1, 2, -1):
            _shift(db, start=BASE + timedelta(days=d))
        assert _engine(db)._calculate_conflict_penalties(
            current, db.get(User, EXEC_ID)) == 0.0

    def test_window_and_user_filters(self, db, current):
        from uk_management_bot.database.models.user import User

        # Пятой смены не набирается: одна вне окна ±3, одна чужая.
        for d in (1, 2, -1):
            _shift(db, start=BASE + timedelta(days=d))
        _shift(db, start=BASE + timedelta(days=5))            # вне окна
        _shift(db, start=BASE + timedelta(days=1),
               user_id=OTHER_ID)                              # чужая
        assert _engine(db)._calculate_conflict_penalties(
            current, db.get(User, EXEC_ID)) == 0.0
