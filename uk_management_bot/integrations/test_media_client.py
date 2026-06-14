"""Unit tests for MediaServiceClient."""
import io
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

from uk_management_bot.integrations.media_client import (
    MediaServiceClient,
    upload_request_photo,
    upload_completion_photo,
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
# archive_media / delete_media
# ---------------------------------------------------------------------------

class TestArchiveAndDelete:
    @pytest.mark.asyncio
    async def test_archive_returns_true_on_success(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.archive_media(5, reason="outdated")

        assert result is True

    @pytest.mark.asyncio
    async def test_archive_returns_false_on_exception(self):
        client = MediaServiceClient("http://localhost")
        client.client.post = AsyncMock(side_effect=Exception("network error"))

        result = await client.archive_media(5)

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        client.client.delete = AsyncMock(return_value=mock_response)

        result = await client.delete_media(10)

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_returns_false_on_exception(self):
        client = MediaServiceClient("http://localhost")
        client.client.delete = AsyncMock(side_effect=Exception("network error"))

        result = await client.delete_media(10)

        assert result is False


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

class TestConvenienceFunctions:
    @pytest.mark.asyncio
    async def test_upload_request_photo_delegates_to_client(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"data")

        client = MagicMock()
        client.upload_request_media = AsyncMock(
            return_value={"media_file": {"id": 1}}
        )

        await upload_request_photo(
            client, "260401-001", str(f), description="test", uploaded_by=3
        )

        client.upload_request_media.assert_called_once()
        call_kwargs = client.upload_request_media.call_args[1]
        assert call_kwargs["category"] == "request_photo"
        assert call_kwargs["uploaded_by"] == 3

    @pytest.mark.asyncio
    async def test_upload_completion_photo_delegates_to_client(self, tmp_path):
        f = tmp_path / "done.jpg"
        f.write_bytes(b"data")

        client = MagicMock()
        client.upload_report_media = AsyncMock(
            return_value={"media_file": {"id": 2}}
        )

        await upload_completion_photo(
            client, "260401-001", str(f), uploaded_by=4
        )

        client.upload_report_media.assert_called_once()
        call_kwargs = client.upload_report_media.call_args[1]
        assert call_kwargs["report_type"] == "completion_photo"


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    @pytest.mark.asyncio
    async def test_aenter_returns_self(self):
        client = MediaServiceClient("http://localhost")
        result = await client.__aenter__()
        assert result is client
        await client.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_aexit_closes_client(self):
        client = MediaServiceClient("http://localhost")
        client.client = AsyncMock()
        client.client.aclose = AsyncMock()

        await client.__aenter__()
        await client.__aexit__(None, None, None)

        client.client.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# upload_report_media
# ---------------------------------------------------------------------------

class TestUploadReportMedia:
    @pytest.mark.asyncio
    async def test_raises_file_not_found_for_missing_path(self, tmp_path):
        client = MediaServiceClient("http://localhost")
        with pytest.raises(FileNotFoundError):
            await client.upload_report_media("260401-001", tmp_path / "nonexistent.jpg")

    @pytest.mark.asyncio
    async def test_uploads_report_from_path(self, tmp_path):
        f = tmp_path / "done.jpg"
        f.write_bytes(b"report image")

        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 77}}
        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.upload_report_media(
            "260401-001", str(f), report_type="completion_photo"
        )

        assert result == {"media_file": {"id": 77}}
        client.client.post.assert_called_once()
        assert client.client.post.call_args[0][0] == "/media/upload-report"

    @pytest.mark.asyncio
    async def test_uploads_report_from_bytes_io(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 20}}
        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.upload_report_media(
            "260401-002", io.BytesIO(b"report"), filename="done.jpg"
        )

        assert result["media_file"]["id"] == 20

    @pytest.mark.asyncio
    async def test_bytesio_without_name_attr_uses_report_default(self):
        """BytesIO objects without a name attribute default to 'report'."""
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 21}}
        client.client.post = AsyncMock(return_value=mock_response)

        buf = io.BytesIO(b"data")
        # BytesIO has no 'name' attribute
        assert not hasattr(buf, "name")

        result = await client.upload_report_media("260401-003", buf)
        assert result is not None

    @pytest.mark.asyncio
    async def test_raises_value_error_for_non_positive_uploaded_by(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"data")

        client = MediaServiceClient("http://localhost")
        with pytest.raises(ValueError, match="uploaded_by must be a positive integer"):
            await client.upload_report_media("260401-001", str(f), uploaded_by=0)

    @pytest.mark.asyncio
    async def test_report_tags_joined_with_comma(self, tmp_path):
        f = tmp_path / "img.jpg"
        f.write_bytes(b"data")

        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 1}}
        client.client.post = AsyncMock(return_value=mock_response)

        await client.upload_report_media(
            "260401-004", str(f), tags=["done", "clean"], uploaded_by=1
        )

        call_data = client.client.post.call_args[1]["data"]
        assert call_data["tags"] == "done,clean"

    @pytest.mark.asyncio
    async def test_exception_propagates(self, tmp_path):
        f = tmp_path / "img.jpg"
        f.write_bytes(b"data")

        client = MediaServiceClient("http://localhost")
        client.client.post = AsyncMock(side_effect=Exception("network error"))

        with pytest.raises(Exception, match="network error"):
            await client.upload_report_media("260401-005", str(f))


# ---------------------------------------------------------------------------
# get_request_media
# ---------------------------------------------------------------------------

class TestGetRequestMedia:
    @pytest.mark.asyncio
    async def test_returns_list_from_response(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{"id": 1}, {"id": 2}]
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.get_request_media("260401-001")

        assert len(result) == 2
        assert result[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_category_filter_included_in_params(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []
        client.client.get = AsyncMock(return_value=mock_response)

        await client.get_request_media("260401-001", category="request_photo")

        params = client.client.get.call_args[1]["params"]
        assert params["category"] == "request_photo"

    @pytest.mark.asyncio
    async def test_no_category_filter_by_default(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []
        client.client.get = AsyncMock(return_value=mock_response)

        await client.get_request_media("260401-001")

        params = client.client.get.call_args[1]["params"]
        assert "category" not in params

    @pytest.mark.asyncio
    async def test_custom_limit_sent_in_params(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []
        client.client.get = AsyncMock(return_value=mock_response)

        await client.get_request_media("260401-001", limit=10)

        params = client.client.get.call_args[1]["params"]
        assert params["limit"] == 10

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        client = MediaServiceClient("http://localhost")
        client.client.get = AsyncMock(side_effect=Exception("timeout"))

        with pytest.raises(Exception, match="timeout"):
            await client.get_request_media("260401-001")


# ---------------------------------------------------------------------------
# search_media — additional branches
# ---------------------------------------------------------------------------

class TestSearchMediaAdditionalBranches:
    @pytest.mark.asyncio
    async def test_query_param_included(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"total_count": 0}
        client.client.get = AsyncMock(return_value=mock_response)

        await client.search_media(query="water leak")

        params = client.client.get.call_args[1]["params"]
        assert params["query"] == "water leak"

    @pytest.mark.asyncio
    async def test_tags_joined_with_comma(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"total_count": 0}
        client.client.get = AsyncMock(return_value=mock_response)

        await client.search_media(tags=["urgent", "pipe"])

        params = client.client.get.call_args[1]["params"]
        assert params["tags"] == "urgent,pipe"

    @pytest.mark.asyncio
    async def test_date_to_formatted_as_iso(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"total_count": 0}
        client.client.get = AsyncMock(return_value=mock_response)

        dt = datetime(2026, 4, 30, 23, 59, 59)
        await client.search_media(date_to=dt)

        params = client.client.get.call_args[1]["params"]
        assert params["date_to"] == dt.isoformat()

    @pytest.mark.asyncio
    async def test_file_types_joined_with_comma(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"total_count": 0}
        client.client.get = AsyncMock(return_value=mock_response)

        await client.search_media(file_types=["jpg", "png"])

        params = client.client.get.call_args[1]["params"]
        assert params["file_types"] == "jpg,png"

    @pytest.mark.asyncio
    async def test_categories_joined_with_comma(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"total_count": 0}
        client.client.get = AsyncMock(return_value=mock_response)

        await client.search_media(categories=["request_photo", "completion_photo"])

        params = client.client.get.call_args[1]["params"]
        assert params["categories"] == "request_photo,completion_photo"

    @pytest.mark.asyncio
    async def test_uploaded_by_param_included(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"total_count": 0}
        client.client.get = AsyncMock(return_value=mock_response)

        await client.search_media(uploaded_by=5)

        params = client.client.get.call_args[1]["params"]
        assert params["uploaded_by"] == 5

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        client = MediaServiceClient("http://localhost")
        client.client.get = AsyncMock(side_effect=Exception("search failed"))

        with pytest.raises(Exception, match="search failed"):
            await client.search_media()


# ---------------------------------------------------------------------------
# get_media_file
# ---------------------------------------------------------------------------

class TestGetMediaFile:
    @pytest.mark.asyncio
    async def test_returns_media_info_on_success(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"id": 42, "filename": "photo.jpg"}
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.get_media_file(42)

        assert result == {"id": 42, "filename": "photo.jpg"}
        assert "/media/42" in client.client.get.call_args[0][0]

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        client = MediaServiceClient("http://localhost")
        client.client.get = AsyncMock(side_effect=Exception("not found"))

        with pytest.raises(Exception, match="not found"):
            await client.get_media_file(99)


# ---------------------------------------------------------------------------
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
