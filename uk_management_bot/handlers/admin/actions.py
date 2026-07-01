"""Менеджер: приёмка/отклонение/уточнение/закуп/выполнение/удаление заявок."""
from aiogram import F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.keyboards.admin import (
    get_manager_main_keyboard,
    get_assignment_type_keyboard,
)
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_CANCELLED,
)

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import has_admin_access
from datetime import datetime, timezone

from ._router import router

from .shared import (
    _ACCEPT_REQUEST_NUMBER_RE,
    _PURCHASE_REQUEST_NUMBER_RE,
    ManagerStates,
)

from .lists import _render_manager_request_list

logger = logging.getLogger(__name__)


# ===== ОБРАБОТЧИКИ ДЕЙСТВИЙ С ЗАЯВКАМИ ДЛЯ МЕНЕДЖЕРОВ =====

@router.callback_query(F.data.regexp(_ACCEPT_REQUEST_NUMBER_RE))
async def handle_accept_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка принятия заявки менеджером - показ выбора типа назначения"""
    try:
        lang = language
        logger.info(f"Обработка принятия заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("accept_", "")

        # Канон-переход Новая→В работе через единый layer (PR2c). Менеджер
        # «берёт» заявку без выбора исполнителя (пустой payload ⇒ status-only,
        # без assigned_*/assignment-строки); назначение — отдельным шагом ниже.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        try:
            run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                ActionCommand(callback.id, Action.MANAGER_ASSIGN, {}),
            )
        except RequestNotFound:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return
        except WorkflowError as e:
            logger.info(f"MANAGER_ASSIGN (accept) отклонён для {request_number}: {e}")
            await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)
            return

        # run_command работал в своей сессии → перечитываем свежей для отрисовки.
        svc = AdminHandlerService(db)
        svc.expire_all()
        request = svc.get_request_by_number(request_number)
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Показываем выбор типа назначения
        await callback.message.edit_text(
            get_text("admin.handlers.request_accepted_choose_assignment", language=lang).format(
                request_number=request_number,
                category=get_category_display(resolve_category_key(request.category), language=lang),
                address=request.address
            ),
            reply_markup=get_assignment_type_keyboard(request_number),
            parse_mode="HTML"
        )

        logger.info(f"Заявка {request_number} принята менеджером {callback.from_user.id}, ожидание выбора типа назначения")

    except Exception as e:
        logger.error(f"Ошибка обработки принятия заявки менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("mgr_deny_"))
async def handle_deny_request(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка отклонения заявки менеджером"""
    try:
        lang = language
        logger.info(f"Обработка отклонения заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("mgr_deny_", "")

        # Получаем заявку
        request = AdminHandlerService(db).get_request_by_number(request_number)
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Запрашиваем причину отклонения
        await callback.message.edit_text(
            get_text("admin.handlers.deny_request_prompt", language=lang).format(
                request_number=request_number,
                category=get_category_display(resolve_category_key(request.category), language=lang),
                address=request.address
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_text("admin.handlers.btn_cancel", language=lang), callback_data=f"view_{request_number}")]
            ])
        )

        # Сохраняем номер заявки в состоянии для отклонения
        await state.update_data(deny_request_number=request_number)
        
        # Устанавливаем состояние ожидания причины отклонения
        await state.set_state(ManagerStates.cancel_reason)
        
        logger.info(f"Запрошена причина отклонения заявки {request_number} менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки отклонения заявки менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("clarify_"))
async def handle_clarify_request(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка запроса уточнения по заявке"""
    try:
        lang = language
        logger.info(f"Обработка запроса уточнения по заявке менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("clarify_", "")

        # Получаем заявку
        request = AdminHandlerService(db).get_request_by_number(request_number)
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем, что заявка не отменена
        if request.status == REQUEST_STATUS_CANCELLED:
            await callback.answer(get_text("admin.handlers.cannot_clarify_cancelled", language=lang), show_alert=True)
            return
        
        # Сохраняем номер заявки в состоянии
        await state.update_data(request_number=request_number)
        
        # Запрашиваем текст уточнения
        await callback.message.edit_text(
            get_text("admin.handlers.clarify_prompt", language=lang).format(
                request_number=request_number,
                category=get_category_display(resolve_category_key(request.category), language=lang),
                address=request.address
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_clarification")]
            ])
        )
        
        # Устанавливаем состояние ожидания текста уточнения
        await state.set_state(ManagerStates.waiting_for_clarification_text)
        
        logger.info(f"Запрошен текст уточнения для заявки {request_number} менеджером {callback.from_user.id}")
        
    except Exception as e:
        # BUG-BOT-022: ранее логировалось без stack-trace, что затрудняло диагностику.
        logger.error(f"Ошибка обработки запроса уточнения: {e}", exc_info=True)
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "cancel_clarification")
async def handle_cancel_clarification(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Отмена уточнения.

    BUG-BOT-035: раньше звался `handle_manager_back_to_list`, который безусловно
    парсил `mreq_back_` из callback.data == "cancel_clarification" → IndexError.
    Теперь: явный guard прав, request_number берём из FSM до clear(), рендер
    списка через render-only helper.
    """
    lang = language

    # Guard прав явно (у cancel-callback своей проверки не было)
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
        return

    try:
        data = await state.get_data()
        request_number = data.get("request_number")
        await state.clear()

        await _render_manager_request_list(callback, db, request_number, lang)
        await callback.answer(get_text("admin.handlers.clarification_cancelled", language=lang))

    except Exception as e:
        logger.error(f"Ошибка отмены уточнения: {e}", exc_info=True)
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.regexp(_PURCHASE_REQUEST_NUMBER_RE))
async def handle_purchase_request(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка перевода заявки в статус 'Закуп' менеджером"""
    try:
        lang = language
        logger.info(f"Обработка перевода заявки в закуп менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("purchase_", "")

        # Получаем заявку
        request = AdminHandlerService(db).get_request_by_number(request_number)
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Формируем текст с учетом истории закупок
        prompt_text = get_text("admin.handlers.purchase_transfer_header", language=lang) + "\n\n"

        # Проверяем, есть ли история предыдущих закупок
        if request.purchase_history:
            prompt_text += get_text("admin.handlers.purchase_history_found", language=lang) + "\n"

            # Показываем последние данные из истории
            history_lines = request.purchase_history.split('\n')
            last_requested = None
            last_comment = None

            for i in range(len(history_lines) - 1, -1, -1):
                line = history_lines[i].strip()
                if line.startswith("Запрошенные материалы:") and not last_requested:
                    last_requested = line.replace("Запрошенные материалы:", "").strip()
                elif line.startswith("Комментарий менеджера:") and not last_comment:
                    last_comment = line.replace("Комментарий менеджера:", "").strip()

                if last_requested and last_comment:
                    break

            not_specified = get_text("admin.handlers.not_specified", language=lang)
            no_comments = get_text("admin.handlers.no_comments", language=lang)
            if last_requested and last_requested != "Не указано" and last_requested != not_specified:
                prompt_text += get_text("admin.handlers.purchase_last_materials", language=lang).format(materials=last_requested) + "\n"
            if last_comment and last_comment != "Без комментариев" and last_comment != no_comments:
                prompt_text += get_text("admin.handlers.purchase_last_comment", language=lang).format(comment=last_comment) + "\n"

            prompt_text += "\n"

        prompt_text += get_text("admin.handlers.purchase_enter_materials", language=lang)
        
        # Запрашиваем список материалов
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        await callback.message.edit_text(
            prompt_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_text("admin.handlers.btn_cancel", language=lang), callback_data=f"view_{request_number}")]
            ])
        )

        # Сохраняем состояние
        from uk_management_bot.states.request_status import RequestStatusStates
        
        # Получаем контекст состояния
        try:
            await state.update_data(
                request_number=request_number,
                action="purchase_materials_admin"
            )
            await state.set_state(RequestStatusStates.waiting_for_materials)
        except Exception as e:
            logger.error(f"Ошибка установки состояния: {e}")
            await callback.answer(get_text("admin.handlers.error_processing", language=lang), show_alert=True)

        await callback.answer()

        logger.info(f"Заявка {request_number} переведена в закуп менеджером {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки перевода в закуп менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("mgr_complete_"))
async def handle_complete_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Завершение заявки менеджером (канон PR2a-7: MANAGER_COMPLETE → Выполнена).

    Менеджерский shortcut-аналог EXECUTOR_COMPLETE: единый layer владеет
    транзакцией (status→Выполнена, is_returned=False, audit, webhook). Допустим
    из В работе/Закуп/Уточнение; из прочих статусов run_command отклонит.
    """
    try:
        lang = language
        logger.info(f"Обработка завершения заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("mgr_complete_", "")

        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, NotAuthorized, WorkflowError)
        try:
            run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=(user.id if user else None),
                             source="telegram"),
                ActionCommand(
                    f"mgr-complete-{request_number}",
                    Action.MANAGER_COMPLETE, {},
                ),
            )
        except RequestNotFound:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return
        except NotAuthorized:
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return
        except WorkflowError as e:
            logger.info(f"MANAGER_COMPLETE отклонён для {request_number}: {e}")
            await callback.answer(get_text("admin.handlers.cannot_complete_status", language=lang), show_alert=True)
            return

        await callback.answer(get_text("admin.handlers.request_marked_completed", language=lang))

        # run_command коммитит в отдельной сессии — сбрасываем кэш middleware-сессии
        # перед перечитыванием списка заявок. BUG-BOT-035: рендер списка через
        # render-only helper с request_number; ошибка рендера после уже отправленного
        # success-answer только логируется (без повторного callback.answer).
        db.expire_all()
        try:
            await _render_manager_request_list(callback, db, request_number, lang)
        except Exception as render_err:
            logger.error(f"Ошибка ре-рендера списка после завершения {request_number}: {render_err}", exc_info=True)

        logger.info(f"Заявка {request_number} отмечена как выполненная менеджером {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки завершения заявки менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("mgr_delete_"))
async def handle_delete_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка удаления заявки администратором (только для админов!)"""
    try:
        lang = language
        logger.info(f"Попытка удаления заявки пользователем {callback.from_user.id}")

        # Проверяем права доступа - ТОЛЬКО АДМИНИСТРАТОРЫ могут удалять заявки
        import os
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]

        if callback.from_user.id not in admin_ids:
            await callback.answer(get_text("admin.handlers.delete_admin_only", language=lang), show_alert=True)
            logger.warning(f"Пользователь {callback.from_user.id} попытался удалить заявку без прав администратора")
            return
        
        request_number = callback.data.replace("mgr_delete_", "")

        svc = AdminHandlerService(db)
        # Получаем заявку
        request = svc.get_request_by_number(request_number)
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Каскадное удаление связанных записей + самой заявки (один commit)
        svc.delete_request_cascade(request, request_number)

        await callback.answer(get_text("admin.handlers.request_deleted", language=lang))

        # Возвращаемся к списку заявок. BUG-BOT-035: render-only helper с
        # request_number (заявка удалена → helper покажет активные по fallback);
        # ошибка рендера после success-answer только логируется.
        try:
            await _render_manager_request_list(callback, db, request_number, lang)
        except Exception as render_err:
            logger.error(f"Ошибка ре-рендера списка после удаления {request_number}: {render_err}", exc_info=True)

        logger.info(f"Заявка {request_number} удалена менеджером {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки удаления заявки менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.message(ManagerStates.waiting_for_clarification_text)
async def handle_clarification_text(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка текста уточнения от менеджера"""
    try:
        lang = language
        logger.info(f"Получен текст уточнения от менеджера {message.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await message.answer(get_text("admin.handlers.no_access_actions", language=lang))
            await state.clear()
            return

        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        if not request_number:
            await message.answer(get_text("admin.handlers.error_request_not_found_state", language=lang))
            await state.clear()
            return

        svc = AdminHandlerService(db)
        # Получаем заявку
        request = svc.get_request_by_number(request_number)
        if not request:
            await message.answer(get_text("admin.handlers.request_not_found", language=lang))
            await state.clear()
            return

        # Получаем текст уточнения
        clarification_text = message.text.strip()
        
        if not clarification_text:
            await message.answer(get_text("admin.handlers.clarification_empty", language=lang))
            return
        
        # Формируем имя менеджера
        manager_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not manager_name:
            manager_name = get_text("admin.handlers.manager_by_id", language=lang).format(telegram_id=user.telegram_id)

        # Формируем форматированное примечание уточнения
        timestamp = datetime.now().strftime('%d.%m.%Y %H:%M')
        new_note = get_text("admin.handlers.clarification_note_header", language=lang).format(timestamp=timestamp) + "\n"
        new_note += f"👨‍💼 {manager_name}:\n"
        new_note += f"{clarification_text}"

        # Каноническая проводка (PR2a-7): из Новая/В работе уточнение —
        # переход CLARIFY_REQUEST через единый layer (status→Уточнение, notes
        # APPEND, audit, webhook в одной транзакции). Из прочих статусов
        # канон-ребра нет — дописываем только примечание, статус не трогаем
        # (раньше он ошибочно сбрасывался в «Уточнение», затирая Закуп/возврат).
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, NotAuthorized, WorkflowError)
        if request.status in (REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS):
            from uk_management_bot.database.session import SessionLocal
            from uk_management_bot.services.workflow_runner import (
                run_command_sync, RequestNotFound)
            try:
                run_command_sync(
                    SessionLocal, request_number,
                    PrincipalRef(kind="user", user_id=(user.id if user else None),
                                 source="telegram"),
                    ActionCommand(
                        f"clarify-{request_number}",
                        Action.CLARIFY_REQUEST,
                        {"question": clarification_text, "notes": "\n\n" + new_note},
                    ),
                )
            except RequestNotFound:
                await message.answer(get_text("admin.handlers.request_not_found", language=lang))
                await state.clear()
                return
            except NotAuthorized:
                await message.answer(get_text("admin.handlers.no_access_actions", language=lang))
                await state.clear()
                return
            except WorkflowError as e:
                logger.info(f"CLARIFY_REQUEST отклонён для {request_number}: {e}")
                await message.answer(get_text("admin.handlers.error_sending_clarification", language=lang))
                await state.clear()
                return
            # run_command коммитит в отдельной сессии — сбрасываем кэш middleware
            svc.expire_all()
        else:
            # вне канон-перехода: дописываем только примечание, статус не меняем
            svc.append_clarification_note(
                request, new_note, datetime.now(timezone.utc)
            )


        # Отправляем уведомление заявителю
        try:
            from uk_management_bot.services.notification_service import send_to_user

            # Получаем telegram_id пользователя
            user_obj = svc.get_user_by_id(request.user_id)
            if user_obj and user_obj.telegram_id:
                notification_text = get_text("admin.handlers.notify_user_clarification", language=lang).format(
                    request_number=request.request_number,
                    category=get_category_display(resolve_category_key(request.category), language=lang),
                    address=request.address,
                    clarification_text=clarification_text
                )
                
                # Получаем bot из состояния
                bot = message.bot
                await send_to_user(bot, user_obj.telegram_id, notification_text)
            
            logger.info(f"Уведомление об уточнении отправлено пользователю {request.user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об уточнении: {e}")
        
        # Подтверждаем менеджеру
        await message.answer(
            get_text("admin.handlers.clarification_sent", language=lang).format(
                request_number=request.request_number,
                text_preview=clarification_text[:100] + ('...' if len(clarification_text) > 100 else '')
            )
        )
        
        # Очищаем состояние
        await state.clear()
        
        logger.info(f"Уточнение по заявке {request_number} добавлено менеджером {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки текста уточнения: {e}")
        await message.answer(get_text("admin.handlers.error_sending_clarification", language=lang))
        await state.clear()


@router.message(ManagerStates.cancel_reason)
async def handle_cancel_reason_text(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка причины отклонения заявки"""
    try:
        lang = language
        logger.info(f"Получена причина отклонения от менеджера {message.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await message.answer(get_text("admin.handlers.no_access_actions", language=lang))
            await state.clear()
            return

        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("deny_request_number")

        if not request_number:
            await message.answer(get_text("admin.handlers.error_request_not_found_state", language=lang))
            await state.clear()
            return

        # Получаем заявку
        request = AdminHandlerService(db).get_request_by_number(request_number)
        if not request:
            await message.answer(get_text("admin.handlers.request_not_found", language=lang))
            await state.clear()
            return

        # Получаем причину отклонения
        cancel_reason = message.text.strip()
        
        if not cancel_reason:
            await message.answer(get_text("admin.handlers.cancel_reason_empty", language=lang))
            return
        
        # Формируем имя менеджера
        manager_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not manager_name:
            manager_name = get_text("admin.handlers.manager_by_id", language=lang).format(telegram_id=user.telegram_id)

        # Каноническая отмена (PR2a-6): CANCEL через единый layer. Причина →
        # audit (reason); форматированное примечание дописывается в notes
        # (Op.APPEND) внутри run_command.
        cancel_note = get_text("admin.handlers.cancel_note_text", language=lang).format(
            manager_name=manager_name,
            cancel_date=datetime.now().strftime('%d.%m.%Y %H:%M'),
            cancel_reason=cancel_reason
        )
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        try:
            run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=(user.id if user else None),
                             source="telegram"),
                ActionCommand(
                    f"cancel-{request_number}",
                    Action.CANCEL,
                    {"reason": cancel_reason, "notes": "\n\n" + cancel_note},
                ),
            )
        except RequestNotFound:
            await message.answer(get_text("admin.handlers.request_not_found", language=lang))
            await state.clear()
            return
        except WorkflowError as e:
            logger.info(f"CANCEL отклонён для {request_number}: {e}")
            await message.answer(get_text("admin.handlers.error_denying_request", language=lang))
            await state.clear()
            return

        await message.answer(
            get_text("admin.handlers.request_denied", language=lang).format(
                request_number=request_number,
                cancel_reason=cancel_reason
            ),
            reply_markup=get_manager_main_keyboard(language=lang)
        )

        # Очищаем состояние
        await state.clear()

        logger.info(f"Заявка {request_number} отклонена менеджером {message.from_user.id} с причиной: {cancel_reason}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки причины отклонения: {e}")
        await message.answer(get_text("admin.handlers.error_denying_request", language=lang))
        await state.clear()


