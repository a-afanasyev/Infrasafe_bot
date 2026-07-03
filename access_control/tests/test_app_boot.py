"""Skeleton-тесты загрузки приложения access_control (Фаза 1, каркас).

Проверяют только сборку FastAPI-приложения и health-роутер. Никакой
бизнес-логики, сущностей БД или пилотных эндпоинтов §13 здесь нет — они
относятся к следующим фазам.

Для health-вызова используется синхронный starlette.testclient.TestClient
(httpx-backed) вместо httpx.AsyncClient из tests/api/conftest.py: каркасный
тест остаётся независимым от asyncio_mode/pyproject и от наличия pytest-asyncio
в окружении исполнения.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from access_control.app.main import create_app


def test_create_app_returns_fastapi_instance() -> None:
    """create_app() собирает FastAPI-приложение с ожидаемым title."""
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "UK Access API"


def test_health_route_registered() -> None:
    """Роутер health подключён; с Ф3 подключён и ANPR-эндпоинт §13.1."""
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/health" in paths
    # Ф3: подключён ingestion-эндпоинт камеры (§13.1). Прочие §13-префиксы — позже.
    assert "/api/v1/access/camera-events/anpr" in paths


def test_health_endpoint_returns_ok() -> None:
    """GET /health → 200 и корректный JSON-конверт сервиса."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "uk-access-api"
    assert isinstance(payload["version"], str)
    assert payload["version"]


def test_security_headers_present_on_every_response() -> None:
    """SEC-05 (аудит #4): baseline security-заголовки на ответах (паритет бот-API)."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "max-age=" in response.headers["Strict-Transport-Security"]
