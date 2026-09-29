"""Ревью 2026-09-28: docker healthcheck смотрит на /api/v1/health/ready.

Прежняя цель `/api/v1/health` отвечала ok без проверок — контейнер числился
healthy при лежащей БД. /ready проверяет БД и доступен без API-ключа (docker
его не пошлёт); наружу отдаёт только «готов/нет».
"""
from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_ready_without_api_key_when_db_ok():
    with _client() as c:
        resp = c.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_ready_is_503_when_db_down(monkeypatch):
    from app.api.v1 import health

    monkeypatch.setattr(health, "check_db_connection", lambda: False)
    with _client() as c:
        resp = c.get("/api/v1/health/ready")
    assert resp.status_code == 503


def test_other_health_details_still_require_key():
    with _client() as c:
        assert c.get("/api/v1/health/detailed").status_code == 401


def test_healthchecks_target_ready():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent
    targets = [root / "Dockerfile"]
    targets += [p for p in (root.parent / "docker-compose.profk.yml", root.parent / "docker-compose.media.yml") if p.exists()]
    for path in targets:
        text = path.read_text()
        assert "localhost:8000/api/v1/health/ready" in text, path
        assert "localhost:8000/api/v1/health'" not in text, path
