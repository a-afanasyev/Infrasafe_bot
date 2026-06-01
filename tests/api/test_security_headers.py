"""SEC-061 — baseline security headers on every API response.

The app previously set only CORS headers. A `@app.middleware("http")` now adds
the standard hardening set (`X-Content-Type-Options`, `X-Frame-Options`,
`Referrer-Policy`, HSTS) via `setdefault`, so the edge proxy can still own a
header if it sets one. These tests pin that the headers are present on a normal
response.
"""
import pytest


@pytest.mark.asyncio
async def test_security_headers_present_on_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "max-age=" in r.headers["strict-transport-security"]


@pytest.mark.asyncio
async def test_security_headers_present_on_json_route(client):
    # A regular JSON route gets the same treatment (middleware is global).
    r = await client.get("/api/v2/announcements")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
