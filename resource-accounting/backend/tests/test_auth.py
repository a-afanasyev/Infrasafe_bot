from fastapi.testclient import TestClient

from app.main import app


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_unauthenticated_gets_401(client):
    resp = client.get("/v1/meters")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_me(admin):
    resp = admin.get("/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["data"]["role"] == "resource_admin"


def test_ticket_requires_service_token(client):
    resp = client.post(
        "/v1/auth/tickets",
        json={"external_user_id": "42", "display_name": "Manager", "role": "resource_operator"},
        headers={"X-Service-Token": "wrong"},
    )
    assert resp.status_code == 401


def test_ticket_exchange_full_flow():
    minting = TestClient(app)
    resp = minting.post(
        "/v1/auth/tickets",
        json={"external_user_id": "uk-777", "display_name": "UK Manager", "role": "resource_reviewer"},
        headers={"X-Service-Token": "test-service-token"},
    )
    assert resp.status_code == 200, resp.text
    ticket = resp.json()["data"]["ticket"]

    browser = TestClient(app)
    resp = browser.post("/v1/auth/session/exchange", json={"ticket": ticket})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["role"] == "resource_reviewer"
    assert browser.get("/v1/auth/me").status_code == 200

    # One-shot: second exchange fails
    resp = TestClient(app).post("/v1/auth/session/exchange", json={"ticket": ticket})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "ticket_used"


def test_ticket_expiry(monkeypatch):
    minting = TestClient(app)
    resp = minting.post(
        "/v1/auth/tickets",
        json={"external_user_id": "uk-888", "display_name": "X", "role": "resource_viewer"},
        headers={"X-Service-Token": "test-service-token"},
    )
    ticket = resp.json()["data"]["ticket"]

    from datetime import timedelta

    import app.api.auth as auth_module

    real_utcnow = auth_module.utcnow
    monkeypatch.setattr(auth_module, "utcnow", lambda: real_utcnow() + timedelta(seconds=120))
    resp = TestClient(app).post("/v1/auth/session/exchange", json={"ticket": ticket})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "ticket_expired"


def test_invalid_ticket(client):
    resp = client.post("/v1/auth/session/exchange", json={"ticket": "x" * 40})
    assert resp.status_code == 401
