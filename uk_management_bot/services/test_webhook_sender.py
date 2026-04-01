"""Unit tests for webhook_sender service — extends Phase 1 with queue/send coverage."""
import hashlib
import hmac
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from uk_management_bot.services.webhook_sender import (
    build_building_payload,
    build_request_payload,
    queue_webhook,
    send_webhook,
    sign_payload,
)


# ---------------------------------------------------------------------------
# sign_payload (re-covered for completeness)
# ---------------------------------------------------------------------------

class TestSignPayload:
    def test_produces_t_v1_format(self):
        header = sign_payload('{"event":"test"}', "secret")
        assert header.startswith("t=")
        assert ",v1=" in header

    def test_hmac_sha256_verifiable(self):
        body = '{"event":"test"}'
        secret = "test-secret"
        header = sign_payload(body, secret)
        parts = dict(p.split("=", 1) for p in header.split(","))
        message = f"{parts['t']}.{body}"
        expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        assert parts["v1"] == expected

    def test_timestamp_is_recent(self):
        header = sign_payload('{"x":1}', "s")
        ts = int(dict(p.split("=", 1) for p in header.split(","))["t"])
        assert abs(ts - int(time.time())) < 5

    def test_different_secrets_produce_different_signatures(self):
        body = '{"event":"test"}'
        h1 = sign_payload(body, "secret1")
        h2 = sign_payload(body, "secret2")
        assert h1.split(",v1=")[1] != h2.split(",v1=")[1]


# ---------------------------------------------------------------------------
# build_request_payload
# ---------------------------------------------------------------------------

class TestBuildRequestPayload:
    def test_created_event_fields(self):
        result = build_request_payload("request.created", {
            "request_number": "260402-001",
            "category": "plumbing",
            "status": "Новая",
            "urgency": "Обычная",
            "description": "Broken pipe",
            "address": "Block 3, apt 15",
            "apartment_id": 42,
            "created_at": "2026-04-02T10:00:00Z",
        })
        assert result["event"] == "request.created"
        assert result["request"]["request_number"] == "260402-001"
        assert result["request"]["category"] == "plumbing"
        assert result["request"]["status"] == "Новая"
        assert result["request"]["urgency"] == "Обычная"
        assert result["request"]["apartment_id"] == 42
        assert result["timestamp"].endswith("Z")
        assert "event_id" in result

    def test_status_changed_event_fields(self):
        result = build_request_payload("request.status_changed", {
            "request_number": "260402-001",
            "old_status": "Новая",
            "new_status": "В работе",
        })
        assert result["event"] == "request.status_changed"
        assert result["request"]["old_status"] == "Новая"
        assert result["request"]["new_status"] == "В работе"
        # created fields must NOT be present for status_changed
        assert "category" not in result["request"]

    def test_unknown_event_has_only_request_number(self):
        result = build_request_payload("request.unknown", {
            "request_number": "260402-001",
        })
        assert result["request"]["request_number"] == "260402-001"
        assert "category" not in result["request"]

    def test_event_id_is_unique_per_call(self):
        r1 = build_request_payload("request.created", {"request_number": "260402-001"})
        r2 = build_request_payload("request.created", {"request_number": "260402-001"})
        assert r1["event_id"] != r2["event_id"]

    def test_missing_optional_fields_default_empty_string(self):
        result = build_request_payload("request.created", {
            "request_number": "260402-001",
        })
        assert result["request"]["category"] == ""
        assert result["request"]["status"] == ""
        assert result["request"]["description"] == ""


# ---------------------------------------------------------------------------
# queue_webhook (async)
# ---------------------------------------------------------------------------

class TestQueueWebhook:
    @pytest.mark.asyncio
    async def test_returns_early_when_webhook_disabled(self):
        db = AsyncMock()

        with patch(
            "uk_management_bot.services.webhook_sender.settings"
        ) as mock_settings:
            mock_settings.INFRASAFE_WEBHOOK_ENABLED = False
            await queue_webhook(db, "request.created", "/webhooks/requests", {
                "request_number": "260402-001",
            })

        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_adds_outbox_record_when_enabled(self):
        # db.add is synchronous inside queue_webhook — use MagicMock to avoid
        # coroutine-never-awaited warnings from AsyncMock.
        db = MagicMock()

        with patch(
            "uk_management_bot.services.webhook_sender.settings"
        ) as mock_settings:
            mock_settings.INFRASAFE_WEBHOOK_ENABLED = True
            await queue_webhook(db, "request.created", "/webhooks/requests", {
                "request_number": "260402-001",
                "category": "plumbing",
                "status": "Новая",
                "urgency": "Обычная",
                "description": "Test",
                "address": "Test address",
                "apartment_id": 1,
            })

        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_building_payload_for_building_events(self):
        # db.add is a synchronous call inside queue_webhook — use MagicMock so
        # side_effect captures work without coroutine warnings.
        db = MagicMock()
        added_records = []
        db.add.side_effect = lambda r: added_records.append(r)

        with patch(
            "uk_management_bot.services.webhook_sender.settings"
        ) as mock_settings:
            mock_settings.INFRASAFE_WEBHOOK_ENABLED = True
            await queue_webhook(db, "building.created", "/webhooks/buildings", {
                "id": 1,
                "address": "Test St, 1",
                "yard_name": "Yard A",
            })

        assert len(added_records) == 1
        record = added_records[0]
        assert record.event == "building.created"
        assert record.payload["building"]["id"] == 1

    @pytest.mark.asyncio
    async def test_uses_generic_payload_for_unknown_events(self):
        db = MagicMock()
        added_records = []
        db.add.side_effect = lambda r: added_records.append(r)

        with patch(
            "uk_management_bot.services.webhook_sender.settings"
        ) as mock_settings:
            mock_settings.INFRASAFE_WEBHOOK_ENABLED = True
            await queue_webhook(db, "custom.event", "/webhooks/custom", {
                "key": "value",
            })

        assert len(added_records) == 1
        record = added_records[0]
        assert record.event == "custom.event"
        assert record.payload["data"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_record_has_pending_status(self):
        db = MagicMock()
        added_records = []
        db.add.side_effect = lambda r: added_records.append(r)

        with patch(
            "uk_management_bot.services.webhook_sender.settings"
        ) as mock_settings:
            mock_settings.INFRASAFE_WEBHOOK_ENABLED = True
            await queue_webhook(db, "request.created", "/webhooks/requests", {
                "request_number": "260402-001",
            })

        record = added_records[0]
        assert record.status == "pending"


# ---------------------------------------------------------------------------
# send_webhook (async)
# ---------------------------------------------------------------------------

class TestSendWebhook:
    def _make_response(self, status_code: int, headers: dict = None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.headers = headers or {}
        return resp

    @pytest.mark.asyncio
    async def test_200_returns_success(self):
        client = AsyncMock()
        client.post.return_value = self._make_response(200)

        with patch("uk_management_bot.services.webhook_sender.settings") as ms:
            ms.INFRASAFE_WEBHOOK_TIMEOUT = 10
            success, error, retryable, retry_after = await send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                "secret",
                client,
            )

        assert success is True
        assert error == ""
        assert retryable is False
        assert retry_after == 0

    @pytest.mark.asyncio
    async def test_400_returns_permanent_failure(self):
        client = AsyncMock()
        client.post.return_value = self._make_response(400)

        with patch("uk_management_bot.services.webhook_sender.settings") as ms:
            ms.INFRASAFE_WEBHOOK_TIMEOUT = 10
            success, error, retryable, retry_after = await send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                "secret",
                client,
            )

        assert success is False
        assert retryable is False
        assert "400" in error

    @pytest.mark.asyncio
    async def test_429_returns_retryable_with_retry_after(self):
        client = AsyncMock()
        client.post.return_value = self._make_response(429, headers={"Retry-After": "120"})

        with patch("uk_management_bot.services.webhook_sender.settings") as ms:
            ms.INFRASAFE_WEBHOOK_TIMEOUT = 10
            success, error, retryable, retry_after = await send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                "secret",
                client,
            )

        assert success is False
        assert retryable is True
        assert retry_after == 120
        assert "429" in error

    @pytest.mark.asyncio
    async def test_429_without_retry_after_header_defaults_to_60(self):
        client = AsyncMock()
        client.post.return_value = self._make_response(429, headers={})

        with patch("uk_management_bot.services.webhook_sender.settings") as ms:
            ms.INFRASAFE_WEBHOOK_TIMEOUT = 10
            success, error, retryable, retry_after = await send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                "secret",
                client,
            )

        assert success is False
        assert retryable is True
        assert retry_after == 60

    @pytest.mark.asyncio
    async def test_503_returns_non_retryable(self):
        client = AsyncMock()
        client.post.return_value = self._make_response(503)

        with patch("uk_management_bot.services.webhook_sender.settings") as ms:
            ms.INFRASAFE_WEBHOOK_TIMEOUT = 10
            success, error, retryable, retry_after = await send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                "secret",
                client,
            )

        assert success is False
        assert retryable is False
        assert "503" in error

    @pytest.mark.asyncio
    async def test_500_returns_retryable(self):
        client = AsyncMock()
        client.post.return_value = self._make_response(500)

        with patch("uk_management_bot.services.webhook_sender.settings") as ms:
            ms.INFRASAFE_WEBHOOK_TIMEOUT = 10
            success, error, retryable, retry_after = await send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                "secret",
                client,
            )

        assert success is False
        assert retryable is True
        assert "500" in error

    @pytest.mark.asyncio
    async def test_timeout_exception_retryable(self):
        client = AsyncMock()
        client.post.side_effect = httpx.TimeoutException("timed out")

        with patch("uk_management_bot.services.webhook_sender.settings") as ms:
            ms.INFRASAFE_WEBHOOK_TIMEOUT = 10
            success, error, retryable, retry_after = await send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                "secret",
                client,
            )

        assert success is False
        assert retryable is True
        assert "Timeout" in error

    @pytest.mark.asyncio
    async def test_generic_exception_retryable(self):
        client = AsyncMock()
        client.post.side_effect = Exception("network error")

        with patch("uk_management_bot.services.webhook_sender.settings") as ms:
            ms.INFRASAFE_WEBHOOK_TIMEOUT = 10
            success, error, retryable, retry_after = await send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                "secret",
                client,
            )

        assert success is False
        assert retryable is True
        assert "error" in error.lower()

    @pytest.mark.asyncio
    async def test_signature_header_is_sent(self):
        client = AsyncMock()
        client.post.return_value = self._make_response(200)

        with patch("uk_management_bot.services.webhook_sender.settings") as ms:
            ms.INFRASAFE_WEBHOOK_TIMEOUT = 10
            await send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                "secret",
                client,
            )

        call_kwargs = client.post.call_args
        headers = call_kwargs.kwargs.get("headers", {}) or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else {})
        # headers is passed as kwarg
        sent_headers = client.post.call_args.kwargs["headers"]
        assert "x-webhook-signature" in sent_headers
        sig = sent_headers["x-webhook-signature"]
        assert sig.startswith("t=") and ",v1=" in sig
