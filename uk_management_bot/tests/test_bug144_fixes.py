"""BUG-144 — предсуществующие дефекты пакета handlers/user_verification/.

  1. document.created_at.strftime без NULL-guard'а (document_review.py,
     documents.py x2) — строка с NULL роняла хендлер в unknown_error;
  2. карточка verify_document подставляла сырой type_value вместо
     get_text('verification.document_types.…');
  3. после process_request_comment меню перерисовывалось с пустой
     статистикой {} — счётчики на кнопках обнулялись;
  4. caption скачанного документа содержал захардкоженный русский
     «📅 Загружен:» вместо ключа user_verification.handlers.uploaded_date.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from uk_management_bot.utils.helpers import get_text


def _make_callback(data):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 42
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.bot.send_document = AsyncMock()
    cb.bot.send_photo = AsyncMock()
    return cb


def _make_doc(created_at):
    from uk_management_bot.database.models.user_verification import VerificationStatus

    doc = MagicMock()
    doc.id = 5
    doc.document_type.value = "passport"
    doc.verification_status = VerificationStatus.PENDING
    doc.file_id = "FID"
    doc.file_name = "passport.jpg"
    doc.file_size = 2048
    doc.created_at = created_at
    doc.verification_notes = None
    return doc


def _db_single_doc(doc):
    q = MagicMock()
    q.filter.return_value = q
    q.first.return_value = doc
    db = MagicMock()
    db.query.return_value = q
    return db


def _db_documents_page(user, docs):
    from uk_management_bot.database.models.user import User

    def query_side_effect(model):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        if model is User:
            q.first.return_value = user
        else:
            q.all.return_value = docs
        return q

    db = MagicMock()
    db.query.side_effect = query_side_effect
    return db


# ── 1: NULL-guard created_at ────────────────────────────────────────────────

async def test_verify_document_null_created_at_renders_card():
    from uk_management_bot.handlers.user_verification import document_review

    cb = _make_callback("document_verify_5")
    db = _db_single_doc(_make_doc(created_at=None))

    await document_review.verify_document(cb, roles=["manager"], language="ru", _db=db)

    cb.message.edit_text.assert_awaited_once()


async def test_view_user_documents_null_created_at_renders_list():
    from uk_management_bot.handlers.user_verification import documents

    user = MagicMock()
    user.first_name = "Иван"
    user.username = "ivan"
    cb = _make_callback("view_user_documents_9")
    db = _db_documents_page(user, [_make_doc(created_at=None)])

    await documents.view_user_documents(cb, roles=["manager"], language="ru", _db=db)

    cb.message.edit_text.assert_awaited_once()


async def test_download_document_null_created_at_still_sends():
    from uk_management_bot.handlers.user_verification import documents

    cb = _make_callback("download_document_5")
    db = _db_single_doc(_make_doc(created_at=None))

    await documents.download_user_document(cb, roles=["manager"], language="ru", _db=db)

    cb.bot.send_document.assert_awaited_once()


# ── 2: локализация типа документа в карточке ────────────────────────────────

async def test_verify_document_card_localizes_doc_type():
    from uk_management_bot.handlers.user_verification import document_review

    cb = _make_callback("document_verify_5")
    db = _db_single_doc(_make_doc(created_at=datetime(2026, 1, 1, 10, 0)))

    await document_review.verify_document(cb, roles=["manager"], language="ru", _db=db)

    cb.message.edit_text.assert_awaited_once()
    text = cb.message.edit_text.await_args.args[0]
    localized = get_text("verification.document_types.passport", language="ru")
    assert localized in text, f"в карточке нет локализованного типа: {text!r}"


# ── 3: статистика меню пересчитывается после запроса ────────────────────────

async def test_request_comment_redraws_menu_with_fresh_stats():
    from uk_management_bot.handlers.user_verification import info_requests

    message = MagicMock()
    message.text = "прошу приложить паспорт"
    message.from_user.id = 77
    message.answer = AsyncMock()
    message.bot.send_message = AsyncMock()
    state = AsyncMock()
    state.get_data.return_value = {"target_user_id": 9, "info_type": "passport"}
    stats = {"pending": 3, "approved": 1}

    with patch("uk_management_bot.handlers.user_verification._units.UserVerificationService") as svc, \
         patch("uk_management_bot.handlers.user_verification._units.NotificationService") as ns, \
         patch.object(info_requests, "get_verification_main_keyboard") as kb:
        svc.return_value.get_verification_stats.return_value = stats
        ns.return_value.collect_verification_request_message.return_value = None
        await info_requests.process_request_comment(
            message, state, roles=["manager"], language="ru", _db=MagicMock(),
        )

    kb.assert_called_once()
    assert kb.call_args.args[0] == stats, (
        f"меню перерисовано с пустой статистикой: {kb.call_args.args[0]!r}"
    )


# ── 4: caption без русского хардкода ────────────────────────────────────────

async def test_download_caption_localized_for_uz():
    from uk_management_bot.handlers.user_verification import documents

    cb = _make_callback("download_document_5")
    db = _db_single_doc(_make_doc(created_at=datetime(2026, 1, 2, 9, 30)))

    await documents.download_user_document(cb, roles=["manager"], language="uz", _db=db)

    cb.bot.send_document.assert_awaited_once()
    caption = cb.bot.send_document.await_args.kwargs["caption"]
    assert "Загружен" not in caption, f"русский хардкод в uz-caption: {caption!r}"
    assert get_text("user_verification.handlers.uploaded_date", language="uz") in caption
