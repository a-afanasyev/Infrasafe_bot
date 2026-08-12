"""Unit tests for MediaServiceClient — tags, timeline, popular tags, statistics, similar media, health check, close, BytesIO name handling.

AUD5-ARCH-3 волна 14: часть исходного test_media_client.py (1019), тела байт-в-байт.
"""
import io
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

from uk_management_bot.integrations.media_client import (
    MediaServiceClient,
    upload_request_photo,
    upload_completion_photo,
)

# update_media_tags
# ---------------------------------------------------------------------------

class TestUpdateMediaTags:
    @pytest.mark.asyncio
    async def test_sends_put_request_with_tags(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"id": 5, "tags": ["water", "urgent"]}
        client.client.put = AsyncMock(return_value=mock_response)

        result = await client.update_media_tags(5, ["water", "urgent"])

        assert result["tags"] == ["water", "urgent"]
        client.client.put.assert_called_once()
        url = client.client.put.call_args[0][0]
        assert "/media/5/tags" in url

    @pytest.mark.asyncio
    async def test_replace_flag_included_in_body(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"id": 5}
        client.client.put = AsyncMock(return_value=mock_response)

        await client.update_media_tags(5, ["new"], replace=True)

        body = client.client.put.call_args[1]["json"]
        assert body["replace"] is True

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        client = MediaServiceClient("http://localhost")
        client.client.put = AsyncMock(side_effect=Exception("update failed"))

        with pytest.raises(Exception, match="update failed"):
            await client.update_media_tags(5, ["x"])


# ---------------------------------------------------------------------------
# get_request_timeline
# ---------------------------------------------------------------------------

class TestGetRequestTimeline:
    @pytest.mark.asyncio
    async def test_returns_timeline_dict(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"events": [], "request_number": "260401-001"}
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.get_request_timeline("260401-001")

        assert result["request_number"] == "260401-001"
        url = client.client.get.call_args[0][0]
        assert "260401-001" in url
        assert "timeline" in url

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        client = MediaServiceClient("http://localhost")
        client.client.get = AsyncMock(side_effect=Exception("timeline error"))

        with pytest.raises(Exception, match="timeline error"):
            await client.get_request_timeline("260401-001")


# ---------------------------------------------------------------------------
# get_popular_tags
# ---------------------------------------------------------------------------

class TestGetPopularTags:
    @pytest.mark.asyncio
    async def test_returns_list_of_tags(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{"tag": "water", "count": 10}]
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.get_popular_tags()

        assert isinstance(result, list)
        assert result[0]["tag"] == "water"

    @pytest.mark.asyncio
    async def test_custom_limit_sent_in_params(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []
        client.client.get = AsyncMock(return_value=mock_response)

        await client.get_popular_tags(limit=5)

        params = client.client.get.call_args[1]["params"]
        assert params["limit"] == 5

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        client = MediaServiceClient("http://localhost")
        client.client.get = AsyncMock(side_effect=Exception("tags error"))

        with pytest.raises(Exception, match="tags error"):
            await client.get_popular_tags()


# ---------------------------------------------------------------------------
# get_media_statistics
# ---------------------------------------------------------------------------

class TestGetMediaStatistics:
    @pytest.mark.asyncio
    async def test_returns_statistics_dict(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"total_files": 100, "total_size_mb": 512}
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.get_media_statistics()

        assert result["total_files"] == 100
        assert "/media/statistics" in client.client.get.call_args[0][0]

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        client = MediaServiceClient("http://localhost")
        client.client.get = AsyncMock(side_effect=Exception("stats error"))

        with pytest.raises(Exception, match="stats error"):
            await client.get_media_statistics()


# ---------------------------------------------------------------------------
# find_similar_media
# ---------------------------------------------------------------------------

class TestFindSimilarMedia:
    @pytest.mark.asyncio
    async def test_returns_list_of_similar_files(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{"id": 10, "similarity": 0.85}]
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.find_similar_media(42)

        assert isinstance(result, list)
        assert result[0]["id"] == 10

    @pytest.mark.asyncio
    async def test_similarity_threshold_and_limit_in_params(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []
        client.client.get = AsyncMock(return_value=mock_response)

        await client.find_similar_media(42, similarity_threshold=0.9, limit=5)

        params = client.client.get.call_args[1]["params"]
        assert params["similarity_threshold"] == 0.9
        assert params["limit"] == 5

    @pytest.mark.asyncio
    async def test_url_contains_media_id(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []
        client.client.get = AsyncMock(return_value=mock_response)

        await client.find_similar_media(99)

        url = client.client.get.call_args[0][0]
        assert "99" in url
        assert "similar" in url

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        client = MediaServiceClient("http://localhost")
        client.client.get = AsyncMock(side_effect=Exception("similar error"))

        with pytest.raises(Exception, match="similar error"):
            await client.find_similar_media(1)


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
