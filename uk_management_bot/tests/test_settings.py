"""Tests for uk_management_bot.config.settings — BUG-BOT-001.

Verify that BOT_USERNAME:
  * is None when the environment variable is unset (no hardcoded default);
  * reflects the value when the environment variable is set.

Settings is module-scope; we reload the module under controlled env to pick
up the new value. We keep DEBUG=True during reload to avoid tripping the
production-only guards (ADMIN_PASSWORD, REDIS_URL, etc.).
"""
from __future__ import annotations

import importlib
import sys

import pytest


def _reload_settings(monkeypatch: pytest.MonkeyPatch, **env: str):
    """Reload settings module with patched env and return the new module."""
    # Always keep DEBUG=True so the production guards do not raise.
    monkeypatch.setenv("DEBUG", "True")
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    mod_name = "uk_management_bot.config.settings"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


@pytest.mark.unit
def test_bot_username_none_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """BOT_USERNAME must be None (no hardcoded default) when env var is missing."""
    monkeypatch.delenv("BOT_USERNAME", raising=False)
    mod = _reload_settings(monkeypatch)
    assert mod.settings.BOT_USERNAME is None


@pytest.mark.unit
def test_bot_username_uses_env_value_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """BOT_USERNAME must reflect the env var when set."""
    mod = _reload_settings(monkeypatch, BOT_USERNAME="Work_space_away_bot")
    assert mod.settings.BOT_USERNAME == "Work_space_away_bot"


# ---------------------------------------------------------------------------
# SEC-083: ADMIN_PASSWORD production strength guard (min length 16 + entropy)
# ---------------------------------------------------------------------------

def _reload_prod(monkeypatch: pytest.MonkeyPatch, admin_password: str):
    """Reload settings under a full valid PRODUCTION env (DEBUG=False), varying
    only ADMIN_PASSWORD, so the ADMIN_PASSWORD guard is the only thing that can
    trip."""
    monkeypatch.setenv("DEBUG", "False")
    monkeypatch.setenv("BOT_TOKEN", "123:test-bot-token")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@postgres:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("INVITE_SECRET", "invite-secret-aaaaaaaaaaaaaaaa")
    monkeypatch.setenv("JWT_SECRET", "jwt-secret-bbbbbbbbbbbbbbbbbbbb")
    monkeypatch.setenv("OUTBOX_SOURCE_INSTANCE", "profk")  # ARCH-010: обязателен в prod
    monkeypatch.setenv("ADMIN_PASSWORD", admin_password)
    mod_name = "uk_management_bot.config.settings"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


@pytest.mark.unit
def test_admin_password_strong_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 16-char password with enough distinct chars passes in production."""
    mod = _reload_prod(monkeypatch, "Abc123Xyz789Qwer")  # 16 chars, 15 distinct
    assert mod.settings.ADMIN_PASSWORD == "Abc123Xyz789Qwer"


@pytest.mark.unit
def test_admin_password_too_short_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """SEC-083: a 12-char password (old minimum) is now rejected — min is 16."""
    with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
        _reload_prod(monkeypatch, "Abcdef123456")  # 12 chars


@pytest.mark.unit
def test_admin_password_low_entropy_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """SEC-083: a long but low-entropy password (few distinct chars) is rejected."""
    with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
        _reload_prod(monkeypatch, "aaaaaaaaaaaaaaaa")  # 16 chars, 1 distinct


# ---------------------------------------------------------------------------
# ARCH-010: OUTBOX_SOURCE_INSTANCE — идентификатор инсталляции для UUIDv5
# event_id. Allowlist работает всегда; фолбэк "dev" — только в DEBUG.
# ---------------------------------------------------------------------------

def _reload_prod_outbox(monkeypatch: pytest.MonkeyPatch, source_instance: str | None):
    """Полный валидный prod-env (DEBUG=False), варьируется только
    OUTBOX_SOURCE_INSTANCE (None = переменная отсутствует)."""
    monkeypatch.setenv("DEBUG", "False")
    monkeypatch.setenv("BOT_TOKEN", "123:test-bot-token")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@postgres:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("INVITE_SECRET", "invite-secret-aaaaaaaaaaaaaaaa")
    monkeypatch.setenv("JWT_SECRET", "jwt-secret-bbbbbbbbbbbbbbbbbbbb")
    monkeypatch.setenv("ADMIN_PASSWORD", "Abc123Xyz789Qwer")
    if source_instance is None:
        monkeypatch.delenv("OUTBOX_SOURCE_INSTANCE", raising=False)
    else:
        monkeypatch.setenv("OUTBOX_SOURCE_INSTANCE", source_instance)
    mod_name = "uk_management_bot.config.settings"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


@pytest.mark.unit
def test_outbox_source_instance_valid_prod_value_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _reload_prod_outbox(monkeypatch, "infrasafe")
    assert mod.settings.OUTBOX_SOURCE_INSTANCE == "infrasafe"


@pytest.mark.unit
def test_outbox_source_instance_required_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-DEBUG без переменной → ValueError (fail-loud, без тихого фолбэка)."""
    with pytest.raises(ValueError, match="OUTBOX_SOURCE_INSTANCE"):
        _reload_prod_outbox(monkeypatch, None)


@pytest.mark.unit
def test_outbox_source_instance_garbage_rejected_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="OUTBOX_SOURCE_INSTANCE"):
        _reload_prod_outbox(monkeypatch, "staging")


@pytest.mark.unit
def test_outbox_source_instance_garbage_rejected_in_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allowlist работает и при DEBUG=True — мусор не проходит нигде."""
    with pytest.raises(ValueError, match="OUTBOX_SOURCE_INSTANCE"):
        _reload_settings(monkeypatch, OUTBOX_SOURCE_INSTANCE="garbage")


@pytest.mark.unit
def test_outbox_source_instance_debug_fallback_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    """DEBUG=True без переменной → стабильный фолбэк "dev"."""
    mod = _reload_settings(monkeypatch, OUTBOX_SOURCE_INSTANCE=None)
    assert mod.settings.OUTBOX_SOURCE_INSTANCE == "dev"
