"""A9-P1-2: общий юнит старта/стопа смены (services/shift_lifecycle), sync-обёртка.

Реальная sqlite-сессия: выбор planned живёт в SQL. Юнит НЕ коммитит — смена
и её audit одна транзакция вызывающего (rollback уносит обе). HTTP-путь и
паритет бот⟺API — tests/api/test_executor_shift_lifecycle.py.
"""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.shift_lifecycle import (
    end_shift_sync,
    shift_notify_payload,
    start_shift_sync,
)
from uk_management_bot.utils.datetime_utils import utc_now


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _user(db, tg=4242):
    u = User(telegram_id=tg, roles='["executor"]', status="approved", language="ru")
    db.add(u)
    db.commit()
    return u


def _planned(db, user_id, *, start_min, end_min):
    now = utc_now()
    s = Shift(user_id=user_id, status="planned",
              start_time=now + timedelta(minutes=start_min),
              end_time=now + timedelta(minutes=end_min))
    db.add(s)
    db.commit()
    return s


def test_start_activates_running_planned_and_audits(db):
    user = _user(db)
    planned = _planned(db, user.id, start_min=-10, end_min=+60)

    shift = start_shift_sync(db, user, notes="вышел")
    db.commit()

    assert shift.id == planned.id
    assert shift.status == "active"
    assert db.query(Shift).count() == 1
    [audit] = db.query(AuditLog).all()
    assert (audit.action, audit.details["shift_id"]) == ("shift_started", planned.id)


def test_expired_planned_is_not_activated(db):
    user = _user(db)
    stale = _planned(db, user.id, start_min=-120, end_min=-60)

    shift = start_shift_sync(db, user)
    db.commit()

    assert shift.id != stale.id
    db.expire_all()
    assert stale.status == "planned"


def test_unit_does_not_commit_rollback_drops_shift_and_audit(db):
    user = _user(db)

    start_shift_sync(db, user)
    db.rollback()

    assert db.query(Shift).count() == 0
    assert db.query(AuditLog).count() == 0


def test_end_completes_and_audits_with_specializations(db):
    user = _user(db)
    shift = start_shift_sync(db, user)
    shift.specialization_focus = ["plumber"]
    db.commit()

    end_shift_sync(db, user, shift, notes="сдал")
    db.commit()

    assert shift.status == "completed"
    assert shift.end_time is not None
    audit = db.query(AuditLog).filter(AuditLog.action == "shift_ended").one()
    assert audit.details == {"shift_id": shift.id, "notes": "сдал",
                             "specializations": ["plumber"]}


def test_notify_payload_skips_user_without_telegram(db):
    user = _user(db)
    shift = start_shift_sync(db, user)
    db.commit()
    user.telegram_id = None

    assert shift_notify_payload(user, shift, started=True) is None
