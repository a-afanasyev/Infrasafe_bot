"""PR-16 — OPS-105: outbox retention + Prometheus /metrics."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from uk_management_bot.api.main import (
    prometheus_metrics, settings as main_settings,
)
from uk_management_bot.services.outbox_retention import purge_old_sent_outbox
from uk_management_bot.database.models.webhook_outbox import WebhookOutbox


def _rec(**kw):
    base = dict(
        event_id=str(uuid.uuid4()),
        event="building.created",
        endpoint="/api/webhooks/uk/building",
        payload={"event": "building.created"},
        status="pending",
    )
    base.update(kw)
    return WebhookOutbox(**base)


# ---------------------------------------------------------------------------
# OPS-105 retention — purge_old_sent_outbox
# ---------------------------------------------------------------------------

class TestRetention:
    @pytest.mark.asyncio
    async def test_purges_only_old_sent(self, monkeypatch, db_session_factory):
        monkeypatch.setattr(
            "uk_management_bot.database.session.AsyncSessionLocal", db_session_factory
        )
        now = datetime.now(timezone.utc)
        async with db_session_factory() as db:
            db.add_all([
                _rec(status="sent", sent_at=now - timedelta(days=40)),   # удалить
                _rec(status="sent", sent_at=now - timedelta(days=31)),   # удалить
                _rec(status="sent", sent_at=now - timedelta(days=5)),    # оставить (свежая)
                _rec(status="failed", sent_at=now - timedelta(days=40)), # оставить (не sent)
                _rec(status="pending"),                                  # оставить
            ])
            await db.commit()

        result = await purge_old_sent_outbox(retention_days=30)
        assert result == {"deleted": 2}

        async with db_session_factory() as db:
            rows = (await db.execute(select(WebhookOutbox))).scalars().all()
            statuses = sorted(r.status for r in rows)
        # остались: 1 свежий sent + 1 failed + 1 pending
        assert statuses == ["failed", "pending", "sent"]

    @pytest.mark.asyncio
    async def test_nothing_to_purge(self, monkeypatch, db_session_factory):
        monkeypatch.setattr(
            "uk_management_bot.database.session.AsyncSessionLocal", db_session_factory
        )
        now = datetime.now(timezone.utc)
        async with db_session_factory() as db:
            db.add(_rec(status="sent", sent_at=now - timedelta(days=1)))
            await db.commit()
        assert await purge_old_sent_outbox(retention_days=30) == {"deleted": 0}

    @pytest.mark.asyncio
    async def test_db_unavailable_no_raise(self, monkeypatch):
        monkeypatch.setattr("uk_management_bot.database.session.AsyncSessionLocal", None)
        result = await purge_old_sent_outbox()
        assert result == {"deleted": 0, "error": "db_unavailable"}


# ---------------------------------------------------------------------------
# OPS-105 /metrics — Prometheus exposition
# ---------------------------------------------------------------------------

class TestPrometheusMetrics:
    @pytest.mark.asyncio
    async def test_metrics_disabled_no_gauges(self, monkeypatch):
        monkeypatch.setattr(main_settings, "INFRASAFE_WEBHOOK_ENABLED", False)
        resp = await prometheus_metrics()
        body = resp.body.decode()
        assert "uk_outbox_pending" not in body  # gauges absent when disabled

    @pytest.mark.asyncio
    async def test_metrics_reports_gauges(self, monkeypatch, db_session_factory):
        monkeypatch.setattr(main_settings, "INFRASAFE_WEBHOOK_ENABLED", True)
        monkeypatch.setattr(
            "uk_management_bot.database.session.AsyncSessionLocal", db_session_factory
        )
        async with db_session_factory() as db:
            db.add_all([_rec(), _rec(), _rec(status="failed")])
            await db.commit()

        resp = await prometheus_metrics()
        body = resp.body.decode()
        assert "uk_outbox_pending 2.0" in body
        assert "uk_outbox_failed_last_24h 1.0" in body
        assert "uk_outbox_oldest_pending_age_seconds" in body
        assert "uk_outbox_stuck_in_flight 0.0" in body
