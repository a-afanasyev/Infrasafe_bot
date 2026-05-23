"""ARCH-113 — contract (snapshot) tests for request.* webhook payload builders.

Locks the on-the-wire shape so a future field tweak to one emit site can't
silently diverge from the others — adding a key to a Request model that
isn't routed through the builder will break here, not at runtime in prod.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

from uk_management_bot.services.webhook_payloads import (
    build_request_created_payload,
    build_request_status_changed_payload,
)


def _req(**overrides):
    """Minimal Request-like object with the fields the builder reads."""
    defaults = dict(
        request_number="260523-042",
        category="Электрика",
        status="Новая",
        urgency="Обычная",
        description="lift broken",
        address="ул. Тестовая, 1",
        apartment_id=None,
        created_at=datetime(2026, 5, 23, 11, 7, 42, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_request_created_payload_full_shape():
    payload = build_request_created_payload(_req())
    assert payload == {
        "request_number": "260523-042",
        "category": "Электрика",
        "status": "Новая",
        "urgency": "Обычная",
        "description": "lift broken",
        "address": "ул. Тестовая, 1",
        "apartment_id": None,
        "created_at": "2026-05-23T11:07:42+00:00",
    }


def test_request_created_payload_created_at_none_renders_empty_string():
    """Bot-path may emit before refresh — created_at can be None. Stays empty string,
    matching the API path's pre-refresh fallback."""
    payload = build_request_created_payload(_req(created_at=None))
    assert payload["created_at"] == ""


def test_request_created_payload_keys_are_exactly_eight():
    """Snapshot the key set. Adding a field to Request mustn't silently leak into
    the wire payload without updating this test (and the InfraSafe contract)."""
    payload = build_request_created_payload(_req())
    assert set(payload.keys()) == {
        "request_number", "category", "status", "urgency",
        "description", "address", "apartment_id", "created_at",
    }


def test_request_status_changed_payload_full_shape():
    payload = build_request_status_changed_payload("260523-042", "Новая", "В работе")
    assert payload == {
        "request_number": "260523-042",
        "old_status": "Новая",
        "new_status": "В работе",
    }


def test_request_status_changed_payload_keys_are_exactly_three():
    payload = build_request_status_changed_payload("260523-042", "Новая", "В работе")
    assert set(payload.keys()) == {"request_number", "old_status", "new_status"}
