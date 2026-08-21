"""Group Intake фаза 2: менеджерская приёмка (acceptance_mode='manager').

Решение владельца 2026-08-22 (модель №1): staff-репорт принимает менеджер —
его подтверждение (MANAGER_CONFIRM) сразу завершает заявку («Принято»), шага
жительской приёмки и оценки нет. Жительские APPLICANT_ACCEPT/APPLICANT_RETURN
для таких заявок закрыты НА УРОВНЕ КАНОНА (guards), а не в UI.

Три слоя проверок:
1. Guard-матрица plan_transition (чистое ядро): терминальный confirm,
   отказ жительской приёмки/возврата, менеджерские действия как есть.
2. Регресс resident-режима: дефолт ничего не меняет.
3. e2e через run_command_sync на sqlite — настоящая команда, настоящая запись
   (урок переназначения: мок CommandOutcome классовые ошибки не ловит).
"""

from __future__ import annotations

import dataclasses

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import uk_management_bot.utils.constants as C
from uk_management_bot.utils.constants import (
    ACCEPTANCE_MODE_MANAGER,
    ACCEPTANCE_MODE_RESIDENT,
)
from uk_management_bot.utils.request_workflow import (
    Action,
    NotAuthorized,
    Op,
)
from uk_management_bot.utils.request_workflow.specs import allowed_actions

from .test_request_workflow import (  # канон-фикстуры
    EXECUTOR_ID,
    MANAGER,
    NEIGHBOR,
    OWNER,
    _patch_fields,
    _plan,
    _snap,
)


def _staff_snap(status, **kw):
    """Снапшот staff-репорта: как обычный, но acceptance_mode='manager'."""
    base = _snap(status, **kw)
    return dataclasses.replace(
        base,
        request=dataclasses.replace(
            base.request, acceptance_mode=ACCEPTANCE_MODE_MANAGER
        ),
    )


# ═══ MANAGER_CONFIRM терминален для manager-режима ═══


class TestManagerConfirmTerminal:
    def test_confirm_goes_straight_to_approved(self):
        res = _plan(_staff_snap(C.REQUEST_STATUS_EXECUTED),
                    Action.MANAGER_CONFIRM, MANAGER)
        assert res.new_canon_status == C.REQUEST_STATUS_APPROVED
        fields = _patch_fields(res)
        assert fields["status"] == (Op.SET, C.REQUEST_STATUS_APPROVED)
        assert fields["manager_confirmed"] == (Op.SET, True)
        assert fields["completed_at"] == (Op.SET_NOW, None), \
            "терминальное подтверждение обязано фиксировать момент завершения"

    def test_confirm_creates_no_rating(self):
        """Жительской оценки нет — строка ratings не планируется."""
        res = _plan(_staff_snap(C.REQUEST_STATUS_EXECUTED),
                    Action.MANAGER_CONFIRM, MANAGER)
        assert res.domain_ops == ()

    def test_resident_confirm_unchanged(self):
        """Регресс: дефолтный режим — «Исполнено», без completed_at."""
        res = _plan(_snap(C.REQUEST_STATUS_EXECUTED),
                    Action.MANAGER_CONFIRM, MANAGER)
        assert res.new_canon_status == C.REQUEST_STATUS_COMPLETED
        assert "completed_at" not in _patch_fields(res)


# ═══ Жительская приёмка/возврат закрыты гардами ═══


class TestResidentActionsClosed:
    @pytest.mark.parametrize("actor", [OWNER, NEIGHBOR],
                             ids=["owner", "neighbor"])
    def test_accept_refused(self, actor):
        with pytest.raises(NotAuthorized):
            _plan(_staff_snap(C.REQUEST_STATUS_COMPLETED),
                  Action.APPLICANT_ACCEPT, actor, {"rating": 5})

    def test_return_refused_even_for_owner(self):
        with pytest.raises(NotAuthorized):
            _plan(_staff_snap(C.REQUEST_STATUS_COMPLETED),
                  Action.APPLICANT_RETURN, OWNER, {"return_reason": "плохо"})

    def test_not_in_allowed_actions(self):
        """Структурно: у владельца staff-репорта нет ни accept, ни return."""
        acts = allowed_actions(_staff_snap(C.REQUEST_STATUS_COMPLETED), OWNER)
        assert Action.APPLICANT_ACCEPT not in acts
        assert Action.APPLICANT_RETURN not in acts

    def test_resident_accept_and_return_unchanged(self):
        """Регресс: обычная заявка — владелец принимает и возвращает."""
        res = _plan(_snap(C.REQUEST_STATUS_COMPLETED),
                    Action.APPLICANT_ACCEPT, OWNER, {"rating": 5})
        assert res.new_canon_status == C.REQUEST_STATUS_APPROVED
        res = _plan(_snap(C.REQUEST_STATUS_COMPLETED),
                    Action.APPLICANT_RETURN, OWNER, {"return_reason": "плохо"})
        assert res.new_canon_status == C.REQUEST_STATUS_RETURNED


