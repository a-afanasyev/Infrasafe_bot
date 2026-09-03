"""MANAGER_CHANGE_CATEGORY → уведомление ТОЛЬКО исполнителю (решение владельца
2026-09-03): житель ярлыка не видит, исполнитель «В работе» узнаёт, что заявка
стала другого профиля. Текст несёт локализованную новую категорию."""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.workflow_notifications import (
    _NOTIFY_MATRIX,
    collect_notify_messages_sync,
)
from uk_management_bot.utils.constants import REQUEST_STATUS_IN_PROGRESS
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.request_workflow import Action

NUMBER = "260903-001"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed(db, executor_lang="uz"):
    db.add(User(id=2, telegram_id=200, first_name="Owner", roles='["applicant"]',
                status="approved", language="ru"))
    db.add(User(id=4, telegram_id=400, first_name="Exec", roles='["executor"]',
                status="approved", language=executor_lang))
    db.add(Request(request_number=NUMBER, user_id=2, executor_id=4,
                   category="plumbing", description="d", urgency="low",
                   status=REQUEST_STATUS_IN_PROGRESS, address="Дом <1>"))
    db.commit()


def _intent():
    return SimpleNamespace(kind="notify", data={
        "action": Action.MANAGER_CHANGE_CATEGORY.value, "request_number": NUMBER})


def test_matrix_targets_only_executor():
    roles, key = _NOTIFY_MATRIX[Action.MANAGER_CHANGE_CATEGORY]
    assert roles == ("executor",)
    assert key == "notifications.workflow.category_changed"


def test_only_executor_gets_message_in_own_language_with_localized_category(db):
    _seed(db, executor_lang="uz")
    messages = collect_notify_messages_sync(db, NUMBER, [_intent()])
    assert [tg for tg, _ in messages] == [400]
    text = messages[0][1]
    assert text == get_text(
        "notifications.workflow.category_changed", language="uz",
        request_number=NUMBER, category="Santexnika", address="Дом &lt;1&gt;")
    assert "Santexnika" in text and "&lt;1&gt;" in text   # локализовано и экранировано


def test_locale_keys_exist_in_both_languages():
    for lang in ("ru", "uz"):
        text = get_text("notifications.workflow.category_changed", language=lang,
                        request_number=NUMBER, category="X", address="Y")
        assert not text.startswith("notifications."), lang
        assert NUMBER in text and "X" in text
