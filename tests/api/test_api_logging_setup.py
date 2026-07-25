"""API-процесс обязан настраивать прикладное логирование.

Регрессия: `setup_structured_logging()` звался только из main.py бота, а API
поднимается через `uvicorn api.main:app`. Uvicorn настраивает лишь свои
логгеры, поэтому у прикладных не было ни одного handler'а: logger.info()
пропадал целиком, WARNING+ вытекал случайно через logging.lastResort. Обнаружено
по отсутствию в api-логах строки о регистрации бота уведомлений — а её сосед по
модулю, диспетчер уведомлений, сообщает о сбоях отправки именно логом.
"""
import logging

import pytest

from uk_management_bot.api.lifecycle import lifespan


@pytest.mark.asyncio
async def test_lifespan_configures_application_logging(monkeypatch):
    called = []
    monkeypatch.setattr(
        "uk_management_bot.utils.structured_logger.setup_structured_logging",
        lambda: called.append(True),
    )
    # Остальной startup в тесте не нужен — гасим его побочные эффекты.
    monkeypatch.setattr(
        "uk_management_bot.api.rate_limit.rate_limit_backend_status",
        lambda: "memory",
    )

    app = type("App", (), {"state": type("S", (), {})()})()
    async with lifespan(app):
        pass

    assert called, "lifespan не настроил прикладное логирование"


@pytest.mark.asyncio
async def test_logging_setup_failure_does_not_block_startup(monkeypatch):
    """Логирование — не причина отказать в старте API."""
    def boom():
        raise RuntimeError("no stdout")

    monkeypatch.setattr(
        "uk_management_bot.utils.structured_logger.setup_structured_logging", boom)
    monkeypatch.setattr(
        "uk_management_bot.api.rate_limit.rate_limit_backend_status",
        lambda: "memory",
    )

    app = type("App", (), {"state": type("S", (), {})()})()
    async with lifespan(app):
        pass  # не бросило — этого достаточно


def test_root_logger_gets_handler_after_setup():
    """Прямая проверка эффекта: после настройки у root есть handler и уровень."""
    from uk_management_bot.utils.structured_logger import setup_structured_logging

    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)

    setup_structured_logging()

    assert root.handlers, "прикладные логи снова уходили бы в никуда"
