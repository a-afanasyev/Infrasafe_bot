"""MGR-02: resident search must return only жители (applicant role), searching by
name/username/phone. Real sqlite — мок не ловит семантику SQL-фильтров.

Critical: a multi-role applicant+executor user IS a resident and must be
included; an executor-only user must be excluded.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.services.user_management_service import UserManagementService


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SF = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = SF()
    yield s
    s.close()
    engine.dispose()


def _add(session, *, user_id, telegram_id, first_name="Ivan", roles='["applicant"]',
         role="applicant", active_role="applicant", phone=None):
    session.add(User(
        id=user_id, telegram_id=telegram_id, first_name=first_name,
        roles=roles, role=role, active_role=active_role,
        status="approved", language="ru", phone=phone,
    ))
    session.commit()


class TestSearchResidents:
    def test_excludes_non_applicants_includes_multi_role(self, session):
        _add(session, user_id=1, telegram_id=101, roles='["applicant"]')
        _add(session, user_id=2, telegram_id=102, roles='["applicant", "executor"]')
        _add(session, user_id=3, telegram_id=103, roles='["executor"]',
             role="executor", active_role="executor")

        ids = {u.id for u in UserManagementService(session).search_residents("Ivan")}
        assert ids == {1, 2}  # executor-only (id=3) excluded; applicant+executor included

    def test_legacy_role_fallback_included(self, session):
        _add(session, user_id=1, telegram_id=101, roles=None)  # legacy: role='applicant'
        ids = {u.id for u in UserManagementService(session).search_residents("Ivan")}
        assert ids == {1}

    def test_search_by_phone(self, session):
        _add(session, user_id=1, telegram_id=101, first_name="Ivan", phone="+998901234567")
        _add(session, user_id=2, telegram_id=102, first_name="Petr", phone="+998905550000")
        ids = {u.id for u in UserManagementService(session).search_residents("90123")}
        assert ids == {1}

    def test_no_match_returns_empty(self, session):
        _add(session, user_id=1, telegram_id=101, first_name="Ivan")
        assert UserManagementService(session).search_residents("zzzzz") == []
