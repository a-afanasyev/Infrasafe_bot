"""PR-14 — auth-слой hardening: SEC-02, SEC-04, NICE-082.

SEC-02:  JWT подписывается ОТДЕЛЬНЫМ JWT_SECRET (нет fallback на INVITE_SECRET);
         в проде отсутствие JWT_SECRET валит старт; hardcoded dev-секрет убран.
SEC-04:  fail-closed на auth-роутах, когда Redis-бэкенд rate-limit деградировал.
NICE-082: refresh-token TTL сокращён 30d → 7d.
"""
import inspect
import os
import subprocess
import sys

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# SEC-02 — settings-level prod guard (отдельный обязательный JWT_SECRET)
#
# settings.py исполняет guard'ы на уровне модуля. Тестируем в ИЗОЛИРОВАННОМ
# subprocess: in-process `del sys.modules + reimport` подменил бы общий объект
# settings и протёк бы prod-конфигом в остальные тесты того же прогона
# (tests/api и tests/services идут одним вызовом pytest).
# ---------------------------------------------------------------------------

def _prod_env(*, jwt_secret):
    """Полный валидный prod-env (DEBUG=False); INVITE_SECRET задан намеренно —
    проверяем, что fallback на него больше НЕ спасает. JWT_SECRET варьируется."""
    env = {
        **os.environ,
        "DEBUG": "False",
        "BOT_TOKEN": "123:test-bot-token",
        "DATABASE_URL": "postgresql://u:p@postgres:5432/db",
        "REDIS_URL": "redis://redis:6379/0",
        "INVITE_SECRET": "invite-secret-aaaaaaaaaaaaaaaa",
        "ADMIN_PASSWORD": "Abc123Xyz789Qwer",  # strong, 16 chars
        "OUTBOX_SOURCE_INSTANCE": "profk",  # ARCH-010: обязателен при DEBUG=False
    }
    if jwt_secret is None:
        env.pop("JWT_SECRET", None)
    else:
        env["JWT_SECRET"] = jwt_secret
    return env


def _import_settings_subprocess(env):
    return subprocess.run(
        [sys.executable, "-c", "import uk_management_bot.config.settings"],
        env=env,
        capture_output=True,
        text=True,
    )


def test_sec02_jwt_secret_required_in_prod_no_invite_fallback():
    """Прод без JWT_SECRET валит старт, даже если INVITE_SECRET задан."""
    result = _import_settings_subprocess(_prod_env(jwt_secret=None))
    assert result.returncode != 0
    assert "JWT_SECRET must be set" in result.stderr


def test_sec02_jwt_secret_present_in_prod_loads():
    result = _import_settings_subprocess(_prod_env(jwt_secret="jwt-secret-bbbbbbbbbbbbbbbbbbbb"))
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# SEC-02 — service-level: нет hardcoded dev-секрета, ключ установлен
# ---------------------------------------------------------------------------

def test_sec02_no_hardcoded_dev_jwt_secret_in_source():
    from uk_management_bot.api.auth import service

    src = inspect.getsource(service)
    assert "dev-jwt-secret-DO-NOT-USE-IN-PROD" not in src
    assert service.SECRET_KEY  # ключ всё равно установлен (env или ephemeral dev)


def test_sec02_secret_key_not_old_constant():
    from uk_management_bot.api.auth import service

    assert service.SECRET_KEY != "dev-jwt-secret-DO-NOT-USE-IN-PROD"


# ---------------------------------------------------------------------------
# NICE-082 — refresh TTL 30d → 7d
# ---------------------------------------------------------------------------

def test_nice082_refresh_token_ttl_is_7_days():
    from uk_management_bot.api.auth.service import REFRESH_TOKEN_EXPIRE_DAYS

    assert REFRESH_TOKEN_EXPIRE_DAYS == 7


# ---------------------------------------------------------------------------
# SEC-04 — fail-closed auth-guard при деградации rate-limit бэкенда
# ---------------------------------------------------------------------------

class TestAuthRatelimitGuard:
    def test_fails_closed_503_when_redis_configured_and_dead(self, monkeypatch):
        from uk_management_bot.api import rate_limit as rl

        monkeypatch.setattr(rl.settings, "USE_REDIS_RATE_LIMIT", True, raising=False)
        monkeypatch.setattr(rl.limiter, "_storage_dead", True, raising=False)

        with pytest.raises(HTTPException) as ei:
            rl.auth_ratelimit_guard()
        assert ei.value.status_code == 503

    def test_noop_when_backend_healthy(self, monkeypatch):
        from uk_management_bot.api import rate_limit as rl

        monkeypatch.setattr(rl.settings, "USE_REDIS_RATE_LIMIT", True, raising=False)
        monkeypatch.setattr(rl.limiter, "_storage_dead", False, raising=False)

        assert rl.auth_ratelimit_guard() is None  # не поднимает

    def test_noop_when_redis_not_configured(self, monkeypatch):
        """Dev (in-memory by design): даже если _storage_dead взведён —
        guard не должен мешать."""
        from uk_management_bot.api import rate_limit as rl

        monkeypatch.setattr(rl.settings, "USE_REDIS_RATE_LIMIT", False, raising=False)
        monkeypatch.setattr(rl.limiter, "_storage_dead", True, raising=False)

        assert rl.auth_ratelimit_guard() is None

    def test_noop_when_storage_dead_attr_missing(self, monkeypatch):
        """getattr-дефолт: если slowapi переименует приватный атрибут —
        guard деградирует в no-op (fail-open), а не падает."""
        from uk_management_bot.api import rate_limit as rl

        monkeypatch.setattr(rl.settings, "USE_REDIS_RATE_LIMIT", True, raising=False)
        # Подменяем limiter объектом без _storage_dead
        sentinel = type("X", (), {})()
        monkeypatch.setattr(rl, "limiter", sentinel)

        assert rl.auth_ratelimit_guard() is None
