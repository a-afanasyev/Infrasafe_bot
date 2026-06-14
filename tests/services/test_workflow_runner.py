"""PR2a-0 (SSOT-кластер #1): entry-layer run_command_sync/async.

Тесты фундамента: свежая сессия из factory, FOR UPDATE-загрузка,
ActorContext+snapshot из БД, plan_transition/check_repeat, применение
patch+domain_ops+audit+outbox в ОДНОЙ транзакции, CommandOutcome.

Хендлеры здесь не участвуют — проверяется только сам layer (canonical-write
модели A: MANAGER_CONFIRM пишет статус «Исполнено», возврат — Исполнено+
is_returned, т.е. канон «Возвращена»).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.rating import Rating
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.webhook_outbox import WebhookOutbox
from uk_management_bot.database.models.shift import Shift

from uk_management_bot.services.workflow_runner import (
    run_command_sync,
    run_command_async,
    CommandOutcome,
    RequestNotFound,
)
from uk_management_bot.utils.request_workflow import (
    Action,
    ActionCommand,
    PrincipalRef,
    NotAuthorized,
    RepeatRejected,
)
import uk_management_bot.utils.constants as C


# ---------------------------------------------------------------------------
# Фикстура: общий in-memory engine (StaticPool — все сессии factory видят одну БД)
# ---------------------------------------------------------------------------

@pytest.fixture()
def factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SF = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield SF
    engine.dispose()


def _seed(SF, *, status, manager_confirmed=False, is_returned=False,
          apartment_id=None, executor_id=None):
    """Заявка owner=2 + менеджер=3 + исполнитель=4. Возвращает фабрику."""
    s = SF()
    s.add(User(id=2, telegram_id=2, first_name="Owner",
               roles='["applicant"]', active_role="applicant",
               status="approved", language="ru"))
    s.add(User(id=3, telegram_id=3, first_name="Mgr",
               roles='["manager"]', active_role="manager",
               status="approved", language="ru"))
    s.add(User(id=4, telegram_id=4, first_name="Exec",
               roles='["executor"]', active_role="executor",
               status="approved", language="ru"))
    s.add(Request(
        request_number="260610-001", user_id=2, category="c", description="d",
        urgency="low", status=status, manager_confirmed=manager_confirmed,
        is_returned=is_returned, apartment_id=apartment_id,
        executor_id=executor_id,
    ))
    s.commit()
    s.close()
    return SF


def _mgr():
    return PrincipalRef(kind="user", user_id=3, source="telegram")


def _owner():
    return PrincipalRef(kind="user", user_id=2, source="telegram")


# ---------------------------------------------------------------------------
# SYSTEM_DISPATCH_ASSIGN — авто-диспетчер (PR2d): created_by = seeded system-user
# ---------------------------------------------------------------------------

class TestSystemDispatch:
    def test_creates_assignment_with_system_user_created_by(self, factory):
        from uk_management_bot.config.settings import settings
        SF = _seed(factory, status=C.REQUEST_STATUS_NEW)
        # seed system-user (created_by для SYSTEM-назначений, PR2d)
        s = SF()
        s.add(User(id=1, telegram_id=settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID,
                   first_name="System", roles='["manager"]', active_role="manager",
                   status="approved", language="ru"))
        s.commit()
        s.close()
        sysp = PrincipalRef(kind="system", user_id=None,
                            source="dispatcher", system_actor="dispatcher")
        out = run_command_sync(
            SF, "260610-001", sysp,
            ActionCommand("sys-1", Action.SYSTEM_DISPATCH_ASSIGN, {"executor_id": 4}))
        assert out.new_status == C.REQUEST_STATUS_IN_PROGRESS  # Новая→В работе
        s = SF()
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.executor_id == 4
        ra = s.query(RequestAssignment).filter_by(
            request_number="260610-001", status="active").first()
        assert ra is not None
        assert ra.created_by == 1  # seeded system-user, НЕ None (created_by NOT NULL)
        s.close()


# ---------------------------------------------------------------------------
# MANAGER_CONFIRM — первый canonical-writer
# ---------------------------------------------------------------------------

class TestManagerConfirm:
    def test_writes_canon_completed(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_EXECUTED)
        out = run_command_sync(
            SF, "260610-001", _mgr(),
            ActionCommand("cmd-1", Action.MANAGER_CONFIRM, {}),
        )
        assert isinstance(out, CommandOutcome)
        assert out.no_op is False
        assert out.new_status == C.REQUEST_STATUS_COMPLETED  # canonical-write
        assert out.new_canon_status == C.REQUEST_STATUS_COMPLETED

    def test_persisted_in_fresh_session(self, factory):
        """run_command владеет своей tx — НОВАЯ сессия видит коммит."""
        SF = _seed(factory, status=C.REQUEST_STATUS_EXECUTED)
        run_command_sync(SF, "260610-001", _mgr(),
                         ActionCommand("cmd-1", Action.MANAGER_CONFIRM, {}))
        s = SF()
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.status == C.REQUEST_STATUS_COMPLETED
        assert req.manager_confirmed is True
        assert req.manager_confirmed_by == 3
        s.close()

    def test_audit_and_outbox_in_same_tx(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_EXECUTED)
        run_command_sync(SF, "260610-001", _mgr(),
                         ActionCommand("cmd-1", Action.MANAGER_CONFIRM, {}))
        s = SF()
        assert s.query(AuditLog).filter_by(action="request_status_changed").count() == 1
        # public-проекция меняется (Выполнена→Исполнено) → webhook поставлен
        wh = s.query(WebhookOutbox).all()
        assert len(wh) == 1
        s.close()

    def test_repeat_no_op_if_same(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_EXECUTED)
        run_command_sync(SF, "260610-001", _mgr(),
                         ActionCommand("c1", Action.MANAGER_CONFIRM, {}))
        out2 = run_command_sync(SF, "260610-001", _mgr(),
                                ActionCommand("c2", Action.MANAGER_CONFIRM, {}))
        assert out2.no_op is True
        s = SF()
        # повтор не плодит audit/outbox
        assert s.query(AuditLog).count() == 1
        assert s.query(WebhookOutbox).count() == 1
        s.close()

    def test_non_manager_rejected(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_EXECUTED)
        with pytest.raises(NotAuthorized):
            run_command_sync(SF, "260610-001", _owner(),
                             ActionCommand("c1", Action.MANAGER_CONFIRM, {}))
        s = SF()
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.status == C.REQUEST_STATUS_EXECUTED  # откат, ничего не записано
        assert s.query(AuditLog).count() == 0
        s.close()


# ---------------------------------------------------------------------------
# APPLICANT_ACCEPT — domain_op create_rating
# ---------------------------------------------------------------------------

class TestApplicantAccept:
    def test_creates_rating_and_approves(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_COMPLETED)
        out = run_command_sync(
            SF, "260610-001", _owner(),
            ActionCommand("c1", Action.APPLICANT_ACCEPT, {"rating": 5}),
        )
        assert out.new_status == C.REQUEST_STATUS_APPROVED
        s = SF()
        r = s.query(Rating).filter_by(request_number="260610-001").first()
        assert r is not None and r.rating == 5 and r.user_id == 2
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.status == C.REQUEST_STATUS_APPROVED
        assert req.completed_at is not None
        s.close()

    def test_repeat_rejected(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_COMPLETED)
        run_command_sync(SF, "260610-001", _owner(),
                         ActionCommand("c1", Action.APPLICANT_ACCEPT, {"rating": 5}))
        with pytest.raises(RepeatRejected):
            run_command_sync(SF, "260610-001", _owner(),
                             ActionCommand("c2", Action.APPLICANT_ACCEPT, {"rating": 4}))
        s = SF()
        assert s.query(Rating).count() == 1  # дубля нет
        s.close()

    def test_non_owner_rejected(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_COMPLETED)
        stranger = PrincipalRef(kind="user", user_id=4, source="telegram")
        with pytest.raises(NotAuthorized):
            run_command_sync(SF, "260610-001", stranger,
                             ActionCommand("c1", Action.APPLICANT_ACCEPT, {"rating": 5}))


# ---------------------------------------------------------------------------
# APPLICANT_RETURN — канон «Возвращена» (после cutover PR3+4 пишется напрямую)
# ---------------------------------------------------------------------------

class TestApplicantReturn:
    def test_writes_returned_flag(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_COMPLETED)
        out = run_command_sync(
            SF, "260610-001", _owner(),
            ActionCommand("c1", Action.APPLICANT_RETURN,
                          {"return_reason": "не доделано"}),
        )
        assert out.new_canon_status == "Возвращена"
        assert out.new_status == "Возвращена"  # canonical-write (cutover PR4)
        assert out.public_status == C.REQUEST_STATUS_COMPLETED  # проекция наружу
        s = SF()
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.status == "Возвращена"  # хранится канон напрямую
        assert req.is_returned is True      # исторический флаг сохранён
        assert req.return_reason == "не доделано"
        assert req.returned_by == 2
        s.close()

    def test_no_webhook_when_public_unchanged(self, factory):
        """Возврат не меняет public-проекцию (Исполнено→Исполнено) → нет webhook,
        но audit пишется."""
        SF = _seed(factory, status=C.REQUEST_STATUS_COMPLETED)
        run_command_sync(SF, "260610-001", _owner(),
                         ActionCommand("c1", Action.APPLICANT_RETURN,
                                       {"return_reason": "x"}))
        s = SF()
        assert s.query(AuditLog).count() == 1
        assert s.query(WebhookOutbox).count() == 0
        s.close()


# ---------------------------------------------------------------------------
# Прочее
# ---------------------------------------------------------------------------

class TestExecutorActions:
    def _add_shift(self, SF, user_id):
        from datetime import datetime, timezone
        s = SF()
        s.add(Shift(user_id=user_id, status="active",
                    start_time=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc)))
        s.commit()
        s.close()

    def _exec(self):
        return PrincipalRef(kind="user", user_id=4, source="telegram")

    def test_complete_requires_active_shift(self, factory):
        """Канон PR0 Р2: завершение требует активную смену."""
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS, executor_id=4)
        with pytest.raises(NotAuthorized):
            run_command_sync(SF, "260610-001", self._exec(),
                             ActionCommand("c", Action.EXECUTOR_COMPLETE, {}))

    def test_complete_with_shift_writes_executed(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS, executor_id=4)
        self._add_shift(SF, 4)
        out = run_command_sync(
            SF, "260610-001", self._exec(),
            ActionCommand("c", Action.EXECUTOR_COMPLETE,
                          {"completion_report": "готово"}),
        )
        assert out.new_status == C.REQUEST_STATUS_EXECUTED
        s = SF()
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.completion_report == "готово"
        s.close()

    def test_purchase_writes_requested_materials(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS, executor_id=4)
        self._add_shift(SF, 4)
        run_command_sync(SF, "260610-001", self._exec(),
                         ActionCommand("c", Action.EXECUTOR_PURCHASE,
                                       {"requested_materials": "трубы"}))
        s = SF()
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.status == C.REQUEST_STATUS_PURCHASE
        assert req.requested_materials == "трубы"
        s.close()

    def test_resume_from_purchase(self, factory):
        """EXECUTOR_RESUME: Закуп→В работе (self-resume, продуктовое решение)."""
        SF = _seed(factory, status=C.REQUEST_STATUS_PURCHASE, executor_id=4)
        self._add_shift(SF, 4)
        out = run_command_sync(SF, "260610-001", self._exec(),
                               ActionCommand("c", Action.EXECUTOR_RESUME, {}))
        assert out.new_status == C.REQUEST_STATUS_IN_PROGRESS

    def test_unassigned_executor_rejected(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS, executor_id=999)
        self._add_shift(SF, 4)
        with pytest.raises(NotAuthorized):
            run_command_sync(SF, "260610-001", self._exec(),
                             ActionCommand("c", Action.EXECUTOR_COMPLETE, {}))


class TestCancel:
    def test_manager_cancel_appends_notes(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS)
        out = run_command_sync(
            SF, "260610-001", _mgr(),
            ActionCommand("c", Action.CANCEL,
                          {"reason": "дубль", "notes": "\n\nотменено менеджером"}),
        )
        assert out.new_status == C.REQUEST_STATUS_CANCELLED
        s = SF()
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.status == C.REQUEST_STATUS_CANCELLED
        assert "отменено менеджером" in (req.notes or "")
        s.close()

    def test_bare_cancel_succeeds(self, factory):
        """PR2b: reason опционален — дашборд-drag в «Отменена» шлёт голый статус."""
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS)
        out = run_command_sync(SF, "260610-001", _mgr(),
                               ActionCommand("c", Action.CANCEL, {}))
        assert out.new_status == C.REQUEST_STATUS_CANCELLED


class TestManagerComplete:
    """PR2a-7: менеджерский MANAGER_COMPLETE → Выполнена (shortcut-аналог
    EXECUTOR_COMPLETE, authorize=_is_manager, без активной смены/назначения)."""

    def test_writes_executed_from_in_progress(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS)
        out = run_command_sync(SF, "260610-001", _mgr(),
                               ActionCommand("c", Action.MANAGER_COMPLETE, {}))
        assert out.new_status == C.REQUEST_STATUS_EXECUTED
        s = SF()
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.status == C.REQUEST_STATUS_EXECUTED
        assert req.completed_at is None  # канон: completed_at ставит только приёмка
        s.close()

    def test_writes_executed_from_purchase(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_PURCHASE)
        out = run_command_sync(SF, "260610-001", _mgr(),
                               ActionCommand("c", Action.MANAGER_COMPLETE, {}))
        assert out.new_status == C.REQUEST_STATUS_EXECUTED

    def test_clears_returned_flag(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_CLARIFICATION, is_returned=True)
        run_command_sync(SF, "260610-001", _mgr(),
                         ActionCommand("c", Action.MANAGER_COMPLETE, {}))
        s = SF()
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.is_returned is False
        s.close()

    def test_non_manager_rejected(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS)
        with pytest.raises(NotAuthorized):
            run_command_sync(SF, "260610-001", _owner(),
                             ActionCommand("c", Action.MANAGER_COMPLETE, {}))

    def test_rejected_from_new(self, factory):
        from uk_management_bot.utils.request_workflow import InvalidTransition
        SF = _seed(factory, status=C.REQUEST_STATUS_NEW)
        with pytest.raises(InvalidTransition):
            run_command_sync(SF, "260610-001", _mgr(),
                             ActionCommand("c", Action.MANAGER_COMPLETE, {}))


class TestClarifyRequest:
    """PR2a-7: CLARIFY_REQUEST из Новая/В работе → Уточнение + notes APPEND."""

    def test_writes_clarification_and_notes(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS)
        out = run_command_sync(
            SF, "260610-001", _mgr(),
            ActionCommand("c", Action.CLARIFY_REQUEST,
                          {"question": "уточните адрес", "notes": "\n\nвопрос менеджера"}))
        assert out.new_status == C.REQUEST_STATUS_CLARIFICATION
        s = SF()
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.status == C.REQUEST_STATUS_CLARIFICATION
        assert "вопрос менеджера" in (req.notes or "")
        s.close()

    def test_allowed_from_purchase(self, factory):
        """PR2b: канон расширен — Закуп→Уточнение разрешён менеджеру (дашборд-ребро)."""
        SF = _seed(factory, status=C.REQUEST_STATUS_PURCHASE)
        out = run_command_sync(SF, "260610-001", _mgr(),
                               ActionCommand("c", Action.CLARIFY_REQUEST,
                                             {"question": "q"}))
        assert out.new_status == C.REQUEST_STATUS_CLARIFICATION

    def test_rejected_from_executed(self, factory):
        from uk_management_bot.utils.request_workflow import InvalidTransition
        SF = _seed(factory, status=C.REQUEST_STATUS_EXECUTED)
        with pytest.raises(InvalidTransition):
            run_command_sync(SF, "260610-001", _mgr(),
                             ActionCommand("c", Action.CLARIFY_REQUEST,
                                           {"question": "q"}))

    def test_non_manager_rejected(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS)
        with pytest.raises(NotAuthorized):
            run_command_sync(SF, "260610-001", _owner(),
                             ActionCommand("c", Action.CLARIFY_REQUEST,
                                           {"question": "q"}))


class TestManagerPurchase:
    """PR2b: менеджерский MANAGER_PURCHASE → Закуп (дашборд-рёбра Новая/В работе→Закуп).
    requested_materials опционален (Kanban-drag шлёт только статус)."""

    def test_writes_purchase_from_new(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_NEW)
        out = run_command_sync(SF, "260610-001", _mgr(),
                               ActionCommand("c", Action.MANAGER_PURCHASE, {}))
        assert out.new_status == C.REQUEST_STATUS_PURCHASE

    def test_writes_purchase_from_in_progress_with_materials(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_IN_PROGRESS)
        run_command_sync(SF, "260610-001", _mgr(),
                         ActionCommand("c", Action.MANAGER_PURCHASE,
                                       {"requested_materials": "трубы"}))
        s = SF()
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.status == C.REQUEST_STATUS_PURCHASE
        assert req.requested_materials == "трубы"
        s.close()

    def test_non_manager_rejected(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_NEW)
        with pytest.raises(NotAuthorized):
            run_command_sync(SF, "260610-001", _owner(),
                             ActionCommand("c", Action.MANAGER_PURCHASE, {}))


class TestManagerReturnToWork:
    """PR2b: канон расширен — Исполнено→В работе менеджером (re-open подтверждённой)."""

    def test_return_from_completed_clears_confirmed(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_COMPLETED, manager_confirmed=True)
        out = run_command_sync(SF, "260610-001", _mgr(),
                               ActionCommand("c", Action.MANAGER_RETURN_TO_WORK, {}))
        assert out.new_status == C.REQUEST_STATUS_IN_PROGRESS
        s = SF()
        req = s.query(Request).filter_by(request_number="260610-001").first()
        assert req.status == C.REQUEST_STATUS_IN_PROGRESS
        assert req.manager_confirmed is False
        assert req.is_returned is False
        s.close()


class TestRunnerContract:
    def test_request_not_found(self, factory):
        SF = _seed(factory, status=C.REQUEST_STATUS_EXECUTED)
        with pytest.raises(RequestNotFound):
            run_command_sync(SF, "999999-999", _mgr(),
                             ActionCommand("c1", Action.MANAGER_CONFIRM, {}))

    def test_post_commit_intents_are_best_effort_only(self, factory):
        """В CommandOutcome — только realtime/notify (durable audit/outbox в tx)."""
        SF = _seed(factory, status=C.REQUEST_STATUS_EXECUTED)
        out = run_command_sync(SF, "260610-001", _mgr(),
                               ActionCommand("c1", Action.MANAGER_CONFIRM, {}))
        kinds = {i.kind for i in out.post_commit_intents}
        assert kinds <= {"realtime", "notify"}
        assert "notify" in kinds

    def test_async_is_coroutine(self):
        assert asyncio.iscoroutinefunction(run_command_async)


# ---------------------------------------------------------------------------
# Parity sync/async — общий чистый _decide гарантирует эквивалентность; тест
# защищает от расхождения ORM-I/O обёрток. Async-движок прогоняется на
# in-memory aiosqlite (StaticPool — общая БД между сессиями factory).
# ---------------------------------------------------------------------------

async def _async_run(status, command):
    """Поднять async aiosqlite-движок, засеять заявку, прогнать run_command_async."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    AF = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with AF() as s:
        s.add(User(id=3, telegram_id=3, first_name="Mgr", roles='["manager"]',
                   active_role="manager", status="approved", language="ru"))
        s.add(Request(request_number="260610-001", user_id=2, category="c",
                      description="d", urgency="low", status=status))
        await s.commit()
    try:
        return await run_command_async(AF, "260610-001", _mgr(), command)
    finally:
        await engine.dispose()


class TestParity:
    def test_sync_async_parity(self, factory):
        """Один и тот же MANAGER_CONFIRM через sync и async → идентичный outcome."""
        SF = _seed(factory, status=C.REQUEST_STATUS_EXECUTED)
        sync_out = run_command_sync(SF, "260610-001", _mgr(),
                                    ActionCommand("c", Action.MANAGER_CONFIRM, {}))
        async_out = asyncio.run(
            _async_run(C.REQUEST_STATUS_EXECUTED,
                       ActionCommand("c", Action.MANAGER_CONFIRM, {})))
        assert async_out.new_status == sync_out.new_status
        assert async_out.new_canon_status == sync_out.new_canon_status
        assert async_out.public_status == sync_out.public_status
        assert async_out.no_op == sync_out.no_op
        assert {i.kind for i in async_out.post_commit_intents} == \
               {i.kind for i in sync_out.post_commit_intents}
