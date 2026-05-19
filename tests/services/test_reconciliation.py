"""PR-D — reconcile_buildings() drift detection and replay.

InfraSafe state and the outbox writer are mocked; the advisory-lock SQL is
exercised against PostgreSQL only at deploy time.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from uk_management_bot.services import reconciliation


class _FakeSession:
    """Minimal async-context session: controllable lock result and query rows."""

    def __init__(self, lock_result: bool, rows: list):
        self._lock_result = lock_result
        self._rows = rows
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def scalar(self, *args, **kwargs):
        # Only call is the advisory-lock acquisition.
        return self._lock_result

    async def execute(self, *args, **kwargs):
        # Serves both the buildings SELECT and the advisory-unlock statement.
        result = MagicMock()
        result.all.return_value = self._rows
        return result


def _building_row(bid: int):
    return SimpleNamespace(
        id=bid,
        address=f"Test St {bid}",
        yard_id=1,
        name="Test Yard",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def _wired(monkeypatch):
    """Enable webhooks and return monkeypatch + mocks for fetch/queue."""
    monkeypatch.setattr(reconciliation.settings, "INFRASAFE_WEBHOOK_ENABLED", True)
    mock_fetch = AsyncMock()
    mock_queue = AsyncMock()
    monkeypatch.setattr(reconciliation, "fetch_infrasafe_external_buildings", mock_fetch)
    monkeypatch.setattr(reconciliation, "queue_webhook", mock_queue)
    return monkeypatch, mock_fetch, mock_queue


@pytest.mark.asyncio
async def test_in_sync_when_counts_match(_wired):
    """UK count == InfraSafe count → in_sync, nothing re-enqueued."""
    monkeypatch, mock_fetch, mock_queue = _wired
    rows = [_building_row(1), _building_row(2), _building_row(3)]
    mock_fetch.return_value = {"uuid-1", "uuid-2", "uuid-3"}
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(True, rows)
    )

    result = await reconciliation.reconcile_buildings()

    assert result == {"in_sync": True, "uk": 3, "infrasafe": 3}
    mock_queue.assert_not_called()


@pytest.mark.asyncio
async def test_drift_replays_missing_buildings(_wired):
    """UK has more buildings than InfraSafe → drift, recent buildings replayed."""
    monkeypatch, mock_fetch, mock_queue = _wired
    rows = [_building_row(1), _building_row(2), _building_row(3)]
    mock_fetch.return_value = {"uuid-1"}  # InfraSafe knows only one
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(True, rows)
    )

    result = await reconciliation.reconcile_buildings()

    assert result["in_sync"] is False
    assert result["uk"] == 3
    assert result["infrasafe"] == 1
    assert result["enqueued"] == 3
    assert mock_queue.call_count == 3


@pytest.mark.asyncio
async def test_skips_when_advisory_lock_held(_wired):
    """pg_try_advisory_lock returns false → another worker owns the cycle."""
    monkeypatch, mock_fetch, mock_queue = _wired
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(False, [])
    )

    result = await reconciliation.reconcile_buildings()

    assert result == {"skipped": "lock_held"}
    mock_fetch.assert_not_called()
    mock_queue.assert_not_called()
