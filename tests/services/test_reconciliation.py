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
    """Minimal async-context session: controllable lock result and query rows.

    `extra_rows`: what the SECOND (and later) `execute()` call returns, by
    call count — not SQL inspection. `reconcile_requests()` issues exactly
    two execute().all()-consuming statements (uk_stmt, then the
    building-resolve join); the advisory-unlock execute() in `finally`
    never reads `.all()`. Defaults to `_rows` when omitted — harmless for
    `reconcile_buildings()` callers, which never issue a second
    read-consuming query.
    """

    def __init__(self, lock_result: bool, rows: list, extra_rows: list | None = None):
        self._lock_result = lock_result
        self._rows = rows
        self._extra_rows = rows if extra_rows is None else extra_rows
        self._execute_count = 0
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def scalar(self, *args, **kwargs):
        # Only call is the advisory-lock acquisition.
        return self._lock_result

    async def execute(self, *args, **kwargs):
        self._execute_count += 1
        result = MagicMock()
        result.all.return_value = (
            self._rows if self._execute_count == 1 else self._extra_rows
        )
        return result


def _building_row(bid: int, *, gps_latitude=None, gps_longitude=None):
    return SimpleNamespace(
        id=bid,
        address=f"Test St {bid}",
        yard_id=1,
        name="Test Yard",
        gps_latitude=gps_latitude,
        gps_longitude=gps_longitude,
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
async def test_in_sync_when_expected_set_matches(_wired, caplog):
    """InfraSafe has exactly the expected external_ids → in_sync, no replay."""
    monkeypatch, mock_fetch, mock_queue = _wired
    rows = [_building_row(1), _building_row(2), _building_row(3)]
    mock_fetch.return_value = {_expected_eid(1), _expected_eid(2), _expected_eid(3)}
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(True, rows)
    )

    with caplog.at_level("WARNING", logger="uk_management_bot.services.reconciliation"):
        result = await reconciliation.reconcile_buildings()

    assert result == {"in_sync": True, "uk": 3, "infrasafe": 3}
    mock_queue.assert_not_called()
    # 2026-07-24: WARNING (not INFO) so "converged" survives prod's
    # LOG_LEVEL=WARNING — otherwise indistinguishable from a dead loop.
    assert any("cycle complete, in sync" in rec.message for rec in caplog.records)


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

    # ARCH-010: каждый replay обязан несёт repair-identity — без него one-shot
    # building.created пере-минтит ОРИГИНАЛЬНЫЙ детерминированный id, и
    # бессрочный дедуп InfraSafe молча глушит ремонт навсегда (fail-loud
    # funnel'а one-shot путь НЕ прикрывает). Nonce общий на весь запуск.
    identities = [call.args[4] for call in mock_queue.call_args_list]
    assert all(ident.repair_run_id for ident in identities)
    assert all(ident.version is None for ident in identities)
    assert len({ident.repair_run_id for ident in identities}) == 1


@pytest.mark.asyncio
async def test_drift_replay_repair_nonce_differs_between_runs(_wired):
    """ARCH-010: разные запуски reconcile дают разные repair_run_id →
    повторный ремонт не дедупится ни нашим unique, ни InfraSafe."""
    monkeypatch, mock_fetch, mock_queue = _wired
    rows = [_building_row(1), _building_row(2)]
    mock_fetch.return_value = {_expected_eid(1)}
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(True, rows)
    )

    await reconciliation.reconcile_buildings()
    first_run = mock_queue.call_args.args[4].repair_run_id
    await reconciliation.reconcile_buildings()
    second_run = mock_queue.call_args.args[4].repair_run_id
    assert first_run != second_run


@pytest.mark.asyncio
async def test_skips_when_advisory_lock_held(_wired):
    """pg_try_advisory_lock returns false → another worker owns the cycle.

    REFACTOR-091 (PR-5): внешний HTTP-фетч теперь идёт ДО лока (лок не должен
    висеть на время сети), поэтому fetch ВЫЗЫВАЕТСЯ; гарантия lock'а — что под
    ним ничего не enqueue'ится и цикл скипается.
    """
    monkeypatch, mock_fetch, mock_queue = _wired
    mock_fetch.return_value = set()
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(False, [])
    )

    result = await reconciliation.reconcile_buildings()

    assert result == {"skipped": "lock_held"}
    mock_fetch.assert_called_once()
    mock_queue.assert_not_called()


@pytest.mark.asyncio
async def test_precise_diff_enqueues_exactly_missing(_wired):
    """UK has ids 1,2,3 with coords; InfraSafe knows only 1 and 2 → id=3 enqueued with coords."""
    monkeypatch, mock_fetch, mock_queue = _wired
    rows = [
        _building_row(1),
        _building_row(2),
        _building_row(3, gps_latitude=41.0, gps_longitude=69.0),
    ]
    mock_fetch.return_value = {_expected_eid(1), _expected_eid(2)}
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(True, rows)
    )

    result = await reconciliation.reconcile_buildings()

    assert mock_queue.call_count == 1
    payload = mock_queue.call_args.args[3]  # (db, event, endpoint, data)
    assert payload["id"] == 3
    assert payload["address"] == "Test St 3"
    # PR-F: replay carries the coords stored in UK.
    assert payload["latitude"] == 41.0
    assert payload["longitude"] == 69.0

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


