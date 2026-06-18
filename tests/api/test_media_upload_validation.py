"""SEC-021 — input validation on POST /api/v2/media/upload.

Pre-fix the endpoint forwarded `request_number` and `category` straight to
the downstream Media Service. An authenticated attacker could push values
like `../../etc/passwd` or arbitrary category strings to be interpreted by
the Media Service's storage layer (path-traversal / IDOR / log poisoning).

We validate at the proxy boundary:
  * `request_number` must match REQUEST_NUMBER_PATTERN (`YYMMDD-NNN`)
  * `category` must be a FileCategories enum value

Both fail with HTTP 422 *before* any outbound httpx call — verified here by
not mocking the Media Service.
"""
import io
import pytest


def _file_part(name: str = "evidence.jpg", content: bytes = b"\xff\xd8\xff\xe0test"):
    """A small in-memory file part suitable for multipart/form-data POSTs."""
    return ("file", (name, io.BytesIO(content), "image/jpeg"))


def _bypass_request_access(monkeypatch):
    """The proxy gates uploads on check_request_access (request ownership).
    These tests target the validation/forward layer, not access control, and
    don't seed a request row — stub the access check to a no-op so we reach
    the code under test instead of a 404.

    ARCH-012: the media-proxy endpoints moved out of `api.main` into
    `api.routes.media_proxy`; patch `check_request_access` where it is now
    looked up."""
    from uk_management_bot.api.routes import media_proxy

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(media_proxy, "check_request_access", _noop)


@pytest.mark.asyncio
async def test_invalid_request_number_rejected_before_media_service_call(client):
    """Path-traversal request_number is rejected at the proxy boundary."""
    resp = await client.post(
        "/api/v2/media/upload",
        files=[_file_part()],
        data={"request_number": "../../etc/passwd", "category": "request_photo"},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_short_request_number_rejected(client):
    """Loose `\\d{3,}`-shaped numbers still get caught by `\\d{6}-\\d{3}`."""
    resp = await client.post(
        "/api/v2/media/upload",
        files=[_file_part()],
        data={"request_number": "1234-5", "category": "request_photo"},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_invalid_category_rejected(client):
    """`category` not in FileCategories enum → 422 via FastAPI validation."""
    resp = await client.post(
        "/api/v2/media/upload",
        files=[_file_part()],
        data={"request_number": "260524-001", "category": "../etc/passwd"},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_well_formed_request_passes_validation_layer(client, monkeypatch):
    """Valid request_number + category get past validation. We stub the
    outbound httpx call so the test doesn't actually need the Media Service —
    the assertion is that we move past validation and produce a normal proxy
    response shape."""
    from uk_management_bot.api import main as api_main

    class _StubResp:
        status_code = 200
        text = "ok"

        @staticmethod
        def json():
            return {"id": "media-stub", "ok": True}

    class _StubClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, files=None, data=None):
            # Capture the forwarded payload so the test asserts what the
            # proxy actually relays.
            _StubClient.last_url = url
            _StubClient.last_data = data
            return _StubResp()

    monkeypatch.setattr(api_main.httpx, "AsyncClient", _StubClient)
    # MEDIA_SERVICE_URL must be set for the proxy to not 503.
    monkeypatch.setattr(api_main.settings, "MEDIA_SERVICE_URL", "http://stub-media")
    _bypass_request_access(monkeypatch)

    resp = await client.post(
        "/api/v2/media/upload",
        files=[_file_part()],
        data={"request_number": "260524-001", "category": "completion_photo"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"id": "media-stub", "ok": True}
    assert _StubClient.last_url.endswith("/api/v1/media/upload")
    # Enum-valued category is forwarded as its string value, not the enum repr.
    assert _StubClient.last_data["category"] == "completion_photo"
    assert _StubClient.last_data["request_number"] == "260524-001"


@pytest.mark.asyncio
async def test_spoofed_content_rejected_by_magic_bytes(client, monkeypatch):
    """H2: bytes that aren't a real media file are rejected even with a valid
    image Content-Type header, BEFORE any outbound media-service call."""
    from uk_management_bot.api import main as api_main

    called = {"n": 0}

    class _StubClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            called["n"] += 1
            raise AssertionError("media service must not be called for spoofed content")

    monkeypatch.setattr(api_main.httpx, "AsyncClient", _StubClient)
    monkeypatch.setattr(api_main.settings, "MEDIA_SERVICE_URL", "http://stub-media")
    _bypass_request_access(monkeypatch)

    resp = await client.post(
        "/api/v2/media/upload",
        files=[("file", ("x.jpg", io.BytesIO(b"<html><script>alert(1)</script>"), "image/jpeg"))],
        data={"request_number": "260524-001", "category": "completion_photo"},
    )
    assert resp.status_code == 422, resp.text
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_forwarded_content_type_is_sniffed_not_client(client, monkeypatch):
    """H2: the proxy forwards a server-derived content_type (from magic bytes),
    not the client-supplied header — a client lying image/png over JPEG bytes
    is relayed as image/jpeg."""
    from uk_management_bot.api import main as api_main

    captured = {}

    class _StubResp:
        status_code = 200
        text = "ok"

        @staticmethod
        def json():
            return {"ok": True}

    class _StubClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, files=None, data=None):
            captured["files"] = files
            return _StubResp()

    monkeypatch.setattr(api_main.httpx, "AsyncClient", _StubClient)
    monkeypatch.setattr(api_main.settings, "MEDIA_SERVICE_URL", "http://stub-media")
    _bypass_request_access(monkeypatch)

    resp = await client.post(
        "/api/v2/media/upload",
        files=[("file", ("x.png", io.BytesIO(b"\xff\xd8\xff\xe0jpegdata"), "image/png"))],
        data={"request_number": "260524-001", "category": "request_photo"},
    )
    assert resp.status_code == 200, resp.text
    # files["file"] == (filename, bytes, content_type)
    assert captured["files"]["file"][2] == "image/jpeg"
