"""Тесты публичного (без аутентификации) API визуальных отчётов «до/после»
(T8, /api/v2/public/work-reports). Это первое место в кодовой базе, где
контент work-report покидает авторизованный периметр — IDOR-гварды и
асимметрия флага (feed=200 [], media=404) здесь проверяются буквально,
не как формальность.

`_mk_report` — тот же паттерн, что и в test_work_reports_lifecycle.py.
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import uk_management_bot.api.work_reports.public_router as public_router
from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.work_report import WorkReport

BASE = "/api/v2/public/work-reports"

NON_PUBLISHED_STATUSES = ["pending", "needs_media", "publishing", "needs_review", "rejected"]


# ── Helpers ──────────────────────────────────────────────────────────


def _enable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WORK_REPORTS_ENABLED", True)


def _disable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WORK_REPORTS_ENABLED", False)


async def _mk_report(db, number: str, **kwargs) -> WorkReport:
    defaults = dict(
        category_key="plumbing",
        address_public="Двор Х",
        performed_at=datetime.now(timezone.utc),
        before_media_ids=[1], after_media_ids=[2],
        media_meta=[
            {"id": 1, "file_type": "photo", "mime": "image/jpeg", "size": 1024},
            {"id": 2, "file_type": "photo", "mime": "image/png", "size": 2048},
        ],
        locked_media_ids=[],
        status="pending", source="manual",
    )
    defaults.update(kwargs)
    report = WorkReport(request_number=number, **defaults)
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


@pytest_asyncio.fixture
async def anon_client(db_session_factory):
    """A genuinely anonymous HTTP client — only `get_db` overridden, NOT
    `get_current_user`. Used to prove no-auth-required is actually true,
    unlike the shared `client` fixture which always injects a manager."""

    async def override_get_db():
        async with db_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _reset_work_reports_public_state():
    """Module-level TTL cache + revoke-throttle timestamp leak across tests
    without this — same rationale as conftest's _reset_public_board_cache."""
    public_router._work_reports_feed_cache.clear()
    public_router._last_revoke_check_at = None
    yield
    public_router._work_reports_feed_cache.clear()
    public_router._last_revoke_check_at = None


