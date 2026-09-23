"""A9-P3-11 (ревью): AuthService.get_users_by_role(_sync) отбирает ТОЛЬКО по roles.

Был `or_(User.active_role == role, ...)`: получатели админ-уведомлений
(handlers/auth.py — новая заявка по инвайту с ПД) включали пользователя, у
которого роль осталась лишь в устаревшем active_role.
Реальная БД (sqlite, как в test_pr31_role_drop), а не мок: фильтр живёт в SQL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.auth_service import AuthService


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _mk(session, telegram_id, roles, active_role=None, status="approved"):
    session.add(User(telegram_id=telegram_id, roles=roles, active_role=active_role, status=status))
    session.commit()


def _ids(users):
    return sorted(u.telegram_id for u in users)


def test_stale_active_role_is_not_selected(session):
    _mk(session, 1, '["applicant"]', active_role="admin")      # только active_role
    _mk(session, 2, None, active_role="admin")                 # пустые roles
    _mk(session, 3, '["applicant", "admin"]', active_role="applicant")  # настоящий
    assert _ids(AuthService(session).get_users_by_role_sync("admin")) == [3]


def test_exact_token_and_status(session):
    _mk(session, 1, '["system_admin"]')                 # подстрока — не матч
    _mk(session, 2, '["admin"]', status="pending")      # не approved
    _mk(session, 3, '["admin"]')
    assert _ids(AuthService(session).get_users_by_role_sync("admin")) == [3]


@pytest.mark.asyncio
async def test_async_wrapper_same_semantics(session):
    _mk(session, 1, '["applicant"]', active_role="executor")
    _mk(session, 2, '["executor"]', active_role="applicant")
    assert _ids(await AuthService(session).get_users_by_role("executor")) == [2]


def test_sql_has_no_active_role_branch_on_postgres_dialect():
    """Тот же запрос, скомпилированный под PG: active_role в фильтре нет,
    матч — LIKE по закавыченному токену (одинаково для sqlite и PG)."""
    from unittest.mock import MagicMock

    captured = {}
    db = MagicMock()

    def _query(model):
        q = MagicMock()

        def _filter(*clauses):
            captured["clauses"] = clauses
            r = MagicMock()
            r.all.return_value = []
            return r

        q.filter.side_effect = _filter
        return q

    db.query.side_effect = _query
    AuthService(db).get_users_by_role_sync("admin")
    sql = " AND ".join(
        str(c.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for c in captured["clauses"]
    )
    assert "active_role" not in sql
    assert "LIKE" in sql
