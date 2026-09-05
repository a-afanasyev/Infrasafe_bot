"""`bulk_confirm_async`: порядок, изоляция сбоев, лимит (runner подменён на уровне вызова)."""

from __future__ import annotations

import asyncio

import pytest

from uk_management_bot.services.elevator_service import (
    MAX_BULK_CONFIRM,
    BulkItemResult,
    ElevatorValidationError,
    bulk_confirm_async,
)
from uk_management_bot.services.elevator_service import grouping
from uk_management_bot.utils.request_workflow import (
    Action,
    EventIntent,
    InvalidTransition,
    PrincipalRef,
)

pytestmark = pytest.mark.unit

PRINCIPAL = PrincipalRef(kind="user", user_id=3, source="api")


class _Outcome:
    def __init__(self, intents=()):
        self.post_commit_intents = tuple(intents)


def _fake_runner(calls, failures=(), boom=None):
    async def run_command_async(session_factory, request_number, principal, command, now=None):
        calls.append((request_number, principal, command.action, command.command_id, now))
        if request_number in failures:
            raise InvalidTransition(f"нельзя: {request_number}")
        if boom is not None and request_number == boom:
            raise RuntimeError("db down")
        return _Outcome([EventIntent(kind="notify", data={"n": request_number})])

    return run_command_async


def test_sorted_order_and_partial_failure_isolated(monkeypatch):
    calls = []
    monkeypatch.setattr(grouping, "run_command_async", _fake_runner(calls, failures={"260905-002"}))

    results = asyncio.run(bulk_confirm_async(
        "factory", ["260905-003", "260905-001", "260905-002"], principal=PRINCIPAL))

    assert [c[0] for c in calls] == ["260905-001", "260905-002", "260905-003"]
    assert all(c[1] is PRINCIPAL and c[2] is Action.MANAGER_CONFIRM for c in calls)
    assert [c[3] for c in calls] == ["bulk-confirm:260905-001", "bulk-confirm:260905-002", "bulk-confirm:260905-003"]
    assert results == (
        BulkItemResult("260905-001", True, post_commit_intents=(EventIntent(kind="notify", data={"n": "260905-001"}),)),
        BulkItemResult("260905-002", False, error_kind="InvalidTransition", error="нельзя: 260905-002"),
        BulkItemResult("260905-003", True, post_commit_intents=(EventIntent(kind="notify", data={"n": "260905-003"}),)),
    )


def test_non_workflow_error_propagates(monkeypatch):
    calls = []
    monkeypatch.setattr(grouping, "run_command_async", _fake_runner(calls, boom="260905-002"))
    with pytest.raises(RuntimeError):
        asyncio.run(bulk_confirm_async("factory", ["260905-001", "260905-002", "260905-003"], principal=PRINCIPAL))
    assert [c[0] for c in calls] == ["260905-001", "260905-002"]


def test_now_and_prefix_passed_through(monkeypatch):
    from datetime import datetime, timezone

    calls = []
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(grouping, "run_command_async", _fake_runner(calls))
    asyncio.run(bulk_confirm_async("factory", ["260905-001"], principal=PRINCIPAL, now=now, command_prefix="api"))
    assert calls == [("260905-001", PRINCIPAL, Action.MANAGER_CONFIRM, "api:260905-001", now)]


@pytest.mark.parametrize("numbers", [
    [], [""], ["  "], ["a", "a"], "260905-001", [f"26090{i:04d}" for i in range(MAX_BULK_CONFIRM + 1)],
])
def test_invalid_input_rejected_before_runner(monkeypatch, numbers):
    calls = []
    monkeypatch.setattr(grouping, "run_command_async", _fake_runner(calls))
    with pytest.raises(ElevatorValidationError):
        asyncio.run(bulk_confirm_async("factory", numbers, principal=PRINCIPAL))
    assert calls == []


def test_max_is_accepted(monkeypatch):
    calls = []
    monkeypatch.setattr(grouping, "run_command_async", _fake_runner(calls))
    numbers = [f"260905-{i:03d}" for i in range(MAX_BULK_CONFIRM)]
    results = asyncio.run(bulk_confirm_async("factory", numbers, principal=PRINCIPAL))
    assert len(results) == MAX_BULK_CONFIRM and all(r.ok for r in results)
