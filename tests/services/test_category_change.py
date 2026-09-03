"""Оркестратор смены категории (`services/category_change`) — интеграционно.

Диспетч здесь НАСТОЯЩИЙ (sqlite, дежурные на смене, флаг автоназначения в
`auto_manager_config`), а не «диспетчер был вызван»: `auto_dispatch_*`
best-effort и раньше ничего не возвращал — вердикт о фактическом назначении
может дать только свежее чтение заявки после всех команд.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import uk_management_bot.services.dispatch as dispatch
from uk_management_bot.database.models.auto_manager_config import AutoManagerConfig
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.auto_manager.config import CONFIG_ROW_ID, DEFAULT_CONFIG
from uk_management_bot.services.category_change import (
    CategoryChangeResult,
    change_category_sync,
)
from uk_management_bot.utils.datetime_utils import utc_now
from uk_management_bot.utils.request_workflow import InvalidTransition, PrincipalRef
import uk_management_bot.utils.constants as C

NUMBER = "260903-001"
APPLICANT, MANAGER, ELECTRICIAN, PLUMBER, UNIVERSAL = 2, 3, 4, 5, 6


@pytest.fixture()
def factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SF = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    # Telegram-уведомление дежурному внутри диспетча ходит в прод-SessionLocal
    # через asyncio.run — в тесте это внешний I/O, глушим.
    monkeypatch.setattr(dispatch, "_notify_assigned_sync", lambda *a, **k: None)
    yield SF
    engine.dispose()


def _seed(SF, *, status=C.REQUEST_STATUS_NEW, category="electricity",
          executor_id=None, assignment=None, plumber_on_shift=False,
          auto_assign=True, universal_executor=False):
    from uk_management_bot.config.settings import settings

    s = SF()
    # system-user: created_by для назначений system-принципала «dispatcher»
    s.add(User(id=1, telegram_id=settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID,
               first_name="System", roles='["manager"]', active_role="manager",
               status="approved", language="ru"))
    s.add(User(id=APPLICANT, telegram_id=20, first_name="Owner", roles='["applicant"]',
               active_role="applicant", status="approved", language="ru"))
    s.add(User(id=MANAGER, telegram_id=30, first_name="Mgr", roles='["manager"]',
               active_role="manager", status="approved", language="ru"))
    s.add(User(id=ELECTRICIAN, telegram_id=40, first_name="El", roles='["executor"]',
               active_role="executor", status="approved", language="ru",
               specialization="electrician"))
    s.add(User(id=PLUMBER, telegram_id=50, first_name="Pl", roles='["executor"]',
               active_role="executor", status="approved", language="ru",
               specialization="plumber"))
    if universal_executor:
        s.add(User(id=UNIVERSAL, telegram_id=60, first_name="Uni", roles='["executor"]',
                   active_role="executor", status="approved", language="ru",
                   specialization="universal"))
    if plumber_on_shift:
        now = utc_now()
        s.add(Shift(user_id=PLUMBER, start_time=now - timedelta(hours=1),
                    end_time=now + timedelta(hours=8), status="active"))
    s.add(AutoManagerConfig(id=CONFIG_ROW_ID,
                            data={**DEFAULT_CONFIG, "enabled": auto_assign}))
    req = Request(request_number=NUMBER, user_id=APPLICANT, category=category,
                  description="d", urgency="low", status=status,
                  executor_id=executor_id, address="Дом 1")
    if assignment is not None:
        kind, value = assignment
        req.assignment_type = kind
        if kind == "group":
            req.assigned_group = value
            s.add(RequestAssignment(request_number=NUMBER, assignment_type="group",
                                    group_specialization=value, executor_id=None,
                                    created_by=MANAGER, status="active"))
        else:
            s.add(RequestAssignment(request_number=NUMBER, assignment_type="individual",
                                    executor_id=value, created_by=MANAGER,
                                    status="active"))
    s.add(req)
    s.commit()
    s.close()
    return SF


def _mgr():
    return PrincipalRef(kind="user", user_id=MANAGER, source="telegram")


def _change(SF, category="plumbing"):
    return change_category_sync(SF, NUMBER, _mgr(), category)


def _db_state(SF):
    s = SF()
    req = s.query(Request).filter_by(request_number=NUMBER).first()
    rows = s.query(RequestAssignment).filter_by(request_number=NUMBER).all()
    comments = s.query(RequestComment).filter_by(request_number=NUMBER).count()
    state = (req.status, req.executor_id, req.category, req.assigned_group,
             sorted((r.assignment_type, r.group_specialization, r.executor_id, r.status)
                    for r in rows), comments)
    s.close()
    return state


class TestNewWithGroupRedispatch:
    def test_duty_plumber_on_shift_gets_assigned(self, factory):
        SF = _seed(factory, assignment=("group", "electrician"), plumber_on_shift=True)
        res = _change(SF, "plumbing")
        assert isinstance(res, CategoryChangeResult)
        assert res.no_op is False
        assert res.specialization_changed is True
        assert res.dispatch is not None and res.dispatch.kind == "assigned"
        assert res.status == C.REQUEST_STATUS_IN_PROGRESS
        assert res.executor_id == PLUMBER
        assert res.executor_spec_mismatch is False
        assert res.redispatched is True
        status, executor, category, group, rows, comments = _db_state(SF)
        assert (status, executor, category, group) == (
            C.REQUEST_STATUS_IN_PROGRESS, PLUMBER, "plumbing", None)
        assert rows == [("group", "electrician", None, "cancelled"),
                        ("individual", None, PLUMBER, "active")]
        assert comments == 1
        # DTO собран из свежего чтения, не из первого outcome
        assert (res.status, res.executor_id) == (status, executor)

    def test_no_duty_regroups_under_new_specialization(self, factory):
        SF = _seed(factory, assignment=("group", "electrician"), plumber_on_shift=False)
        res = _change(SF, "plumbing")
        assert res.dispatch.kind == "grouped"
        assert res.status == C.REQUEST_STATUS_NEW and res.executor_id is None
        assert res.redispatched is True
        rows = _db_state(SF)[4]
        assert rows == [("group", "electrician", None, "cancelled"),
                        ("group", "plumber", None, "active")]

    def test_auto_assign_disabled_leaves_new_without_group(self, factory):
        SF = _seed(factory, assignment=("group", "electrician"), auto_assign=False)
        res = _change(SF, "plumbing")
        assert res.dispatch.kind == "disabled"
        assert res.redispatched is False
        status, executor, category, group, rows, _ = _db_state(SF)
        assert (status, executor, group) == (C.REQUEST_STATUS_NEW, None, None)
        assert rows == [("group", "electrician", None, "cancelled")]

    def test_same_specialization_does_not_touch_assignment(self, factory):
        SF = _seed(factory, assignment=("group", "electrician"), plumber_on_shift=True)
        res = _change(SF, "internet")   # internet → electrician, как electricity
        assert res.specialization_changed is False
        assert res.dispatch is None and res.redispatched is False
        status, _, category, group, rows, _ = _db_state(SF)
        assert (category, group) == ("internet", "electrician")
        assert rows == [("group", "electrician", None, "active")]

    def test_new_without_assignment_just_dispatches(self, factory):
        SF = _seed(factory, plumber_on_shift=True)
        res = _change(SF, "plumbing")
        assert res.dispatch.kind == "assigned" and res.executor_id == PLUMBER


class TestNoOp:
    def test_legacy_label_equivalent_is_no_op(self, factory):
        SF = _seed(factory, category="Сантехника", assignment=("group", "plumber"))
        res = _change(SF, "plumbing")
        assert res.no_op is True and res.dispatch is None
        status, _, category, _, rows, comments = _db_state(SF)
        assert category == "Сантехника" and comments == 0
        assert rows == [("group", "plumber", None, "active")]


class TestInProgress:
    def test_executor_without_new_spec_is_flagged_and_kept(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS, executor_id=ELECTRICIAN,
                   assignment=("individual", ELECTRICIAN), plumber_on_shift=True)
        res = _change(SF, "plumbing")
        assert res.dispatch is None
        assert res.executor_id == ELECTRICIAN
        assert res.executor_spec_mismatch is True
        assert res.can_reassign is True
        assert [i.kind for i in res.post_commit_intents] == ["notify"]
        assert _db_state(SF)[4] == [("individual", None, ELECTRICIAN, "active")]

    def test_universal_executor_is_not_a_mismatch(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS, executor_id=UNIVERSAL,
                   assignment=("individual", UNIVERSAL), universal_executor=True)
        res = _change(SF, "plumbing")
        assert res.executor_spec_mismatch is False

    def test_purchase_status_cannot_reassign(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_PURCHASE, executor_id=ELECTRICIAN,
                   assignment=("individual", ELECTRICIAN))
        res = _change(SF, "plumbing")
        assert res.executor_spec_mismatch is True
        assert res.can_reassign is False
        assert res.post_commit_intents == ()   # уведомление только «В работе»


class TestErrors:
    def test_terminal_raises(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_APPROVED)
        with pytest.raises(InvalidTransition):
            _change(SF, "plumbing")


# ══════════════════════════════════════════════════════════════════════════
# Ревью 2026-09-03: async-путь (дашборд) и исчезнувшая заявка
# ══════════════════════════════════════════════════════════════════════════


def _seed_objects(*, status=C.REQUEST_STATUS_NEW, category="electricity",
                  assignment=None, auto_assign=True):
    """Те же строки, что кладёт `_seed`, но списком — для async-сессии."""
    from uk_management_bot.config.settings import settings

    objs = [
        User(id=1, telegram_id=settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID,
             first_name="System", roles='["manager"]', active_role="manager",
             status="approved", language="ru"),
        User(id=APPLICANT, telegram_id=20, first_name="Owner", roles='["applicant"]',
             active_role="applicant", status="approved", language="ru"),
        User(id=MANAGER, telegram_id=30, first_name="Mgr", roles='["manager"]',
             active_role="manager", status="approved", language="ru"),
        User(id=PLUMBER, telegram_id=50, first_name="Pl", roles='["executor"]',
             active_role="executor", status="approved", language="ru",
             specialization="plumber"),
        AutoManagerConfig(id=CONFIG_ROW_ID, data={**DEFAULT_CONFIG, "enabled": auto_assign}),
    ]
    req = Request(request_number=NUMBER, user_id=APPLICANT, category=category,
                  description="d", urgency="low", status=status, address="Дом 1")
    if assignment is not None:
        kind, value = assignment
        req.assignment_type = kind
        req.assigned_group = value
        objs.append(RequestAssignment(request_number=NUMBER, assignment_type="group",
                                      group_specialization=value, executor_id=None,
                                      created_by=MANAGER, status="active"))
    objs.append(req)
    return objs


async def _async_change(monkeypatch, *, auto_assign=True, duty=PLUMBER):
    from unittest.mock import AsyncMock

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from uk_management_bot.services.category_change import change_category_async

    engine = create_async_engine("sqlite+aiosqlite://",
                                 connect_args={"check_same_thread": False},
                                 poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    AF = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with AF() as s:
        s.add_all(_seed_objects(assignment=("group", "electrician"), auto_assign=auto_assign))
        await s.commit()

    # Подбор дежурного в async-пути идёт в отдельном потоке через прод-SessionLocal
    # (`pick_duty_executor_id(spec, None)`) — подменяем результат; sync-диспетч в
    # event loop'е недопустим (`asyncio.run` внутри loop) — ловим подмену.
    monkeypatch.setattr(dispatch, "pick_duty_executor_id", lambda *a, **k: duty)
    monkeypatch.setattr(dispatch, "auto_dispatch_new_request_sync",
                        lambda *a, **k: pytest.fail("sync dispatch used in async path"))
    monkeypatch.setattr(dispatch, "_publish_status_changed", AsyncMock())
    monkeypatch.setattr(dispatch, "_publish_updated", AsyncMock())
    monkeypatch.setattr("uk_management_bot.services.workflow_notifications."
                        "dispatch_notify_intents_detached", AsyncMock())

    res = await change_category_async(AF, NUMBER, _mgr(), "plumbing")
    async with AF() as s:
        req = (await s.execute(select(Request).where(
            Request.request_number == NUMBER))).scalar_one()
        rows = [(r.assignment_type, r.group_specialization, r.executor_id, r.status)
                for r in (await s.execute(select(RequestAssignment).order_by(
                    RequestAssignment.id))).scalars()]
        comments = len((await s.execute(select(RequestComment))).scalars().all())
    await engine.dispose()
    return res, req, rows, comments


class TestAsyncPath:
    def test_async_mirrors_sync_duty_assignment(self, monkeypatch):
        import asyncio
        res, req, rows, comments = asyncio.run(_async_change(monkeypatch))
        assert res.no_op is False and res.specialization_changed is True
        assert res.dispatch is not None and res.dispatch.kind == "assigned"
        assert (res.status, res.executor_id) == (C.REQUEST_STATUS_IN_PROGRESS, PLUMBER)
        assert (req.status, req.executor_id, req.category, req.assigned_group) == (
            C.REQUEST_STATUS_IN_PROGRESS, PLUMBER, "plumbing", None)
        assert rows == [("group", "electrician", None, "cancelled"),
                        ("individual", None, PLUMBER, "active")]
        assert comments == 1

    def test_async_disabled_leaves_new_without_group(self, monkeypatch):
        import asyncio
        res, req, rows, _ = asyncio.run(_async_change(monkeypatch, auto_assign=False))
        assert res.dispatch.kind == "disabled" and res.redispatched is False
        assert (req.status, req.executor_id, req.assigned_group) == (
            C.REQUEST_STATUS_NEW, None, None)
        assert rows == [("group", "electrician", None, "cancelled")]


class TestFreshReadMissingRequest:
    """Окно между commit и свежим чтением узкое, но исход обязан быть одним и
    тем же на обоих путях: `RequestNotFound`, а не AttributeError/NoResultFound."""

    def test_sync_raises_request_not_found(self, factory):
        from uk_management_bot.services.category_change import _fresh_sync
        from uk_management_bot.services.workflow_runner import RequestNotFound
        s = factory()
        try:
            with pytest.raises(RequestNotFound):
                _fresh_sync(s, "000000-000")
        finally:
            s.close()

    def test_async_raises_request_not_found(self):
        import asyncio
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from uk_management_bot.services.category_change import _fresh_async
        from uk_management_bot.services.workflow_runner import RequestNotFound

        async def run():
            engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            AF = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with AF() as s:
                    with pytest.raises(RequestNotFound):
                        await _fresh_async(s, "000000-000")
            finally:
                await engine.dispose()

        asyncio.run(run())
