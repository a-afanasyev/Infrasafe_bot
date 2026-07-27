"""П10 — прод-гейты конфигурации: сила JWT_SECRET (AUD5-SEC-NEW-3) и наличие
пароля у redis (SEC-124).

HS256 подписывает секретом произвольной длины: короткий брутфорсится оффлайн
по одному перехваченному токену, жертве для этого делать ничего не нужно.
Проверка наличия от этого не защищает.

Модуль настроек читает окружение НА ИМПОРТЕ и бросает прямо в теле класса,
поэтому проверяется реальный импорт в подпроцессе — то же, что делает
контейнер при старте. Подмена атрибутов уже импортированного `settings` этот
путь не воспроизводит.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Корень репозитория выводится из расположения файла, а НЕ зашит как «/app»:
# `make test-ci` гоняет сьют внутри контейнера (там код в /app), а CI-джоба —
# прямо на раннере, где такого пути нет. Зашитый путь давал зелёный локальный
# прогон и FileNotFoundError в CI.
ROOT = Path(__file__).resolve().parents[2]

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
    "REDIS_URL": "redis://:" + "r" * 32 + "@redis:6379/0",
    "PYTHONPATH": str(ROOT),
}


def _import_settings(
    *, debug: str, jwt_secret: str = "a" * 64, **overrides: str
) -> subprocess.CompletedProcess:
    env = {
        **BASE_ENV,
        "DEBUG": debug,
        "JWT_SECRET": jwt_secret,
        "PATH": os.environ.get("PATH", ""),
        **overrides,
    }
    return subprocess.run(
        [sys.executable, "-c", "import uk_management_bot.config.settings"],
        env=env, capture_output=True, text=True, cwd=str(ROOT),
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


class TestRedisMustBeAuthenticated:
    """SEC-124: пустой `REDIS_PASSWORD` не должен молча давать redis без auth.

    Пароль опционален по построению — в compose он подставляется как
    `${REDIS_PASSWORD:+--requirepass ...}`, чтобы локальная разработка шла без
    него. Обратная сторона: выпади значение из конфига, redis поднимется без
    auth, а приложение так же тихо подключится, и ни одна проверка не
    сработает. Гейт ловит это на старте — в проде.
    """

    def test_url_without_credentials_stops_startup_in_production(self):
        result = _import_settings(debug="false", REDIS_URL="redis://redis:6379/0")

        assert result.returncode != 0, "беспарольный redis принят в проде"
        assert "REDIS_URL must carry credentials" in result.stderr

    def test_url_with_credentials_starts(self):
        """Форма, которая реально стоит на обоих продах (проверено 2026-07-27)."""
        result = _import_settings(
            debug="false", REDIS_URL="redis://:" + "r" * 64 + "@uk-redis:6379/0"
        )

        assert result.returncode == 0, result.stderr[-400:]

    def test_password_in_the_path_does_not_count_as_credentials(self):
        """`@` где угодно ≠ auth: проверяется authority-часть, а не вся строка."""
        result = _import_settings(
            debug="false", REDIS_URL="redis://redis:6379/0?tag=a@b"
        )

        assert result.returncode != 0, "«@» в query принят за учётные данные"

    def test_dev_mode_allows_passwordless_redis(self):
        """Локалка без пароля — осознанный сценарий, ломать его нельзя."""
        result = _import_settings(debug="true", REDIS_URL="redis://localhost:6379/0")

        assert result.returncode == 0, result.stderr[-400:]
