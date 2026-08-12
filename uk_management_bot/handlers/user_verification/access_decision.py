"""Права доступа и решение по верификации: одобрение/отклонение пользователя.

AUD5-ARCH-3 (волна 11): перенос 1:1 из handlers/user_verification.py.
"""

import logging

from aiogram import F
from aiogram.types import CallbackQuery

from uk_management_bot.database.session import run_db
from uk_management_bot.services.user_verification_service import (
    cleanup_user_documents_media,
)
from uk_management_bot.utils.telegram_client import SEND_TIMEOUT
from uk_management_bot.keyboards.user_verification import (
    get_access_rights_keyboard
)
from uk_management_bot.utils.helpers import get_text

from ._router import router
from ._units import (
    _approve_user_db,
    _load_access_rights_card,
    _purge_user_documents,
    _reject_user_db,
)

logger = logging.getLogger(__name__)

# ═══ УПРАВЛЕНИЕ ПРАВАМИ ДОСТУПА ═══

@router.callback_query(F.data.startswith("access_rights_"))
async def manage_access_rights(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Управление правами доступа пользователя"""
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
        card = await run_db(lambda s: _load_access_rights_card(s, user_id), db=_db)
        if card is None:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        name, current_rights = card

        # Формируем информацию о правах доступа
        rights_info = get_text("user_verification.handlers.access_rights_title", language=lang).format(
            name=name,
            count=len(current_rights)
        )

        if current_rights:
            for right in current_rights:
                rights_info += f"• {right.level_value}"
                if right.apartment_number:
                    rights_info += f" ({get_text('user_verification.handlers.apt_short', language=lang)} {right.apartment_number})"
                elif right.house_number:
                    rights_info += f" ({get_text('user_verification.handlers.house_short', language=lang)} {right.house_number})"
                elif right.yard_name:
                    rights_info += f" ({get_text('user_verification.handlers.yard_short', language=lang)} {right.yard_name})"
                rights_info += "\n"
        else:
            rights_info += "• " + get_text("user_verification.handlers.no_access_rights", language=lang) + "\n"

        await callback.message.edit_text(
            rights_info,
            reply_markup=get_access_rights_keyboard(user_id, lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка управления правами доступа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ОДОБРЕНИЕ/ОТКЛОНЕНИЕ ВЕРИФИКАЦИИ ═══

@router.callback_query(F.data.startswith("verify_approve_"))
async def approve_user_verification(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Одобрить верификацию пользователя"""
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
        admin_id = callback.from_user.id
        # DB-фазы (статусы + квартиры + fetch уведомлений) — в потоке; сеть ниже.
        success, telegram_id, notify_pair, restart_target = await run_db(
            lambda s: _approve_user_db(s, user_id, admin_id), db=_db
        )

        if success:
            # Зачистка документов в Media Service (сеть, best-effort) и затем
            # удаление записей о документах — порядок 1:1 с историческим
            # approve_verification.
            await cleanup_user_documents_media(telegram_id)
            await run_db(lambda s: _purge_user_documents(s, user_id), db=_db)

            # Отправляем уведомление пользователю (best-effort, как в
            # send_verification_approved_notification)
            if notify_pair is not None:
                notify_tg, notify_text = notify_pair
                try:
                    await callback.bot.send_message(notify_tg, notify_text, request_timeout=SEND_TIMEOUT)
                    logger.info(f"Уведомление об одобрении верификации отправлено пользователю {user_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления об одобрении верификации: {e}")

            # Отправляем обновленное главное меню пользователю
            try:
                if restart_target is not None:
                    target_tg, target_lang = restart_target
                    # Создаем клавиатуру с кнопкой перезапуска
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    restart_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("user_verification.handlers.btn_restart_bot", language=target_lang), callback_data="restart_bot")]
                    ])

                    # Отправляем уведомление об одобрении с кнопкой перезапуска
                    await callback.bot.send_message(
                        chat_id=target_tg,
                        text=get_text("user_verification.handlers.application_approved_notification", language=target_lang),
                        reply_markup=restart_keyboard
                    )

            except Exception as e:
                logger.error(f"Ошибка отправки обновленного меню пользователю {user_id}: {e}")

            await callback.answer(
                get_text('verification.user_approved', language=lang),
                show_alert=True
            )
        else:
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка одобрения верификации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("verify_reject_"))
async def reject_user_verification(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Отклонить верификацию пользователя"""
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
        admin_id = callback.from_user.id
        reject_notes = get_text("user_verification.handlers.verification_rejected_by_admin", language=lang)
        success, notify_pair = await run_db(
            lambda s: _reject_user_db(s, user_id, admin_id, reject_notes), db=_db
        )

        if success:
            # Отправляем уведомление пользователю (best-effort, как в
            # send_verification_rejected_notification)
            if notify_pair is not None:
                notify_tg, notify_text = notify_pair
                try:
                    await callback.bot.send_message(notify_tg, notify_text, request_timeout=SEND_TIMEOUT)
                    logger.info(f"Уведомление об отклонении верификации отправлено пользователю {user_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления об отклонении верификации: {e}")

            await callback.answer(
                get_text('verification.user_rejected', language=lang),
                show_alert=True
            )
        else:
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка отклонения верификации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )

