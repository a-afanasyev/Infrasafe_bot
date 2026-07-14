"""Tests for POST /api/v2/resource-accounting/ticket — launch-ticket issuance.

The endpoint is manager-gated and issues a one-time launch-ticket by calling the
partner API server-to-server with a secret X-Service-Token. These tests pin:
auth/role gating, server-side role mapping, fail-closed on missing token, partner
error/timeout mapping, and that the service token never leaks to the client.
"""
import json

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from uk_management_bot.api.main import app
from uk_management_bot.api.dependencies import get_current_user, get_db
import uk_management_bot.api.resource_accounting.router as ra_router
from uk_management_bot.database.models.user import User

TICKET_PATH = "/api/v2/resource-accounting/ticket"
_TOKEN = "svc-secret"


def _user(uid: int, roles: list[str], **kw) -> User:
    return User(
        id=uid,
        telegram_id=uid,
        roles=json.dumps(roles),
        active_role=roles[0] if roles else None,
        status="approved",
        **kw,
    )


class _StubResp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _StubClient:
    """Захватывает исходящий POST партнёру и отдаёт заранее заданный ответ/исключение."""

    captured: dict = {}
    response = _StubResp(200, {"data": {"ticket": "opaque-xyz", "expires_in": 60}})
    exc: Exception | None = None

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        _StubClient.captured = {"url": url, "headers": headers or {}, "json": json or {}}
        if _StubClient.exc is not None:
            raise _StubClient.exc
        return _StubClient.response


@pytest.fixture(autouse=True)
def _stub_partner(monkeypatch):
    _StubClient.captured = {}
    _StubClient.response = _StubResp(200, {"data": {"ticket": "opaque-xyz", "expires_in": 60}})
    _StubClient.exc = None
    monkeypatch.setattr(ra_router.httpx, "AsyncClient", _StubClient)
    monkeypatch.setattr(ra_router.settings, "RESOURCE_SERVICE_TOKEN", _TOKEN)
    monkeypatch.setattr(ra_router.settings, "RESOURCE_SERVICE_URL", "https://partner.example/v1")
    yield


@pytest_asyncio.fixture
async def ticket_client(db_session_factory):
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


# ── Auth / role gating ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_requires_auth(ticket_client):
    resp = await ticket_client(None).post(TICKET_PATH)
    assert resp.status_code == 401
    assert _StubClient.captured == {}  # партнёра не звали


@pytest.mark.asyncio
async def test_forbidden_for_applicant(ticket_client):
    resp = await ticket_client(_user(2, ["applicant"])).post(TICKET_PATH)
    assert resp.status_code == 403
    assert _StubClient.captured == {}


# ── Role mapping (authoritative, server-side) ───────────────────────

@pytest.mark.asyncio
async def test_manager_maps_to_operator(ticket_client):
    user = _user(5, ["manager"], first_name="Ivan", last_name="Petrov", username="ivanp")
    resp = await ticket_client(user).post(TICKET_PATH)
    assert resp.status_code == 200
    assert resp.json() == {"ticket": "opaque-xyz", "expires_in": 60}

    sent = _StubClient.captured
    assert sent["url"] == "https://partner.example/v1/auth/tickets"
    assert sent["headers"]["X-Service-Token"] == _TOKEN
    assert sent["json"] == {
        "external_user_id": "5",
        "display_name": "Ivan Petrov",
        "role": "resource_operator",
    }
    # Секрет не должен утечь клиенту.
    assert _TOKEN not in resp.text


@pytest.mark.asyncio
async def test_system_admin_maps_to_admin(ticket_client):
    resp = await ticket_client(_user(7, ["system_admin"])).post(TICKET_PATH)
    assert resp.status_code == 200
    assert _StubClient.captured["json"]["role"] == "resource_admin"


@pytest.mark.asyncio
async def test_display_name_falls_back_to_username_then_id(ticket_client):
    # Нет first/last → username; нет и username → user-<id>.
    resp = await ticket_client(_user(9, ["manager"], username="only_username")).post(TICKET_PATH)
    assert resp.status_code == 200
    assert _StubClient.captured["json"]["display_name"] == "only_username"

    resp = await ticket_client(_user(11, ["manager"])).post(TICKET_PATH)
    assert _StubClient.captured["json"]["display_name"] == "user-11"


# ── Fail-closed / partner errors ────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_token_returns_503_without_calling_partner(ticket_client, monkeypatch):
    monkeypatch.setattr(ra_router.settings, "RESOURCE_SERVICE_TOKEN", "")
    resp = await ticket_client(_user(5, ["manager"])).post(TICKET_PATH)
    assert resp.status_code == 503
    assert _StubClient.captured == {}


