"""Tests for webhook sender service — Phase 1: building webhooks only."""
import hashlib
import hmac
import json
import time
import pytest

from uk_management_bot.services.webhook_sender import (
    sign_payload,
    build_building_payload,
)


class TestSignPayload:
    def test_sign_produces_valid_format(self):
        """Signature header must be t=<timestamp>,v1=<hex>."""
        body = '{"event":"test"}'
        secret = "test-secret-key-32chars-minimum!!"
        result = sign_payload(body, secret)
        assert result.startswith("t=")
        assert ",v1=" in result

    def test_sign_is_hmac_sha256(self):
        """Signature must be verifiable with HMAC-SHA256."""
        body = '{"event":"test"}'
        secret = "test-secret"
        header = sign_payload(body, secret)
        parts = dict(p.split("=", 1) for p in header.split(","))
        timestamp = parts["t"]
        sig = parts["v1"]
        message = f"{timestamp}.{body}"
        expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        assert sig == expected

    def test_sign_timestamp_is_recent(self):
        """Timestamp must be within 5 seconds of now."""
        body = '{"event":"test"}'
        header = sign_payload(body, "secret")
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
        assert abs(ts - int(time.time())) < 5


class TestBuildBuildingPayload:
    def test_building_created_payload(self):
        """building.created maps address->name, yard_name->town."""
        result = build_building_payload("building.created", {
            "id": 1,
            "address": "Yangi Olmazor, 12V",
            "yard_name": "Фаза 1(LOT 4)",
        })
        assert result["event"] == "building.created"
        assert result["building"]["id"] == 1
        assert result["building"]["name"] == "Yangi Olmazor, 12V"
        assert result["building"]["address"] == "Yangi Olmazor, 12V"
        assert result["building"]["town"] == "Фаза 1(LOT 4)"
        assert "event_id" in result
        assert "timestamp" in result
        assert result["timestamp"].endswith("Z")

    def test_building_deleted_payload(self):
        """building.deleted includes the same structure."""
        result = build_building_payload("building.deleted", {
            "id": 5,
            "address": "Test",
            "yard_name": "Yard",
        })
        assert result["event"] == "building.deleted"
        assert result["building"]["id"] == 5


class TestBuildRequestPayload:
    def test_request_created_payload(self):
        from uk_management_bot.services.webhook_sender import build_request_payload
        result = build_request_payload("request.created", {
            "request_number": "260329-001",
            "category": "plumbing",
            "status": "Новая",
            "urgency": "Обычная",
            "description": "Test request",
            "address": "Test address",
            "apartment_id": 54,
            "created_at": "2026-03-29T10:00:00Z",
        })
        assert result["event"] == "request.created"
        assert result["request"]["request_number"] == "260329-001"
        assert result["request"]["category"] == "plumbing"
        assert result["request"]["status"] == "Новая"
        assert result["request"]["apartment_id"] == 54
        assert "event_id" in result
        assert result["timestamp"].endswith("Z")

    def test_request_status_changed_payload(self):
        from uk_management_bot.services.webhook_sender import build_request_payload
        result = build_request_payload("request.status_changed", {
            "request_number": "260329-001",
            "old_status": "Новая",
            "new_status": "В работе",
        })
        assert result["event"] == "request.status_changed"
        assert result["request"]["request_number"] == "260329-001"
        assert result["request"]["old_status"] == "Новая"
        assert result["request"]["new_status"] == "В работе"
