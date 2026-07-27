"""П10 / AUD5-SEC-NEW-3 — в проде проверяется не только наличие JWT_SECRET, но и длина.

HS256 подписывает секретом произвольной длины: короткий брутфорсится оффлайн
по одному перехваченному токену, жертве для этого делать ничего не нужно.
Проверка наличия от этого не защищает.

Модуль настроек читает окружение НА ИМПОРТЕ и бросает прямо в теле класса,
поэтому проверяется реальный импорт в подпроцессе — то же, что делает
контейнер при старте. Подмена атрибутов уже импортированного `settings` этот
путь не воспроизводит.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

BASE_ENV = {
    "BOT_TOKEN": "123:dummy",
    "INVITE_SECRET": "x" * 40,
    "UK_WEBHOOK_SECRET": "x" * 40,
    "INFRASAFE_WEBHOOK_SECRET": "x" * 40,
    "ADMIN_PASSWORD": "ci-dummy-admin-pw-0123456",
    "OUTBOX_SOURCE_INSTANCE": "profk",
    # Прод-режим отвергает sqlite отдельной проверкой — даём валидный DSN,
    # чтобы падение было именно на длине секрета, а не раньше.
    "DATABASE_URL": "postgresql://u:p@db:5432/uk",
    "PYTHONPATH": "/app",
}


def _import_settings(*, debug: str, jwt_secret: str) -> subprocess.CompletedProcess:
    env = {**BASE_ENV, "DEBUG": debug, "JWT_SECRET": jwt_secret, "PATH": "/usr/local/bin:/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-c", "import uk_management_bot.config.settings"],
        env=env, capture_output=True, text=True, cwd="/app",
    )


class TestProductionRejectsWeakSecret:
    @pytest.mark.parametrize("length", [1, 12, 31])
    def test_short_secret_stops_startup(self, length):
        result = _import_settings(debug="false", jwt_secret="a" * length)

        assert result.returncode != 0, (
            f"секрет из {length} символов принят в проде — подпись HS256 "
            "брутфорсится оффлайн"
        )
        assert "JWT_SECRET too short" in result.stderr

    def test_error_names_the_actual_length(self):
        """Сообщение должно говорить, что не так, а не «неверная конфигурация»."""
        result = _import_settings(debug="false", jwt_secret="a" * 10)

        assert "10 chars" in result.stderr and "minimum 32" in result.stderr


class TestLegitimateSecretsPass:
    @pytest.mark.parametrize("length", [32, 64])
    def test_secret_at_or_above_the_threshold_starts(self, length):
        """64 — фактическая длина на обоих продах (проверено 2026-07-27)."""
        result = _import_settings(debug="false", jwt_secret="a" * length)

        assert result.returncode == 0, result.stderr[-400:]

    def test_dev_mode_is_not_gated(self):
        """Локалка и CI не должны требовать прод-стойкий секрет."""
        result = _import_settings(debug="true", jwt_secret="short")

        assert result.returncode == 0, result.stderr[-400:]
