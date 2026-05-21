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
