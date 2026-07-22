"""Unit tests for webhook_sender service — extends Phase 1 with queue/send coverage."""
import hashlib
import hmac
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from uk_management_bot.services.webhook_sender import (
    EventIdentity,
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
        # ARCH-010: versioned-событие требует identity (fail-loud в funnel'е).
        result = build_request_payload("request.status_changed", {
            "request_number": "260402-001",
            "old_status": "Новая",
            "new_status": "В работе",
        }, identity=EventIdentity(version=1))
        assert result["event"] == "request.status_changed"
        assert result["request"]["old_status"] == "Новая"
        assert result["request"]["new_status"] == "В работе"
        # created fields must NOT be present for status_changed
        assert "category" not in result["request"]

    def test_unknown_contract_event_raises(self):
        """ARCH-010 fail-loud: неизвестное request.*-событие — ошибка программиста,
        а не тихий payload (раньше строился с uuid4)."""
        with pytest.raises(ValueError, match="request.unknown"):
            build_request_payload("request.unknown", {
                "request_number": "260402-001",
            })

    def test_event_id_is_deterministic_per_identity(self):
        """ARCH-010: одинаковый вход → одинаковый UUIDv5 (был uuid4 → разные)."""
        r1 = build_request_payload("request.created", {"request_number": "260402-001"})
        r2 = build_request_payload("request.created", {"request_number": "260402-001"})
        assert r1["event_id"] == r2["event_id"]

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

def _mock_db():
    """ARCH-010: queue_webhook пишет через await db.execute(INSERT ... ON
    CONFLICT), а не db.add — мокаем execute (async) и get_bind (sync)."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.get_bind.return_value.dialect.name = "sqlite"
    return db


def _executed_values(db) -> dict:
    """Значения INSERT-стейтмента, переданного в db.execute."""
    from sqlalchemy.dialects import sqlite as sqlite_dialect
    stmt = db.execute.await_args.args[0]
    return dict(stmt.compile(dialect=sqlite_dialect.dialect()).params)


class TestQueueWebhook:
    @pytest.mark.asyncio
    async def test_returns_early_when_webhook_disabled(self):
        db = _mock_db()

        with patch(
            "uk_management_bot.services.webhook_sender.settings"
        ) as mock_settings:
            mock_settings.INFRASAFE_WEBHOOK_ENABLED = False
            await queue_webhook(db, "request.created", "/webhooks/requests", {
                "request_number": "260402-001",
            })

        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inserts_outbox_record_when_enabled(self):
        db = _mock_db()

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

        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uses_building_payload_for_building_events(self):
        db = _mock_db()

        with patch(
            "uk_management_bot.services.webhook_sender.settings"
        ) as mock_settings:
            mock_settings.INFRASAFE_WEBHOOK_ENABLED = True
            await queue_webhook(db, "building.created", "/webhooks/buildings", {
                "id": 1,
                "address": "Test St, 1",
                "yard_name": "Yard A",
            })

        values = _executed_values(db)
        assert values["event"] == "building.created"
        assert values["payload"]["building"]["id"] == 1

    @pytest.mark.asyncio
    async def test_uses_generic_payload_for_unknown_events(self):
        db = _mock_db()

        with patch(
            "uk_management_bot.services.webhook_sender.settings"
        ) as mock_settings:
            mock_settings.INFRASAFE_WEBHOOK_ENABLED = True
            await queue_webhook(db, "custom.event", "/webhooks/custom", {
                "key": "value",
            })

        values = _executed_values(db)
        assert values["event"] == "custom.event"
        assert values["payload"]["data"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_record_has_pending_status(self):
        db = _mock_db()

        with patch(
            "uk_management_bot.services.webhook_sender.settings"
        ) as mock_settings:
            mock_settings.INFRASAFE_WEBHOOK_ENABLED = True
            await queue_webhook(db, "request.created", "/webhooks/requests", {
                "request_number": "260402-001",
            })

        assert _executed_values(db)["status"] == "pending"


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
    async def test_503_returns_retryable(self):
        # 503 Service Unavailable is transient → retryable (same as 5xx below).
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
        assert retryable is True
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

        # headers is passed as kwarg
        sent_headers = client.post.call_args.kwargs["headers"]
        assert "x-webhook-signature" in sent_headers
        sig = sent_headers["x-webhook-signature"]
        assert sig.startswith("t=") and ",v1=" in sig

    @pytest.mark.asyncio
    async def test_401_returns_permanent_failure(self):
        client = AsyncMock()
        client.post.return_value = self._make_response(401)

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
        assert "401" in error

    @pytest.mark.asyncio
    async def test_403_returns_permanent_failure(self):
        client = AsyncMock()
        client.post.return_value = self._make_response(403)

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

    @pytest.mark.asyncio
    async def test_unexpected_4xx_returns_retryable(self):
        client = AsyncMock()
        client.post.return_value = self._make_response(418)

        with patch("uk_management_bot.services.webhook_sender.settings") as ms:
            ms.INFRASAFE_WEBHOOK_TIMEOUT = 10
            success, error, retryable, retry_after = await send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                "secret",
                client,
            )

        assert success is False
        assert "418" in error


# ---------------------------------------------------------------------------
# build_building_payload
# ---------------------------------------------------------------------------

class TestBuildBuildingPayload:
    def test_building_created_fields(self):
        result = build_building_payload("building.created", {
            "id": 5,
            "address": "Ленина 1",
            "yard_name": "Двор А",
        })
        assert result["event"] == "building.created"
        assert result["building"]["id"] == 5
        assert result["building"]["address"] == "Ленина 1"
        assert result["building"]["town"] == "Двор А"
        assert "event_id" in result
        assert result["timestamp"].endswith("Z")

    def test_missing_yard_name_defaults_empty(self):
        result = build_building_payload("building.created", {
            "id": 1,
            "address": "Test",
        })
        assert result["building"]["town"] == ""

    def test_event_id_is_deterministic(self):
        """ARCH-010: одинаковый вход → одинаковый UUIDv5 (был uuid4 → разные)."""
        r1 = build_building_payload("building.created", {"id": 1, "address": "A"})
        r2 = build_building_payload("building.created", {"id": 1, "address": "A"})
        assert r1["event_id"] == r2["event_id"]


# ---------------------------------------------------------------------------
# ARCH-010: детерминированный UUIDv5 event_id + EventIdentity + fail-loud
# ---------------------------------------------------------------------------

class TestDeterministicEventId:
    def test_versioned_same_version_same_id(self):
        p1 = build_building_payload("building.updated", {"id": 7, "address": "A"},
                                    identity=EventIdentity(version=3))
        p2 = build_building_payload("building.updated", {"id": 7, "address": "A"},
                                    identity=EventIdentity(version=3))
        assert p1["event_id"] == p2["event_id"]

    def test_versioned_different_version_different_id(self):
        p1 = build_request_payload(
            "request.status_changed",
            {"request_number": "260402-001", "old_status": "a", "new_status": "b"},
            identity=EventIdentity(version=1))
        p2 = build_request_payload(
            "request.status_changed",
            {"request_number": "260402-001", "old_status": "a", "new_status": "b"},
            identity=EventIdentity(version=2))
        assert p1["event_id"] != p2["event_id"]

    def test_event_id_is_uuid_36_chars(self):
        p = build_building_payload("building.created", {"id": 1, "address": "A"})
        import uuid as _uuid
        parsed = _uuid.UUID(p["event_id"])
        assert parsed.version == 5
        assert len(p["event_id"]) == 36

    def test_cross_instance_different_id(self, monkeypatch):
        # Патчим settings-инстанс, на который ссылается сам webhook_sender —
        # test_settings.py перезагружает модуль settings, и «свежий» импорт в
        # тесте может оказаться другим объектом.
        from uk_management_bot.services import webhook_sender as ws
        monkeypatch.setattr(ws.settings, "OUTBOX_SOURCE_INSTANCE", "profk")
        p1 = build_building_payload("building.created", {"id": 1, "address": "A"})
        monkeypatch.setattr(ws.settings, "OUTBOX_SOURCE_INSTANCE", "infrasafe")
        p2 = build_building_payload("building.created", {"id": 1, "address": "A"})
        assert p1["event_id"] != p2["event_id"]

    # ── fail-loud ──
    def test_versioned_without_identity_raises(self):
        with pytest.raises(ValueError, match="building.updated"):
            build_building_payload("building.updated", {"id": 1, "address": "A"})

    def test_version_and_repair_mutually_exclusive(self):
        with pytest.raises(ValueError, match="building.deleted"):
            build_building_payload(
                "building.deleted", {"id": 1, "address": "A"},
                identity=EventIdentity(version=1, repair_run_id="abc"))

    def test_one_shot_with_version_raises(self):
        with pytest.raises(ValueError, match="building.created"):
            build_building_payload("building.created", {"id": 1, "address": "A"},
                                   identity=EventIdentity(version=1))

    # ── repair-nonce ──
    def test_repair_id_differs_and_sets_top_level_flag(self):
        versioned = build_building_payload("building.updated", {"id": 1, "address": "A"},
                                           identity=EventIdentity(version=1))
        repair = build_building_payload("building.updated", {"id": 1, "address": "A"},
                                        identity=EventIdentity(repair_run_id="run1"))
        assert repair["event_id"] != versioned["event_id"]
        assert repair["repair"] is True          # top-level, не внутри building
        assert "repair" not in repair["building"]
        assert "repair" not in versioned

    def test_repair_different_runs_different_ids(self):
        p1 = build_request_payload(
            "request.status_changed",
            {"request_number": "260402-001", "old_status": "x", "new_status": "x"},
            identity=EventIdentity(repair_run_id="run1"))
        p2 = build_request_payload(
            "request.status_changed",
            {"request_number": "260402-001", "old_status": "x", "new_status": "x"},
            identity=EventIdentity(repair_run_id="run2"))
        assert p1["event_id"] != p2["event_id"]

    def test_repair_one_shot_event_allowed(self):
        """Reconcile переигрывает building.created c nonce — репейр валиден и для one-shot."""
        normal = build_building_payload("building.created", {"id": 1, "address": "A"})
        repair = build_building_payload("building.created", {"id": 1, "address": "A"},
                                        identity=EventIdentity(repair_run_id="run1"))
        assert repair["event_id"] != normal["event_id"]
        assert repair["repair"] is True


# ---------------------------------------------------------------------------
# process_outbox (async) — mocked AsyncSessionLocal + httpx
# ---------------------------------------------------------------------------

