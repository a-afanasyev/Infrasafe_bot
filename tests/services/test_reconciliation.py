"""PR-D / PR-D2 — reconcile_buildings() precise set-diff drift detection.

InfraSafe state and the outbox writer are mocked; the advisory-lock SQL is
exercised against PostgreSQL only at deploy time.

`_expected_eid` is intentionally duplicated from production — pinning the
SHA-256 → UUID algorithm in tests means a silent prod-side change will trip
this suite. The same algorithm lives on the InfraSafe side at
src/services/ukIntegrationService.js:158-167.
"""
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from uk_management_bot.services import reconciliation


def _expected_eid(uk_id: int) -> str:
    h = hashlib.sha256(f"uk-building-{uk_id}".encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


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


def test_expected_external_id_matches_infrasafe_algorithm():
    """Pin the SHA-256 → UUID-shape algorithm — InfraSafe relies on the same."""
    # Hand-computed reference: SHA-256("uk-building-1") truncated to 32 hex.
    eid = reconciliation._expected_external_id(1)
    assert eid == _expected_eid(1)
    # UUID shape: 8-4-4-4-12 hex chars.
    parts = eid.split("-")
    assert [len(p) for p in parts] == [8, 4, 4, 4, 12]
    assert all(c in "0123456789abcdef" for p in parts for c in p)


@pytest.mark.asyncio
async def test_in_sync_when_expected_set_matches(_wired):
    """InfraSafe has exactly the expected external_ids → in_sync, no replay."""
    monkeypatch, mock_fetch, mock_queue = _wired
    rows = [_building_row(1), _building_row(2), _building_row(3)]
    mock_fetch.return_value = {_expected_eid(1), _expected_eid(2), _expected_eid(3)}
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(True, rows)
    )

    result = await reconciliation.reconcile_buildings()

    assert result == {"in_sync": True, "uk": 3, "infrasafe": 3}
    mock_queue.assert_not_called()


@pytest.mark.asyncio
async def test_drift_replays_only_missing_buildings(_wired):
    """UK has 3 buildings, InfraSafe knows 1 → exactly 2 replays, the missing ones."""
    monkeypatch, mock_fetch, mock_queue = _wired
    rows = [_building_row(1), _building_row(2), _building_row(3)]
    mock_fetch.return_value = {_expected_eid(1)}
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(True, rows)
    )

    result = await reconciliation.reconcile_buildings()

    assert result["in_sync"] is False
    assert result["uk"] == 3
    assert result["infrasafe"] == 1
    assert result["missing"] == 2
    assert result["enqueued"] == 2
    assert result["orphans"] == 0
    assert mock_queue.call_count == 2

    # And the two replayed ids are exactly the missing UK building ids (2 and 3).
    replayed_ids = sorted(call.args[3]["id"] for call in mock_queue.call_args_list)
    assert replayed_ids == [2, 3]


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


@pytest.mark.asyncio
async def test_precise_diff_enqueues_exactly_missing(_wired):
    """UK has ids 1,2,3; InfraSafe knows only 1 and 2 → only id=3 enqueued."""
    monkeypatch, mock_fetch, mock_queue = _wired
    rows = [_building_row(1), _building_row(2), _building_row(3)]
    mock_fetch.return_value = {_expected_eid(1), _expected_eid(2)}
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(True, rows)
    )

    result = await reconciliation.reconcile_buildings()

    assert mock_queue.call_count == 1
    payload = mock_queue.call_args.args[3]  # (db, event, endpoint, data)
    assert payload["id"] == 3
    assert payload["address"] == "Test St 3"

    assert result["enqueued"] == 1
    assert result["missing"] == 1
    assert result["orphans"] == 0
    assert result["in_sync"] is False


@pytest.mark.asyncio
async def test_orphans_in_infrasafe_logged_but_not_deleted(_wired, caplog):
    """InfraSafe has an external_id not matching any active UK building → orphan."""
    monkeypatch, mock_fetch, mock_queue = _wired
    rows = [_building_row(1)]
    # InfraSafe knows building 1 plus a leftover external_id for a non-existent UK id.
    mock_fetch.return_value = {_expected_eid(1), _expected_eid(99)}
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(True, rows)
    )

    with caplog.at_level("WARNING", logger="uk_management_bot.services.reconciliation"):
        result = await reconciliation.reconcile_buildings()

    # No replay — UK isn't missing anything.
    mock_queue.assert_not_called()
    assert result["missing"] == 0
    assert result["orphans"] == 1
    assert result["in_sync"] is False
    # Orphan was logged, not silently swallowed.
    assert any("orphan" in rec.message.lower() for rec in caplog.records)


@pytest.mark.asyncio
async def test_replay_capped_at_replay_cap(_wired, monkeypatch):
    """A huge missing set is capped to REPLAY_CAP per cycle to bound outbox bursts."""
    _, mock_fetch, mock_queue = _wired
    # 60 UK buildings, InfraSafe knows none → 60 missing, but cap is 50.
    rows = [_building_row(i) for i in range(1, 61)]
    mock_fetch.return_value = set()
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(True, rows)
    )

    result = await reconciliation.reconcile_buildings()

    assert result["missing"] == 60
    assert result["enqueued"] == reconciliation.REPLAY_CAP == 50
    assert mock_queue.call_count == 50
