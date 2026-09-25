"""Наряд исполнителю о назначении — с inline-кнопкой «Открыть» (web_app).

Уведомление `notifications.workflow.assigned_executor` приходило голым текстом:
исполнитель читал наряд и шёл искать заявку в меню. Кнопка открывает карточку
заявки исполнителя в TWA (`/uk/twa/exec/tasks/<номер>`). web_app-кнопка
допустима только в личном чате — наряд и шлётся в личку (chat_id =
telegram_id исполнителя). Жителю и прочим текстам кнопка не положена:
у жителя свой раздел TWA, и маршрут исполнителя его отправит обратно.
FRONTEND_URL — bare origin; при пустом кнопки нет (как у webapp_buttons).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.request_workflow import Action

NUMBER = "260925-001"
APPLICANT_ID, EXECUTOR_ID = 1, 2
APPLICANT_TG, EXECUTOR_TG = 100, 200
FRONTEND = "https://example.test"
TASK_URL = f"{FRONTEND}/uk/twa/exec/tasks/{NUMBER}"


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
    session.add(User(id=APPLICANT_ID, telegram_id=APPLICANT_TG,
                     roles='["applicant"]', status="approved", language="ru"))
    session.add(User(id=EXECUTOR_ID, telegram_id=EXECUTOR_TG,
                     roles='["executor"]', status="approved", language="uz"))
    session.add(Request(request_number=NUMBER, user_id=APPLICANT_ID,
                        executor_id=EXECUTOR_ID, category="electricity",
                        description="d", address="Дом 1", status="В работе"))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def frontend(monkeypatch):
    from uk_management_bot.config.settings import settings

    monkeypatch.setattr(settings, "FRONTEND_URL", FRONTEND)
    return FRONTEND


class _FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str, object]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs.get("reply_markup")))
        return True

    def markup_for(self, chat_id):
        (markup,) = [m for cid, _, m in self.sent if cid == chat_id]
        return markup


def _intents(action=Action.MANAGER_ASSIGN):
    return [SimpleNamespace(kind="notify", data={"action": action.value})]


def _single_webapp_url(markup) -> str:
    (row,) = markup.inline_keyboard
    (button,) = row
    assert button.web_app is not None, "нужна именно web_app-кнопка"
    return button.web_app.url


@pytest.mark.parametrize("language", ["ru", "uz"])
def test_open_button_text_exists_in_both_locales(language):
    text = get_text("notifications.workflow.btn_open_request", language=language)
    assert not text.startswith("notifications."), language


class TestSyncDispatch:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("action", [Action.MANAGER_ASSIGN, Action.SYSTEM_DISPATCH_ASSIGN])
    async def test_executor_work_order_has_open_button(self, db, frontend, action):
        from uk_management_bot.services.workflow_notifications import (
            dispatch_notify_intents_sync,
        )

        bot = _FakeBot()
        await dispatch_notify_intents_sync(db, NUMBER, _intents(action), bot=bot)
        markup = bot.markup_for(EXECUTOR_TG)
        assert markup is not None
        assert _single_webapp_url(markup) == TASK_URL
        # Текст кнопки — на языке ПОЛУЧАТЕЛЯ (исполнитель в фикстуре uz).
        assert markup.inline_keyboard[0][0].text == get_text(
            "notifications.workflow.btn_open_request", language="uz")

    @pytest.mark.asyncio
    async def test_applicant_status_has_no_button(self, db, frontend):
        from uk_management_bot.services.workflow_notifications import (
            dispatch_notify_intents_sync,
        )

        bot = _FakeBot()
        await dispatch_notify_intents_sync(db, NUMBER, _intents(), bot=bot)
        assert bot.markup_for(APPLICANT_TG) is None

    @pytest.mark.asyncio
    async def test_no_button_without_frontend_url(self, db, monkeypatch):
        from uk_management_bot.config.settings import settings
        from uk_management_bot.services.workflow_notifications import (
            dispatch_notify_intents_sync,
        )

        monkeypatch.setattr(settings, "FRONTEND_URL", "")
        bot = _FakeBot()
        await dispatch_notify_intents_sync(db, NUMBER, _intents(), bot=bot)
        assert bot.markup_for(EXECUTOR_TG) is None


class TestCollectAndSend:
    """Путь AUD3-37 (переназначение/приёмка из бота): collect → send."""

    def test_messages_stay_pairs(self, db, frontend):
        from uk_management_bot.services.workflow_notifications import (
            collect_notify_messages_sync,
        )

        messages = collect_notify_messages_sync(db, NUMBER, _intents())
        # Контракт (telegram_id, text) сохранён: dict()/распаковка по двое.
        assert set(dict(messages)) == {APPLICANT_TG, EXECUTOR_TG}

    @pytest.mark.asyncio
    async def test_executor_gets_open_button_via_send(self, db, frontend):
        from uk_management_bot.services.workflow_notifications import (
            collect_notify_messages_sync, send_notify_messages,
        )

        bot = _FakeBot()
        messages = collect_notify_messages_sync(db, NUMBER, _intents())
        assert await send_notify_messages(bot, messages) == 2
        assert _single_webapp_url(bot.markup_for(EXECUTOR_TG)) == TASK_URL
        assert bot.markup_for(APPLICANT_TG) is None

    @pytest.mark.asyncio
    async def test_plain_pairs_still_sent_without_markup(self):
        """Другие продюсеры (лифты, планировщик) шлют голые пары."""
        from uk_management_bot.services.workflow_notifications import (
            send_notify_messages,
        )

        bot = _FakeBot()
        assert await send_notify_messages(bot, [(1, "t")]) == 1
        assert bot.sent == [(1, "t", None)]
