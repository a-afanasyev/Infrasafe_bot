"""save_document → Media Service: uploaded_by = внутренний users.id.

Ревью медиасервиса 2026-09-28 (C2): раньше уходил Telegram ID, а колонка
`uploaded_by_user_id` в media-service — INT4. У аккаунтов с id > 2^31-1 INSERT
падал уже после отправки скана в архивный канал: файл оставался в канале без
строки, и зачистка документов пользователя его не находила.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from uk_management_bot.handlers import onboarding

BIG_TG_ID = 6055402868
INTERNAL_ID = 53


@pytest.mark.asyncio
async def test_save_document_passes_internal_user_id_to_media_service():
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=BIG_TG_ID)
    msg.answer = AsyncMock()
    msg.bot = MagicMock()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={
        "selected_document_type": "passport",
        "file_id": "doc_fid",
        "file_name": "scan.jpg",
        "file_size": 100,
    })
    state.clear = AsyncMock()

    upload = AsyncMock(return_value={"media_file": {"id": 1}})
    # run_db: 1) владелец документа → users.id, 2) запись UserDocument.
    run_db = AsyncMock(side_effect=[INTERNAL_ID, None])
    with patch.object(onboarding, "run_db", run_db), \
         patch("uk_management_bot.utils.media_helpers.upload_document_to_media_service", upload):
        await onboarding.save_document(msg, state, "ru")

    upload.assert_awaited_once()
    kwargs = upload.await_args.kwargs
    assert kwargs["uploaded_by_user_id"] == INTERNAL_ID
    assert kwargs["user_telegram_id"] == BIG_TG_ID
