"""Проверка документов: карточка документа, одобрение, отклонение.

AUD5-ARCH-3 (волна 11): перенос 1:1 из handlers/user_verification.py.
"""

import logging

from aiogram import F
from aiogram.types import CallbackQuery

from uk_management_bot.database.session import run_db
from uk_management_bot.keyboards.user_verification import (
    get_document_verification_keyboard
)
from uk_management_bot.database.models.user_verification import (
    VerificationStatus
)
from uk_management_bot.utils.helpers import get_text

from ._router import router
from ._units import _fmt_created_at, _load_document, _verify_document

logger = logging.getLogger(__name__)

# ═══ УПРАВЛЕНИЕ ДОКУМЕНТАМИ ═══

@router.callback_query(F.data.startswith("document_verify_"))
async def verify_document(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Проверить документ пользователя"""
    lang = language
    document_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        document = await run_db(lambda s: _load_document(s, document_id), db=_db)
        if document is None:
            await callback.answer(
                get_text('errors.document_not_found', language=lang),
                show_alert=True
            )
            return

        # Показываем информацию о документе
        doc_size = str(document.file_size) if document.file_size else get_text("user_verification.handlers.unknown_value", language=lang)
        doc_status = get_text(f'verification.document_status.{document.status.value}', language=lang)
        # BUG-144: тип локализуем (как в documents.py/panel.py), created_at — NULL-safe.
        document_info = get_text("user_verification.handlers.document_info", language=lang).format(
            doc_type=get_text(f'verification.document_types.{document.type_value}', language=lang),
            uploaded=_fmt_created_at(document.created_at),
            size=doc_size,
            status=doc_status
        )

        if document.notes:
            document_info += "\n📝 <b>" + get_text("user_verification.handlers.comments_label", language=lang) + ":</b> " + document.notes

        await callback.message.edit_text(
            document_info,
            reply_markup=get_document_verification_keyboard(document_id, lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка проверки документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("document_approve_"))
async def approve_document(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Одобрить документ"""
    lang = language
    document_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        admin_id = callback.from_user.id
        success = await run_db(
            lambda s: _verify_document(s, document_id, admin_id, VerificationStatus.APPROVED),
            db=_db,
        )

        if success:
            await callback.answer(
                get_text('verification.document_approved', language=lang),
                show_alert=True
            )
        else:
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка одобрения документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("document_reject_"))
async def reject_document(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Отклонить документ"""
    lang = language
    document_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        admin_id = callback.from_user.id
        reject_notes = get_text("user_verification.handlers.document_rejected_by_admin", language=lang)
        success = await run_db(
            lambda s: _verify_document(
                s, document_id, admin_id, VerificationStatus.REJECTED, notes=reject_notes
            ),
            db=_db,
        )

        if success:
            await callback.answer(
                get_text('verification.document_rejected', language=lang),
                show_alert=True
            )
        else:
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка отклонения документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )

