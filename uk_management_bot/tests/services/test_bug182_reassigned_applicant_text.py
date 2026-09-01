"""BUG-182: жителю при СМЕНЕ исполнителя — свой текст, а не повтор «принята в работу».

Матрица интентов не знает, менялся исполнитель или появился (интент несёт
только действие и номер), поэтому признак `reassigned` приходит от
вызывающего, который видит `outcome.old_state.executor_id`. Решение владельца
2026-09-01: уведомлять при смене отдельным текстом
(`notifications.workflow.reassigned`).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.request_workflow import Action

NUMBER = "260901-001"
APPLICANT_ID, NEW_EXECUTOR_ID = 1, 2


@pytest.fixture()
def db():
    from uk_management_bot.database.models.request import Request
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.session import Base

    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    session.add(User(id=APPLICANT_ID, telegram_id=100, roles='["applicant"]',
                     status="approved", language="uz"))
    session.add(User(id=NEW_EXECUTOR_ID, telegram_id=200, roles='["executor"]',
                     status="approved", language="ru"))
    session.add(Request(request_number=NUMBER, user_id=APPLICANT_ID,
                        executor_id=NEW_EXECUTOR_ID, category="electricity",
                        description="d", address="Дом 1", status="В работе"))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _assign_intent():
    return [SimpleNamespace(kind="notify",
                            data={"action": Action.MANAGER_ASSIGN.value})]


@pytest.mark.parametrize("language", ["ru", "uz"])
def test_reassigned_template_exists_in_both_locales(language):
    text = get_text("notifications.workflow.reassigned", language=language,
                    request_number=NUMBER, address="Дом 1", category="c")
    assert not text.startswith("notifications."), \
        f"нет шаблона reassigned в локали {language}"
    assert NUMBER in text


class TestCollectMessages:
    def test_reassign_renders_reassigned_text_for_applicant(self, db):
        from uk_management_bot.services.workflow_notifications import (
            collect_notify_messages_sync,
        )

        messages = dict(collect_notify_messages_sync(
            db, NUMBER, _assign_intent(), reassigned=True))
        # Язык ПОЛУЧАТЕЛЯ: житель в фикстуре uz.
        assert messages[100] == get_text(
            "notifications.workflow.reassigned", language="uz",
            request_number=NUMBER, address="Дом 1", category="electricity")

    def test_reassign_keeps_executor_work_order(self, db):
        """Новому исполнителю — тот же наряд, что и при первичном назначении."""
        from uk_management_bot.services.workflow_notifications import (
            collect_notify_messages_sync,
        )

        base = dict(collect_notify_messages_sync(db, NUMBER, _assign_intent()))
        reassigned = dict(collect_notify_messages_sync(
            db, NUMBER, _assign_intent(), reassigned=True))
        assert reassigned[200] == base[200]

    def test_primary_assign_still_renders_assigned_text(self, db):
        from uk_management_bot.services.workflow_notifications import (
            collect_notify_messages_sync,
        )

        messages = dict(collect_notify_messages_sync(db, NUMBER, _assign_intent()))
        assert messages[100] == get_text(
            "notifications.workflow.assigned", language="uz",
            request_number=NUMBER, address="Дом 1", category="electricity")

    def test_reassigned_flag_does_not_touch_other_actions(self, db):
        """Флаг подменяет ТОЛЬКО жительский ключ назначения."""
        from uk_management_bot.services.workflow_notifications import (
            collect_notify_messages_sync,
        )

        intents = [SimpleNamespace(
            kind="notify", data={"action": Action.EXECUTOR_COMPLETE.value})]
        messages = dict(collect_notify_messages_sync(
            db, NUMBER, intents, reassigned=True))
        assert messages[100] == get_text(
            "notifications.workflow.executed", language="uz",
            request_number=NUMBER, address="Дом 1", category="electricity")


class TestDispatchersAcceptFlag:
    """Все входы диспетчера принимают `reassigned` — иначе API-путь не смог бы
    его передать (detached делегирует в dispatch_notify_intents)."""

    def test_all_entry_points_take_reassigned_kwarg(self):
        import inspect

        from uk_management_bot.services import workflow_notifications as wn

        for fn in (wn.dispatch_notify_intents, wn.dispatch_notify_intents_detached,
                   wn.dispatch_notify_intents_sync, wn.collect_notify_messages_sync):
            assert "reassigned" in inspect.signature(fn).parameters, fn.__name__
