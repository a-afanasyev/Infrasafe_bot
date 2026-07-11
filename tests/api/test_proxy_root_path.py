"""F-03: edge terminates TLS and rewrites /uk/api/ -> /api/, so a bare uvicorn
builds trailing-slash redirect Location as http://.../api/... (loses https + /uk).

The fix is uvicorn config, not app code, so this exercises a real uvicorn.Server
(with ProxyHeadersMiddleware + root_path) rather than the full app:

- proxy_headers + trusted peer + X-Forwarded-Proto: https  -> scheme becomes https
- root_path="/uk"                                          -> prefix restored in Location

Negative cases prove the failure mode the finding describes: an untrusted peer's
X-Forwarded-Proto is ignored (scheme stays http), and without root_path the /uk
prefix is lost.
"""
import asyncio
import socket
import threading

import httpx
import pytest
import uvicorn
from fastapi import FastAPI


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _probe_app() -> FastAPI:
    app = FastAPI()

    # Route WITHOUT trailing slash → a request WITH the slash triggers the 307.
    @app.post("/api/v2/auth/login")
    def login():  # pragma: no cover - never reached (redirect fires first)
        return {"ok": True}

    return app


async def _redirect_location(*, forwarded_allow_ips: str, root_path: str) -> tuple[int, str]:
    port = _free_port()
    config = uvicorn.Config(
        _probe_app(),
        host="127.0.0.1",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips=forwarded_allow_ips,
        root_path=root_path,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        assert server.started, "uvicorn did not start in time"

        async with httpx.AsyncClient(follow_redirects=False) as client:
            resp = await client.post(
                f"http://127.0.0.1:{port}/api/v2/auth/login/",
                headers={"X-Forwarded-Proto": "https", "Host": "profk.uz"},
            )
        return resp.status_code, resp.headers.get("location", "")
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_trusted_proxy_and_root_path_preserve_https_and_prefix():
    status, location = await _redirect_location(
        forwarded_allow_ips="127.0.0.1", root_path="/uk"
    )
    assert status == 307
    assert location == "https://profk.uz/uk/api/v2/auth/login"


@pytest.mark.asyncio
async def test_untrusted_peer_ignores_forwarded_proto():
    # Peer 127.0.0.1 is NOT in the allow-list → X-Forwarded-Proto is dropped,
    # scheme falls back to http (the vulnerable behaviour without the fix).
    status, location = await _redirect_location(
        forwarded_allow_ips="10.99.99.99", root_path="/uk"
    )
    assert status == 307
    assert location.startswith("http://")


@pytest.mark.asyncio
async def test_without_root_path_prefix_is_lost():
    status, location = await _redirect_location(
        forwarded_allow_ips="127.0.0.1", root_path=""
    )
    assert status == 307
    assert location == "https://profk.uz/api/v2/auth/login"  # no /uk
