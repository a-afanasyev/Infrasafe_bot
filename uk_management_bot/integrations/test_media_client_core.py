"""Unit tests for MediaServiceClient — init, upload validation/formatting, search params, URL building.

AUD5-ARCH-3 волна 14: test_media_client.py (1019) разнесён на три файла
по доменам; тела классов перенесены байт-в-байт, инвариант — суммарная
коллекция 73 теста не изменилась.
"""
import io
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

from uk_management_bot.integrations.media_client import (
    MediaServiceClient,
)

# ---------------------------------------------------------------------------
# __init__ / URL building
# ---------------------------------------------------------------------------

class TestInit:
    def test_strips_trailing_slash_from_base_url(self):
        client = MediaServiceClient("http://media-service:8000/")
        assert client.base_url == "http://media-service:8000"

    def test_base_url_without_slash_kept(self):
        client = MediaServiceClient("http://media-service:8000")
        assert client.base_url == "http://media-service:8000"

    def test_timeout_stored(self):
        client = MediaServiceClient("http://localhost", timeout=60)
        assert client.timeout == 60

    def test_default_timeout_is_30(self):
        client = MediaServiceClient("http://localhost")
        assert client.timeout == 30

    def test_api_key_added_to_headers(self):
        client = MediaServiceClient("http://localhost", api_key="secret123")
        # httpx client headers should contain the api key
        assert "X-API-Key" in client.client.headers
        assert client.client.headers["X-API-Key"] == "secret123"

    def test_no_api_key_by_default(self):
        client = MediaServiceClient("http://localhost")
        assert "X-API-Key" not in client.client.headers


# ---------------------------------------------------------------------------
# upload_request_media — input validation
# ---------------------------------------------------------------------------

class TestUploadRequestMediaValidation:
    @pytest.mark.asyncio
    async def test_raises_file_not_found_for_missing_path(self, tmp_path):
        client = MediaServiceClient("http://localhost")
        with pytest.raises(FileNotFoundError):
            await client.upload_request_media("260401-001", tmp_path / "nonexistent.jpg")

    @pytest.mark.asyncio
    async def test_raises_value_error_for_non_positive_uploaded_by(self):
        client = MediaServiceClient("http://localhost")
        # Inject a mock httpx client that never actually calls network
        client.client = AsyncMock()
        client.client.post = AsyncMock(side_effect=ValueError(
            "uploaded_by must be a positive integer"
        ))

        # Negative uploaded_by should raise ValueError directly in our code
        with pytest.raises((ValueError, Exception)):
            await client.upload_request_media(
                "260401-001",
                io.BytesIO(b"data"),
                filename="photo.jpg",
                uploaded_by=-1,
            )

    @pytest.mark.asyncio
    async def test_raises_value_error_for_zero_uploaded_by(self, tmp_path):
        client = MediaServiceClient("http://localhost")

        f = tmp_path / "photo.jpg"
        f.write_bytes(b"image data")

        # uploaded_by=0 should raise ValueError
        with pytest.raises(ValueError, match="uploaded_by must be a positive integer"):
            await client.upload_request_media(
                "260401-001",
                str(f),
                uploaded_by=0,
            )


# ---------------------------------------------------------------------------
# upload_request_media — request formatting
# ---------------------------------------------------------------------------

class TestUploadRequestMediaFormatting:
    @pytest.mark.asyncio
    async def test_uploads_file_from_path(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"fake image")

        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 42}}

        mock_post = AsyncMock(return_value=mock_response)
        client.client.post = mock_post

        result = await client.upload_request_media(
            "260401-001",
            str(f),
            category="request_photo",
            uploaded_by=5,
        )

        assert result == {"media_file": {"id": 42}}
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[0][0] == "/media/upload"

    @pytest.mark.asyncio
    async def test_uploads_file_from_bytes_io(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 10}}

        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.upload_request_media(
            "260401-002",
            io.BytesIO(b"data"),
            filename="test.jpg",
            uploaded_by=1,
        )

        assert result["media_file"]["id"] == 10

    @pytest.mark.asyncio
    async def test_tags_joined_with_comma(self, tmp_path):
        f = tmp_path / "img.jpg"
        f.write_bytes(b"data")

        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 1}}
        client.client.post = AsyncMock(return_value=mock_response)

        await client.upload_request_media(
            "260401-003",
            str(f),
            tags=["water", "urgent"],
            uploaded_by=1,
        )

        call_data = client.client.post.call_args[1]["data"]
        assert call_data["tags"] == "water,urgent"

    @pytest.mark.asyncio
    async def test_description_included_in_data(self, tmp_path):
        f = tmp_path / "img.jpg"
        f.write_bytes(b"data")

        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 1}}
        client.client.post = AsyncMock(return_value=mock_response)

        await client.upload_request_media(
            "260401-004",
            str(f),
            description="Water leak",
            uploaded_by=2,
        )

        call_data = client.client.post.call_args[1]["data"]
        assert call_data["description"] == "Water leak"

    @pytest.mark.asyncio
    async def test_uploaded_by_sent_as_string(self, tmp_path):
        f = tmp_path / "img.jpg"
        f.write_bytes(b"data")

        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 1}}
        client.client.post = AsyncMock(return_value=mock_response)

        await client.upload_request_media(
            "260401-005",
            str(f),
            uploaded_by=7,
        )

        call_data = client.client.post.call_args[1]["data"]
        assert call_data["uploaded_by"] == "7"


# ---------------------------------------------------------------------------
# search_media — params building
# ---------------------------------------------------------------------------

class TestSearchMediaParams:
    @pytest.mark.asyncio
    async def test_basic_params_always_present(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"total_count": 0, "items": []}
        client.client.get = AsyncMock(return_value=mock_response)

        await client.search_media()

        params = client.client.get.call_args[1]["params"]
        assert "status" in params
        assert "limit" in params
        assert "offset" in params

    @pytest.mark.asyncio
    async def test_request_numbers_joined_with_comma(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"total_count": 0}
        client.client.get = AsyncMock(return_value=mock_response)

        await client.search_media(request_numbers=["260401-001", "260401-002"])

        params = client.client.get.call_args[1]["params"]
        assert params["request_numbers"] == "260401-001,260401-002"

    @pytest.mark.asyncio
    async def test_date_from_formatted_as_iso(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"total_count": 0}
        client.client.get = AsyncMock(return_value=mock_response)

        dt = datetime(2026, 4, 1, 12, 0, 0)
        await client.search_media(date_from=dt)

        params = client.client.get.call_args[1]["params"]
        assert params["date_from"] == dt.isoformat()


# ---------------------------------------------------------------------------
# get_media_url
# ---------------------------------------------------------------------------

class TestGetMediaUrl:
    @pytest.mark.asyncio
    async def test_returns_url_from_response(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"file_url": "http://cdn/file.jpg"}
        client.client.get = AsyncMock(return_value=mock_response)

        url = await client.get_media_url(42)

        assert url == "http://cdn/file.jpg"

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        client = MediaServiceClient("http://localhost")
        client.client.get = AsyncMock(side_effect=Exception("timeout"))

        url = await client.get_media_url(99)

        assert url is None


# ---------------------------------------------------------------------------