class _FakeUpstreamResponse:
    def __init__(self, status_code=200, chunks=None):
        self.status_code = status_code
        self._chunks = chunks if chunks is not None else [b"fakebytes"]
        self.aclose_called = False

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self):
        self.aclose_called = True


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient, mirroring the subset of the API the
    router actually uses: build_request + send(stream=True) + aclose."""

    def __init__(self, response=None, raise_transport_error=False):
        self._response = response
        self._raise = raise_transport_error
        self.aclose_called = False

    def build_request(self, method, url, headers=None):
        return {"method": method, "url": url, "headers": headers}

    async def send(self, request, stream=True):
        if self._raise:
            raise httpx.TransportError("boom")
        return self._response

    async def aclose(self):
        self.aclose_called = True


def _patch_httpx_client(monkeypatch, fake_client: _FakeAsyncClient) -> None:
    monkeypatch.setattr(public_router.httpx, "AsyncClient", lambda timeout=None: fake_client)
    monkeypatch.setattr(public_router.settings, "MEDIA_SERVICE_URL", "http://stub-media")


# ── Feed: status filtering ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_feed_only_published_visible(client, db_session, monkeypatch):
    _enable(monkeypatch)
    for status in NON_PUBLISHED_STATUSES:
        await _mk_report(db_session, f"260725-{status}", status=status)
    published = await _mk_report(
        db_session, "260725-pub", status="published",
        published_at=datetime.now(timezone.utc),
    )

    resp = await client.get(BASE)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == published.id


# ── Feed: ordering ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_feed_ordering_published_at_desc_then_id_desc(client, db_session, monkeypatch):
    _enable(monkeypatch)
    now = datetime.now(timezone.utc)

    older = await _mk_report(db_session, "260725-o1", status="published", published_at=now - timedelta(hours=1))
    # Same published_at as `tie2` below but created first (lower id) — id DESC
    # must break the tie in favour of the higher id.
    tie1 = await _mk_report(db_session, "260725-t1", status="published", published_at=now)
    tie2 = await _mk_report(db_session, "260725-t2", status="published", published_at=now)

    resp = await client.get(BASE)
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert ids == [tie2.id, tie1.id, older.id]


# ── Feed: no PII / privileged fields leak ────────────────────────────


@pytest.mark.asyncio
async def test_feed_no_pii_fields_leak(client, db_session, monkeypatch):
    _enable(monkeypatch)
    await _mk_report(db_session, "260725-pii", status="published", published_at=datetime.now(timezone.utc))

    resp = await client.get(BASE)
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert set(item.keys()) == {"id", "category_key", "address", "completed_on", "before", "after"}
    for forbidden in ("request_number", "description", "user_id", "moderated_by", "reject_reason"):
        assert forbidden not in item


# ── Media endpoint: non-published statuses → 404 ─────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status", NON_PUBLISHED_STATUSES)
async def test_media_404_for_non_published_status(client, db_session, monkeypatch, status):
    _enable(monkeypatch)
    report = await _mk_report(db_session, f"260725-np-{status}", status=status)

    resp = await client.get(f"{BASE}/{report.id}/media/1")
    assert resp.status_code == 404


# ── Media endpoint: IDOR — cross-report media_id ─────────────────────


@pytest.mark.asyncio
async def test_media_404_cross_report_media_id_idor(client, db_session, monkeypatch):
    _enable(monkeypatch)
    now = datetime.now(timezone.utc)
    r1 = await _mk_report(
        db_session, "260725-idor1", status="published", published_at=now,
        before_media_ids=[1], after_media_ids=[2],
        media_meta=[{"id": 1, "mime": "image/jpeg"}, {"id": 2, "mime": "image/jpeg"}],
    )
    r2 = await _mk_report(
        db_session, "260725-idor2", status="published", published_at=now,
        before_media_ids=[3], after_media_ids=[4],
        media_meta=[{"id": 3, "mime": "image/jpeg"}, {"id": 4, "mime": "image/jpeg"}],
    )

    # media_id 3 is real and belongs to a PUBLISHED report (r2) — but not r1.
    resp = await client.get(f"{BASE}/{r1.id}/media/3")
    assert resp.status_code == 404

    # Sanity: it IS retrievable under its own report.
    _patch_httpx_client(monkeypatch, _FakeAsyncClient(response=_FakeUpstreamResponse()))
    resp_own = await client.get(f"{BASE}/{r2.id}/media/3")
    assert resp_own.status_code == 200


# ── Media endpoint: headers / conditional GET ────────────────────────


@pytest.mark.asyncio
async def test_media_200_has_cache_headers(client, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(
        db_session, "260725-hdr", status="published", published_at=datetime.now(timezone.utc),
        before_media_ids=[1], after_media_ids=[2],
        media_meta=[{"id": 1, "mime": "image/jpeg"}, {"id": 2, "mime": "image/png"}],
    )
    _patch_httpx_client(monkeypatch, _FakeAsyncClient(response=_FakeUpstreamResponse(chunks=[b"abc", b"def"])))

    resp = await client.get(f"{BASE}/{report.id}/media/1")
    assert resp.status_code == 200
    assert resp.headers["etag"] == '"wr-1"'
    assert resp.headers["cache-control"] == "public, max-age=3600"
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == b"abcdef"


@pytest.mark.asyncio
async def test_media_304_on_matching_if_none_match(client, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(
        db_session, "260725-etag", status="published", published_at=datetime.now(timezone.utc),
    )
    # No httpx client patched — a 304 hit must never call media-service.
    unreachable = _FakeAsyncClient(raise_transport_error=True)
    _patch_httpx_client(monkeypatch, unreachable)

    resp = await client.get(f"{BASE}/{report.id}/media/1", headers={"If-None-Match": '"wr-1"'})
    assert resp.status_code == 304
    assert resp.content == b""
    assert resp.headers["etag"] == '"wr-1"'


# ── Media endpoint: unpublish revokes access ──────────────────────────


@pytest.mark.asyncio
async def test_media_404_after_unpublish(client, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(
        db_session, "260725-unpub", status="published", published_at=datetime.now(timezone.utc),
    )
    _patch_httpx_client(monkeypatch, _FakeAsyncClient(response=_FakeUpstreamResponse()))

    resp_before = await client.get(f"{BASE}/{report.id}/media/1")
    assert resp_before.status_code == 200

    # Direct DB manipulation — simplest way to move the report out of
    # `published` without pulling in the (separately-tested) manager API.
    report.status = "rejected"
    db_session.add(report)
    await db_session.commit()

    resp_after = await client.get(f"{BASE}/{report.id}/media/1")
    assert resp_after.status_code == 404


# ── Media-service availability asymmetry ──────────────────────────────


@pytest.mark.asyncio
async def test_feed_200_even_when_media_service_unconfigured(client, db_session, monkeypatch):
    """The feed builds entirely from `media_meta` — it must never call
    media-service, so it must return real items even with no
    MEDIA_SERVICE_URL configured / reachable."""
    _enable(monkeypatch)
    monkeypatch.setattr(settings, "MEDIA_SERVICE_URL", "")
    await _mk_report(db_session, "260725-noms", status="published", published_at=datetime.now(timezone.utc))

    resp = await client.get(BASE)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_media_503_when_media_service_unreachable(client, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(
        db_session, "260725-unreach", status="published", published_at=datetime.now(timezone.utc),
    )
    _patch_httpx_client(monkeypatch, _FakeAsyncClient(raise_transport_error=True))

    resp = await client.get(f"{BASE}/{report.id}/media/1")
    assert resp.status_code == 503


# ── Feature-flag gate asymmetry ────────────────────────────────────────


@pytest.mark.asyncio
async def test_flag_disabled_feed_returns_empty_200(client, db_session, monkeypatch):
    _disable(monkeypatch)
    await _mk_report(db_session, "260725-flagoff", status="published", published_at=datetime.now(timezone.utc))

    resp = await client.get(BASE)
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


@pytest.mark.asyncio
async def test_flag_disabled_media_returns_404(client, db_session, monkeypatch):
    _disable(monkeypatch)
    report = await _mk_report(
        db_session, "260725-flagoffm", status="published", published_at=datetime.now(timezone.utc),
    )

    resp = await client.get(f"{BASE}/{report.id}/media/1")
    assert resp.status_code == 404


# ── Genuine anonymous access (no `client` fixture) ─────────────────────


@pytest.mark.asyncio
async def test_genuine_anonymous_access_feed(anon_client, db_session, monkeypatch):
    _enable(monkeypatch)
    await _mk_report(db_session, "260725-anon1", status="published", published_at=datetime.now(timezone.utc))

    assert "authorization" not in {k.lower() for k in anon_client.headers.keys()}
    resp = await anon_client.get(BASE)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_genuine_anonymous_access_media(anon_client, db_session, monkeypatch):
    _enable(monkeypatch)
    report = await _mk_report(
        db_session, "260725-anon2", status="published", published_at=datetime.now(timezone.utc),
    )
    _patch_httpx_client(monkeypatch, _FakeAsyncClient(response=_FakeUpstreamResponse()))

    resp = await anon_client.get(f"{BASE}/{report.id}/media/1")
    assert resp.status_code == 200


# ── Cache behaviour ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_feed_cache_hit_serves_stale_within_ttl(client, db_session, monkeypatch):
    _enable(monkeypatch)
    await _mk_report(db_session, "260725-cache1", status="published", published_at=datetime.now(timezone.utc))

    resp1 = await client.get(BASE, params={"limit": 10, "offset": 0})
    assert resp1.status_code == 200
    assert resp1.json()["total"] == 1
    assert (10, 0) in public_router._work_reports_feed_cache

    # A second published report lands in the DB, but a cache hit must keep
    # serving the stale payload until the TTL expires.
    await _mk_report(db_session, "260725-cache2", status="published", published_at=datetime.now(timezone.utc))

    resp2 = await client.get(BASE, params={"limit": 10, "offset": 0})
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 1  # still stale/cached


# ── Revoke-throttle ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoke_stale_publications_called_at_most_once_across_two_calls(
    client, db_session, monkeypatch
):
    _enable(monkeypatch)
    await _mk_report(db_session, "260725-rev1", status="published", published_at=datetime.now(timezone.utc))

    calls = {"n": 0}

    async def fake_revoke(db):
        calls["n"] += 1
        return 0

    monkeypatch.setattr(public_router, "revoke_stale_publications", fake_revoke)

    # Different params so both requests are cache MISSES (revoke check only
    # runs on a miss) — otherwise the second call would trivially skip it
    # via the cache hit path instead of the throttle.
    resp1 = await client.get(BASE, params={"limit": 5, "offset": 0})
    resp2 = await client.get(BASE, params={"limit": 5, "offset": 1})
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert calls["n"] <= 1


# ── Streaming byte-limit abort ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_media_stream_aborts_when_actual_bytes_exceed_limit(client, db_session, monkeypatch):
    """metadata (`media_meta[].size`) is a claim from the source, not a
    guarantee — the router must count REAL streamed bytes, not trust the
    stored size field."""
    _enable(monkeypatch)
    report = await _mk_report(
        db_session, "260725-overflow", status="published", published_at=datetime.now(timezone.utc),
        before_media_ids=[1], after_media_ids=[2],
        # media_meta claims a tiny size — irrelevant, the router doesn't
        # even read "size", but this underscores the point: it must not be
        # trusted even if it were consulted.
        media_meta=[{"id": 1, "mime": "image/jpeg", "size": 1}, {"id": 2, "mime": "image/jpeg", "size": 1}],
    )
    monkeypatch.setattr(settings, "PUBLIC_MEDIA_MAX_BYTES", 10)
    # 5 + 5 = 10 (<=10, both yielded), then +6 = 16 (>10, aborts without yielding).
    chunks = [b"12345", b"67890", b"abcdef"]
    _patch_httpx_client(monkeypatch, _FakeAsyncClient(response=_FakeUpstreamResponse(chunks=chunks)))

    resp = await client.get(f"{BASE}/{report.id}/media/1")
    assert resp.status_code == 200
    assert resp.content == b"1234567890"
    assert len(resp.content) <= 10
    assert resp.content != b"".join(chunks)
