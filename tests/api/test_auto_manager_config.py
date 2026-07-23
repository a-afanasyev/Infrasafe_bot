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
from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.database.models.auto_manager_config import AutoManagerConfig
from uk_management_bot.database.models.user import User
from uk_management_bot.services.auto_manager.config import DEFAULT_CONFIG

PATH = "/api/v2/auto-manager-config"


def _user(uid: int, roles: list[str], **kw) -> User:
    return User(
        id=uid,
        telegram_id=uid,
        roles=json.dumps(roles),
        active_role=roles[0] if roles else None,
        status="approved",
        **kw,
    )


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
    assert resp.json() == DEFAULT_CONFIG


@pytest.mark.asyncio
async def test_get_as_admin_returns_default_when_no_row(am_client):
    # Explicit positive admin test: require_roles("manager", "admin") is OR —
    # a subtly wrong require_roles("manager") alone would 403 here.
    resp = await am_client(_user(11, ["admin"])).get(PATH)
    assert resp.status_code == 200
    assert resp.json() == DEFAULT_CONFIG


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
async def test_put_rejects_mode_ai_until_phase2(am_client, db_session_factory):
    # mode="ai" is genuinely accepted by the shared services/auto_manager/
    # config.py::validate_config (deliberate Phase-2 forward-compat), but the
    # API schema is deliberately STRICTER: the orchestrator ignores `mode`
    # entirely today, and neither the bot nor dashboard UI can select "ai" —
    # letting a raw API caller persist it would make GET/PUT report a mode
    # that silently doesn't do anything. Revisit when Phase 2 wires the AI
    # engine into the orchestrator.
    manager = _user(23, ["manager"])
    resp = await am_client(manager).put(PATH, json=_valid_payload(mode="ai"))
    assert resp.status_code == 422

    async with db_session_factory() as session:
        result = await session.execute(select(AutoManagerConfig))
        assert result.scalar_one_or_none() is None


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
