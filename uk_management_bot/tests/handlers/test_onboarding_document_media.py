"""save_document: строгая зашифрованная загрузка.

Документ сохраняется, только если он лёг в медиа-сервис: нет `media_id` —
нет строки (раньше скан молча сохранялся мимо хранилища). Guard проверяется
дважды: до загрузки и при вставке под блокировкой; отказ или сбой вставки
после загрузки — blob удаляется по `media_id` (компенсация).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from uk_management_bot.handlers import onboarding
from uk_management_bot.services.user_verification_service import UploadDenied
from uk_management_bot.states.onboarding import OnboardingStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.media_helpers import DocumentUploadError, EncryptedUpload

TG_ID = 6055402868
USER_ID = 53
UPLOAD = EncryptedUpload(media_id=77, key=b"k" * 32, document_uuid="00000000-0000-4000-8000-000000000077")


def _msg():
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=TG_ID)
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()
    msg.bot = MagicMock()
    return msg


def _state():
    state = MagicMock()
    state.get_data = AsyncMock(return_value={
        "selected_document_type": "passport", "file_id": "doc_fid",
        "file_name": "scan.jpg", "file_size": 100,
    })
    state.clear = AsyncMock()
    state.set_state = AsyncMock()
    state.set_data = AsyncMock()
    return state


def _texts(msg):
    return " ".join(str(c.args[0]) for c in msg.answer.await_args_list)


async def _save(run_db_results, upload=None, discard=None):
    msg, state = _msg(), _state()
    upload = upload or AsyncMock(return_value=UPLOAD)
    discard = discard or AsyncMock()
    with patch.object(onboarding, "run_db", AsyncMock(side_effect=run_db_results)), \
         patch.object(onboarding, "upload_encrypted_document", upload), \
         patch.object(onboarding, "_discard_document_blob", discard):
        await onboarding.save_document(msg, state, "ru")
    return msg, state, upload, discard


@pytest.mark.parametrize("language", ["ru", "uz"])
@pytest.mark.parametrize("key", [
    "onboarding.documents.upload_unsupported", "onboarding.documents.upload_unavailable",
    "onboarding.documents.upload_not_required", "onboarding.documents.upload_rejected",
    "onboarding.documents.upload_limit", "onboarding.documents.upload_too_large",
])
def test_upload_texts_exist(key, language):
    """get_text без ключа возвращает сам ключ — без этой проверки тесты выше прошли бы и без локалей."""
    assert get_text(key, language=language) != key


@pytest.mark.asyncio
async def test_saved_with_media_id_and_internal_user_id():
    # run_db: 1) guard → (users.id, None), 2) вставка → None (сохранён)
    msg, state, upload, discard = await _save([(USER_ID, None), None])

    upload.assert_awaited_once()
    assert upload.await_args.kwargs == {"user_id": USER_ID, "document_type": "passport"}
    discard.assert_not_awaited()
    assert get_text("onboarding.documents.document_saved", language="ru") in _texts(msg)
    # открытый скан не остаётся в чате с ботом
    msg.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_denied_before_upload_sends_nothing_to_media():
    msg, state, upload, _ = await _save([(USER_ID, UploadDenied.NOT_REQUIRED)])
    upload.assert_not_awaited()
    assert get_text("onboarding.documents.upload_not_required", language="ru") in _texts(msg)


@pytest.mark.parametrize("reason, key", [
    ("unavailable", "onboarding.documents.upload_unavailable"),
    ("unsupported", "onboarding.documents.upload_unsupported"),
])
@pytest.mark.asyncio
async def test_upload_failure_creates_no_row_and_offers_skip(reason, key):
    upload = AsyncMock(side_effect=DocumentUploadError(reason))
    msg, state, _, discard = await _save([(USER_ID, None)], upload=upload)

    assert get_text(key, language="ru") in _texts(msg)
    # снова экран выбора типа — там «Пропустить», онбординг не застревает
    state.set_state.assert_awaited_with(OnboardingStates.waiting_for_document_type)
    discard.assert_not_awaited()


@pytest.mark.asyncio
async def test_denied_at_insert_discards_blob():
    """Гонка: решение менеджера закоммичено между загрузкой и вставкой."""
    msg, _, _, discard = await _save([(USER_ID, None), UploadDenied.NOT_REQUIRED])
    discard.assert_awaited_once_with(77)
    assert get_text("onboarding.documents.document_saved", language="ru") not in _texts(msg)


@pytest.mark.asyncio
async def test_insert_failure_discards_blob():
    msg, _, _, discard = await _save([(USER_ID, None), RuntimeError("db down")])
    discard.assert_awaited_once_with(77)
    assert get_text("errors.unknown_error", language="ru") in _texts(msg)


# ─── Шаг подтверждения убран ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_file_is_saved_without_confirmation_step():
    msg = _msg()
    msg.document = MagicMock(file_id="d", file_name="scan.pdf", file_size=100)
    msg.photo = None
    state = _state()
    state.update_data = AsyncMock()
    save = AsyncMock()
    with patch.object(onboarding, "save_document", save):
        await onboarding.process_document_file(msg, state, "ru")

    save.assert_awaited_once()
    state.update_data.assert_awaited_once_with(
        {"file_id": "d", "file_name": "document.pdf", "file_size": 100})  # без исходного имени
    assert OnboardingStates.waiting_for_document_confirmation not in [
        c.args[0] for c in state.set_state.await_args_list]


@pytest.mark.asyncio
async def test_stale_confirmation_state_is_reset_with_hint():
    """Кто застрял в старом шаге подтверждения в момент деплоя — сброс и вход заново."""
    msg = _msg()
    state = _state()
    await onboarding.stale_document_confirmation(msg, state, "ru")
    state.clear.assert_awaited_once()
    kb = msg.answer.await_args.kwargs["reply_markup"]
    assert kb.inline_keyboard[0][0].callback_data == "docs:upload"
