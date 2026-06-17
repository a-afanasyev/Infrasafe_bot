"""FEAT-группы (PR-4): запросы пула и разделение «мои» vs «пул».

`_get_group_pool_query` — «свободные» group-заявки (В работе + active group +
executor_id NULL + matching spec + on-shift). `_get_executor_requests_query` —
ТОЛЬКО персональные (individual/взятые); непривязанные group сюда не попадают.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.handlers.requests import (
    _get_executor_requests_query,
    _get_group_pool_query,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield s
    s.close()
    engine.dispose()


def _plumber(session, *, on_shift=True, spec="plumber"):
    u = User(id=4, telegram_id=4, first_name="Plumber", roles='["executor"]',
             active_role="executor", status="approved", language="ru",
             specialization=spec)
    session.add(u)
    if on_shift:
        session.add(Shift(user_id=4, status="active",
                          start_time=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc)))
    session.commit()
    return u


def _request(session, *, number="260610-001", status="В работе", executor_id=None):
    session.add(Request(request_number=number, user_id=2, category="plumbing",
                        description="d", urgency="low", status=status,
                        executor_id=executor_id))
    session.commit()


def _group_assignment(session, *, number="260610-001", spec="plumber",
                      executor_id=None, status="active",
                      assignment_type="group"):
    session.add(RequestAssignment(
        request_number=number, assignment_type=assignment_type,
        group_specialization=spec, executor_id=executor_id,
        created_by=3, status=status))
    session.commit()


def _pool_numbers(session, user):
    return {r.request_number for r in _get_group_pool_query(session, user).all()}


def _mine_numbers(session, user):
    return {r.request_number for r in _get_executor_requests_query(session, user).all()}


class TestGroupPoolQuery:
    def test_unclaimed_group_matching_spec_on_shift_in_pool(self, session):
        u = _plumber(session)
        _request(session)
        _group_assignment(session)
        assert _pool_numbers(session, u) == {"260610-001"}

    def test_not_on_shift_empty(self, session):
        u = _plumber(session, on_shift=False)
        _request(session)
        _group_assignment(session)
        assert _pool_numbers(session, u) == set()

    def test_wrong_spec_excluded(self, session):
        u = _plumber(session, spec="plumber")
        _request(session)
        _group_assignment(session, spec="electric")
        assert _pool_numbers(session, u) == set()

    def test_claimed_excluded(self, session):
        u = _plumber(session)
        _request(session, executor_id=99)
        _group_assignment(session, executor_id=99, assignment_type="individual")
        assert _pool_numbers(session, u) == set()

    def test_wrong_status_excluded(self, session):
        u = _plumber(session)
        _request(session, status="Новая")
        _group_assignment(session)
        assert _pool_numbers(session, u) == set()


class TestLocaleKeys:
    def test_claim_keys_present_in_ru_and_uz(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[2] / "uk_management_bot/config/locales"
        keys = ["executor_claim_button", "group_pool_title", "group_pool_empty",
                "request_already_claimed", "request_claimed_success",
                "claimed_by_other_notify"]
        for lang in ("ru", "uz"):
            data = json.loads((root / f"{lang}.json").read_text(encoding="utf-8"))
            for k in keys:
                assert k in data["requests"], f"{lang}: requests.{k} отсутствует"


class TestMineExcludesPool:
    def test_unclaimed_group_not_in_mine(self, session):
        u = _plumber(session)
        _request(session)
        _group_assignment(session)
        assert _mine_numbers(session, u) == set()

    def test_individual_assignment_in_mine(self, session):
        u = _plumber(session)
        _request(session, number="260610-002")
        _group_assignment(session, number="260610-002", executor_id=4,
                          assignment_type="individual")
        assert "260610-002" in _mine_numbers(session, u)

    def test_executor_id_fallback_in_mine(self, session):
        u = _plumber(session)
        _request(session, number="260610-003", executor_id=4)
        assert "260610-003" in _mine_numbers(session, u)
