"""PR-6b (closure-plan волна 1): SQL-level тесты CODE-05 и CODE-10.

CODE-05 — выборка жителей идёт по реальной роли 'applicant'
(мёртвая ветка 'resident' удалена), заявители видны менеджеру.
CODE-10 — auto_approve_user ДОБАВЛЯЕТ роль в непустой roles-массив
(раньше непустой массив не трогался — роль терялась).

Реальный sqlite (create_all) — мок не ловит семантику SQL-фильтров.
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.services.auth_service import AuthService
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


def _add_user(session, *, user_id, telegram_id, roles, role="applicant",
              active_role="applicant", status="approved"):
    session.add(User(
        id=user_id, telegram_id=telegram_id, first_name=f"U{user_id}",
        roles=roles, role=role, active_role=active_role,
        status=status, language="ru",
    ))
    session.commit()


# ── CODE-05 ───────────────────────────────────────────────────────────


class TestApplicantSelection:
    def test_get_residents_by_status_returns_applicants(self, session):
        """Заявители (новая roles-система) видны в выборке жителей."""
        _add_user(session, user_id=1, telegram_id=101, roles='["applicant"]')
        _add_user(session, user_id=2, telegram_id=102,
                  roles='["applicant", "executor"]')
        # Сотрудник без applicant — НЕ житель
        _add_user(session, user_id=3, telegram_id=103, roles='["manager"]',
                  role="manager", active_role="manager")

        svc = UserManagementService(session)
        result = svc.get_residents_by_status("approved")

        ids = {u.id for u in result["users"]}
        assert ids == {1, 2}
        assert result["total"] == 2

    def test_get_residents_legacy_role_field_fallback(self, session):
        """Старая система (roles пуст, role='applicant') тоже видна."""
        _add_user(session, user_id=1, telegram_id=101, roles=None,
                  role="applicant", active_role=None)

        svc = UserManagementService(session)
        result = svc.get_residents_by_status("approved")

        assert [u.id for u in result["users"]] == [1]

    def test_get_user_stats_counts_applicants(self, session):
        _add_user(session, user_id=1, telegram_id=101, roles='["applicant"]',
                  status="pending")
        _add_user(session, user_id=2, telegram_id=102, roles='["applicant"]',
                  status="approved")

        svc = UserManagementService(session)
        stats = svc.get_user_stats()

        assert stats["pending"] == 1
        assert stats["approved"] == 1


# ── CODE-10 ───────────────────────────────────────────────────────────


class TestAutoApproveRolesConsistency:
    @pytest.mark.asyncio
    async def test_appends_role_to_non_empty_roles(self, session):
        """Роль добавляется в НЕпустой roles-массив (как в process_invite_join)."""
        _add_user(session, user_id=1, telegram_id=101, roles='["executor"]',
                  role="executor", active_role="executor", status="pending")

        svc = AuthService(session)
        ok = await svc.auto_approve_user(101, "applicant")

        assert ok is True
        user = session.query(User).get(1)
        assert user.status == "approved"
        assert set(json.loads(user.roles)) == {"executor", "applicant"}
        # активная роль уже была — не перетирается
        assert user.active_role == "executor"

    @pytest.mark.asyncio
    async def test_initializes_empty_roles(self, session):
        _add_user(session, user_id=1, telegram_id=101, roles=None,
                  role="applicant", active_role=None, status="pending")

        svc = AuthService(session)
        ok = await svc.auto_approve_user(101, "executor")

        assert ok is True
        user = session.query(User).get(1)
        assert json.loads(user.roles) == ["executor"]
        assert user.active_role == "executor"

    @pytest.mark.asyncio
    async def test_role_already_present_is_not_duplicated(self, session):
        _add_user(session, user_id=1, telegram_id=101, roles='["applicant"]',
                  status="pending")

        svc = AuthService(session)
        ok = await svc.auto_approve_user(101, "applicant")

        assert ok is True
        user = session.query(User).get(1)
        assert json.loads(user.roles) == ["applicant"]
