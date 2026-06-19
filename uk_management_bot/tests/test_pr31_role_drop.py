"""PR-31 / DB-060 — поведение после дропа legacy-колонки ``users.role``.

Покрывает: модель без колонки role; legacy_role_filter теперь матчит по
JSON-массиву roles (расширение AUD3-01); sync_legacy_role — no-op;
legacy_primary_role — active_role / первая роль / None (без дефолта applicant);
has_admin_access / has_executor_access / get_user_roles работают без .role.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import (
    legacy_role_filter,
    sync_legacy_role,
    legacy_primary_role,
    has_admin_access,
    has_executor_access,
    get_user_roles,
)


def test_model_has_no_role_column():
    assert "role" not in User.__table__.columns, "колонка users.role должна быть удалена (DB-060)"


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _mk(session, telegram_id, roles, active_role=None, status="approved"):
    u = User(telegram_id=telegram_id, roles=roles, active_role=active_role, status=status)
    session.add(u)
    session.commit()
    return u


class TestLegacyRoleFilter:
    def test_matches_role_inside_roles_array(self, session):
        _mk(session, 1, '["applicant", "executor", "manager"]', active_role="manager")
        _mk(session, 2, '["applicant"]', active_role="applicant")
        found = session.query(User).filter(legacy_role_filter("executor")).all()
        assert [u.telegram_id for u in found] == [1]

    def test_multiple_roles_is_or(self, session):
        _mk(session, 1, '["manager"]')
        _mk(session, 2, '["executor"]')
        _mk(session, 3, '["applicant"]')
        found = session.query(User).filter(legacy_role_filter("manager", "executor")).all()
        assert {u.telegram_id for u in found} == {1, 2}

    def test_no_false_match_on_substring(self, session):
        # "manager" не должен матчиться как подстрока другой роли — токен закавычен.
        _mk(session, 1, '["applicant"]')
        found = session.query(User).filter(legacy_role_filter("manager")).all()
        assert found == []

    def test_null_roles_not_matched(self, session):
        _mk(session, 1, None)
        found = session.query(User).filter(legacy_role_filter("applicant")).all()
        assert found == []


class TestSyncLegacyRole:
    def test_is_noop(self):
        u = User(telegram_id=1, roles='["applicant"]')
        # Не бросает и не создаёт колоночного состояния.
        assert sync_legacy_role(u, "manager") is None


class TestLegacyPrimaryRole:
    def test_prefers_active_role(self):
        u = User(telegram_id=1, roles='["applicant", "manager"]', active_role="manager")
        assert legacy_primary_role(u) == "manager"

    def test_falls_back_to_first_role(self):
        u = User(telegram_id=1, roles='["executor", "manager"]', active_role=None)
        assert legacy_primary_role(u) == "executor"

    def test_none_without_default(self):
        u = User(telegram_id=1, roles=None, active_role=None)
        assert legacy_primary_role(u) is None  # без дефолта applicant


class TestAccessHelpersWithoutRoleColumn:
    def test_has_admin_access_via_roles(self):
        u = User(telegram_id=1, roles='["applicant", "manager"]', active_role="applicant")
        assert has_admin_access(user=u) is True

    def test_has_executor_access_via_roles(self):
        u = User(telegram_id=1, roles='["applicant", "executor"]', active_role="applicant")
        assert has_executor_access(user=u) is True

    def test_no_access_for_plain_applicant(self):
        u = User(telegram_id=1, roles='["applicant"]', active_role="applicant")
        assert has_admin_access(user=u) is False
        assert has_executor_access(user=u) is False

    def test_get_user_roles_without_role_column(self):
        u = User(telegram_id=1, roles='["executor"]')
        assert get_user_roles(u) == ["executor"]

    def test_get_user_roles_defaults_applicant(self):
        u = User(telegram_id=1, roles=None)
        assert get_user_roles(u) == ["applicant"]
