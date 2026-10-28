"""API мониторинга отключений: /api/v2/news-watch (dashboard + inbox юзербота).

DARK без NEWS_WATCH_ENABLED (404), сервисный токен fail-closed, права
менеджера (board.configure), конвейер — с замоканным LLM.
"""
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.api.main import app
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
def _flags(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_WATCH_ENABLED", True)
    monkeypatch.setattr(settings, "NEWS_WATCH_SERVICE_TOKEN", TOKEN)


@pytest.fixture(autouse=True)
def _no_telegram(monkeypatch):
    sent = []

    async def fake(chat_id, text, **kw):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(pipeline.telegram_send, "send_message", fake)
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
