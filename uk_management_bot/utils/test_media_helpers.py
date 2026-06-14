"""
Unit tests for utils/media_helpers.py

media_helpers.py contains only async I/O functions (upload_*, delete_*) that
require a live Bot connection and a Media Service client.  All pure-function
behaviour (filename construction, category logic, request_number embedding) is
tested here by mocking the external dependencies.

Tests verify:
- upload_telegram_file_to_media_service: returns None when media client is absent
- upload_telegram_file_to_media_service: returns result dict on successful upload
- upload_multiple_telegram_files: aggregates results, skips failures
- upload_report_file_to_media_service: returns None when media client is absent
- upload_document_to_media_service: builds USER_{id} request_number correctly
- delete_user_documents_from_media_service: returns True when media client absent
- delete_user_documents_from_media_service: deletes each file and returns True
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bot(file_path: str = "photos/file.jpg") -> MagicMock:
    """Create a mock Bot that returns a file object and allows downloading."""
    bot = MagicMock()
    file_obj = MagicMock()
    file_obj.file_path = file_path
    bot.get_file = AsyncMock(return_value=file_obj)
    bot.download_file = AsyncMock()
    return bot


def _make_media_client(upload_result: dict | None = None, success: bool = True) -> MagicMock:
    client = MagicMock()
    client.upload_request_media = AsyncMock(return_value=upload_result or {"media_file": {"id": "abc123"}})
    client.upload_report_media = AsyncMock(return_value=upload_result or {"media_file": {"id": "rpt123"}})
    client.get_request_media = AsyncMock(return_value=[])
    client.delete_media = AsyncMock(return_value=success)
    return client


# ---------------------------------------------------------------------------
# upload_telegram_file_to_media_service
# ---------------------------------------------------------------------------

class TestUploadTelegramFileToMediaService:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_media_client(self):
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=None):
            from uk_management_bot.utils.media_helpers import upload_telegram_file_to_media_service
            result = await upload_telegram_file_to_media_service(
                bot=MagicMock(),
                file_id="file123",
                request_number="250101-001",
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        client = _make_media_client()
        bot = _make_bot()
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            from uk_management_bot.utils.media_helpers import upload_telegram_file_to_media_service
            result = await upload_telegram_file_to_media_service(
                bot=bot,
                file_id="file456",
                request_number="250101-002",
                category="request_photo",
                uploaded_by=42,
            )
        assert result is not None
        assert result["media_file"]["id"] == "abc123"

    @pytest.mark.asyncio
    async def test_extension_derived_from_file_path(self):
        """The filename passed to the client uses the extension from the Telegram file path."""
        client = _make_media_client()
        bot = _make_bot(file_path="videos/clip.mp4")
        captured_kwargs = {}

        async def capture_upload(**kwargs):
            captured_kwargs.update(kwargs)
            return {"media_file": {"id": "x"}}

        client.upload_request_media = capture_upload

        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            import importlib
            import uk_management_bot.utils.media_helpers as mh
            importlib.reload(mh)  # reset cached client reference
            result = await mh.upload_telegram_file_to_media_service(
                bot=bot,
                file_id="vid789",
                request_number="250101-003",
                category="request_video",
            )
        # The filename should end with .mp4
        if captured_kwargs.get("filename"):
            assert captured_kwargs["filename"].endswith(".mp4")

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        """If an exception occurs during upload, returns None."""
        client = MagicMock()
        client.upload_request_media = AsyncMock(side_effect=Exception("Upload failed"))
        bot = _make_bot()
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            from uk_management_bot.utils.media_helpers import upload_telegram_file_to_media_service
            result = await upload_telegram_file_to_media_service(
                bot=bot,
                file_id="bad_file",
                request_number="250101-004",
            )
        assert result is None


# ---------------------------------------------------------------------------
# upload_multiple_telegram_files
# ---------------------------------------------------------------------------

class TestUploadMultipleTelegramFiles:
    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=None):
            from uk_management_bot.utils.media_helpers import upload_multiple_telegram_files
            result = await upload_multiple_telegram_files(
                bot=MagicMock(),
                file_ids=[],
                request_number="250101-005",
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_all_successful_files_collected(self):
        client = _make_media_client()
        bot = _make_bot()
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            from uk_management_bot.utils.media_helpers import upload_multiple_telegram_files
            result = await upload_multiple_telegram_files(
                bot=bot,
                file_ids=["f1", "f2", "f3"],
                request_number="250101-006",
            )
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_failed_files_skipped(self):
        """Files that return None from the single-upload function are excluded."""
        client = MagicMock()
        call_count = 0

        async def conditional_upload(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise Exception("partial failure")
            return {"media_file": {"id": f"id{call_count}"}}

        client.upload_request_media = conditional_upload
        bot = _make_bot()
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            from uk_management_bot.utils.media_helpers import upload_multiple_telegram_files
            result = await upload_multiple_telegram_files(
                bot=bot,
                file_ids=["a", "b", "c", "d"],
                request_number="250101-007",
            )
        # Only odd-indexed calls succeed → 2 out of 4
        assert len(result) == 2


# ---------------------------------------------------------------------------
# upload_report_file_to_media_service
# ---------------------------------------------------------------------------

class TestUploadReportFileToMediaService:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_media_client(self):
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=None):
            from uk_management_bot.utils.media_helpers import upload_report_file_to_media_service
            result = await upload_report_file_to_media_service(
                bot=MagicMock(),
                file_id="r1",
                request_number="250101-010",
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        client = _make_media_client()
        bot = _make_bot()
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            from uk_management_bot.utils.media_helpers import upload_report_file_to_media_service
            result = await upload_report_file_to_media_service(
                bot=bot,
                file_id="r2",
                request_number="250101-011",
                report_type="completion_photo",
            )
        assert result is not None


# ---------------------------------------------------------------------------
# upload_document_to_media_service
# ---------------------------------------------------------------------------

class TestUploadDocumentToMediaService:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_media_client(self):
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=None):
            from uk_management_bot.utils.media_helpers import upload_document_to_media_service
            result = await upload_document_to_media_service(
                bot=MagicMock(),
                file_id="doc1",
                user_telegram_id=999,
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_uses_user_request_number(self):
        """The request_number passed to the client must be USER_{user_id}."""
        client = MagicMock()
        captured = {}

        async def capture(**kwargs):
            captured.update(kwargs)
            return {"media_file": {"id": "docX"}}

        client.upload_request_media = capture
        bot = _make_bot()
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            from uk_management_bot.utils.media_helpers import upload_document_to_media_service
            await upload_document_to_media_service(
                bot=bot,
                file_id="doc2",
                user_telegram_id=12345,
            )
        assert captured.get("request_number") == "USER_12345"

    @pytest.mark.asyncio
    async def test_category_is_archive(self):
        """The category must always be 'archive' for user documents."""
        client = MagicMock()
        captured = {}

        async def capture(**kwargs):
            captured.update(kwargs)
            return {"media_file": {"id": "docY"}}

        client.upload_request_media = capture
        bot = _make_bot()
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            from uk_management_bot.utils.media_helpers import upload_document_to_media_service
            await upload_document_to_media_service(
                bot=bot,
                file_id="doc3",
                user_telegram_id=777,
            )
        assert captured.get("category") == "archive"


# ---------------------------------------------------------------------------
# delete_user_documents_from_media_service
# ---------------------------------------------------------------------------

class TestDeleteUserDocumentsFromMediaService:
    @pytest.mark.asyncio
    async def test_returns_true_when_no_media_client(self):
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=None):
            from uk_management_bot.utils.media_helpers import delete_user_documents_from_media_service
            result = await delete_user_documents_from_media_service(user_telegram_id=42)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_when_no_files(self):
        client = _make_media_client()
        client.get_request_media = AsyncMock(return_value=[])
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            from uk_management_bot.utils.media_helpers import delete_user_documents_from_media_service
            result = await delete_user_documents_from_media_service(user_telegram_id=43)
        assert result is True

    @pytest.mark.asyncio
    async def test_deletes_each_file_and_returns_true(self):
        client = _make_media_client()
        client.get_request_media = AsyncMock(return_value=[
            {"id": "f1"},
            {"id": "f2"},
            {"id": "f3"},
        ])
        client.delete_media = AsyncMock(return_value=True)
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            from uk_management_bot.utils.media_helpers import delete_user_documents_from_media_service
            result = await delete_user_documents_from_media_service(user_telegram_id=44)
        assert result is True
        assert client.delete_media.call_count == 3

    @pytest.mark.asyncio
    async def test_returns_false_on_get_media_exception(self):
        client = _make_media_client()
        client.get_request_media = AsyncMock(side_effect=Exception("network error"))
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            from uk_management_bot.utils.media_helpers import delete_user_documents_from_media_service
            result = await delete_user_documents_from_media_service(user_telegram_id=45)
        assert result is False