# ═══ Менеджерские инструменты работают как есть ═══


class TestManagerToolsUntouched:
    def test_return_to_work_still_available(self):
        """Менеджер недоволен работой — возврат исполнителю как обычно."""
        res = _plan(_staff_snap(C.REQUEST_STATUS_EXECUTED,
                                executor=EXECUTOR_ID),
                    Action.MANAGER_RETURN_TO_WORK, MANAGER,
                    {"reason": "переделать"})
        assert res.new_canon_status == C.REQUEST_STATUS_IN_PROGRESS

    def test_owner_still_cancels_own_new_request(self):
        """Гард отмены не тронут: владелец-applicant отменяет свою «Новую»
        независимо от режима приёмки (закрыты только приёмка/возврат)."""
        res = _plan(_staff_snap(C.REQUEST_STATUS_NEW), Action.CANCEL, OWNER)
        assert res.new_canon_status == C.REQUEST_STATUS_CANCELLED


# ═══ e2e: настоящая команда против настоящей БД (sqlite) ═══


@pytest.fixture()
def factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Модели импортируются ДО create_all — иначе metadata пуста и таблиц нет.
    from uk_management_bot.database.models import (  # noqa: F401
        audit, rating, request, request_assignment, user, webhook_outbox,
    )
    from uk_management_bot.database.session import Base
    Base.metadata.create_all(bind=engine)
    SF = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield SF
    engine.dispose()


def _seed(SF, *, acceptance_mode, status):
    from uk_management_bot.database.models.request import Request
    from uk_management_bot.database.models.user import User

    s = SF()
    s.add(User(id=2, telegram_id=2, first_name="Staff",
               roles='["executor"]', active_role="executor",
               status="approved", language="ru"))
    s.add(User(id=3, telegram_id=3, first_name="Mgr",
               roles='["manager"]', active_role="manager",
               status="approved", language="ru"))
    s.add(User(id=4, telegram_id=4, first_name="Exec",
               roles='["executor"]', active_role="executor",
               status="approved", language="ru"))
    s.add(Request(
        request_number="260822-001", user_id=2, category="electricity",
        description="d", urgency="high", status=status, executor_id=4,
        acceptance_mode=acceptance_mode, reported_by_user_id=2,
    ))
    s.commit()
    s.close()
    return SF


class TestEndToEnd:
    def test_manager_confirm_writes_approved(self, factory):
        from uk_management_bot.database.models.rating import Rating
        from uk_management_bot.database.models.request import Request
        from uk_management_bot.services.workflow_runner import run_command_sync
        from uk_management_bot.utils.request_workflow import (
            ActionCommand, PrincipalRef,
        )

        SF = _seed(factory, acceptance_mode=ACCEPTANCE_MODE_MANAGER,
                   status=C.REQUEST_STATUS_EXECUTED)
        out = run_command_sync(
            SF, "260822-001",
            PrincipalRef(kind="user", user_id=3, source="telegram"),
            ActionCommand("c1", Action.MANAGER_CONFIRM, {}))

        assert out.new_status == C.REQUEST_STATUS_APPROVED
        assert out.public_status == C.REQUEST_STATUS_APPROVED
        s = SF()
        req = s.query(Request).filter_by(request_number="260822-001").one()
        assert req.status == C.REQUEST_STATUS_APPROVED
        assert req.manager_confirmed is True
        assert req.completed_at is not None
        assert s.query(Rating).count() == 0
        s.close()

    def test_resident_confirm_still_two_step(self, factory):
        from uk_management_bot.database.models.request import Request
        from uk_management_bot.services.workflow_runner import run_command_sync
        from uk_management_bot.utils.request_workflow import (
            ActionCommand, PrincipalRef,
        )

        SF = _seed(factory, acceptance_mode=ACCEPTANCE_MODE_RESIDENT,
                   status=C.REQUEST_STATUS_EXECUTED)
        out = run_command_sync(
            SF, "260822-001",
            PrincipalRef(kind="user", user_id=3, source="telegram"),
            ActionCommand("c1", Action.MANAGER_CONFIRM, {}))

        assert out.new_status == C.REQUEST_STATUS_COMPLETED
        s = SF()
        req = s.query(Request).filter_by(request_number="260822-001").one()
        assert req.status == C.REQUEST_STATUS_COMPLETED
        assert req.completed_at is None
        s.close()

    def test_owner_accept_refused_at_runner_level(self, factory):
        """Даже долетев до раннера, приёмка автором отклоняется каноном."""
        from uk_management_bot.services.workflow_runner import run_command_sync
        from uk_management_bot.utils.request_workflow import (
            ActionCommand, PrincipalRef,
        )

        SF = _seed(factory, acceptance_mode=ACCEPTANCE_MODE_MANAGER,
                   status=C.REQUEST_STATUS_COMPLETED)
        with pytest.raises(NotAuthorized):
            run_command_sync(
                SF, "260822-001",
                PrincipalRef(kind="user", user_id=2, source="telegram"),
                ActionCommand("c1", Action.APPLICANT_ACCEPT, {"rating": 5}))


