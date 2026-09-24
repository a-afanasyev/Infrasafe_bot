"""A9-P3-36: статистика смен отбирает исполнителей по ``User.roles``, а не по
``User.active_role``.

``active_role`` — только текущая активная роль. Исполнитель, переключённый в
другую роль, из счётчиков пропадал; пользователь с «грязным» active_role без
роли executor в ``roles`` — попадал. Канон отбора — ``legacy_role_filter``.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import uk_management_bot.database.models  # noqa: F401 — регистрация моделей
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.shift_management_service import ShiftManagementService

SHIFT_START = datetime(2026, 9, 10, 4, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db, tg_id: int, roles: list[str], active_role: str, status="approved") -> User:
    user = User(
        telegram_id=tg_id,
        first_name=f"U{tg_id}",
        roles=json.dumps(roles),
        active_role=active_role,
        status=status,
    )
    db.add(user)
    db.commit()
    return user


def _shift(db, user_id: int) -> None:
    db.add(Shift(
        user_id=user_id,
        status="planned",
        start_time=SHIFT_START,
        end_time=SHIFT_START + timedelta(hours=8),
    ))
    db.commit()


@pytest.fixture()
def mixed_users(db):
    switched = _user(db, 1, ["applicant", "executor"], active_role="applicant")
    dirty = _user(db, 2, ["manager"], active_role="executor")
    plain = _user(db, 3, ["executor"], active_role="executor")
    pending = _user(db, 4, ["executor"], active_role="executor", status="pending")
    return {"switched": switched, "dirty": dirty, "plain": plain, "pending": pending}


class TestCountAvailableExecutors:
    def test_executor_switched_to_other_role_is_counted(self, db):
        _user(db, 1, ["applicant", "executor"], active_role="applicant")
        assert ShiftManagementService(db).count_available_executors() == 1

    def test_dirty_active_role_without_executor_in_roles_is_not_counted(self, db):
        _user(db, 2, ["manager"], active_role="executor")
        assert ShiftManagementService(db).count_available_executors() == 0

    def test_status_filter_kept(self, db, mixed_users):
        # switched + plain; dirty (нет executor в roles) и pending — нет
        assert ShiftManagementService(db).count_available_executors() == 2


class TestExecutorWorkloadStats:
    def test_selects_by_roles_not_active_role(self, db, mixed_users):
        for user in mixed_users.values():
            _shift(db, user.id)

        rows = ShiftManagementService(db).get_executor_workload_stats(
            SHIFT_START - timedelta(days=1), date(2026, 9, 30)
        )

        ids = {row.id for row in rows}
        assert mixed_users["switched"].id in ids
        assert mixed_users["plain"].id in ids
        assert mixed_users["dirty"].id not in ids
