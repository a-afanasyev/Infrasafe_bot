"""FSM-обработка комментариев модерации и навигация.

AUD3-07/AUD5-ARCH-1 (A2-хвост, волна 7): DB-фаза каждого хендлера — цельный
sync unit-of-work под ``run_db``; наружу выходят примитивы и готовые
InlineKeyboardMarkup (``format_user_info``/``get_user_actions_keyboard``/
``get_user_management_main_keyboard`` читают ORM-строку и статистику, поэтому
живут внутри юнита). Telegram-IO вынесено из сессии; в
``process_document_request`` применён B3-раскрой «собрать текст → отправить».

Инвентарь живости: все восемь хендлеров живые. Пять FSM-состояний ставит
handlers/user_management/actions.py (approval_comment:246, block_reason:293,
unblock_comment:340, delete_reason:387, document_request:734), три callback'а
рождает keyboards/user_management.py (user_mgmt_cancel:444, user_mgmt_nop:99/115,
user_mgmt_back_to_list:248). Мёртвых нет.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.keyboards.user_management import (
    get_user_management_main_keyboard,
    get_user_actions_keyboard,
)
from uk_management_bot.keyboards.base import get_main_keyboard
from uk_management_bot.states.user_management import UserManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User

from ._router import router

logger = logging.getLogger(__name__)


# ==========================================================================
# DTO + sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке
# через run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# ==========================================================================


@dataclass(frozen=True)
class _ModerationResult:
    """Итог модерационной операции — только примитивы и готовая клавиатура."""
    success: bool
    user_name: Optional[str] = None
    user_info: Optional[str] = None
    actions_keyboard: object = None
    target_telegram_id: Optional[int] = None
    target_language: Optional[str] = None


def _user_card(db, user_mgmt_service, target_user_id: int, lang: str):
    """Общий хвост трёх модерационных юнитов: карточка пользователя."""
    target_user = user_mgmt_service.get_user_by_id(target_user_id)

    user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)

    return _ModerationResult(
        success=True,
        user_name=user_name,
        user_info=user_mgmt_service.format_user_info(target_user, lang, detailed=True),
        actions_keyboard=get_user_actions_keyboard(target_user, lang),
        target_telegram_id=target_user.telegram_id,
        target_language=target_user.language or 'ru',
    )


def _apply_approval(db, target_user_id: int, manager_id: int, comment: str, lang: str) -> _ModerationResult:
    """Одобряет пользователя. -> результат с карточкой (или success=False)."""
    # Выполняем одобрение
    auth_service = AuthService(db)
    success = auth_service.approve_user(target_user_id, manager_id, comment)

    if not success:
        return _ModerationResult(success=False)

    # Получаем обновленную информацию о пользователе
    user_mgmt_service = UserManagementService(db)
    return _user_card(db, user_mgmt_service, target_user_id, lang)


def _apply_block(db, target_user_id: int, manager_id: int, reason: str, lang: str) -> _ModerationResult:
    """Блокирует пользователя. -> результат с карточкой (или success=False)."""
    # Выполняем блокировку
    auth_service = AuthService(db)
    success = auth_service.block_user(target_user_id, manager_id, reason)

    if not success:
        return _ModerationResult(success=False)

    user_mgmt_service = UserManagementService(db)
    return _user_card(db, user_mgmt_service, target_user_id, lang)


def _apply_unblock(db, target_user_id: int, manager_id: int, comment: str, lang: str) -> _ModerationResult:
    """Разблокирует пользователя. -> результат с карточкой (или success=False)."""
    # Выполняем разблокировку
    auth_service = AuthService(db)
    success = auth_service.unblock_user(target_user_id, manager_id, comment)

    if not success:
        return _ModerationResult(success=False)

    user_mgmt_service = UserManagementService(db)
    return _user_card(db, user_mgmt_service, target_user_id, lang)


def _apply_delete(db, target_user_id: int, manager_id: int, reason: str) -> bool:
    """Удаляет пользователя. -> success."""
    # Выполняем удаление
    auth_service = AuthService(db)
    return auth_service.delete_user(target_user_id, manager_id, reason)


def _load_main_panel(db, lang: str):
    """-> готовая клавиатура главной панели (статистика читается тут же)."""
    user_mgmt_service = UserManagementService(db)
    stats = user_mgmt_service.get_user_stats()
    return get_user_management_main_keyboard(stats, lang)


@dataclass(frozen=True)
class _DocumentRequest:
    """Итог запроса документов: success + готовые тексты уведомлений."""
    success: bool
    target_telegram_id: Optional[int] = None
    user_text: Optional[str] = None
    channel_text: Optional[str] = None


def _apply_document_request(db, action: str, target_user_id: int, manager_id: int,
                            request_text: str, document_type, selected_docs) -> _DocumentRequest:
    """Запрашивает документы и СОБИРАЕТ тексты уведомлений (B3-раскрой).

    build_*_message читают ORM-строку (язык, telegram_id), поэтому текст
    рождается здесь, внутри сессии; отправка — в async-слое, вне её.
    """
    from uk_management_bot.services.user_verification_service import UserVerificationService
    from uk_management_bot.services.notification_service import (
        build_document_request_message,
        build_multiple_documents_request_message,
    )

    user_verification_service = UserVerificationService(db)

    if action == 'request_specific_document':
        # Запрос конкретного типа документа
        logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Запрос конкретного документа типа: {document_type}")
        success = user_verification_service.request_specific_document(target_user_id, manager_id, document_type, request_text)
        logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Результат запроса конкретного документа: {success}")
    elif action == 'request_multiple_documents':
        # Запрос множественных документов
        logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Запрос множественных документов: {selected_docs}")
        success = user_verification_service.request_multiple_documents(target_user_id, manager_id, selected_docs, request_text)
        logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Результат запроса множественных документов: {success}")
    else:
        # Общий запрос документов (для обратной совместимости)
        logger.info("🔍 PROCESS_DOCUMENT_REQUEST: Общий запрос документов")
        success = user_verification_service.request_additional_documents(target_user_id, manager_id, request_text)
        logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Результат общего запроса: {success}")

    if not success:
        return _DocumentRequest(success=False)

    target_user = db.query(User).filter(User.id == target_user_id).first()

    if not target_user:
        return _DocumentRequest(success=True)

    if action == 'request_multiple_documents':
        return _DocumentRequest(
            success=True,
            target_telegram_id=target_user.telegram_id,
            user_text=build_multiple_documents_request_message(target_user, request_text, selected_docs, for_channel=False),
            channel_text=build_multiple_documents_request_message(target_user, request_text, selected_docs, for_channel=True),
        )

    doc_type = document_type if action == 'request_specific_document' else None
    return _DocumentRequest(
        success=True,
        target_telegram_id=target_user.telegram_id,
        user_text=build_document_request_message(target_user, request_text, doc_type, for_channel=False),
        channel_text=build_document_request_message(target_user, request_text, doc_type, for_channel=True),
    )


def _load_user_card(db, target_user_id: int, lang: str):
    """-> (user_info, клавиатура действий) | None (пользователя нет)."""
    user_mgmt_service = UserManagementService(db)
    target_user = user_mgmt_service.get_user_by_id(target_user_id)

    if not target_user:
        return None

    return (
        user_mgmt_service.format_user_info(target_user, lang, detailed=True),
        get_user_actions_keyboard(target_user, lang),
    )


# ═══ ОБРАБОТКА КОММЕНТАРИЕВ ═══

@router.message(UserManagementStates.waiting_for_approval_comment)
async def process_approval_comment(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработать комментарий для одобрения"""
    lang = language

    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        comment = message.text

        result = await run_db(
            lambda s: _apply_approval(s, target_user_id, manager_id, comment, lang), db=_db
        )

        if result.success:
            await message.answer(
                get_text('moderation.user_approved_successfully', language=lang).format(
                    user_name=result.user_name
                )
            )

            # Отправляем обновленное главное меню пользователю
            try:

                # Создаем клавиатуру с кнопкой перезапуска
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

                # Определяем язык целевого пользователя
                target_lang = result.target_language

                restart_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text('user_mgmt.handlers.restart_bot_btn', language=target_lang), callback_data="restart_bot")]
                ])

                # Отправляем уведомление об одобрении с кнопкой перезапуска
                await message.bot.send_message(
                    chat_id=result.target_telegram_id,
                    text=get_text('user_mgmt.handlers.application_approved_restart', language=target_lang),
                    reply_markup=restart_keyboard
                )

            except Exception as e:
                logger.error(f"Ошибка отправки обновленного меню пользователю {result.target_telegram_id}: {e}")

            # Показываем детали пользователя
            await message.answer(
                result.user_info,
                reply_markup=result.actions_keyboard
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки комментария одобрения: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


@router.message(UserManagementStates.waiting_for_block_reason)
async def process_block_reason(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработать причину блокировки"""
    lang = language

    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        reason = message.text

        result = await run_db(
            lambda s: _apply_block(s, target_user_id, manager_id, reason, lang), db=_db
        )

        if result.success:
            await message.answer(
                get_text('moderation.user_blocked_successfully', language=lang).format(
                    user_name=result.user_name
                )
            )

            # Показываем обновленные детали пользователя
            await message.answer(
                result.user_info,
                reply_markup=result.actions_keyboard
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки причины блокировки: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


@router.message(UserManagementStates.waiting_for_unblock_comment)
async def process_unblock_comment(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработать комментарий для разблокировки"""
    lang = language

    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        comment = message.text

        result = await run_db(
            lambda s: _apply_unblock(s, target_user_id, manager_id, comment, lang), db=_db
        )

        if result.success:
            await message.answer(
                get_text('moderation.user_unblocked_successfully', language=lang).format(
                    user_name=result.user_name
                )
            )

            # Показываем обновленные детали пользователя
            await message.answer(
                result.user_info,
                reply_markup=result.actions_keyboard
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки комментария разблокировки: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


@router.message(UserManagementStates.waiting_for_delete_reason)
async def process_delete_reason(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработать причину удаления пользователя"""
    lang = language

    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        reason = message.text

        success = await run_db(
            lambda s: _apply_delete(s, target_user_id, manager_id, reason), db=_db
        )

        if success:
            await message.answer(
                get_text('moderation.user_deleted_successfully', language=lang)
            )

            try:
                # Возвращаемся к панели управления пользователями
                panel_keyboard = await run_db(lambda s: _load_main_panel(s, lang), db=_db)

                await message.answer(
                    get_text('user_management.main_title', language=lang),
                    reply_markup=panel_keyboard
                )
            except Exception as e:
                logger.error(f"Ошибка при возврате к панели управления пользователями после удаления: {e}")
                await message.answer(
                    get_text('moderation.user_deleted_successfully', language=lang) +
                    "\n\n" + get_text('user_mgmt.handlers.error_returning_to_panel', language=lang)
                )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки причины удаления: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


@router.message(UserManagementStates.waiting_for_document_request)
async def process_document_request(message: Message, state: FSMContext,
                                 roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Обработать запрос дополнительных документов"""
    lang = language
    
    logger.info("🔍 PROCESS_DOCUMENT_REQUEST: Начало обработки запроса документов")
    logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Пользователь: {message.from_user.id}, Текст: {message.text}")
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Права доступа: {has_access}")
    
    if not has_access:
        await message.answer(
            get_text('errors.permission_denied', language=lang),
            reply_markup=get_main_keyboard(lang)
        )
        await state.clear()
        return
    
    try:
        data = await state.get_data()
        logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Данные состояния: {data}")
        
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        request_text = message.text
        action = data.get('action', 'request_documents')
        
        logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: target_user_id={target_user_id}, manager_id={manager_id}, action={action}")
        
        document_type = data.get('document_type')
        selected_docs = data.get('selected_documents', [])

        requested = await run_db(
            lambda s: _apply_document_request(
                s, action, target_user_id, manager_id, request_text, document_type, selected_docs
            ),
            db=_db,
        )

        if requested.success:
            # Отправляем уведомление пользователю. B3-раскрой: тексты собраны
            # в юните (читают ORM-строку), сеть — здесь, вне сессии.
            # Best-effort, как и раньше в async_notify_*.
            if requested.target_telegram_id is not None:
                from uk_management_bot.services.notification_service import (
                    send_to_channel,
                    send_to_user,
                )
                # Получаем бота из контекста сообщения
                bot = message.bot

                try:
                    await send_to_user(bot, requested.target_telegram_id, requested.user_text)
                    await send_to_channel(bot, requested.channel_text)
                except Exception as e:
                    logger.warning(f"Ошибка async уведомления о запросе документов: {e}")

            await message.answer(
                get_text('moderation.document_request_sent', language=lang)
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
            await state.clear()
            return

        # Возвращаемся к деталям пользователя
        card = await run_db(lambda s: _load_user_card(s, target_user_id, lang), db=_db)

        if card is not None:
            user_info, actions_keyboard = card
            await message.answer(
                user_info,
                reply_markup=actions_keyboard
            )

        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки запроса документов: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


# ═══ ОТМЕНА ОПЕРАЦИЙ ═══

@router.callback_query(F.data == "user_mgmt_cancel")
async def cancel_user_management_operation(callback: CallbackQuery, state: FSMContext,
                                         roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Отменить текущую операцию управления пользователями"""
    lang = language

    try:
        await state.clear()

        # Возвращаемся к главному меню панели управления
        panel_keyboard = await run_db(lambda s: _load_main_panel(s, lang), db=_db)

        await callback.message.edit_text(
            get_text('user_management.main_title', language=lang),
            reply_markup=panel_keyboard
        )

        await callback.answer(
            get_text('buttons.operation_cancelled', language=lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка отмены операции: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ЗАГЛУШКИ ДЛЯ НЕАКТИВНЫХ КНОПОК ═══

@router.callback_query(F.data == "user_mgmt_nop")
async def user_management_nop(callback: CallbackQuery, language: str = "ru"):
    """Заглушка для неактивных кнопок"""
    await callback.answer()


# ═══ НАВИГАЦИЯ ═══

@router.callback_query(F.data == "user_mgmt_back_to_list")
async def back_to_user_list(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Вернуться к списку пользователей"""
    lang = language

    try:
        # Очищаем состояние
        await state.clear()

        # Возвращаемся к главному меню панели управления
        panel_keyboard = await run_db(lambda s: _load_main_panel(s, lang), db=_db)

        await callback.message.edit_text(
            get_text('user_management.main_title', language=lang),
            reply_markup=panel_keyboard
        )

        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к списку: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