# ═══════════════════════ ARCH-114: reconcile_requests ═══════════════════════


def _request_row(rn: str, status: str = "Новая"):
    return SimpleNamespace(request_number=rn, status=status)


def _bld_row(rn: str, building_id):
    """Row shape of the building-resolve join (request_number, coalesced building_id)."""
    return SimpleNamespace(request_number=rn, building_id=building_id)


@pytest.fixture
def _wired_requests(monkeypatch):
    """Enable webhooks + ARCH-114 flag + URL, return monkeypatch + mocks for fetch/emit."""
    monkeypatch.setattr(reconciliation.settings, "INFRASAFE_WEBHOOK_ENABLED", True)
    monkeypatch.setattr(reconciliation.settings, "RECONCILE_REQUESTS_ENABLED", True)
    monkeypatch.setattr(
        reconciliation.settings, "INFRASAFE_REQUESTS_INVENTORY_URL",
        "http://test/api/uk-requests-metrics",
    )
    mock_fetch = AsyncMock()
    mock_emit = AsyncMock()
    monkeypatch.setattr(reconciliation, "fetch_infrasafe_uk_request_numbers", mock_fetch)
    monkeypatch.setattr(reconciliation, "emit_request_reconcile", mock_emit)
    return monkeypatch, mock_fetch, mock_emit


@pytest.mark.asyncio
async def test_requests_in_sync_when_inventory_matches(_wired_requests, caplog):
    monkeypatch, mock_fetch, mock_emit = _wired_requests
    rows = [_request_row("260524-001"), _request_row("260524-002")]
    mock_fetch.return_value = {"260524-001", "260524-002"}
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(True, rows)
    )

    with caplog.at_level("WARNING", logger="uk_management_bot.services.reconciliation"):
        result = await reconciliation.reconcile_requests()

    assert result == {"in_sync": True, "uk": 2, "infrasafe": 2}
    mock_emit.assert_not_called()
    # 2026-07-24: same fix as reconcile_buildings — WARNING survives prod filter.
    assert any("cycle complete, in sync" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_requests_drift_replays_missing_with_current_status(_wired_requests):
    """Missing on InfraSafe → emit request.reconcile with the current projected status."""
    monkeypatch, mock_fetch, mock_emit = _wired_requests
    rows = [
        _request_row("260524-001", status="Новая"),
        _request_row("260524-002", status="Принято"),
        _request_row("260524-003", status="В работе"),
    ]
    mock_fetch.return_value = {"260524-001"}
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal",
        lambda: _FakeSession(True, rows, extra_rows=[]),
    )

    result = await reconciliation.reconcile_requests()

    assert result["missing"] == 2
    assert result["enqueued"] == 2
    assert mock_emit.call_count == 2
    # Each call must pass (db, request_number, status, source="reconcile", ...).
    by_rn = {c.args[1]: c for c in mock_emit.call_args_list}
    assert by_rn["260524-002"].args[2] == "Принято"
    assert by_rn["260524-002"].kwargs["source"] == "reconcile"
    assert by_rn["260524-002"].kwargs["building_external_id"] is None
    assert by_rn["260524-003"].args[2] == "В работе"
    # ARCH-010: repair-identity (nonce) обязателен и общий на весь запуск.
    run_ids = [c.kwargs["repair_run_id"] for c in mock_emit.call_args_list]
    assert all(run_ids)
    assert len(set(run_ids)) == 1


@pytest.mark.asyncio
async def test_requests_repair_building_external_id_from_building_type(_wired_requests):
    """address_type='building': Request.building_id напрямую → external_id посчитан."""
    monkeypatch, mock_fetch, mock_emit = _wired_requests
    rows = [_request_row("260524-001", status="Новая")]
    mock_fetch.return_value = set()
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal",
        lambda: _FakeSession(True, rows, extra_rows=[_bld_row("260524-001", 5)]),
    )

    await reconciliation.reconcile_requests()

    assert mock_emit.call_count == 1
    assert mock_emit.call_args.kwargs["building_external_id"] == _expected_eid(5)


@pytest.mark.asyncio
async def test_requests_repair_building_external_id_from_apartment_type(_wired_requests):
    """address_type='apartment': building_id резолвится через Apartment.building_id
    (outerjoin-путь). Fake-сессия отдаёт результат по счётчику вызова, не по SQL —
    не отличает «резолв через join» от «прямой столбец» на уровне механики (см. план);
    тест пинует бизнес-ожидание: заявка квартирного типа получает external_id так же,
    как заявка типа building, если резолв успешен. Сам JOIN проверяется на деплое."""
    monkeypatch, mock_fetch, mock_emit = _wired_requests
    rows = [_request_row("260524-002", status="Принято")]
    mock_fetch.return_value = set()
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal",
        lambda: _FakeSession(True, rows, extra_rows=[_bld_row("260524-002", 7)]),
    )

    await reconciliation.reconcile_requests()

    assert mock_emit.call_count == 1
    assert mock_emit.call_args.kwargs["building_external_id"] == _expected_eid(7)


