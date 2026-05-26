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
