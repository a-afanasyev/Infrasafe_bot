"""API мониторинга отключений: /api/v2/news-watch (dashboard + inbox юзербота).

DARK без NEWS_WATCH_ENABLED (404), сервисный токен fail-closed, права
менеджера (board.configure), конвейер — с замоканным LLM.
"""
import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.api.main import app
from uk_management_bot.api.telegram_send import STATUS_ERROR, STATUS_OK, TelegramResult
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.database.models.news_item import NewsItem
from uk_management_bot.database.models.user import User
from uk_management_bot.services.news_watch import pipeline

BASE = "/api/v2/news-watch"
TOKEN = "svc-token-123"


def _user(uid: int, roles: list[str]) -> User:
    return User(id=uid, telegram_id=uid, roles=json.dumps(roles),
                active_role=roles[0] if roles else None, status="approved")


@pytest.fixture(autouse=True)
def _llm_budget(monkeypatch):
    """Бюджет LLM не исчерпан. Гарантии лимитера (Redis) — tests/services/test_news_watch_limiter.py."""
    monkeypatch.setattr(pipeline, "news_watch_llm_allowed", AsyncMock(return_value=True))
    from uk_management_bot.api.news_watch import notify
    monkeypatch.setattr(notify, "_notify_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(notify, "_overflow_allowed", AsyncMock(return_value=True))


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_WATCH_ENABLED", True)
    monkeypatch.setattr(settings, "NEWS_WATCH_SERVICE_TOKEN", TOKEN)


@pytest.fixture(autouse=True)
def _no_telegram(monkeypatch):
    sent = []

    async def fake(chat_id, text, **kw):
        sent.append((chat_id, text))
        return TelegramResult(STATUS_OK, 200)

    from uk_management_bot.api.news_watch import notify
    monkeypatch.setattr(notify.telegram_send, "send_message", fake)
    return sent


@pytest_asyncio.fixture
async def client(db_session_factory):
    clients: list[AsyncClient] = []

    async def override_get_db():
        async with db_session_factory() as session:
            yield session

    def _make(user: User | None) -> AsyncClient:
        app.dependency_overrides[get_db] = override_get_db
        if user is not None:
            app.dependency_overrides[get_current_user] = lambda: user
        else:
            app.dependency_overrides.pop(get_current_user, None)
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(c)
        return c

    yield _make
    for c in clients:
        await c.aclose()
    app.dependency_overrides.clear()


def _verdict(**over):
    base = {"relevant": True, "kind": "water", "starts_at": None, "ends_at": None,
            "summary_ru": "нет воды", "summary_uz": "suv yo'q", "confidence": 0.9}
    base.update(over)
    return base


def _llm(monkeypatch, verdict):
    async def fake(**kwargs):
        return verdict
    monkeypatch.setattr(pipeline, "llm_json_async", fake)


INBOX = {"source_chat_id": -1001, "source_message_id": 7, "chat_title": "Водоканал",
         "text": "Отключение воды 29.10 по ул. Тестовая", "posted_at": "2026-10-28T09:00:00+05:00"}


# ───────────── гейты ─────────────


@pytest.mark.asyncio
async def test_dark_without_flag(client, monkeypatch):
    monkeypatch.setattr(settings, "NEWS_WATCH_ENABLED", False)
    manager = _user(1, ["manager"])
    assert (await client(manager).get(f"{BASE}/config")).status_code == 404
    assert (await client(None).post(f"{BASE}/inbox", json=INBOX,
                                    headers={"X-Service-Token": TOKEN})).status_code == 404


@pytest.mark.asyncio
async def test_inbox_requires_service_token_fail_closed(client, monkeypatch):
    assert (await client(None).post(f"{BASE}/inbox", json=INBOX)).status_code == 401
    assert (await client(None).post(f"{BASE}/inbox", json=INBOX,
                                    headers={"X-Service-Token": "wrong"})).status_code == 401
    assert (await client(None).get(f"{BASE}/sources", headers={"X-Service-Token": "wrong"})).status_code == 401
    monkeypatch.setattr(settings, "NEWS_WATCH_SERVICE_TOKEN", "")
    assert (await client(None).post(f"{BASE}/inbox", json=INBOX,
                                    headers={"X-Service-Token": ""})).status_code == 401


@pytest.mark.asyncio
async def test_manager_routes_require_role(client):
    assert (await client(None).get(f"{BASE}/config")).status_code == 401
    assert (await client(_user(2, ["executor"])).get(f"{BASE}/config")).status_code == 403
    assert (await client(_user(3, ["manager"])).get(f"{BASE}/config")).status_code == 200


# ───────────── конфиг и источники ─────────────


@pytest.mark.asyncio
async def test_config_roundtrip_and_sources_for_watcher(client):
    manager = _user(3, ["manager"])
    payload = {"sources": [{"chat": "https://t.me/Toshkent_Elektr", "title": "Электросети"}],
               "complex_context": "ЖК Тест, ул. Тестовая 1-20", "keywords": ["отключ", "suv"],
               "auto_publish": False, "min_confidence": 0.85, "broadcast": {"dm": True, "residents_groups": False}}
    resp = await client(manager).put(f"{BASE}/config", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["sources"] == [{"chat": "@toshkent_elektr", "title": "Электросети"}]
    assert (await client(manager).get(f"{BASE}/config")).json()["complex_context"] == "ЖК Тест, ул. Тестовая 1-20"
    src = await client(None).get(f"{BASE}/sources", headers={"X-Service-Token": TOKEN})
    assert src.status_code == 200 and src.json() == {"sources": [{"chat": "@toshkent_elektr", "title": "Электросети"}]}


@pytest.mark.asyncio
async def test_config_rejects_bad_values(client):
    manager = _user(3, ["manager"])
    resp = await client(manager).put(f"{BASE}/config", json={"min_confidence": 2})
    assert resp.status_code == 422
    resp = await client(manager).put(f"{BASE}/config", json={"sources": [{"chat": "not a handle!"}]})
    assert resp.status_code == 422


# ───────────── inbox → очередь → решения ─────────────


@pytest.mark.asyncio
async def test_inbox_to_pending_then_publish(client, db_session_factory, monkeypatch, _no_telegram):
    _llm(monkeypatch, _verdict())
    manager = _user(3, ["manager"])
    async with db_session_factory() as s:
        s.add(_user(4, ["manager"]))  # получатель уведомления о pending
        await s.commit()
    headers = {"X-Service-Token": TOKEN}
    resp = await client(None).post(f"{BASE}/inbox", json=INBOX, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending" and body["created"] is True
    assert [c for c, _ in _no_telegram] == [4]

    again = await client(None).post(f"{BASE}/inbox", json=INBOX, headers=headers)
    assert again.json() == {**body, "created": False}

    listed = await client(manager).get(f"{BASE}/items?status=pending")
    assert listed.status_code == 200 and listed.json()["total"] == 1
    item = listed.json()["items"][0]
    assert item["kind"] == "water" and item["summary_ru"] == "нет воды"

    pub = await client(manager).post(f"{BASE}/items/{item['id']}/publish")
    assert pub.status_code == 200 and pub.json()["status"] == "published"
    assert pub.json()["broadcast_status"] == "pending" and pub.json()["decided_by"] == 3
    assert (await client(manager).post(f"{BASE}/items/{item['id']}/publish")).status_code == 409
    assert (await client(manager).post(f"{BASE}/items/{item['id']}/reject")).status_code == 409
    assert (await client(manager).post(f"{BASE}/items/999/publish")).status_code == 404
    assert (await client(manager).post(f"{BASE}/items/{item['id']}/retry-broadcast")).status_code == 409

    async with db_session_factory() as s:
        board = (await s.execute(select(BoardConfig))).scalar_one()
        assert board.data["announcements"][0]["id"] == f"news-{item['id']}"
        row = (await s.execute(select(NewsItem))).scalar_one()
        assert row.status == "published"


@pytest.mark.asyncio
async def test_reject_and_list_filters(client, monkeypatch):
    _llm(monkeypatch, _verdict())
    manager = _user(3, ["manager"])
    headers = {"X-Service-Token": TOKEN}
    created = (await client(None).post(f"{BASE}/inbox", json=INBOX, headers=headers)).json()
    rej = await client(manager).post(f"{BASE}/items/{created['id']}/reject")
    assert rej.status_code == 200 and rej.json()["status"] == "rejected"
    assert (await client(manager).get(f"{BASE}/items?status=pending")).json()["total"] == 0
    assert (await client(manager).get(f"{BASE}/items?status=rejected")).json()["total"] == 1
    assert (await client(manager).get(f"{BASE}/items?status=bogus")).status_code == 422


@pytest.mark.asyncio
async def test_inbox_validation(client):
    headers = {"X-Service-Token": TOKEN}
    assert (await client(None).post(f"{BASE}/inbox", json={**INBOX, "text": ""}, headers=headers)).status_code == 422
    assert (await client(None).post(f"{BASE}/inbox", json={"text": "x"}, headers=headers)).status_code == 422


# ───────────── A11-CODE-01: уведомление менеджеру ─────────────


async def test_pending_notification_strips_tags_and_escapes(client, db_session_factory, monkeypatch,
                                                                     _no_telegram):
    _llm(monkeypatch, _verdict(summary_ru='Нет <b>воды</b> & <a href="https://phish.example">x</a>'))
    async with db_session_factory() as s:
        s.add(_user(4, ["manager"]))
        await s.commit()
    payload = {**INBOX, "chat_title": "Водо<канал> & Co"}
    resp = await client(None).post(f"{BASE}/inbox", json=payload, headers={"X-Service-Token": TOKEN})
    assert resp.status_code == 200, resp.text
    [(chat_id, text)] = _no_telegram
    assert chat_id == 4
    assert "Водо&lt;канал&gt; &amp; Co" in text
    assert "Нет воды &amp; x" in text  # теги вырезаны, остальное экранировано
    assert "<a href" not in text and "&lt;b&gt;" not in text and "&lt;a " not in text


async def test_pending_notification_counts_only_delivered(db_session_factory, monkeypatch):
    """Telegram-400 возвращается результатом, а не исключением — не считать его доставкой."""
    from uk_management_bot.api.news_watch import notify

    async def refuse(chat_id, text, **kw):
        return TelegramResult(STATUS_ERROR, 400, "Bad Request: can't parse entities")

    monkeypatch.setattr(notify.telegram_send, "send_message", refuse)
    async with db_session_factory() as s:
        s.add(_user(4, ["manager"]))
        item = NewsItem(source_chat_id=-1, source_message_id=1, raw_text="x", status="pending",
                        broadcast_status="none")
        s.add(item)
        await s.commit()
        assert await notify.notify_managers_pending(s, item) == 0


async def test_put_config_writes_audit_with_diff(client, db_session_factory):
    """A11-CODE-05: правка источников/автопубликации оставляет след."""
    from uk_management_bot.database.models.audit import AuditLog

    manager = _user(3, ["manager"])
    async with db_session_factory() as s:
        s.add(manager)
        await s.commit()
    body = (await client(manager).get(f"{BASE}/config")).json()
    resp = await client(manager).put(f"{BASE}/config", json={**body, "auto_publish": True})
    assert resp.status_code == 200, resp.text
    async with db_session_factory() as s:
        [row] = (await s.execute(select(AuditLog).where(AuditLog.action == "news_watch_config_updated"))).scalars()
    assert row.user_id == 3 and row.details["changed"] == {"auto_publish": {"before": False, "after": True}}


async def test_put_config_rejects_short_keyword_with_422_and_keeps_config(client, db_session_factory):
    manager = _user(3, ["manager"])
    async with db_session_factory() as s:
        s.add(manager)
        await s.commit()
    body = (await client(manager).get(f"{BASE}/config")).json()
    resp = await client(manager).put(f"{BASE}/config", json={**body, "keywords": ["вод", "ГВ"]})
    assert resp.status_code == 422 and "keywords" in resp.text
    assert (await client(manager).get(f"{BASE}/config")).json()["keywords"] == body["keywords"]


async def test_window_exhausted_sends_one_overflow_notice_then_silence(client, db_session_factory, monkeypatch,
                                                                     _no_telegram):
    """Флуд источника не превращается в шторм DM: сверх окна — одна сводка «смотрите дашборд», потом тишина."""
    from uk_management_bot.api.news_watch import notify

    monkeypatch.setattr(notify, "_notify_allowed", AsyncMock(return_value=False))
    monkeypatch.setattr(notify, "_overflow_allowed", AsyncMock(side_effect=[True, False]))
    _llm(monkeypatch, _verdict())
    async with db_session_factory() as s:
        s.add(_user(4, ["manager"]))
        await s.commit()
    headers = {"X-Service-Token": TOKEN}
    for msg_id in (101, 102):
        resp = await client(None).post(f"{BASE}/inbox", json={**INBOX, "source_message_id": msg_id}, headers=headers)
        assert resp.status_code == 200 and resp.json()["status"] == "pending"
    assert len(_no_telegram) == 1
    assert "дашборде" in _no_telegram[0][1] and "Отключения" in _no_telegram[0][1]


async def test_no_managers_does_not_spend_notify_window(db_session_factory, monkeypatch):
    from uk_management_bot.api.news_watch import notify

    gate = AsyncMock(return_value=True)
    monkeypatch.setattr(notify, "_notify_allowed", gate)
    async with db_session_factory() as s:
        item = NewsItem(source_chat_id=-1, source_message_id=5, raw_text="x", status="pending",
                        broadcast_status="none")
        s.add(item)
        await s.commit()
        assert await notify.notify_managers_pending(s, item) == 0
    gate.assert_not_awaited()


async def test_list_pages_with_offset_and_exposes_next_attempt(client, db_session_factory):
    """«Отсеяны (527)», а список отдавал только последние 50 — остальное было не видно."""
    from datetime import datetime, timezone

    manager = _user(3, ["manager"])
    next_at = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
    async with db_session_factory() as s:
        s.add(manager)
        s.add_all([NewsItem(source_chat_id=-1, source_message_id=i, raw_text=f"n{i}", status="ignored",
                            broadcast_status="failed", broadcast_next_at=next_at) for i in range(1, 6)])
        await s.commit()
    first = (await client(manager).get(f"{BASE}/items?status=ignored&limit=2")).json()
    second = (await client(manager).get(f"{BASE}/items?status=ignored&limit=2&offset=2")).json()
    assert first["total"] == second["total"] == 5
    assert [i["raw_text"] for i in first["items"]] == ["n5", "n4"]
    assert [i["raw_text"] for i in second["items"]] == ["n3", "n2"]
    assert first["items"][0]["broadcast_next_at"].startswith("2026-11-10T09:00")


async def test_event_keywords_round_trip(client, db_session_factory):
    """Ревью: схема API не знала event_keywords — pydantic молча отбрасывал поле."""
    manager = _user(3, ["manager"])
    async with db_session_factory() as s:
        s.add(manager)
        await s.commit()
    body = (await client(manager).get(f"{BASE}/config")).json()
    assert body["event_keywords"], "дефолтные слова-события видны в форме"
    resp = await client(manager).put(f"{BASE}/config", json={**body, "event_keywords": ["отключ", "to’xtat"]})
    assert resp.status_code == 200, resp.text
    assert (await client(manager).get(f"{BASE}/config")).json()["event_keywords"] == ["отключ", "to'xtat"]
