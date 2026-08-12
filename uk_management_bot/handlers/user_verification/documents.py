"""Документы пользователя: запрос доп. информации, просмотр, скачивание.

AUD5-ARCH-3 (волна 11): перенос 1:1 из handlers/user_verification.py.
"""

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

from ._router import router
from ._units import _load_document, _load_documents_page

logger = logging.getLogger(__name__)

# ═══ ЗАПРОС ДОПОЛНИТЕЛЬНОЙ ИНФОРМАЦИИ ═══

@router.callback_query(F.data.startswith("verification_request_"))
async def request_additional_info(callback: CallbackQuery, roles: list = None, language: str = "ru"):
    """Запросить дополнительную информацию от пользователя"""
    lang = language
    user_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
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
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
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
        user_display_name = first_name or username or unknown_name

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
            documents_text += f"   📁 {get_text('user_verification.handlers.file_label', language=lang)}: {doc.file_name or get_text('user_verification.handlers.no_title', language=lang)}\n"
            if doc.file_size:
                documents_text += f"   📏 {get_text('user_verification.handlers.size_label', language=lang)}: {doc.file_size // 1024} KB\n"
            documents_text += f"   📅 {get_text('user_verification.handlers.uploaded_date', language=lang)}: {doc.created_at.strftime('%d.%m.%Y %H:%M')}\n"

            if doc.notes:
                documents_text += f"   📝 {get_text('user_verification.handlers.comment_label', language=lang)}: {doc.notes}\n"

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

@router.callback_query(F.data.startswith("download_document_"))
async def download_user_document(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Скачать документ пользователя"""
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
        document = await run_db(
            lambda s: _load_document(s, document_id, with_file=True), db=_db
        )
        if document is None:
            await callback.answer(
                get_text("user_verification.handlers.document_not_found", language=lang),
                show_alert=True
            )
            return

        # Отправляем файл
        bot = callback.bot

        try:
            caption = (f"📄 {get_text(f'verification.document_types.{document.type_value}', language=lang)}\n"
                      f"📅 Загружен: {document.created_at.strftime('%d.%m.%Y %H:%M')}")

            # Пробуем отправить как документ, если не получится - как фото
            try:
                await bot.send_document(
                    chat_id=callback.from_user.id,
                    document=document.file_id,
                    caption=caption
                )
                await callback.answer(get_text("user_verification.handlers.document_sent_dm", language=lang))
            except Exception as doc_error:
                # Если ошибка "can't use file of type Photo", отправляем как фото
                if "can't use file of type Photo" in str(doc_error):
                    logger.info(f"Файл {document.file_id} является фото, отправляем как photo")
                    await bot.send_photo(
                        chat_id=callback.from_user.id,
                        photo=document.file_id,
                        caption=caption
                    )
                    await callback.answer(get_text("user_verification.handlers.document_sent_dm", language=lang))
                else:
                    raise  # Пробрасываем другие ошибки
        except Exception as e:
            logger.error(f"Ошибка отправки документа: {e}")
            await callback.answer(get_text("user_verification.handlers.error_sending_document", language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка скачивания документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )

