"""Тесты API конфига авто-менеджера: GET/PUT /api/v2/auto-manager-config.

В отличие от board_config, ОБА маршрута приватные: manager ИЛИ admin
(`require_roles` — OR-семантика, см. api/dependencies.py). Валидация payload
делегирована той же `services.auto_manager.config.validate_config`, что и
бот-путь (uk_management_bot/tests/test_auto_manager_window.py) — тесты ниже
проверяют, что она реально применяется через API, а не переизобретена
независимо в Pydantic-схеме.

Паттерн клиента-фабрики (auth как произвольный пользователь/anon) — как
`ticket_client` в test_resource_accounting.py.
"""
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.auto_manager_config import AutoManagerConfig
from uk_management_bot.database.models.user import User
from uk_management_bot.services.ai_manager import breaker
from uk_management_bot.services.auto_manager.config import DEFAULT_CONFIG

PATH = "/api/v2/auto-manager-config"


@pytest.fixture(autouse=True)
def _ai_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", False)


def _user(uid: int, roles: list[str], **kw) -> User:
    return User(
        id=uid,
        telegram_id=uid,
        roles=json.dumps(roles),
        active_role=roles[0] if roles else None,
        status="approved",
        **kw,
    )


def _stored(body: dict) -> dict:
    """Хранимая часть ответа — без read-only полей (`AutoManagerConfigOut`)."""
    return {k: body[k] for k in DEFAULT_CONFIG}


def _valid_payload(**overrides) -> dict:
    payload = dict(DEFAULT_CONFIG)
    payload.update(overrides)
    return payload


@pytest_asyncio.fixture
async def am_client(db_session_factory):
    """Factory → AsyncClient authenticated as `user` (or anonymous if None)."""
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


# ── GET: auth / role gating ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_requires_auth(am_client):
    resp = await am_client(None).get(PATH)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_forbidden_for_neither_manager_nor_admin(am_client):
    resp = await am_client(_user(1, ["applicant"])).get(PATH)
    assert resp.status_code == 403

    resp = await am_client(_user(2, ["executor"])).get(PATH)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_as_manager_returns_default_when_no_row(am_client):
    resp = await am_client(_user(10, ["manager"])).get(PATH)
    assert resp.status_code == 200
    assert _stored(resp.json()) == DEFAULT_CONFIG and resp.json()["ai_available"] is False


@pytest.mark.asyncio
async def test_get_as_admin_returns_default_when_no_row(am_client):
    # Explicit positive admin test: require_roles("manager", "admin") is OR —
    # a subtly wrong require_roles("manager") alone would 403 here.
    resp = await am_client(_user(11, ["admin"])).get(PATH)
    assert resp.status_code == 200
    assert _stored(resp.json()) == DEFAULT_CONFIG and resp.json()["ai_available"] is False


# ── PUT: persistence + updated_by + roundtrip ────────────────────────

@pytest.mark.asyncio
async def test_put_as_manager_persists_and_roundtrips(am_client, db_session_factory):
    manager = _user(20, ["manager"])
    payload = _valid_payload(enabled=True, max_requests_per_run=5)

    put_resp = await am_client(manager).put(PATH, json=payload)
    assert put_resp.status_code == 200
    assert put_resp.json()["enabled"] is True
    assert put_resp.json()["max_requests_per_run"] == 5

    async with db_session_factory() as session:
        result = await session.execute(select(AutoManagerConfig))
        row = result.scalar_one()
        assert row.updated_by == manager.id
        assert row.data["enabled"] is True

    get_resp = await am_client(manager).get(PATH)
    assert get_resp.status_code == 200
    assert get_resp.json()["enabled"] is True
    assert get_resp.json()["max_requests_per_run"] == 5


@pytest.mark.asyncio
async def test_put_as_admin_persists(am_client, db_session_factory):
    # Explicit positive admin test, same reasoning as the GET admin test.
    admin = _user(21, ["admin"])
    payload = _valid_payload(max_requests_per_run=7)

    resp = await am_client(admin).put(PATH, json=payload)
    assert resp.status_code == 200
    assert resp.json()["max_requests_per_run"] == 7

    async with db_session_factory() as session:
        result = await session.execute(select(AutoManagerConfig))
        row = result.scalar_one()
        assert row.updated_by == admin.id


@pytest.mark.asyncio
async def test_put_upserts_single_row(am_client):
    manager = _user(22, ["manager"])
    await am_client(manager).put(PATH, json=_valid_payload(enabled=True))
    resp = await am_client(manager).put(PATH, json=_valid_payload(enabled=False, max_requests_per_run=3))
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    assert resp.json()["max_requests_per_run"] == 3


@pytest.mark.asyncio
async def test_put_rejects_mode_ai_when_flag_off(am_client, db_session_factory):
    """Без AI_MANAGER_ENABLED режим "ai" не сохраняется — GET/PUT не должны
    показывать режим, который на этой площадке не работает."""
    manager = _user(23, ["manager"])
    resp = await am_client(manager).put(PATH, json=_valid_payload(mode="ai"))
    assert resp.status_code == 422

    async with db_session_factory() as session:
        result = await session.execute(select(AutoManagerConfig))
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_put_accepts_mode_ai_when_flag_on(am_client, db_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)
    manager = _user(24, ["manager"])
    resp = await am_client(manager).put(PATH, json=_valid_payload(mode="ai"))
    assert resp.status_code == 200
    assert resp.json()["mode"] == "ai"
    assert resp.json()["ai_available"] is True

    async with db_session_factory() as session:
        row = (await session.execute(select(AutoManagerConfig))).scalar_one()
        assert row.data["mode"] == "ai"

    get_resp = await am_client(manager).get(PATH)
    assert get_resp.json()["mode"] == "ai"


@pytest.mark.asyncio
async def test_get_reports_ai_available_from_flag(am_client, monkeypatch):
    manager = _user(25, ["manager"])
    assert (await am_client(manager).get(PATH)).json()["ai_available"] is False
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)
    assert (await am_client(manager).get(PATH)).json()["ai_available"] is True


@pytest.mark.asyncio
async def test_put_roundtrips_ai_block_and_keeps_defaults_when_omitted(am_client):
    manager = _user(26, ["manager"])
    ai = {**DEFAULT_CONFIG["ai"], "min_confidence": 0.9, "clarify_enabled": False, "dedup_enabled": True}
    resp = await am_client(manager).put(PATH, json=_valid_payload(ai=ai))
    assert resp.status_code == 200
    assert resp.json()["ai"] == ai
    assert (await am_client(manager).get(PATH)).json()["ai"] == ai

    # Клиент без поля `ai` (старый дашборд) не затирает сохранённое: модель
    # подставляет дефолт только когда поля нет вовсе — это дефолт, а не то,
    # что лежит в БД; проверяем, что ответ по-прежнему валиден и `ai` есть.
    legacy = {k: v for k, v in _valid_payload().items() if k != "ai"}
    resp = await am_client(manager).put(PATH, json=legacy)
    assert resp.status_code == 200
    assert resp.json()["ai"] == DEFAULT_CONFIG["ai"]


@pytest.mark.asyncio
async def test_put_rejects_bad_ai_block(am_client):
    manager = _user(27, ["manager"])
    resp = await am_client(manager).put(PATH, json=_valid_payload(ai={"min_confidence": 2}))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_ignores_client_sent_ai_available(am_client):
    """`ai_available` — read-only: клиент шлёт обратно то, что получил, и это
    не должно ни ломать PUT, ни «включать» ИИ."""
    manager = _user(28, ["manager"])
    resp = await am_client(manager).put(PATH, json=_valid_payload(ai_available=True))
    assert resp.status_code == 200
    assert resp.json()["ai_available"] is False


# ── PUT: validation delegated to the SAME validate_config as the bot path ──

@pytest.mark.asyncio
async def test_put_rejects_bad_time_format_same_rule_as_bot_side(am_client):
    # "99:99" is one of test_auto_manager_window.py's reject-list values for
    # validate_config — proves the API path is rejected by the SAME rule,
    # not an independently reimplemented Pydantic field_validator.
    payload = _valid_payload(window_start="99:99")
    resp = await am_client(_user(30, ["manager"])).put(PATH, json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_rejects_out_of_range_max_requests(am_client):
    payload = _valid_payload(max_requests_per_run=51)
    resp = await am_client(_user(31, ["manager"])).put(PATH, json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_rejects_invalid_mode(am_client):
    payload = _valid_payload(mode="invalid")
    resp = await am_client(_user(32, ["manager"])).put(PATH, json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_rejects_invalid_timezone(am_client):
    payload = _valid_payload(timezone="Not/A_Real_Zone")
    resp = await am_client(_user(33, ["manager"])).put(PATH, json=payload)
    assert resp.status_code == 422


# ── PUT: auth / role gating ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_put_requires_auth(am_client):
    resp = await am_client(None).put(PATH, json=_valid_payload())
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_put_forbidden_for_neither_manager_nor_admin(am_client):
    resp = await am_client(_user(40, ["executor"])).put(PATH, json=_valid_payload())
    assert resp.status_code == 403


# ═══ Нормативы сроков аналитики (sla_hours) ═══


def test_sla_hours_default_and_partial_merge():
    from uk_management_bot.services.auto_manager.config import validate_config

    assert validate_config({})["sla_hours"] == {
        "critical": 4, "high": 24, "medium": 72, "low": 168}
    merged = validate_config({"sla_hours": {"critical": 2}})["sla_hours"]
    assert merged == {"critical": 2, "high": 24, "medium": 72, "low": 168}


@pytest.mark.parametrize("bad", [0, -1, 10_000, "4", True, None])
def test_sla_hours_rejects_bad_values(bad):
    from uk_management_bot.services.auto_manager.config import validate_config

    with pytest.raises(ValueError):
        validate_config({"sla_hours": {"high": bad}})


def test_sla_hours_rejects_unknown_key():
    from uk_management_bot.services.auto_manager.config import validate_config

    with pytest.raises(ValueError):
        validate_config({"sla_hours": {"urgent": 5}})


@pytest.mark.asyncio
async def test_put_roundtrips_sla_hours(am_client):
    manager = _user(5101, ["manager"])
    client = am_client(manager)
    sla = {"critical": 3, "high": 12, "medium": 48, "low": 120}
    resp = await client.put(PATH, json=_valid_payload(sla_hours=sla))
    assert resp.status_code == 200, resp.text
    assert (await client.get(PATH)).json()["sla_hours"] == sla


@pytest.mark.asyncio
async def test_put_switching_ai_off_notifies_managers(am_client, monkeypatch):
    """ai → rule через дашборд: менеджерам уходит число заявок на эскалации
    (счёт — sync-сессией в потоке, отправка — API-sender'ом)."""
    from uk_management_bot.api import telegram_send
    from uk_management_bot.api.auto_manager import router as am_router

    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)
    manager = _user(29, ["manager"])
    assert (await am_client(manager).put(PATH, json=_valid_payload(mode="ai"))).status_code == 200

    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(telegram_send, "send_message", fake_send)
    monkeypatch.setattr(am_router, "_collect_switch_off_notices",
                        lambda old, new: [(777, f"{old}->{new}")])
    resp = await am_client(manager).put(PATH, json=_valid_payload(mode="rule"))
    assert resp.status_code == 200
    assert sent == [(777, "ai->rule")]


# ── страница «Правила ИИ»: read-only состояние, новые поля, сброс предохранителя ──


class _FakeRedis:
    """dict-двойник redis: ровно то, что зовёт breaker (exists/incr/ttl/expire/set/get/delete)."""

    def __init__(self):
        self.store, self.ttl_store = {}, {}

    def exists(self, key):
        return 1 if key in self.store else 0

    def incr(self, key):
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])

    def ttl(self, key):
        return self.ttl_store.get(key, -1)

    def expire(self, key, seconds):
        self.ttl_store[key] = seconds

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        if ex is not None:
            self.ttl_store[key] = ex
        return True

    def get(self, key):
        return self.store.get(key)

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)
            self.ttl_store.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr(breaker, "_get_client", lambda: client)
    return client


