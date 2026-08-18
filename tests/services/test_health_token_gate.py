"""E3 (аудит 2026-08-18): fail-closed для health/metrics-токена — ЛЕНИВО.

Eager-валидация в settings уронила бы app/access-api/migrate на старте
(settings импортируют все четыре сервиса, а переменная прокинута только api).
Поэтому отказ живёт в зависимости require_health_token: прод без токена → 503
на первом обращении; dev остаётся открытым (пробы и curl работают).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from uk_management_bot.api.routes import health as health_mod


def _call(authorization=None):
    # require_health_token — синхронная FastAPI-зависимость
    return health_mod.require_health_token(authorization=authorization)


def test_prod_with_empty_token_is_fail_closed(monkeypatch):
    monkeypatch.setattr(health_mod.settings, "HEALTH_METRICS_TOKEN", "")
    monkeypatch.setattr(health_mod.settings, "DEBUG", False)
    with pytest.raises(HTTPException) as e:
        _call()
    assert e.value.status_code == 503


def test_dev_with_empty_token_stays_open(monkeypatch):
    monkeypatch.setattr(health_mod.settings, "HEALTH_METRICS_TOKEN", "")
    monkeypatch.setattr(health_mod.settings, "DEBUG", True)
    assert _call() is None


def test_valid_bearer_passes_and_wrong_is_401(monkeypatch):
    monkeypatch.setattr(health_mod.settings, "HEALTH_METRICS_TOKEN", "sekret")
    monkeypatch.setattr(health_mod.settings, "DEBUG", False)
    assert _call(authorization="Bearer sekret") is None
    with pytest.raises(HTTPException) as e:
        _call(authorization="Bearer wrong")
    assert e.value.status_code == 401
    with pytest.raises(HTTPException) as e2:
        _call(authorization=None)
    assert e2.value.status_code == 401