@pytest.mark.asyncio
async def test_partner_5xx_maps_to_502(ticket_client):
    _StubClient.response = _StubResp(500, {})
    resp = await ticket_client(_user(5, ["manager"])).post(TICKET_PATH)
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_partner_timeout_maps_to_504(ticket_client):
    _StubClient.exc = httpx.TimeoutException("slow")
    resp = await ticket_client(_user(5, ["manager"])).post(TICKET_PATH)
    assert resp.status_code == 504


@pytest.mark.asyncio
async def test_partner_response_without_ticket_maps_to_502(ticket_client):
    _StubClient.response = _StubResp(200, {"data": {"expires_in": 60}})
    resp = await ticket_client(_user(5, ["manager"])).post(TICKET_PATH)
    assert resp.status_code == 502


# ── TWA meter-entry ticket (initData-authed, mints resource_meter_entry) ──

TWA_PATH = "/api/v2/resource-accounting/twa-ticket"
_INIT = {"init_data": "tg-init-data"}


def _stub_twa(monkeypatch, *, user_data, user):
    """Подменяет initData-верификацию и user-lookup для twa-ticket-эндпоинта."""
    monkeypatch.setattr(ra_router, "verify_twa_init_data", lambda init_data, token: user_data)

    async def _get_user(db, tid):
        return user

    monkeypatch.setattr(ra_router, "get_user_by_telegram_id", _get_user)


@pytest.mark.asyncio
async def test_twa_controller_mints_meter_entry(ticket_client, monkeypatch):
    user = _user(6, ["applicant", "resource_meter_entry"], first_name="Petr", last_name="K")
    _stub_twa(monkeypatch, user_data={"id": 6055402868}, user=user)
    resp = await ticket_client(None).post(TWA_PATH, json=_INIT)
    assert resp.status_code == 200
    assert resp.json() == {"ticket": "opaque-xyz", "expires_in": 60}
    sent = _StubClient.captured
    assert sent["url"] == "https://partner.example/v1/auth/tickets"
    assert sent["headers"]["X-Service-Token"] == _TOKEN
    assert sent["json"] == {
        "external_user_id": "6",
        "display_name": "Petr K",
        "role": "resource_meter_entry",
    }
    assert _TOKEN not in resp.text


@pytest.mark.asyncio
async def test_twa_invalid_init_data_401(ticket_client, monkeypatch):
    _stub_twa(monkeypatch, user_data=None, user=None)
    resp = await ticket_client(None).post(TWA_PATH, json=_INIT)
    assert resp.status_code == 401
    assert _StubClient.captured == {}  # партнёра не звали


@pytest.mark.asyncio
async def test_twa_without_role_403(ticket_client, monkeypatch):
    user = _user(6, ["applicant"])  # нет resource_meter_entry
    _stub_twa(monkeypatch, user_data={"id": 6055402868}, user=user)
    resp = await ticket_client(None).post(TWA_PATH, json=_INIT)
    assert resp.status_code == 403
    assert _StubClient.captured == {}


@pytest.mark.asyncio
async def test_twa_not_approved_403(ticket_client, monkeypatch):
    user = User(
        id=6, telegram_id=6, roles=json.dumps(["resource_meter_entry"]),
        active_role="applicant", status="pending",
    )
    _stub_twa(monkeypatch, user_data={"id": 6055402868}, user=user)
    resp = await ticket_client(None).post(TWA_PATH, json=_INIT)
    assert resp.status_code == 403
    assert _StubClient.captured == {}


@pytest.mark.asyncio
async def test_twa_unknown_user_403(ticket_client, monkeypatch):
    _stub_twa(monkeypatch, user_data={"id": 6055402868}, user=None)
    resp = await ticket_client(None).post(TWA_PATH, json=_INIT)
    assert resp.status_code == 403
    assert _StubClient.captured == {}


@pytest.mark.asyncio
async def test_twa_missing_token_503(ticket_client, monkeypatch):
    monkeypatch.setattr(ra_router.settings, "RESOURCE_SERVICE_TOKEN", "")
    user = _user(6, ["resource_meter_entry"])
    _stub_twa(monkeypatch, user_data={"id": 6055402868}, user=user)
    resp = await ticket_client(None).post(TWA_PATH, json=_INIT)
    assert resp.status_code == 503
    assert _StubClient.captured == {}


@pytest.mark.asyncio
async def test_twa_partner_5xx_maps_to_502(ticket_client, monkeypatch):
    _StubClient.response = _StubResp(500, {})
    user = _user(6, ["resource_meter_entry"])
    _stub_twa(monkeypatch, user_data={"id": 6055402868}, user=user)
    resp = await ticket_client(None).post(TWA_PATH, json=_INIT)
    assert resp.status_code == 502
