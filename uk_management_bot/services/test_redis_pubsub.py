"""Unit tests for redis_pubsub service."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from uk_management_bot.services.redis_pubsub import (
    CHANNEL,
    SHIFTS_CHANNEL,
    BUILDINGS_CHANNEL,
    publish_request_event,
    publish_building_event,
    publish_shift_event,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_redis_mock():
    """Return an AsyncMock redis client with a publish coroutine."""
    client = AsyncMock()
    client.publish = AsyncMock(return_value=1)
    client.ping = AsyncMock(return_value=True)
    return client


# ---------------------------------------------------------------------------
# publish_request_event
# ---------------------------------------------------------------------------

class TestPublishRequestEvent:
    @pytest.mark.asyncio
    async def test_publishes_to_requests_channel(self):
        redis_mock = _make_redis_mock()

        with patch(
            "uk_management_bot.services.redis_pubsub.get_pubsub_redis",
            return_value=redis_mock,
        ):
            await publish_request_event("request.created", {"request_number": "260402-001"})

        redis_mock.publish.assert_called_once()
        channel_arg, message_arg = redis_mock.publish.call_args.args
        assert channel_arg == CHANNEL

    @pytest.mark.asyncio
    async def test_message_contains_event_type(self):
        redis_mock = _make_redis_mock()

        with patch(
            "uk_management_bot.services.redis_pubsub.get_pubsub_redis",
            return_value=redis_mock,
        ):
            await publish_request_event("request.status_changed", {"id": 42})

        _, message_arg = redis_mock.publish.call_args.args
        payload = json.loads(message_arg)
        assert payload["type"] == "request.status_changed"
        assert payload["data"] == {"id": 42}

    @pytest.mark.asyncio
    async def test_message_is_valid_json(self):
        redis_mock = _make_redis_mock()

        with patch(
            "uk_management_bot.services.redis_pubsub.get_pubsub_redis",
            return_value=redis_mock,
        ):
            await publish_request_event("request.created", {"key": "value"})

        _, message_arg = redis_mock.publish.call_args.args
        parsed = json.loads(message_arg)
        assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_does_not_raise_on_redis_failure(self):
        redis_mock = _make_redis_mock()
        redis_mock.publish.side_effect = Exception("Redis connection refused")

        with patch(
            "uk_management_bot.services.redis_pubsub.get_pubsub_redis",
            return_value=redis_mock,
        ):
            # Should not raise — failures are swallowed with a warning
            await publish_request_event("request.created", {})

    @pytest.mark.asyncio
    async def test_does_not_raise_on_get_pubsub_failure(self):
        async def _fail():
            raise Exception("Cannot connect to Redis")

        with patch(
            "uk_management_bot.services.redis_pubsub.get_pubsub_redis",
            side_effect=Exception("Cannot connect"),
        ):
            await publish_request_event("request.created", {})


# ---------------------------------------------------------------------------
# publish_building_event
# ---------------------------------------------------------------------------

class TestPublishBuildingEvent:
    @pytest.mark.asyncio
    async def test_publishes_to_buildings_channel(self):
        redis_mock = _make_redis_mock()

        with patch(
            "uk_management_bot.services.redis_pubsub.get_pubsub_redis",
            return_value=redis_mock,
        ):
            await publish_building_event("building.created", {"id": 1, "address": "St, 1"})

        redis_mock.publish.assert_called_once()
        channel_arg, _ = redis_mock.publish.call_args.args
        assert channel_arg == BUILDINGS_CHANNEL

    @pytest.mark.asyncio
    async def test_message_contains_correct_type_and_data(self):
        redis_mock = _make_redis_mock()

        with patch(
            "uk_management_bot.services.redis_pubsub.get_pubsub_redis",
            return_value=redis_mock,
        ):
            await publish_building_event("building.deleted", {"id": 5})

        _, message_arg = redis_mock.publish.call_args.args
        payload = json.loads(message_arg)
        assert payload["type"] == "building.deleted"
        assert payload["data"]["id"] == 5

    @pytest.mark.asyncio
    async def test_does_not_raise_on_failure(self):
        redis_mock = _make_redis_mock()
        redis_mock.publish.side_effect = ConnectionError("lost")

        with patch(
            "uk_management_bot.services.redis_pubsub.get_pubsub_redis",
            return_value=redis_mock,
        ):
            await publish_building_event("building.updated", {"id": 1})


# ---------------------------------------------------------------------------
# publish_shift_event
# ---------------------------------------------------------------------------

class TestPublishShiftEvent:
    @pytest.mark.asyncio
    async def test_publishes_to_shifts_channel(self):
        redis_mock = _make_redis_mock()

        with patch(
            "uk_management_bot.services.redis_pubsub.get_pubsub_redis",
            return_value=redis_mock,
        ):
            await publish_shift_event("shift.started", {"user_id": 7, "shift_id": 3})

        redis_mock.publish.assert_called_once()
        channel_arg, _ = redis_mock.publish.call_args.args
        assert channel_arg == SHIFTS_CHANNEL

    @pytest.mark.asyncio
    async def test_message_contains_event_type_and_data(self):
        redis_mock = _make_redis_mock()

        with patch(
            "uk_management_bot.services.redis_pubsub.get_pubsub_redis",
            return_value=redis_mock,
        ):
            await publish_shift_event("shift.ended", {"user_id": 7, "duration": 3600})

        _, message_arg = redis_mock.publish.call_args.args
        payload = json.loads(message_arg)
        assert payload["type"] == "shift.ended"
        assert payload["data"]["user_id"] == 7
        assert payload["data"]["duration"] == 3600

    @pytest.mark.asyncio
    async def test_does_not_raise_on_failure(self):
        redis_mock = _make_redis_mock()
        redis_mock.publish.side_effect = Exception("timeout")

        with patch(
            "uk_management_bot.services.redis_pubsub.get_pubsub_redis",
            return_value=redis_mock,
        ):
            await publish_shift_event("shift.started", {})

    @pytest.mark.asyncio
    async def test_published_message_is_json_serialisable(self):
        redis_mock = _make_redis_mock()
        captured = {}

        async def capture_publish(channel, message):
            captured["channel"] = channel
            captured["message"] = message

        redis_mock.publish.side_effect = capture_publish

        with patch(
            "uk_management_bot.services.redis_pubsub.get_pubsub_redis",
            return_value=redis_mock,
        ):
            await publish_shift_event("shift.started", {"shift_id": 99})

        assert captured
        parsed = json.loads(captured["message"])
        assert parsed["type"] == "shift.started"
        assert parsed["data"]["shift_id"] == 99
