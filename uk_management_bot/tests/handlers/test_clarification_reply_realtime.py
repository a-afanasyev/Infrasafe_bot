"""Ответ жителя на уточнение не доезжал до открытой доски.

`_apply_reply` пишет ответ в `request.notes` и бампает `updated_at`, но
realtime-события не публикует. У канбана WS — единственный путь обновления
(`useKanban` слушает request.updated), поэтому менеджер с открытой доской не
видел ответа вообще: ни индикатора, ни свежих примечаний. Одна публикация после
commit закрывает это без правок в SPA — тип события фронт уже слушает.

Публикуем в async-слое, а не внутри юнита: `publish_request_event` асинхронна, а
DB-фаза исполняется в worker-потоке через `run_db` (AUD3-07/AUD5-ARCH-1).
"""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base

_engine = create_engine("sqlite:///:memory:", echo=False)
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
def applicant(db):
    user = User(
        telegram_id=555,
        first_name="Житель",
        roles=json.dumps(["applicant"]),
        active_role="applicant",
        status="approved",
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def request_row(db, applicant):
    req = Request(
        request_number="260816-001",
        user_id=applicant.id,
        category="elevator",
        address="Дом 1",
        description="Не работает",
        status="Уточнение",
    )
    db.add(req)
    db.commit()
    return req


class _Message:
    """Минимальный aiogram-Message: хендлеру нужны text, from_user, bot, answer."""

    def __init__(self, text: str, telegram_id: int):
        self.text = text
        self.from_user = SimpleNamespace(id=telegram_id)
        self.bot = SimpleNamespace()
        self.answers: list[str] = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


class _State:
    def __init__(self, data):
        self._data = data
        self.cleared = False

    async def get_data(self):
        return self._data

    async def clear(self):
        self.cleared = True


@pytest.mark.asyncio
async def test_reply_publishes_request_updated(db, request_row, monkeypatch):
    from uk_management_bot.handlers import clarification_replies as mod

    published: list[tuple] = []

    async def _fake_publish(event_type, payload):
        published.append((event_type, payload))

    monkeypatch.setattr(
        "uk_management_bot.services.redis_pubsub.publish_request_event", _fake_publish,
    )

    async def _no_send(*a, **kw):
        return None

    monkeypatch.setattr(
        "uk_management_bot.services.notification_service.send_to_user", _no_send,
    )

    message = _Message("Лифт всё ещё стоит", telegram_id=555)
    state = _State({"request_number": "260816-001"})

    await mod.handle_reply_text(message, state, language="ru", _db=db)

    assert published, "открытая доска обязана узнать об ответе жителя"
    event_type, payload = published[0]
    assert event_type == "request.updated"
    assert payload["number"] == "260816-001"


@pytest.mark.asyncio
async def test_reply_survives_dead_realtime(db, request_row, monkeypatch):
    """Мёртвый Redis не должен стоить жителю его ответа — он уже сохранён."""
    from uk_management_bot.handlers import clarification_replies as mod

    async def _boom(*a, **kw):
        raise RuntimeError("redis down")

    monkeypatch.setattr(
        "uk_management_bot.services.redis_pubsub.publish_request_event", _boom,
    )

    async def _no_send(*a, **kw):
        return None

    monkeypatch.setattr(
        "uk_management_bot.services.notification_service.send_to_user", _no_send,
    )

    message = _Message("Лифт всё ещё стоит", telegram_id=555)
    state = _State({"request_number": "260816-001"})

    await mod.handle_reply_text(message, state, language="ru", _db=db)

    db.refresh(request_row)
    assert "Лифт всё ещё стоит" in (request_row.notes or ""), "ответ обязан остаться в заявке"