# ═══ Создание: прокидка acceptance_mode/reported_by до строки БД ═══


def test_create_request_record_persists_staff_fields(factory):
    from uk_management_bot.database.models.request import Request
    from uk_management_bot.services.request_handler_service import (
        RequestHandlerService,
    )

    s = factory()
    from uk_management_bot.database.models.user import User
    s.add(User(id=2, telegram_id=2, first_name="Staff",
               roles='["executor"]', active_role="executor",
               status="approved", language="ru"))
    s.commit()

    service = RequestHandlerService(s)
    service.create_request_record(
        request_number="260822-002", category="electricity", address="a",
        description="d", urgency="high", apartment_id=None, building_id=None,
        yard_id=None, address_type=None, media_files=[], user_id=2,
        source="group", reported_by_user_id=2,
        acceptance_mode=ACCEPTANCE_MODE_MANAGER,
    )
    service.commit()

    req = s.query(Request).filter_by(request_number="260822-002").one()
    assert req.acceptance_mode == ACCEPTANCE_MODE_MANAGER
    assert req.reported_by_user_id == 2

    # Дефолты прочих путей: без новых kwargs — resident/None.
    service.create_request_record(
        request_number="260822-003", category="electricity", address="a",
        description="d", urgency="high", apartment_id=None, building_id=None,
        yard_id=None, address_type=None, media_files=[], user_id=2,
        source="bot",
    )
    service.commit()
    req = s.query(Request).filter_by(request_number="260822-003").one()
    assert req.acceptance_mode == ACCEPTANCE_MODE_RESIDENT
    assert req.reported_by_user_id is None
    s.close()


# ═══ Уведомления: staff-репортёру не предлагают «принять работу» ═══


class TestNotificationKeySubstitution:
    def _request(self, mode):
        from uk_management_bot.database.models.request import Request
        return Request(request_number="260822-001", user_id=2, category="c",
                       description="d", urgency="low", status="Выполнена",
                       acceptance_mode=mode)

    def _targets(self, mode, action):
        from uk_management_bot.services.workflow_notifications import (
            _plan as notify_plan, _resolve_targets,
        )
        from uk_management_bot.utils.request_workflow import EventIntent

        intents = [EventIntent("notify", {"action": action.value,
                                          "request_number": "260822-001"})]
        return _resolve_targets(self._request(mode), notify_plan(intents))

    def test_manager_mode_substitutes_keys(self):
        targets = self._targets(ACCEPTANCE_MODE_MANAGER, Action.MANAGER_CONFIRM)
        assert [k for _, k, _ in targets] == \
            ["notifications.workflow.accepted_by_manager"]
        targets = self._targets(ACCEPTANCE_MODE_MANAGER, Action.EXECUTOR_COMPLETE)
        assert [k for _, k, _ in targets] == \
            ["notifications.workflow.executed_staff"]

    def test_resident_mode_keys_unchanged(self):
        targets = self._targets(ACCEPTANCE_MODE_RESIDENT, Action.MANAGER_CONFIRM)
        assert [k for _, k, _ in targets] == \
            ["notifications.workflow.ready_for_acceptance"]

    @pytest.mark.parametrize("key", [
        "notifications.workflow.executed_staff",
        "notifications.workflow.accepted_by_manager",
    ])
    @pytest.mark.parametrize("lang", ["ru", "uz"])
    def test_new_locale_keys_exist(self, key, lang):
        """get_text для НЕИЗВЕСТНОГО ключа возвращает сам ключ — ловим это."""
        from uk_management_bot.utils.helpers import get_text
        text = get_text(key, language=lang, request_number="X", address="Y")
        assert text != key
