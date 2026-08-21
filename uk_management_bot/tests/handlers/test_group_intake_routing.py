"""Интеграционный роутинг Group Intake: боевой пайплайн, а не копия.

Две поверхности:
  * resolve_ctx по РЕАЛЬНОМУ порядку include_router из main.py — кто заберёт
    групповое/приватное сообщение и gint-callback (класс дефектов BUG-155:
    юнит-тест хендлера не видит, доходит ли до него апдейт);
  * настоящий Dispatcher, собранный БОЕВЫМ setup_dispatcher(), + feed_update
    с записывающей Bot-сессией — middleware-цепочка целиком: blocked в группе
    молчит, немониторимая группа молчит, и ни одного вызова Bot API.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User as TgUser
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import uk_management_bot.handlers.group_intake as gi
import uk_management_bot.main as main_mod
from uk_management_bot.config.settings import settings
from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.tests.handlers.routing_probe import resolve_ctx

_ORDER = re.findall(r"dp\.include_router\((\w+)\)", Path(main_mod.__file__).read_text())
ROUTERS = [getattr(main_mod, name) for name in _ORDER]

GROUP_INTAKE_MODULE = "uk_management_bot.handlers.group_intake"
APPLICANT = {"roles": ["applicant"], "user": None}

REQUEST_TEXT = "В подъезде не горит свет уже второй день, почините пожалуйста"


def test_group_intake_router_is_registered_first():
    assert _ORDER[0] == "group_intake_router", (
        "group_intake_router обязан быть ПЕРВЫМ: catch-all групповых сообщений "
        "не работает, если перед ним стоит другой роутер"
    )


def make_group_message(text: str, from_id: int = 1) -> Message:
    user = TgUser(id=from_id, is_bot=False, first_name="Тест")
    chat = Chat(id=-100500, type="supergroup", title="Дом 12")
    return Message(
        message_id=1, date=datetime.now(timezone.utc), chat=chat,
        from_user=user, text=text,
    )


def make_private_message(text: str, from_id: int = 1) -> Message:
    user = TgUser(id=from_id, is_bot=False, first_name="Тест")
    chat = Chat(id=from_id, type="private")
    return Message(
        message_id=1, date=datetime.now(timezone.utc), chat=chat,
        from_user=user, text=text,
    )


def make_group_callback(data: str, from_id: int = 1) -> CallbackQuery:
    user = TgUser(id=from_id, is_bot=False, first_name="Тест")
    chat = Chat(id=-100500, type="supergroup", title="Дом 12")
    message = Message(
        message_id=777, date=datetime.now(timezone.utc), chat=chat,
        from_user=TgUser(id=42, is_bot=True, first_name="Бот"),
    )
    return CallbackQuery(
        id="1", from_user=user, chat_instance="x", data=data, message=message
    )


# ─────────────────── resolve_ctx: кто забирает апдейт ───────────────────


@pytest.mark.parametrize("text", [
    REQUEST_TEXT,
    "/start",                 # групповой /start молчит (не start_router)
    "/help",
    "📝 Создать заявку",       # кнопочный текст не запускает приватный FSM
    "✅ Подтвердить",
])
def test_any_group_message_is_taken_by_group_intake(text):
    winner = resolve_ctx(
        ROUTERS, make_group_message(text), "message", **APPLICANT
    )
    assert winner == (GROUP_INTAKE_MODULE, "group_message_entry"), (
        f"групповое сообщение {text!r} ушло в {winner} — просочилось мимо "
        f"catch-all в приватные хендлеры"
    )


@pytest.mark.parametrize("text", [REQUEST_TEXT, "/start", "📝 Создать заявку"])
def test_private_message_never_hits_group_intake(text):
    winner = resolve_ctx(
        ROUTERS, make_private_message(text), "message", **APPLICANT
    )
    assert winner is None or winner[0] != GROUP_INTAKE_MODULE, (
        f"приватное сообщение {text!r} попало в group_intake: {winner}"
    )


@pytest.mark.parametrize("data", ["gint:yes", "gint:no", "gint:other"])
def test_gint_callbacks_taken_by_group_intake(data):
    winner = resolve_ctx(
        ROUTERS, make_group_callback(data), "callback_query", **APPLICANT
    )
    assert winner == (GROUP_INTAKE_MODULE, "group_intake_callback")


def test_foreign_callback_not_taken_by_group_intake():
    winner = resolve_ctx(
        ROUTERS, make_group_callback("accept_request_1"), "callback_query", **APPLICANT
    )
    assert winner is None or winner[0] != GROUP_INTAKE_MODULE


# ─────────────── feed_update: боевой Dispatcher + middleware ───────────────


class RecordingSession(BaseSession):
    """Bot-сессия без сети: записывает КАЖДЫЙ вызов Bot API. Пустой список
    вызовов = бот молчал по-настоящему (а не «хендлер вернул None»)."""

    def __init__(self):
        super().__init__()
        self.calls: list[str] = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(type(method).__name__)
        raise RuntimeError("no network in tests")

    async def stream_content(self, url, headers=None, timeout=30,
                             chunk_size=65536, raise_for_status=True):
        raise NotImplementedError
        yield b""  # pragma: no cover

    async def close(self):
        pass


@pytest.fixture(scope="module")
def _live_env():
    """Единый боевой Dispatcher на модуль: роутеры — синглтоны, второй
    include_router на новом Dispatcher падает «router is already attached».
    Подмена фабрики сессий — на межпоточный sqlite (run_db/LazySession берут
    SessionLocal module-global lookup'ом)."""
    mp = pytest.MonkeyPatch()
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    import uk_management_bot.database.session as db_session_mod

    mp.setattr(db_session_mod, "SessionLocal", factory)
    mp.setattr(settings, "GROUP_INTAKE_ENABLED", True)
    classify = AsyncMock()
    mp.setattr(gi, "classify_message", classify)

    dp = Dispatcher(storage=MemoryStorage())
    main_mod.setup_dispatcher(dp)  # БОЕВОЙ пайплайн: middleware + роутеры
    session = RecordingSession()
    bot = Bot(token="42:TEST", session=session)
    try:
        yield SimpleNamespace(
            dp=dp, bot=bot, session=session, classify=classify, db_factory=factory
        )
    finally:
        mp.undo()
        engine.dispose()


@pytest.fixture()
def live_dispatcher(_live_env):
    """Сброс записей между тестами; сам пайплайн общий на модуль."""
    _live_env.session.calls.clear()
    _live_env.classify.reset_mock()
    return _live_env


async def test_blocked_user_in_group_is_fully_silent(live_dispatcher):
    """Blocked в группе: ни публичного ответа auth-middleware, ни обработки."""
    db = live_dispatcher.db_factory()
    db.add(User(telegram_id=111, roles='["applicant"]', active_role="applicant",
                status="blocked", language="ru"))
    db.commit()
    db.close()

    update = Update(update_id=1, message=make_group_message(REQUEST_TEXT, from_id=111))
    await live_dispatcher.dp.feed_update(live_dispatcher.bot, update)

    assert live_dispatcher.session.calls == [], (
        f"бот ответил в группу заблокированному: {live_dispatcher.session.calls}"
    )
    live_dispatcher.classify.assert_not_awaited()


async def test_unmonitored_group_is_fully_silent(live_dispatcher):
    """Approved-житель в группе НЕ из реестра: тишина, LLM не вызывается."""
    db = live_dispatcher.db_factory()
    db.add(User(telegram_id=222, roles='["applicant"]', active_role="applicant",
                status="approved", phone="+998901112233", language="ru"))
    db.commit()
    db.close()

    update = Update(update_id=2, message=make_group_message(REQUEST_TEXT, from_id=222))
    await live_dispatcher.dp.feed_update(live_dispatcher.bot, update)

    assert live_dispatcher.session.calls == []
    live_dispatcher.classify.assert_not_awaited()


async def test_group_start_produces_no_api_calls(live_dispatcher):
    """Групповой /start проглатывается catch-all'ом: бот не отвечает."""
    update = Update(update_id=3, message=make_group_message("/start", from_id=333))
    await live_dispatcher.dp.feed_update(live_dispatcher.bot, update)
    assert live_dispatcher.session.calls == []