@pytest.mark.asyncio
async def test_requests_repair_building_external_id_absent_for_yard_or_legacy(_wired_requests):
    """address_type в (yard, legacy): building_id не резолвится ни одним путём → None."""
    monkeypatch, mock_fetch, mock_emit = _wired_requests
    rows = [_request_row("260524-003", status="Новая")]
    mock_fetch.return_value = set()
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal",
        lambda: _FakeSession(True, rows, extra_rows=[_bld_row("260524-003", None)]),
    )

    await reconciliation.reconcile_requests()

    assert mock_emit.call_count == 1
    assert mock_emit.call_args.kwargs["building_external_id"] is None


@pytest.mark.asyncio
async def test_requests_repair_nonce_differs_between_runs(_wired_requests):
    """ARCH-010: разные запуски reconcile_requests дают разные repair_run_id."""
    monkeypatch, mock_fetch, mock_emit = _wired_requests
    rows = [_request_row("260524-001"), _request_row("260524-002")]
    mock_fetch.return_value = {"260524-001"}
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal",
        lambda: _FakeSession(True, rows, extra_rows=[]),
    )

    await reconciliation.reconcile_requests()
    first_run = mock_emit.call_args.kwargs["repair_run_id"]
    await reconciliation.reconcile_requests()
    second_run = mock_emit.call_args.kwargs["repair_run_id"]
    assert first_run != second_run


@pytest.mark.asyncio
async def test_requests_skipped_when_flag_off(monkeypatch):
    """RECONCILE_REQUESTS_ENABLED=false → skip without DB or HTTP."""
    monkeypatch.setattr(reconciliation.settings, "INFRASAFE_WEBHOOK_ENABLED", True)
    monkeypatch.setattr(reconciliation.settings, "RECONCILE_REQUESTS_ENABLED", False)
    mock_fetch = AsyncMock()
    monkeypatch.setattr(reconciliation, "fetch_infrasafe_uk_request_numbers", mock_fetch)

    result = await reconciliation.reconcile_requests()

    assert result == {"skipped": "reconcile_requests_disabled"}
    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_requests_skipped_when_url_missing(monkeypatch):
    """Flag on but URL not configured → skip with explicit reason."""
    monkeypatch.setattr(reconciliation.settings, "INFRASAFE_WEBHOOK_ENABLED", True)
    monkeypatch.setattr(reconciliation.settings, "RECONCILE_REQUESTS_ENABLED", True)
    monkeypatch.setattr(reconciliation.settings, "INFRASAFE_REQUESTS_INVENTORY_URL", "")
    mock_fetch = AsyncMock()
    monkeypatch.setattr(reconciliation, "fetch_infrasafe_uk_request_numbers", mock_fetch)

    result = await reconciliation.reconcile_requests()

    assert result == {"skipped": "no_inventory_url"}
    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_requests_orphan_logged_no_replay(_wired_requests, caplog):
    """InfraSafe knows request_numbers UK doesn't — log warning, don't replay UK-side."""
    monkeypatch, mock_fetch, mock_emit = _wired_requests
    rows = [_request_row("260524-001")]
    # InfraSafe has the local one plus a stale request_number UK no longer carries.
    mock_fetch.return_value = {"260524-001", "260101-999"}
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(True, rows)
    )

    with caplog.at_level("WARNING", logger="uk_management_bot.services.reconciliation"):
        result = await reconciliation.reconcile_requests()

    mock_emit.assert_not_called()
    assert result["orphans"] == 1
    assert result["missing"] == 0
    assert result["in_sync"] is False
    assert any("orphan" in rec.message.lower() for rec in caplog.records)


@pytest.mark.asyncio
async def test_requests_skipped_when_lock_held(_wired_requests):
    """pg_try_advisory_lock returns false → another worker owns the cycle.

    REFACTOR-091 (PR-5): fetch идёт до лока и вызывается; под локом — ничего.
    """
    monkeypatch, mock_fetch, mock_emit = _wired_requests
    mock_fetch.return_value = set()
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal", lambda: _FakeSession(False, [])
    )

    result = await reconciliation.reconcile_requests()

    assert result == {"skipped": "lock_held"}
    mock_fetch.assert_called_once()
    mock_emit.assert_not_called()


@pytest.mark.asyncio
async def test_requests_replay_capped_at_replay_cap(_wired_requests):
    """A huge missing set is capped to REPLAY_CAP per cycle."""
    monkeypatch, mock_fetch, mock_emit = _wired_requests
    rows = [_request_row(f"260524-{i:03d}") for i in range(1, 61)]
    mock_fetch.return_value = set()
    monkeypatch.setattr(
        reconciliation, "AsyncSessionLocal",
        lambda: _FakeSession(True, rows, extra_rows=[]),
    )

    result = await reconciliation.reconcile_requests()

    assert result["missing"] == 60
    assert result["enqueued"] == reconciliation.REPLAY_CAP == 50
    assert mock_emit.call_count == 50
