"""Интеграционный роутинг Group Intake: боевые пайплайны ДВУХ ботов.

Group Intake живёт в выделенном боте (group_intake_main.py). Проверяются обе
стороны:
  * основной бот: group_intake-роутера в нём НЕТ; первым стоит страховочный
    group_silence — групповые тексты/команды не проваливаются в приватные
    хендлеры (класс дефектов BUG-155);
  * групповой бот: собран БОЕВЫМ setup_group_intake_dispatcher() — catch-all
    забирает групповые сообщения, приватные мимо, gint-callback'и наши;
    feed_update с записывающей Bot-сессией: blocked в группе молчит,
    немониторимая группа молчит, и ни одного вызова Bot API.
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

import uk_management_bot.group_intake_main as gi_main
import uk_management_bot.handlers.group_intake as gi
import uk_management_bot.main as main_mod
from uk_management_bot.config.settings import settings
from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.handlers.group_intake import router as group_intake_router
from uk_management_bot.tests.handlers.routing_probe import resolve_ctx

_ORDER = re.findall(r"dp\.include_router\((\w+)\)", Path(main_mod.__file__).read_text())
MAIN_ROUTERS = [getattr(main_mod, name) for name in _ORDER]
GROUP_BOT_ROUTERS = [group_intake_router]

GROUP_INTAKE_MODULE = "uk_management_bot.handlers.group_intake"
GROUP_SILENCE_MODULE = "uk_management_bot.handlers.group_silence"
APPLICANT = {"roles": ["applicant"], "user": None}

REQUEST_TEXT = "В подъезде не горит свет уже второй день, почините пожалуйста"


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


# ─────────────────── основной бот: group_intake ИЗЪЯТ ───────────────────


def test_main_bot_has_no_group_intake_router():
    assert "group_intake_router" not in _ORDER, (
        "group_intake живёт в выделенном боте — в основном ему делать нечего"
    )


def test_main_bot_group_silence_is_first():
    assert _ORDER[0] == "group_silence_router", (
        "страховочный group_silence обязан быть ПЕРВЫМ: без него групповые "
        "тексты проваливаются в приватные хендлеры (BUG-155)"
    )


@pytest.mark.parametrize("text", [
    REQUEST_TEXT,
    "/start",
    "/help",
    "📝 Создать заявку",   # кнопочный текст не запускает приватный FSM
    "✅ Подтвердить",
])
def test_main_bot_swallows_any_group_message(text):
    winner = resolve_ctx(
        MAIN_ROUTERS, make_group_message(text), "message", **APPLICANT
    )
    assert winner == (GROUP_SILENCE_MODULE, "swallow_group_message"), (
        f"групповое сообщение {text!r} ушло в {winner} — просочилось мимо "
        f"страховки в приватные хендлеры"
    )


@pytest.mark.parametrize("text", [REQUEST_TEXT, "/start", "📝 Создать заявку"])
def test_main_bot_private_messages_bypass_group_silence(text):
    winner = resolve_ctx(
        MAIN_ROUTERS, make_private_message(text), "message", **APPLICANT
    )
    # Свободный приватный текст без FSM-состояния может остаться без хендлера
    # (None) — важно лишь, что группо-страховка приватные апдейты не трогает.
    assert winner is None or winner[0] not in (
        GROUP_SILENCE_MODULE, GROUP_INTAKE_MODULE,
    )


# ─────────────────── групповой бот: resolve_ctx ───────────────────


@pytest.mark.parametrize("text", [REQUEST_TEXT, "/start", "болтовня"])
def test_group_bot_takes_any_group_message(text):
    winner = resolve_ctx(
        GROUP_BOT_ROUTERS, make_group_message(text), "message", **APPLICANT
    )
    assert winner == (GROUP_INTAKE_MODULE, "group_message_entry")


def test_group_bot_ignores_private_messages():
    winner = resolve_ctx(
        GROUP_BOT_ROUTERS, make_private_message(REQUEST_TEXT), "message", **APPLICANT
    )
    assert winner is None, "у группового бота нет приватных хендлеров"


@pytest.mark.parametrize("data", ["gint:yes", "gint:no", "gint:other"])
def test_group_bot_takes_gint_callbacks(data):
    winner = resolve_ctx(
        GROUP_BOT_ROUTERS, make_group_callback(data), "callback_query", **APPLICANT
    )
    assert winner == (GROUP_INTAKE_MODULE, "group_intake_callback")


def test_group_bot_ignores_foreign_callbacks():
    winner = resolve_ctx(
        GROUP_BOT_ROUTERS, make_group_callback("accept_request_1"),
        "callback_query", **APPLICANT,
    )
    assert winner is None


# ─────────────── feed_update: боевые Dispatcher'ы + middleware ───────────────


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
    """ОБА боевых Dispatcher'а на модуль (роутеры — синглтоны, второй
    include_router на новом Dispatcher падает «router is already attached»):
      * dp_main — setup_dispatcher() основного бота;
      * dp_group — setup_group_intake_dispatcher() группового.
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

    dp_main = Dispatcher(storage=MemoryStorage())
    main_mod.setup_dispatcher(dp_main)
    dp_group = Dispatcher(storage=MemoryStorage())
    gi_main.setup_group_intake_dispatcher(dp_group)

    session = RecordingSession()
    bot = Bot(token="42:TEST", session=session)
    try:
        yield SimpleNamespace(
            dp_main=dp_main, dp_group=dp_group, bot=bot, session=session,
            classify=classify, db_factory=factory,
        )
    finally:
        mp.undo()
        engine.dispose()


@pytest.fixture()
def live(_live_env):
    """Сброс записей между тестами; сами пайплайны общие на модуль."""
    _live_env.session.calls.clear()
    _live_env.classify.reset_mock()
    return _live_env


async def test_group_bot_blocked_user_is_fully_silent(live):
    """Blocked в группе: ни публичного ответа auth-middleware, ни обработки."""
    db = live.db_factory()
    db.add(User(telegram_id=111, roles='["applicant"]', active_role="applicant",
                status="blocked", language="ru"))
    db.commit()
    db.close()

    update = Update(update_id=1, message=make_group_message(REQUEST_TEXT, from_id=111))
    await live.dp_group.feed_update(live.bot, update)

    assert live.session.calls == [], (
        f"групповой бот ответил заблокированному: {live.session.calls}"
    )
    live.classify.assert_not_awaited()


async def test_group_bot_unmonitored_group_is_fully_silent(live):
    """Approved-житель в группе НЕ из реестра: тишина, LLM не вызывается."""
    db = live.db_factory()
    db.add(User(telegram_id=222, roles='["applicant"]', active_role="applicant",
                status="approved", phone="+998901112233", language="ru"))
    db.commit()
    db.close()

    update = Update(update_id=2, message=make_group_message(REQUEST_TEXT, from_id=222))
    await live.dp_group.feed_update(live.bot, update)

    assert live.session.calls == []
    live.classify.assert_not_awaited()


async def test_main_bot_group_message_produces_no_api_calls(live):
    """Основной бот в группе (нештатно добавлен): страховка молчит и не
    пускает текст в приватные хендлеры — ноль вызовов Bot API."""
    update = Update(update_id=3, message=make_group_message(REQUEST_TEXT, from_id=333))
    await live.dp_main.feed_update(live.bot, update)
    assert live.session.calls == []
    live.classify.assert_not_awaited()


async def test_main_bot_group_start_produces_no_api_calls(live):
    update = Update(update_id=4, message=make_group_message("/start", from_id=444))
    await live.dp_main.feed_update(live.bot, update)
    assert live.session.calls == []
