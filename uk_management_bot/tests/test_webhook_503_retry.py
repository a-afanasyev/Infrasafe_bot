"""Regression test for FIX-005: HTTP 503 must be retryable, not permanent.

The bug: webhook_sender.send_webhook() returned `retryable=False` for status
503, so the very first 503 from InfraSafe pushed the outbox record to
`failed` instead of retrying. That meant any short InfraSafe outage caused
permanent event loss for every webhook fired during the window.

These tests exercise the full process_outbox() cycle against an aiosqlite
in-memory DB with httpx.AsyncClient.post monkeypatched to return 503, and
assert the record stays `pending` with backoff until attempts reach
INFRASAFE_WEBHOOK_MAX_RETRIES.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.webhook_outbox import WebhookOutbox
from uk_management_bot.database.session import Base
from uk_management_bot.services import webhook_sender


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal stand-in for httpx.Response used by send_webhook()."""

    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


@pytest_asyncio.fixture
async def sqlite_session_factory(monkeypatch):
    """Spin up an in-memory aiosqlite engine, create tables, expose factory.

    Patches:
      * webhook_sender.AsyncSessionLocal (the symbol used inside process_outbox
        via a local import — but we also patch the source module to be safe).
      * uk_management_bot.database.session.AsyncSessionLocal so the local
        `from ... import AsyncSessionLocal` inside process_outbox picks up
        the test factory.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # process_outbox does `from uk_management_bot.database.session import AsyncSessionLocal`
    # at call time, so we patch the attribute on the session module.
    from uk_management_bot.database import session as session_mod
    monkeypatch.setattr(session_mod, "AsyncSessionLocal", factory, raising=False)

    yield factory

    await engine.dispose()


@pytest.fixture
def webhook_settings(monkeypatch):
    """Force webhook config to a known, enabled state for the test."""
    monkeypatch.setattr(settings, "INFRASAFE_WEBHOOK_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "INFRASAFE_WEBHOOK_URL", "http://infra.test", raising=False)
    monkeypatch.setattr(settings, "INFRASAFE_WEBHOOK_SECRET", "test-secret-32chars-minimum-aaaaaa", raising=False)
    monkeypatch.setattr(settings, "INFRASAFE_USE_NEXT_SECRET", False, raising=False)
    monkeypatch.setattr(settings, "INFRASAFE_WEBHOOK_SECRET_NEXT", "", raising=False)
    monkeypatch.setattr(settings, "INFRASAFE_WEBHOOK_MAX_RETRIES", 3, raising=False)
    return settings


@pytest.fixture
def patch_httpx_503(monkeypatch):
    """Patch httpx.AsyncClient.post to return HTTP 503 every call."""

    async def fake_post(self, url, **kwargs):  # noqa: ARG001 — matching signature
        return _FakeResponse(status_code=503)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


async def _seed_pending_record(factory: async_sessionmaker[AsyncSession]) -> int:
    """Insert a single pending webhook_outbox row, return its id."""
    async with factory() as db:
        record = WebhookOutbox(
            event_id=str(uuid.uuid4()),
            event="building.created",
            endpoint="/api/v1/uk-webhooks/building.created",
            payload={"event": "building.created", "building": {"id": 1}},
            status="pending",
            attempts=0,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record.id


async def _fetch(factory: async_sessionmaker[AsyncSession], rec_id: int) -> WebhookOutbox:
    async with factory() as db:
        result = await db.execute(select(WebhookOutbox).where(WebhookOutbox.id == rec_id))
        rec = result.scalar_one()
        return rec


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestHttp503Retryable:
    async def test_single_503_keeps_record_pending_and_schedules_retry(
        self,
        sqlite_session_factory,
        webhook_settings,
        patch_httpx_503,
    ):
        """AC: one 503 → status='pending', attempts=1, retry_after set."""
        rec_id = await _seed_pending_record(sqlite_session_factory)

        await webhook_sender.process_outbox()

        rec = await _fetch(sqlite_session_factory, rec_id)
        assert rec.status == "pending", (
            f"503 must remain retryable; got status={rec.status!r} "
            f"(record went to failed after a single 503 — bug FIX-005)"
        )
        assert rec.attempts == 1, f"attempts must be 1 after one cycle, got {rec.attempts}"
        assert rec.retry_after is not None, "retry_after must be scheduled for retryable failure"
        assert rec.last_error and "503" in rec.last_error

    async def test_503_goes_to_failed_only_after_max_retries(
        self,
        sqlite_session_factory,
        webhook_settings,
        patch_httpx_503,
        monkeypatch,
    ):
        """AC: record must reach `failed` only when attempts >= MAX_RETRIES."""
        # Defang retry_after gating so consecutive cycles re-pick the record
        # immediately (the test isn't validating backoff timing).
        from uk_management_bot.services import webhook_sender as ws

        async def _clear_retry_after(factory, rec_id):
            async with factory() as db:
                result = await db.execute(select(WebhookOutbox).where(WebhookOutbox.id == rec_id))
                rec = result.scalar_one()
                rec.retry_after = None
                await db.commit()

        rec_id = await _seed_pending_record(sqlite_session_factory)

        max_retries = settings.INFRASAFE_WEBHOOK_MAX_RETRIES  # 3
        for cycle in range(max_retries - 1):
            await ws.process_outbox()
            rec = await _fetch(sqlite_session_factory, rec_id)
            assert rec.status == "pending", (
                f"cycle {cycle + 1}/{max_retries}: status must stay pending until "
                f"attempts >= MAX_RETRIES, got {rec.status!r} attempts={rec.attempts}"
            )
            assert rec.attempts == cycle + 1
            await _clear_retry_after(sqlite_session_factory, rec_id)

        # Final cycle — attempts will reach MAX_RETRIES and record must fail.
        await ws.process_outbox()
        rec = await _fetch(sqlite_session_factory, rec_id)
        assert rec.attempts == max_retries
        assert rec.status == "failed", (
            f"after attempts={rec.attempts} >= MAX_RETRIES={max_retries} "
            f"record must be `failed`, got {rec.status!r}"
        )
