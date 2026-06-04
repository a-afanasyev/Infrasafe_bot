"""
BUG: invite link for a new employee rendered as `https://t.me/None`.

Root cause: the bot process (main.py) self-heals BOT_USERNAME via getMe() at
startup (BUG-BOT-001), but the invite link is built by the *API* process
(uk-management-api), which only reads os.getenv("BOT_USERNAME"). When the var
is missing from the API environment, the username is None and the link breaks.

Fix: the API resolves the username via Telegram getMe() (using BOT_TOKEN) when
BOT_USERNAME is unset, caching it back into settings. If it cannot be resolved,
the endpoint must fail loudly instead of emitting a t.me/None link.
"""
import pytest

from uk_management_bot.api.shifts import router as router_mod
from uk_management_bot.config.settings import settings


class _FakeResp:
    def __init__(self, payload=None, raise_exc=None):
        self._payload = payload or {}
        self._raise = raise_exc

    def raise_for_status(self):
        if self._raise:
            raise self._raise

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        if self._exc:
            raise self._exc
        return self._resp


def _patch_httpx(monkeypatch, *, resp=None, exc=None):
    monkeypatch.setattr(
        router_mod.httpx,
        "AsyncClient",
        lambda *a, **kw: _FakeClient(resp=resp, exc=exc),
    )


@pytest.mark.asyncio
async def test_uses_configured_username_without_network(monkeypatch):
    """When BOT_USERNAME is set, return it and never touch the network."""
    monkeypatch.setattr(settings, "BOT_USERNAME", "Work_space_away_bot")

    def _boom(*a, **kw):
        raise AssertionError("getMe() must not be called when BOT_USERNAME is set")

    monkeypatch.setattr(router_mod.httpx, "AsyncClient", _boom)

    assert await router_mod._resolve_bot_username() == "Work_space_away_bot"


@pytest.mark.asyncio
async def test_resolves_via_getme_and_caches(monkeypatch):
    """When BOT_USERNAME is unset, resolve via getMe() and cache it."""
    monkeypatch.setattr(settings, "BOT_USERNAME", None)
    monkeypatch.setattr(settings, "BOT_TOKEN", "123:abc")
    _patch_httpx(monkeypatch, resp=_FakeResp({"ok": True, "result": {"username": "infrasafebot"}}))

    assert await router_mod._resolve_bot_username() == "infrasafebot"
    # Cached back into settings so subsequent requests are cheap.
    assert settings.BOT_USERNAME == "infrasafebot"


@pytest.mark.asyncio
async def test_returns_none_when_token_missing(monkeypatch):
    """No BOT_USERNAME and no BOT_TOKEN → cannot resolve → None (never 'None' string)."""
    monkeypatch.setattr(settings, "BOT_USERNAME", None)
    monkeypatch.setattr(settings, "BOT_TOKEN", None)

    assert await router_mod._resolve_bot_username() is None


@pytest.mark.asyncio
async def test_returns_none_when_getme_fails(monkeypatch):
    """getMe() network/auth failure → None, not a broken username."""
    monkeypatch.setattr(settings, "BOT_USERNAME", None)
    monkeypatch.setattr(settings, "BOT_TOKEN", "123:abc")
    _patch_httpx(monkeypatch, exc=RuntimeError("network down"))

    assert await router_mod._resolve_bot_username() is None
