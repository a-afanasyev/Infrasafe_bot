import base64
import hashlib
import json

import pytest

from app.config import Settings
from tests.conftest import make_meter, make_object, make_period


# --- SEC-01: fail-fast on insecure production config ---
def test_config_rejects_default_secrets_in_production():
    cfg = Settings(
        environment="production",
        session_secret="dev-session-secret-change-me",
        service_token="dev-service-token-change-me",
        dev_auth_enabled=False,
        cookie_secure=True,
    )
    with pytest.raises(RuntimeError) as exc:
        cfg.validate_for_environment()
    assert "SESSION_SECRET" in str(exc.value)


def test_config_rejects_dev_auth_and_insecure_cookie_in_production():
    cfg = Settings(
        environment="production",
        session_secret="x" * 40,
        service_token="y" * 40,
        dev_auth_enabled=True,
        cookie_secure=False,
    )
    with pytest.raises(RuntimeError):
        cfg.validate_for_environment()


def test_config_ok_in_production_with_overrides():
    cfg = Settings(
        environment="production",
        session_secret="x" * 40,
        service_token="y" * 40,
        dev_auth_enabled=False,
        cookie_secure=True,
    )
    cfg.validate_for_environment()  # no raise


def test_config_development_is_lenient():
    Settings(environment="development").validate_for_environment()  # no raise


# --- SEC-05: CSRF Origin-check ---
def test_foreign_origin_rejected_on_mutation(admin):
    resp = admin.post(
        "/v1/objects",
        json={"name": "CSRF-объект"},
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_origin"


def test_allowed_origin_passes(admin):
    resp = admin.post(
        "/v1/objects",
        json={"name": "Origin-ок"},
        headers={"Origin": "http://localhost:5273"},
    )
    assert resp.status_code == 201


def test_missing_origin_passes(admin):
    # non-browser client (no Origin header) is allowed through
    assert admin.post("/v1/objects", json={"name": "Без-Origin"}).status_code == 201


# --- SEC-07: security headers present ---
def test_security_headers_present(client):
    resp = client.get("/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors" in resp.headers["Content-Security-Policy"]
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


# --- SEC-03: forged commit_token cannot bypass validation / write foreign meters ---
def _forge_token(rows: list[dict]) -> str:
    source = json.dumps(rows, default=str, sort_keys=True).encode()
    return base64.b64encode(hashlib.sha256(source).digest()[:12] + source).decode()


def test_forged_commit_token_is_rederived_server_side(admin):
    obj = make_object(admin, "SEC03-объект")
    make_meter(admin, "SEC03-REAL", obj["id"])
    make_period(admin, "2030-01")

    # Attacker forges a row: unknown meter_number, errors=[] (claims valid), bogus meter_id.
    forged = [{
        "line": 2,
        "meter_number": "SEC03-GHOST",
        "period": "2030-01",
        "reading_value": "999",
        "read_at": "",
        "note": "",
        "meter_id": "00000000-0000-0000-0000-000000000000",
        "parsed_value": "999",
        "parsed_read_at": None,
        "previous_value": None,
        "consumption": "999",
        "errors": [],
    }]
    resp = admin.post("/v1/imports/readings/commit", json={
        "month": "2030-01", "commit_token": _forge_token(forged),
    })
    assert resp.status_code == 200, resp.text
    # Server re-derived from meter_number "SEC03-GHOST" (not registered) → nothing written.
    assert resp.json()["data"]["saved"] == 0

    ws = admin.get("/v1/periods/2030-01/worksheet").json()["data"]
    assert all(r["reading"] is None for r in ws["rows"])
