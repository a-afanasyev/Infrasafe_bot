"""ARCH-114 — emit_request_reconcile: closes the gap between funnel tests
(call queue_webhook_sync directly) and reconciliation tests (mock
emit_request_reconcile entirely) — the emitter itself needs its own test.
"""
from unittest.mock import AsyncMock

import pytest

from uk_management_bot.services import webhook_payloads
from uk_management_bot.services.webhook_sender import EventIdentity


@pytest.mark.asyncio
async def test_emit_request_reconcile_calls_queue_webhook(monkeypatch):
    mock_queue = AsyncMock()
    monkeypatch.setattr(webhook_payloads, "queue_webhook", mock_queue)
    db = object()

    await webhook_payloads.emit_request_reconcile(
        db, "260523-042", "В работе", source="reconcile",
        repair_run_id="run-1", building_external_id="3f2a9c1e-...-b6c4",
    )

    mock_queue.assert_awaited_once_with(
        db, "request.reconcile", webhook_payloads.REQUEST_WEBHOOK_ENDPOINT,
        {
            "request_number": "260523-042",
            "status": "В работе",
            "building_external_id": "3f2a9c1e-...-b6c4",
        },
        EventIdentity(repair_run_id="run-1"),
    )


@pytest.mark.asyncio
async def test_emit_request_reconcile_defaults_building_external_id_to_none(monkeypatch):
    mock_queue = AsyncMock()
    monkeypatch.setattr(webhook_payloads, "queue_webhook", mock_queue)
    db = object()

    await webhook_payloads.emit_request_reconcile(
        db, "260523-042", "Новая", source="reconcile", repair_run_id="run-1",
    )

    call_data = mock_queue.await_args.args[3]
    assert call_data["building_external_id"] is None