RESET = f"{PATH}/ai-breaker/reset"


@pytest.mark.asyncio
async def test_get_exposes_typed_ai_status_and_template_defaults(am_client, monkeypatch, fake_redis):
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)
    body = (await am_client(_user(40, ["manager"])).get(PATH)).json()
    assert body["ai_status"] == {"open": False, "open_ttl": 0, "failures": 0}
    assert body["template_defaults"]["sla.executor_overdue"]["placeholders"] == sorted(
        ["request_number", "category", "address", "hours"])
    assert "{request_number}" in body["template_defaults"]["public.assigned"]["uz"]
    assert "газ" in body["base_emergency_keywords"]
    assert body["ai"]["triage_instructions"] == "" and body["ai"]["extra_emergency_keywords"] == []


@pytest.mark.asyncio
async def test_get_ai_status_is_null_without_flag(am_client, fake_redis):
    body = (await am_client(_user(41, ["manager"])).get(PATH)).json()
    assert body["ai_available"] is False and body["ai_status"] is None


@pytest.mark.asyncio
async def test_put_ignores_read_only_fields_and_roundtrips_new_ones(am_client, monkeypatch):
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)
    manager = _user(42, ["manager"])
    ai = {**DEFAULT_CONFIG["ai"], "triage_instructions": "Правило", "news_instructions": "Новости",
          "extra_emergency_keywords": ["шлагбаум"],
          "templates": {"public.assigned": {"ru": "Выехали №{request_number}"}}}
    payload = _valid_payload(ai=ai, ai_status={"open": True, "open_ttl": 1, "failures": 9},
                             template_defaults={}, base_emergency_keywords=["x"], ai_available=False)
    resp = await am_client(manager).put(PATH, json=payload)
    assert resp.status_code == 200, resp.text   # read-only поля молча отброшены
    assert resp.json()["ai"] == ai and resp.json()["ai_available"] is True
    assert (await am_client(manager).get(PATH)).json()["ai"] == ai
    bad = _valid_payload(ai={**DEFAULT_CONFIG["ai"], "templates": {"public.assigned": {"ru": "{кто}"}}})
    resp = await am_client(manager).put(PATH, json=bad)
    assert resp.status_code == 422 and "ai.templates.public.assigned.ru" in resp.text


@pytest.mark.asyncio
async def test_reset_breaker_access_and_audit(am_client, db_session_factory, fake_redis):
    for _ in range(3):
        breaker.record_failure()
    assert (await am_client(None).post(RESET)).status_code == 401
    assert (await am_client(_user(43, ["executor"])).post(RESET)).status_code == 403
    assert breaker.is_open() is True   # запрещённые вызовы ничего не сбросили
    resp = await am_client(_user(44, ["manager"])).post(RESET)
    assert resp.status_code == 200 and resp.json() == {"open": False, "open_ttl": 0, "failures": 0}
    async with db_session_factory() as s:
        row = (await s.execute(select(AuditLog).where(AuditLog.action == "ai_breaker_reset"))).scalar_one()
    assert row.user_id == 44
    assert row.details["before"] == {"open": True, "open_ttl": breaker.OPEN_TTL, "failures": 3}
    assert row.details["at"]


@pytest.mark.asyncio
async def test_reset_breaker_503_when_redis_down(am_client, monkeypatch):
    class _Down:
        def __getattr__(self, name):
            def _boom(*a, **k):
                raise ConnectionError("redis down")
            return _boom
    monkeypatch.setattr(breaker, "_get_client", lambda: _Down())
    assert (await am_client(_user(45, ["manager"])).post(RESET)).status_code == 503
