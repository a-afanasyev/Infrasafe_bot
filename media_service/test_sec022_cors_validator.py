"""SEC-022 — fail-fast on wildcard CORS in production.

media_service грузит свой `Settings` на уровне модуля и валидирует на старте
(паттерн SEC-065/066). Этот тест проверяет AC SEC-022: при `DEBUG=False`
(prod) `ALLOWED_ORIGINS`, содержащий `*` (целиком или элементом списка),
обязан завалить старт `RuntimeError`; в dev (`DEBUG=True`) `*` допустим.

ПРИМЕЧАНИЕ ПО ЗАПУСКУ: media_service — отдельный сервис со своим образом и
НЕ входит в образы bot/api, поэтому этот тест НЕ собирается в CI основного
бота. Запуск локально из корня репо:

    pip install "pydantic-settings>=2,<3"
    pytest media_service/test_sec022_cors_validator.py

`app/core/` не является пакетом (нет __init__.py), поэтому модуль грузим по
пути через importlib — это же повторно исполняет валидаторы на каждый кейс.
"""
import importlib.util
import os
from pathlib import Path

import pytest

pytest.importorskip("pydantic_settings")

_CONFIG_PATH = Path(__file__).parent / "app" / "core" / "config.py"

# Минимальный prod-валидный env, проходящий SEC-065/066, чтобы изолировать
# именно SEC-022 (CORS). allowed_origins/debug задаёт каждый тест.
_BASE_ENV = {
    "TELEGRAM_BOT_TOKEN": "x",
    "SECRET_KEY": "a" * 48,
    # ARCH-106 Phase 2: database_url лишился дефолта (содержал пароль) — теперь обязателен.
    "DATABASE_URL": "postgresql://u:p@h/db",
    "CHANNEL_REQUESTS": "@r",
    "CHANNEL_REPORTS": "@rep",
    "CHANNEL_ARCHIVE": "@a",
    "CHANNEL_BACKUP": "@b",
}


def _load_config():
    """Свежая загрузка config.py по пути — повторно прогоняет fail-fast-блоки."""
    spec = importlib.util.spec_from_file_location("_sec022_config", _CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # исполняет top-level валидаторы
    return module


@pytest.fixture
def prod_env(monkeypatch, tmp_path):
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("DEBUG", "false")
    # Settings(env_file=".env") читает .env ОТНОСИТЕЛЬНО cwd. Уходим в пустой
    # tmp-каталог, иначе подхватился бы корневой .env бота (чужие ключи →
    # extra_forbidden) и тест падал бы ещё до SEC-022.
    monkeypatch.chdir(tmp_path)
    return monkeypatch


def test_prod_wildcard_origin_fails_fast(prod_env):
    prod_env.setenv("ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS must not contain"):
        _load_config()


def test_prod_wildcard_in_list_fails_fast(prod_env):
    """Главная защита: main.py defang'ит только точное '*', но
    'https://x.com,*' прошёл бы как валидный origin — валидатор это ловит."""
    prod_env.setenv("ALLOWED_ORIGINS", "https://x.com,*")
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS must not contain"):
        _load_config()


def test_prod_explicit_origin_loads(prod_env):
    prod_env.setenv("ALLOWED_ORIGINS", "https://infrasafe.uz")
    module = _load_config()
    assert module.settings.allowed_origins == "https://infrasafe.uz"


def test_dev_wildcard_tolerated(monkeypatch, tmp_path):
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    monkeypatch.chdir(tmp_path)  # пустой cwd — без корневого .env бота
    module = _load_config()  # dev — не должно падать
    assert module.settings.debug is True
