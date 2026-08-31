"""BUG-180 + BUG-181 — переназначение: гонка same_executor и old-notice API-пути.

BUG-180. Преflight бота сверял `request.executor_id` с целью в СВОЕЙ сессии,
ДО команды. Между фазами другой менеджер успевал назначить того же человека —
и команда проходила как «успех»: новая строка RequestAssignment, повторный
наряд исполнителю, повторное «работы начались» жителю. Ветка `no_op` в
`_deliver` этот случай не ловила и не могла: для MANAGER_ASSIGN «В работе» ∈
from_statuses, поэтому check_repeat всегда отдаёт None. Фикс — проверка в
`plan_transition` (исполняется под тем же FOR UPDATE, где строится снимок) с
отдельным исключением `SameExecutor`: бот показывает честное «уже назначена
этому исполнителю», API отдаёт 409.

BUG-181. Уведомление снятому исполнителю (`reassigned_away`) собиралось только
в бот-адаптере (`reassignment._aftermath`); API-путь (PATCH {executor_id} с
дашборда) фазы aftermath не имеет — человек узнавал о снятии по исчезновению
карточки. Фикс — сборка вынесена в `workflow_notifications`
(`collect_reassigned_away_sync` — общая; `notify_reassigned_away_detached` —
для BackgroundTasks API-пути).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.utils.constants import (
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
)
from uk_management_bot.utils.request_workflow import (
    Action,
    SameExecutor,
    WorkflowError,
)

from .test_request_workflow import (  # канон-фикстуры (общий харнес ядра)
    EXECUTOR_ID,
    MANAGER,
    _plan,
    _snap,
)

OTHER_EXECUTOR_ID = EXECUTOR_ID + 1


# ══════════════════════════════════════════════════════════════════════════
# BUG-180 — чистое ядро: plan_transition
# ══════════════════════════════════════════════════════════════════════════


class TestSameExecutorInCore:
    def test_reassign_to_current_executor_raises_same_executor(self):
        snap = _snap(REQUEST_STATUS_IN_PROGRESS, executor=EXECUTOR_ID)
        with pytest.raises(SameExecutor):
            _plan(snap, Action.MANAGER_ASSIGN, MANAGER,
                  {"executor_id": EXECUTOR_ID})

    def test_same_executor_is_a_workflow_error(self):
        """Иерархия: существующие generic-обработчики (`except WorkflowError`)
        не пропустят исключение мимо себя, даже не зная о нём."""
        assert issubclass(SameExecutor, WorkflowError)

    def test_reassign_to_different_executor_still_plans(self):
        snap = _snap(REQUEST_STATUS_IN_PROGRESS, executor=EXECUTOR_ID)
        result = _plan(snap, Action.MANAGER_ASSIGN, MANAGER,
                       {"executor_id": OTHER_EXECUTOR_ID})
        assert any(f == "executor_id" for f, _op, _v in result.patch)

    def test_primary_assign_from_new_is_untouched(self):
        snap = _snap(REQUEST_STATUS_NEW, executor=None)
        result = _plan(snap, Action.MANAGER_ASSIGN, MANAGER,
                       {"executor_id": EXECUTOR_ID})
        assert result.new_canon_status == REQUEST_STATUS_IN_PROGRESS

    def test_legacy_new_with_same_executor_is_a_real_transition(self):
        """У legacy-заявки в «Новой» может висеть executor_id. Назначение того
        же человека двигает СТАТУС («Новая» → «В работе») — это реальное
        изменение, отказ здесь был бы ложным."""
        snap = _snap(REQUEST_STATUS_NEW, executor=EXECUTOR_ID)
        result = _plan(snap, Action.MANAGER_ASSIGN, MANAGER,
                       {"executor_id": EXECUTOR_ID})
        assert result.new_canon_status == REQUEST_STATUS_IN_PROGRESS


# ══════════════════════════════════════════════════════════════════════════
# BUG-180 — раннер: отказ под тем же локом, БД не тронута
# ══════════════════════════════════════════════════════════════════════════


NUMBER = "260101-777"
NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def runner_db():
    from uk_management_bot.database.models.request import Request
    from uk_management_bot.database.models.request_assignment import (
        RequestAssignment,
    )
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.session import Base

    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = Factory()
    db.add(User(id=1, telegram_id=100, roles='["manager"]',
                active_role="manager", status="approved"))
    db.add(User(id=2, telegram_id=200, roles='["executor"]',
                active_role="executor", status="approved"))
    db.add(Request(request_number=NUMBER, user_id=1, category="electricity",
                   description="d", status=REQUEST_STATUS_IN_PROGRESS,
                   urgency="low", executor_id=2))
    db.add(RequestAssignment(request_number=NUMBER, assignment_type="individual",
                             executor_id=2, created_by=1, status="active"))
    db.commit()

    yield db, Factory

    db.close()
    Base.metadata.drop_all(bind=engine)


class TestSameExecutorInRunner:
    def test_runner_refuses_and_writes_nothing(self, runner_db):
        from uk_management_bot.database.models.audit import AuditLog
        from uk_management_bot.database.models.request_assignment import (
            RequestAssignment,
        )
        from uk_management_bot.services.workflow_runner import run_command_sync
        from uk_management_bot.utils.request_workflow import (
            ActionCommand, PrincipalRef,
        )

        db, factory = runner_db
        with pytest.raises(SameExecutor):
            run_command_sync(
                factory, NUMBER,
                PrincipalRef(kind="user", user_id=1, source="telegram"),
                ActionCommand("cmd-1", Action.MANAGER_ASSIGN,
                              {"executor_id": 2}),
                now=NOW,
            )

        db.expire_all()
        rows = db.query(RequestAssignment).filter(
            RequestAssignment.request_number == NUMBER).all()
        assert len(rows) == 1 and rows[0].status == "active", \
            "отказ не имеет права трогать назначения"
        assert db.query(AuditLog).count() == 0, "отказ не пишет audit"


# ══════════════════════════════════════════════════════════════════════════
# BUG-181 — общая сборка old-notice в workflow_notifications
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def notice_db():
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.session import Base

    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Factory()

    db.add(User(id=10, telegram_id=1010, language="uz", roles='["executor"]',
                status="approved"))
    # telegram_id NOT NULL в модели; falsy-значение пинит гвард «слать некуда»
    # тем же критерием, что у _load_users_sync (`if u.telegram_id`).
    db.add(User(id=11, telegram_id=0, language="ru", roles='["executor"]',
                status="approved"))
    db.commit()

    yield db

    db.close()
    Base.metadata.drop_all(bind=engine)


class TestCollectReassignedAway:
    def test_renders_in_recipient_language(self, notice_db):
        from uk_management_bot.services.workflow_notifications import (
            collect_reassigned_away_sync,
        )
        from uk_management_bot.utils.helpers import get_text

        notice = collect_reassigned_away_sync(notice_db, NUMBER, 10)
        assert notice is not None
        telegram_id, text = notice
        assert telegram_id == 1010
        assert text == get_text("notifications.workflow.reassigned_away",
                                language="uz", request_number=NUMBER)

    def test_no_telegram_id_means_no_notice(self, notice_db):
        from uk_management_bot.services.workflow_notifications import (
            collect_reassigned_away_sync,
        )

        assert collect_reassigned_away_sync(notice_db, NUMBER, 11) is None

    def test_unknown_user_means_no_notice(self, notice_db):
        from uk_management_bot.services.workflow_notifications import (
            collect_reassigned_away_sync,
        )

        assert collect_reassigned_away_sync(notice_db, NUMBER, 999) is None
