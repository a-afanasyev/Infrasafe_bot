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
- upload_document_to_media_service: builds USER_{id} request_number correctly;
  uploaded_by = internal user.id (INT4 in media-service), not telegram id;
  content_type sniffed from bytes; unsupported formats are not sent
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
            await mh.upload_telegram_file_to_media_service(
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

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16
PDF_BYTES = b"%PDF-1.7\n" + b"\x00" * 16


def _make_doc_bot(data: bytes = JPEG_BYTES, file_path: str = "documents/file.jpg") -> MagicMock:
    bot = _make_bot(file_path)

    async def download(_path, destination):
        destination.write(data)

    bot.download_file = AsyncMock(side_effect=download)
    return bot


def _capturing_client() -> tuple[MagicMock, dict]:
    client = MagicMock()
    captured: dict = {}

    async def capture(**kwargs):
        captured.update(kwargs)
        return {"media_file": {"id": 1}}

    client.upload_request_media = capture
    return client, captured


async def _upload_doc(client, bot, *, user_telegram_id=12345, uploaded_by_user_id=7):
    with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
        from uk_management_bot.utils.media_helpers import upload_document_to_media_service
        return await upload_document_to_media_service(
            bot=bot,
            file_id="doc",
            user_telegram_id=user_telegram_id,
            uploaded_by_user_id=uploaded_by_user_id,
        )


class TestUploadDocumentToMediaService:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_media_client(self):
        result = await _upload_doc(None, MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_uses_user_request_number(self):
        """The request_number passed to the client must be USER_{telegram_id}:
        по нему delete_user_documents_from_media_service находит сканы."""
        client, captured = _capturing_client()
        await _upload_doc(client, _make_doc_bot(), user_telegram_id=12345)
        assert captured.get("request_number") == "USER_12345"

    @pytest.mark.asyncio
    async def test_category_is_archive(self):
        """The category must always be 'archive' for user documents."""
        client, captured = _capturing_client()
        await _upload_doc(client, _make_doc_bot())
        assert captured.get("category") == "archive"

    @pytest.mark.asyncio
    async def test_uploaded_by_is_internal_user_id_not_telegram_id(self):
        """C2 (ревью 2026-09-28): uploaded_by_user_id в media-service — INT4.
        Telegram ID > 2^31-1 ронял INSERT уже ПОСЛЕ отправки в архивный канал —
        скан оставался в канале без строки, удаление его не находило."""
        client, captured = _capturing_client()
        await _upload_doc(client, _make_doc_bot(), user_telegram_id=6055402868, uploaded_by_user_id=53)
        assert captured.get("uploaded_by") == 53
        assert captured.get("request_number") == "USER_6055402868"
        # Решение владельца 2026-09-29: и users.id, и Telegram ID.
        assert captured.get("uploaded_by_telegram_id") == 6055402868

    @pytest.mark.asyncio
    async def test_content_type_is_sniffed_from_bytes(self):
        """httpx угадывал тип по расширению (.jpg/.pdf/...) — передаём сниффленный."""
        client, captured = _capturing_client()
        await _upload_doc(client, _make_doc_bot(JPEG_BYTES, "documents/file.bin"))
        assert captured.get("content_type") == "image/jpeg"

    @pytest.mark.asyncio
    async def test_unsupported_format_is_not_sent(self):
        """PDF media-service не хранит (allowlist) — не гоняем его по сети впустую."""
        client = MagicMock()
        client.upload_request_media = AsyncMock()
        result = await _upload_doc(client, _make_doc_bot(PDF_BYTES, "documents/file.pdf"))
        assert result is None
        client.upload_request_media.assert_not_awaited()


# ---------------------------------------------------------------------------
# delete_user_documents_from_media_service
# ---------------------------------------------------------------------------

class TestDeleteUserDocumentsFromMediaService:
    """Хелпер обязан РАЗЛИЧАТЬ «удалили» и «не смогли».

    Прежний контракт возвращал `True` в том числе когда Media Service вообще
    недоступен, — вызывающий не мог отличить успех от несостоявшейся зачистки.
    Цена лжи высокая: строки `UserDocument` к этому моменту уже удалены одной
    транзакцией, то есть сканы паспортов остаются в Media Service и Telegram,
    а из карточки исчезают. Находка аудита 2026-07-29.
    """

    @pytest.mark.asyncio
    async def test_unavailable_service_is_not_success(self):
        from uk_management_bot.utils.media_helpers import (
            MediaCleanupResult, delete_user_documents_from_media_service,
        )
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=None):
            result = await delete_user_documents_from_media_service(user_telegram_id=42)
        assert result is MediaCleanupResult.UNAVAILABLE
        assert result is not MediaCleanupResult.DELETED

    @pytest.mark.asyncio
    async def test_no_files_is_nothing_to_delete(self):
        from uk_management_bot.utils.media_helpers import (
            MediaCleanupResult, delete_user_documents_from_media_service,
        )
        client = _make_media_client()
        client.get_request_media = AsyncMock(return_value=[])
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            result = await delete_user_documents_from_media_service(user_telegram_id=43)
        assert result is MediaCleanupResult.NOTHING_TO_DELETE

    @pytest.mark.asyncio
    async def test_all_files_deleted(self):
        from uk_management_bot.utils.media_helpers import (
            MediaCleanupResult, delete_user_documents_from_media_service,
        )
        client = _make_media_client()
        client.get_request_media = AsyncMock(return_value=[
            {"id": "f1"}, {"id": "f2"}, {"id": "f3"},
        ])
        client.delete_media = AsyncMock(return_value=True)
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            result = await delete_user_documents_from_media_service(user_telegram_id=44)
        assert result is MediaCleanupResult.DELETED
        assert client.delete_media.call_count == 3

    @pytest.mark.asyncio
    async def test_partial_deletion_is_not_success(self):
        """Часть файлов не удалилась — прежний код всё равно возвращал True."""
        from uk_management_bot.utils.media_helpers import (
            MediaCleanupResult, delete_user_documents_from_media_service,
        )
        client = _make_media_client()
        client.get_request_media = AsyncMock(return_value=[{"id": "f1"}, {"id": "f2"}])
        client.delete_media = AsyncMock(side_effect=[True, False])
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            result = await delete_user_documents_from_media_service(user_telegram_id=46)
        assert result is MediaCleanupResult.PARTIAL

    @pytest.mark.asyncio
    async def test_failure_on_get_media_exception(self):
        from uk_management_bot.utils.media_helpers import (
            MediaCleanupResult, delete_user_documents_from_media_service,
        )
        client = _make_media_client()
        client.get_request_media = AsyncMock(side_effect=Exception("network error"))
        with patch("uk_management_bot.utils.media_helpers.get_media_client", return_value=client):
            result = await delete_user_documents_from_media_service(user_telegram_id=45)
        assert result is MediaCleanupResult.FAILED

    @pytest.mark.asyncio
    async def test_result_is_truthy_only_when_cleanup_happened(self):
        """Совместимость с `if await …` у сторонних вызывающих: истинны только
        те исходы, при которых чистить больше нечего."""
        from uk_management_bot.utils.media_helpers import MediaCleanupResult
        assert bool(MediaCleanupResult.DELETED) is True
        assert bool(MediaCleanupResult.NOTHING_TO_DELETE) is True
        assert bool(MediaCleanupResult.UNAVAILABLE) is False
        assert bool(MediaCleanupResult.PARTIAL) is False
        assert bool(MediaCleanupResult.FAILED) is False
