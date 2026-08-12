"""Панель верификации: главное меню и карточка пользователя.

AUD5-ARCH-3 (волна 11): перенос 1:1 из handlers/user_verification.py.
"""

import logging

from aiogram import F
from aiogram.types import CallbackQuery

from uk_management_bot.database.session import run_db
from uk_management_bot.keyboards.user_verification import (
    get_verification_main_keyboard,
    get_user_verification_keyboard,
)
from uk_management_bot.database.models.user_verification import (
    VerificationStatus
)
from uk_management_bot.utils.helpers import get_text

from ._router import router
from ._units import _load_user_card, _load_verification_stats

logger = logging.getLogger(__name__)

# ═══ ГЛАВНОЕ МЕНЮ ВЕРИФИКАЦИИ ═══

@router.callback_query(F.data == "user_verification_panel")
async def show_verification_panel(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Показать панель верификации пользователей"""
    lang = language

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        # Получаем статистику верификации
        stats = await run_db(_load_verification_stats, db=_db)

        # Показываем главное меню
        await callback.message.edit_text(
            get_text('verification.main_title', language=lang),
            reply_markup=get_verification_main_keyboard(stats, lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка отображения панели верификации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ УПРАВЛЕНИЕ ВЕРИФИКАЦИЕЙ ПОЛЬЗОВАТЕЛЕЙ ═══

@router.callback_query(F.data.startswith("verification_user_"))
async def show_user_verification(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Показать информацию о верификации пользователя"""
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
        card = await run_db(lambda s: _load_user_card(s, user_id, lang), db=_db)
        if card is None:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return

        # Формируем информацию о пользователе
        not_specified = get_text("user_verification.handlers.not_specified", language=lang)
        user_info = get_text("user_verification.handlers.user_info_header", language=lang).format(
            first_name=card.first_name or not_specified,
            last_name=card.last_name or not_specified,
            username=card.username or not_specified,
            phone=card.phone or not_specified
        )

        # ОБНОВЛЕНО: Используем новую систему квартир
        if card.has_apartment_links:
            if card.approved_apartments:
                user_info += "\n"
                for apt in card.approved_apartments:
                    primary_marker = " ⭐" if apt.is_primary else ""
                    owner_marker = " (" + get_text("user_verification.handlers.owner", language=lang) + ")" if apt.is_owner else ""
                    user_info += f"• {apt.address}{primary_marker}{owner_marker}\n"
            else:
                user_info += "\n• " + get_text("user_verification.handlers.addresses_pending", language=lang) + "\n"
        else:
            user_info += "\n• " + get_text("user_verification.handlers.addresses_not_specified", language=lang) + "\n"

        verification_status = get_text(f'verification.status.{card.verification_status}', language=lang)
        user_info += "\n\n📋 <b>" + get_text("user_verification.handlers.verification_status_label", language=lang) + ":</b> " + verification_status

        if card.verification_notes:
            user_info += "\n📝 <b>" + get_text("user_verification.handlers.comments_label", language=lang) + ":</b> " + card.verification_notes

        # Добавляем информацию о документах
        if card.documents:
            user_info += "\n\n📄 <b>" + get_text("user_verification.handlers.documents_count", language=lang).format(count=len(card.documents)) + ":</b>"
            for doc in card.documents:
                status_emoji = "✅" if doc.status == VerificationStatus.APPROVED else "⏳" if doc.status == VerificationStatus.PENDING else "❌"
                doc_type_name = get_text(f'verification.document_types.{doc.type_value}', language=lang)
                user_info += f"\n{status_emoji} {doc_type_name}"
        else:
            user_info += "\n\n📄 <b>" + get_text("user_verification.handlers.documents_label", language=lang) + ":</b> " + get_text("user_verification.handlers.not_uploaded", language=lang)

        # Добавляем информацию о правах доступа
        if card.access_rights:
            user_info += "\n\n🔑 <b>" + get_text("user_verification.handlers.access_rights_count", language=lang).format(count=len(card.access_rights)) + ":</b>"
            for right in card.access_rights:
                user_info += f"\n• {right.level_value}"
                if right.apartment_number:
                    user_info += f" ({get_text('user_verification.handlers.apt_short', language=lang)} {right.apartment_number})"
                elif right.house_number:
                    user_info += f" ({get_text('user_verification.handlers.house_short', language=lang)} {right.house_number})"
                elif right.yard_name:
                    user_info += f" ({get_text('user_verification.handlers.yard_short', language=lang)} {right.yard_name})"

        await callback.message.edit_text(
            user_info,
            reply_markup=get_user_verification_keyboard(user_id, lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка отображения верификации пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )

