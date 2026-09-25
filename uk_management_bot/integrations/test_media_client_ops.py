"""Unit tests for MediaServiceClient — archive/delete, publication locks, convenience wrappers, report media, request media, additional search branches, get_media_file.

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


class TestDeleteStatusSemantics:
    """A9-P3-32: 404 на DELETE уточняется GET /media/{id} — старый
    медиа-сервис (до фикса) отвечал 404 и на транзиентный сбой саги, когда
    файл откатан в active. Клиент безопасен при любом порядке деплоя."""

    @staticmethod
    def _client_with(delete_code, get_code=404, get_status=None, get_raises=False):
        import httpx

        seen = []

        def handler(request):
            seen.append(request.method)
            if request.method == "DELETE":
                return httpx.Response(delete_code, json={})
            if get_raises:
                raise httpx.ConnectError("down", request=request)
            body = {"status": get_status} if get_status is not None else {}
            return httpx.Response(get_code, json=body)

        client = MediaServiceClient("http://localhost")
        client.client = httpx.AsyncClient(
            base_url="http://localhost/api/v1",
            transport=httpx.MockTransport(handler),
        )
        return client, seen

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kwargs, expected, methods", [
        # Удалён сейчас / повторно (already_deleted) — без GET.
        ({"delete_code": 200}, True, ["DELETE"]),
        # 404 + GET 404 — файла нет, цель достигнута.
        ({"delete_code": 404, "get_code": 404}, True, ["DELETE", "GET"]),
        # 404 + GET deleted — удалён раньше.
        ({"delete_code": 404, "get_code": 200, "get_status": "deleted"}, True, ["DELETE", "GET"]),
        # Старый медиа-сервис: 404 на транзиентный сбой, файл жив (active).
        ({"delete_code": 404, "get_code": 200, "get_status": "active"}, False, ["DELETE", "GET"]),
        ({"delete_code": 404, "get_code": 200, "get_status": "archived"}, False, ["DELETE", "GET"]),
        # Уточнение не удалось — не удалён, повторить.
        ({"delete_code": 404, "get_code": 500}, False, ["DELETE", "GET"]),
        ({"delete_code": 404, "get_raises": True}, False, ["DELETE", "GET"]),
        # Не удалён: конфликт / транзиентный сбой / ошибка — без GET.
        ({"delete_code": 409}, False, ["DELETE"]),
        ({"delete_code": 503}, False, ["DELETE"]),
        ({"delete_code": 500}, False, ["DELETE"]),
    ])
    async def test_delete_classifies_status(self, kwargs, expected, methods):
        client, seen = self._client_with(**kwargs)
        try:
            assert await client.delete_media(10) is expected
        finally:
            await client.client.aclose()
        assert seen == methods


# ---------------------------------------------------------------------------
# Publication locks (T5)
# ---------------------------------------------------------------------------

class TestPublicationLocks:
    @pytest.mark.asyncio
    async def test_acquire_returns_true_on_success(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.acquire_publication_lock(5)

        assert result is True
        client.client.post.assert_awaited_once_with("/media/5/publication-lock")

    @pytest.mark.asyncio
    async def test_acquire_returns_false_on_exception(self):
        client = MediaServiceClient("http://localhost")
        client.client.post = AsyncMock(side_effect=Exception("network error"))

        result = await client.acquire_publication_lock(5)

        assert result is False

    @pytest.mark.asyncio
    async def test_release_returns_true_on_success(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        client.client.delete = AsyncMock(return_value=mock_response)

        result = await client.release_publication_lock(5)

        assert result is True
        client.client.delete.assert_awaited_once_with("/media/5/publication-lock")

    @pytest.mark.asyncio
    async def test_release_returns_false_on_exception(self):
        client = MediaServiceClient("http://localhost")
        client.client.delete = AsyncMock(side_effect=Exception("network error"))

        result = await client.release_publication_lock(5)

        assert result is False

    @pytest.mark.asyncio
    async def test_list_returns_json_on_success(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"items": [], "total": 0}
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.list_publication_locks(limit=50, offset=10)

        assert result == {"items": [], "total": 0}
        client.client.get.assert_awaited_once_with(
            "/media/publication-locks", params={"limit": 50, "offset": 10}
        )

    @pytest.mark.asyncio
    async def test_list_raises_on_exception(self):
        """UNLIKE acquire/release, list_publication_locks propagates failures —
        a future reconciliation process must not treat a fetch error as "no
        locks held" and release everything it should have preserved."""
        client = MediaServiceClient("http://localhost")
        client.client.get = AsyncMock(side_effect=Exception("network error"))

        with pytest.raises(Exception, match="network error"):
            await client.list_publication_locks()


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
    async def test_report_upload_passes_content_type_and_timeout(self):
        """Атомарное «Готово» (API): тип — server-derived (сниффер), таймаут —
        короче бюджета edge; без них клиент молчит как раньше."""
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 21}}
        client.client.post = AsyncMock(return_value=mock_response)

        await client.upload_report_media(
            "260401-003", io.BytesIO(b"\xff\xd8\xffjpeg"), filename="after.jpg",
            content_type="image/jpeg", timeout=25.0,
        )

        kwargs = client.client.post.call_args.kwargs
        assert kwargs["files"] == [("file", ("after.jpg", b"\xff\xd8\xffjpeg", "image/jpeg"))]
        assert kwargs["timeout"] == 25.0

    @pytest.mark.asyncio
    async def test_report_upload_without_overrides_keeps_wire(self):
        client = MediaServiceClient("http://localhost")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"media_file": {"id": 22}}
        client.client.post = AsyncMock(return_value=mock_response)

        await client.upload_report_media("260401-004", io.BytesIO(b"x"), filename="a.jpg")

        kwargs = client.client.post.call_args.kwargs
        assert kwargs["files"] == [("file", ("a.jpg", b"x"))]
        assert "timeout" not in kwargs

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
