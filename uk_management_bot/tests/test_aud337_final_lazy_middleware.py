"""AUD3-37 финал — ленивая middleware-сессия + auth в worker-потоке.

Контракты, которые держит этот файл:

1. ``LazySession`` не открывает SessionLocal, пока к ней не обратились —
   update конвертированных хендлеров проходит без middleware-сессии вовсе.
2. Первое обращение открывает РОВНО одну сессию; дальше прокси прозрачен.
3. auth_middleware грузит user своей thread-сессией (реальный run_db-путь,
   StaticPool-харнес B1), user приходит detached с читаемыми колонками.

Толстый sqlite-харнес — как в test_aud337_my_shifts_offload.py.
"""

import threading
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database import session as session_mod
from uk_management_bot.database.session import Base, LazySession
from uk_management_bot.database.models.user import User
from uk_management_bot.middlewares import auth as auth_mod

_engine = create_engine(
    "sqlite:///:memory:",
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def thread_sessions(db, monkeypatch):
    monkeypatch.setattr(session_mod, "SessionLocal", _Session)
    return db


async def _noop_handler(event, data):
    data["_handler_called"] = True
    return "ok"


def _seed_user(db, *, tg_id=777, status="approved"):
    user = User(id=1, telegram_id=tg_id, first_name="Иван", last_name="Петров",
                roles='["executor"]', active_role="executor", status=status,
                language="ru")
    db.add(user)
    db.commit()
    return user


# ─────────────────────────── LazySession ───────────────────────────

def test_lazy_session_does_not_open_until_used(monkeypatch):
    calls = []

    def factory():
        calls.append(1)
        return MagicMock(name="real_session")

    monkeypatch.setattr(session_mod, "SessionLocal", factory)
    lazy = LazySession()
    assert lazy.opened is False
    assert calls == []  # создание прокси ≠ открытие сессии


def test_lazy_session_opens_exactly_once_on_first_access(monkeypatch):
    calls = []
    real = MagicMock(name="real_session")

    def factory():
        calls.append(1)
        return real

    monkeypatch.setattr(session_mod, "SessionLocal", factory)
    lazy = LazySession()
    lazy.query("x")
    lazy.commit()
    assert lazy.opened is True
    assert calls == [1]  # одна сессия на все обращения
    real.query.assert_called_once_with("x")
    real.commit.assert_called_once()


def test_lazy_session_proxies_real_queries(thread_sessions):
    _seed_user(thread_sessions, tg_id=555)
    lazy = LazySession()
    row = lazy.query(User).filter(User.telegram_id == 555).first()
    assert row is not None and row.telegram_id == 555
    lazy.close()


# ─────────────────────────── auth в потоке ───────────────────────────

@pytest.mark.asyncio
async def test_auth_loads_user_off_the_event_loop(thread_sessions, monkeypatch):
    """Реальный run_db-путь: юнит auth исполняется НЕ в потоке loop'а."""
    _seed_user(thread_sessions, tg_id=777)
    loop_thread = threading.get_ident()
    seen = {}
    orig_unit = auth_mod._load_auth_user_sync

    def spy_unit(s, telegram_id):
        seen["thread"] = threading.get_ident()
        return orig_unit(s, telegram_id)

    monkeypatch.setattr(auth_mod, "_load_auth_user_sync", spy_unit)

    msg = MagicMock()
    msg.from_user.id = 777
    msg.answer = AsyncMock()
    from aiogram.types import Message
    msg.__class__ = Message  # isinstance-ветка Message в auth

    data = {}
    result = await auth_mod.auth_middleware(_noop_handler, msg, data)

    assert result == "ok"
    assert seen["thread"] != loop_thread
    assert data["user"] is not None
    assert data["user_status"] == "approved"


@pytest.mark.asyncio
async def test_auth_user_is_detached_but_columns_readable(thread_sessions):
    """thread-сессия закрыта — колонки detached-user обязаны читаться."""
    _seed_user(thread_sessions, tg_id=778)

    msg = MagicMock()
    msg.from_user.id = 778
    msg.answer = AsyncMock()
    from aiogram.types import Message
    msg.__class__ = Message

    data = {}
    await auth_mod.auth_middleware(_noop_handler, msg, data)

    user = data["user"]
    # то, что читают потребители data["user"]: роли, статус, язык, имена
    assert user.roles == '["executor"]'
    assert user.active_role == "executor"
    assert user.status == "approved"
    assert user.language == "ru"
    assert user.first_name == "Иван"


@pytest.mark.asyncio
async def test_auth_does_not_open_middleware_lazy_session(thread_sessions):
    """Сквозной инвариант финала: auth-запрос не открывает data["db"]."""
    _seed_user(thread_sessions, tg_id=779)

    msg = MagicMock()
    msg.from_user.id = 779
    msg.answer = AsyncMock()
    from aiogram.types import Message
    msg.__class__ = Message

    lazy = LazySession()
    data = {"db": lazy}
    await auth_mod.auth_middleware(_noop_handler, msg, data)

    assert data["user"] is not None
    assert lazy.opened is False  # middleware-сессия осталась неоткрытой


# ─────────────────────── F2: клавиатура в потоке ───────────────────────

@pytest.mark.asyncio
async def test_contextual_keyboard_loads_roles_off_the_event_loop(thread_sessions, monkeypatch):
    """AUD3-37 F2: get_user_contextual_keyboard грузит роли в worker-потоке."""
    from uk_management_bot.keyboards import base as kb

    _seed_user(thread_sessions, tg_id=880)
    loop_thread = threading.get_ident()
    seen = {}
    orig_unit = kb._load_keyboard_context

    def spy_unit(s, user_id):
        seen["thread"] = threading.get_ident()
        return orig_unit(s, user_id)

    monkeypatch.setattr(kb, "_load_keyboard_context", spy_unit)

    result = await kb.get_user_contextual_keyboard(880)
    assert seen["thread"] != loop_thread
    assert result is not None


def test_keyboard_context_unit_returns_dto_not_orm(db):
    """Юнит возвращает кортеж примитивов — ORM через границу не выходит."""
    from uk_management_bot.keyboards import base as kb

    _seed_user(db, tg_id=881)
    ctx = kb._load_keyboard_context(db, 881)
    roles, active_role, user_status, language = ctx
    assert roles == ["executor"]
    assert (active_role, user_status, language) == ("executor", "approved", "ru")
    assert kb._load_keyboard_context(db, 999999) is None
