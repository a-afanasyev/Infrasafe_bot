"""«Заявку #N взял X» — общий хелпер бота и API (services/group_pool_notify).

Получатели одинаковы для sync (бот) и detached (API) путей: on-shift
исполнители той же группы, кроме взявшего; без смены / чужая специализация —
мимо. Бот-хендлер `claim_request_` зовёт тот же хелпер, а не свою копию.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import uk_management_bot.services.notification_service as notification_service
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services import group_pool_notify as gpn

NUMBER = "260925-001"
CLAIMER = 41


def _rows():
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    end = datetime.now(timezone.utc) + timedelta(hours=7)

    def ex(uid, spec, name=None):
        return User(id=uid, telegram_id=70000 + uid, first_name=name or f"E{uid}",
                    roles='["executor"]', active_role="executor",
                    status="approved", language="ru", specialization=spec)

    return [
        ex(CLAIMER, "plumber", name="Иван <b>"),   # взявший
        ex(42, "plumber"),                         # коллега на смене → да
        ex(43, "plumber"),                         # без смены → нет
        ex(44, "electric"),                        # чужая группа → нет
        *[Shift(user_id=u, status="active", start_time=start, end_time=end)
          for u in (CLAIMER, 42, 44)],
        Request(request_number=NUMBER, user_id=CLAIMER, category="plumbing",
                description="d", status="В работе", urgency="low",
                executor_id=CLAIMER),
        # после взятия назначение individual, группа сохранена как история
        RequestAssignment(request_number=NUMBER, assignment_type="individual",
                          group_specialization="plumber", executor_id=CLAIMER,
                          created_by=CLAIMER, status="active"),
    ]


@pytest.fixture
def fake_bot(monkeypatch):
    bot = MagicMock()
    bot.send_message = AsyncMock()
    monkeypatch.setattr(notification_service, "_get_shared_bot", lambda: bot)
    return bot


def _chat_ids(bot):
    return [c.kwargs["chat_id"] for c in bot.send_message.await_args_list]


def test_detached_notifies_only_group_peers_on_shift(fake_bot, monkeypatch):
    async def run():
        engine = create_async_engine(
            "sqlite+aiosqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession,
                                     expire_on_commit=False)
        async with factory() as s:
            s.add_all(_rows())
            await s.commit()
        monkeypatch.setattr("uk_management_bot.database.session.AsyncSessionLocal",
                            factory)
        try:
            return await gpn.notify_group_pool_claimed_detached(NUMBER, CLAIMER)
        finally:
            await engine.dispose()

    assert asyncio.run(run()) == 1
    assert _chat_ids(fake_bot) == [70042]
    call = fake_bot.send_message.await_args
    assert call.kwargs["parse_mode"] == "HTML"
    assert "Иван &lt;b&gt;" in call.kwargs["text"] and NUMBER in call.kwargs["text"]


def test_sync_path_same_recipients(fake_bot):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    s.add_all(_rows())
    s.commit()
    claimer = s.get(User, CLAIMER)
    try:
        sent = asyncio.run(gpn.notify_group_pool_claimed_sync(s, NUMBER, claimer))
    finally:
        s.close()
        engine.dispose()
    assert sent == 1
    assert _chat_ids(fake_bot) == [70042]


def test_send_failure_is_swallowed_and_logged_without_raw_exception(fake_bot, caplog):
    class HTTPStatusError(Exception):
        response = SimpleNamespace(status_code=500)

    fake_bot.send_message.side_effect = HTTPStatusError(
        "Server error for url https://api.telegram.org/botSECRET/sendMessage")
    peer = SimpleNamespace(id=42, telegram_id=70042, language="ru",
                           roles='["executor"]', active_role="executor",
                           specialization="plumber")
    caplog.set_level("DEBUG", logger=gpn.__name__)
    sent = asyncio.run(gpn._send(NUMBER, "X", [peer]))
    assert sent == 0
    assert "botSECRET" not in caplog.text
    assert "HTTPStatusError (HTTP 500)" in caplog.text


def test_bot_claim_handler_uses_shared_helper(monkeypatch):
    """Бот-хендлер `claim_request_` уведомляет группу через общий хелпер."""
    import contextlib

    import uk_management_bot.handlers.requests.executor as ex_mod

    user = SimpleNamespace(id=CLAIMER, first_name="Иван")
    db = MagicMock()

    @contextlib.contextmanager
    def fake_scope(_db):
        yield db

    svc = MagicMock()
    svc.get_user_by_telegram_id.return_value = user
    monkeypatch.setattr(ex_mod, "_db_scope", fake_scope)
    monkeypatch.setattr(ex_mod, "get_user_language", lambda *_a: "ru")
    monkeypatch.setattr(ex_mod, "RequestHandlerService", lambda _db: svc)
    monkeypatch.setattr(ex_mod, "_run_executor_command",
                        lambda *_a: (object(), None))
    monkeypatch.setattr(ex_mod, "_render_group_pool", AsyncMock())
    helper = AsyncMock(return_value=1)
    monkeypatch.setattr(ex_mod, "notify_group_pool_claimed_sync", helper)

    callback = MagicMock()
    callback.data = f"claim_request_{NUMBER}"
    callback.id = "cb1"
    callback.from_user.id = 70041
    callback.answer = AsyncMock()

    asyncio.run(ex_mod.claim_group_request(callback, MagicMock()))

    helper.assert_awaited_once_with(db, NUMBER, user)
