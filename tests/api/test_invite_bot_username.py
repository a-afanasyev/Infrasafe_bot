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
import httpx
import pytest

# A9-P2-9: getMe идёт через общий модуль `api/telegram_send` — подменяется
# транспорт httpx его клиента (фикстура `telegram_api` из conftest).
from uk_management_bot.api.shifts.router import _helpers as router_mod
from uk_management_bot.config.settings import settings


@pytest.mark.asyncio
async def test_uses_configured_username_without_network(monkeypatch, telegram_api):
    """When BOT_USERNAME is set, return it and never touch the network."""
    monkeypatch.setattr(settings, "BOT_USERNAME", "Work_space_away_bot")

    assert await router_mod._resolve_bot_username() == "Work_space_away_bot"
    assert telegram_api.requests == []


@pytest.mark.asyncio
async def test_resolves_via_getme_and_caches(monkeypatch, telegram_api):
    """When BOT_USERNAME is unset, resolve via getMe() and cache it."""
    monkeypatch.setattr(settings, "BOT_USERNAME", None)
    monkeypatch.setattr(settings, "BOT_TOKEN", "123:abc")
    telegram_api.reply(200, result={"username": "infrasafebot"})

    assert await router_mod._resolve_bot_username() == "infrasafebot"
    assert telegram_api.requests[0].url.path == "/bot123:abc/getMe"
    # Cached back into settings so subsequent requests are cheap.
    assert settings.BOT_USERNAME == "infrasafebot"


@pytest.mark.asyncio
async def test_returns_none_when_token_missing(monkeypatch, telegram_api):
    """No BOT_USERNAME and no BOT_TOKEN → cannot resolve → None (never 'None' string)."""
    monkeypatch.setattr(settings, "BOT_USERNAME", None)
    monkeypatch.setattr(settings, "BOT_TOKEN", None)

    assert await router_mod._resolve_bot_username() is None
    assert telegram_api.requests == []


def _network_down(request):
    raise httpx.ReadTimeout("network down", request=request)


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [
    _network_down,
    lambda r: httpx.Response(401, json={"ok": False, "description": "Unauthorized"}),
])
async def test_returns_none_when_getme_fails(monkeypatch, telegram_api, handler):
    """getMe() network/auth failure → None, not a broken username."""
    monkeypatch.setattr(settings, "BOT_USERNAME", None)
    monkeypatch.setattr(settings, "BOT_TOKEN", "123:abc")
    telegram_api.handler = handler

    assert await router_mod._resolve_bot_username() is None
