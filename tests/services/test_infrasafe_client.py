"""ARCH-114 (H-4): fetch_infrasafe_uk_request_numbers sends x-service-token.

Dormant contract: the header is sent only when INFRASAFE_INVENTORY_TOKEN is set;
empty token → no header (endpoint stays public, current behaviour). Verified by
stubbing the outbound httpx client and capturing the GET headers.
"""
import pytest

import uk_management_bot.clients.infrasafe_client as ic


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _StubClient:
    captured: dict = {}
    payload = {
        "data": [{"uk_request_number": "260523-004"}, {"uk_request_number": "260524-001"}],
        "total": 2,
    }

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        _StubClient.captured = {"url": url, "headers": headers or {}}
        return _Resp(_StubClient.payload)


@pytest.fixture(autouse=True)
def _stub(monkeypatch):
    _StubClient.captured = {}
    monkeypatch.setattr(ic.httpx, "AsyncClient", _StubClient)
    monkeypatch.setattr(
        ic.settings, "INFRASAFE_REQUESTS_INVENTORY_URL",
        "https://infrasafe.example/api/uk-requests-metrics",
    )
    yield


async def test_sends_service_token_header_when_set(monkeypatch):
    monkeypatch.setattr(ic.settings, "INFRASAFE_INVENTORY_TOKEN", "shhh-secret")
    result = await ic.fetch_infrasafe_uk_request_numbers()

    assert result == {"260523-004", "260524-001"}
    assert _StubClient.captured["headers"].get("x-service-token") == "shhh-secret"
    # URL и query сохраняются как раньше.
    assert _StubClient.captured["url"] == (
        "https://infrasafe.example/api/uk-requests-metrics?limit=5000"
    )


async def test_no_header_when_token_empty(monkeypatch):
    monkeypatch.setattr(ic.settings, "INFRASAFE_INVENTORY_TOKEN", "")
    await ic.fetch_infrasafe_uk_request_numbers()

    assert "x-service-token" not in _StubClient.captured["headers"]
