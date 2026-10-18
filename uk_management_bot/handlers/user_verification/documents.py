"""Документы пользователя: запрос доп. информации, просмотр, скачивание.

AUD5-ARCH-3 (волна 11): перенос 1:1 из handlers/user_verification.py.
"""

import html
import logging

from aiogram import F
from aiogram.types import CallbackQuery

from uk_management_bot.database.session import run_db
from uk_management_bot.keyboards.user_verification import (
    get_verification_request_keyboard,
    get_cancel_keyboard
)
from uk_management_bot.database.models.user_verification import (
    VerificationStatus
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.authz import has_action_roles

from ._router import router
from ._units import _fmt_created_at, _load_documents_page

logger = logging.getLogger(__name__)

# ═══ ЗАПРОС ДОПОЛНИТЕЛЬНОЙ ИНФОРМАЦИИ ═══

@router.callback_query(F.data.startswith("verification_request_"))
async def request_additional_info(callback: CallbackQuery, roles: list = None, language: str = "ru"):
    """Запросить дополнительную информацию от пользователя"""
    lang = language
    user_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not has_action_roles(roles, "admin_panel.use"):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        # Переходим в состояние запроса информации
        await callback.message.edit_text(
            get_text('verification.request_info_title', language=lang),
            reply_markup=get_verification_request_keyboard(user_id, lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка запроса дополнительной информации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )

# ═══ ПРОСМОТР ДОКУМЕНТОВ ПОЛЬЗОВАТЕЛЯ ═══

@router.callback_query(F.data.startswith("view_user_documents_"))
async def view_user_documents(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Показать документы пользователя"""
    lang = language
    user_id = int(callback.data.split("_")[3])

    # Проверяем права доступа
    if not roles or not has_action_roles(roles, "admin_panel.use"):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        page = await run_db(lambda s: _load_documents_page(s, user_id), db=_db)
        if page is None:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        (first_name, username), documents = page

        unknown_name = get_text("user_verification.handlers.unknown", language=lang)
        user_display_name = html.escape(first_name or username or unknown_name)

        if not documents:
            await callback.message.edit_text(
                get_text("user_verification.handlers.user_documents_title", language=lang).format(name=user_display_name) + "\n\n" +
                get_text("user_verification.handlers.documents_not_loaded", language=lang),
                reply_markup=get_cancel_keyboard(lang)
            )
            await callback.answer()
            return

        # Формируем список документов
        documents_text = get_text("user_verification.handlers.user_documents_title", language=lang).format(name=user_display_name) + "\n\n"

        for i, doc in enumerate(documents, 1):
            status_emoji = "✅" if doc.status == VerificationStatus.APPROVED else "⏳" if doc.status == VerificationStatus.PENDING else "❌"
            doc_type_name = get_text(f'verification.document_types.{doc.type_value}', language=lang)

            documents_text += f"{i}. {status_emoji} <b>{doc_type_name}</b>\n"
            documents_text += f"   📁 {get_text('user_verification.handlers.file_label', language=lang)}: {html.escape(doc.file_name) if doc.file_name else get_text('user_verification.handlers.no_title', language=lang)}\n"
            if doc.file_size:
                documents_text += f"   📏 {get_text('user_verification.handlers.size_label', language=lang)}: {doc.file_size // 1024} KB\n"
            documents_text += f"   📅 {get_text('user_verification.handlers.uploaded_date', language=lang)}: {_fmt_created_at(doc.created_at)}\n"

            if doc.notes:
                documents_text += f"   📝 {get_text('user_verification.handlers.comment_label', language=lang)}: {html.escape(doc.notes)}\n"

            documents_text += "\n"

        # Добавляем кнопки для управления документами
        from uk_management_bot.keyboards.user_verification import get_document_management_keyboard
        keyboard = get_document_management_keyboard(user_id, lang)

        await callback.message.edit_text(
            documents_text,
            reply_markup=keyboard
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра документов пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )
