"""Unit tests for MediaServiceClient — tags, timeline, popular tags, statistics, similar media, health check, close, BytesIO name handling.

AUD5-ARCH-3 волна 14: часть исходного test_media_client.py (1019), тела байт-в-байт.
"""
import io
import pytest
from unittest.mock import MagicMock, AsyncMock

from uk_management_bot.integrations.media_client import (
    MediaServiceClient,
)

# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_returns_health_status(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "healthy"}
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.health_check()

        assert result["status"] == "healthy"
        url = client.client.get.call_args[0][0]
        assert "/health" in url

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        client = MediaServiceClient("http://localhost")
        client.client.get = AsyncMock(side_effect=Exception("service down"))

        with pytest.raises(Exception, match="service down"):
            await client.health_check()


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------

class TestClose:
    @pytest.mark.asyncio
    async def test_close_calls_aclose_on_httpx_client(self):
        client = MediaServiceClient("http://localhost")
        client.client = AsyncMock()
        client.client.aclose = AsyncMock()

        await client.close()

        client.client.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# upload_request_media — BytesIO with name attr
# ---------------------------------------------------------------------------

class TestUploadRequestMediaBytesIOWithName:
    @pytest.mark.asyncio
    async def test_bytesio_with_name_attr_uses_basename(self):
        """When the file-like object has a .name attribute, use its basename."""
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 5}}
        client.client.post = AsyncMock(return_value=mock_response)

        buf = io.BytesIO(b"data")
        buf.name = "/some/path/photo.jpg"

        result = await client.upload_request_media("260401-001", buf, uploaded_by=1)
        assert result["media_file"]["id"] == 5

    @pytest.mark.asyncio
    async def test_bytesio_without_name_attr_uses_upload_default(self):
        """BytesIO without .name falls back to 'upload'."""
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 6}}
        client.client.post = AsyncMock(return_value=mock_response)

        buf = io.BytesIO(b"data")
        assert not hasattr(buf, "name")

        result = await client.upload_request_media("260401-001", buf, uploaded_by=1)
        assert result["media_file"]["id"] == 6
