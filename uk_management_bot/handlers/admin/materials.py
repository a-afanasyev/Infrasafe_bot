"""Менеджер: смены-кнопка, возврат в работу, редактирование материалов."""
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.keyboards.admin import (
    get_manager_main_keyboard,
)
from uk_management_bot.keyboards.base import get_user_contextual_keyboard
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_PURCHASE,
)

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import has_admin_access
from datetime import datetime, timezone

from ._router import router

from .shared import (
    ADMIN_SHIFTS_TEXTS,
    ManagerStates,
)

logger = logging.getLogger(__name__)


@router.message(F.text.in_(ADMIN_SHIFTS_TEXTS))
async def handle_admin_shifts_button(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработчик кнопки 'Смены' в админ панели"""
    lang = language
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("auth.no_access", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Прямой вызов интерфейса управления сменами без декоратора
    try:
        from uk_management_bot.keyboards.shift_management import get_main_shift_menu
        from uk_management_bot.states.shift_management import ShiftManagementStates
        from uk_management_bot.utils.helpers import get_user_language

        language = get_user_language(message.from_user.id, db)

        # Сначала обновляем Reply клавиатуру на главную клавиатуру менеджера
        await message.answer(
            get_text("admin.handlers.shift_management_title", language=lang),
            reply_markup=get_manager_main_keyboard(language=lang),
            parse_mode="HTML"
        )

        # Затем отправляем меню смен с inline кнопками
        await message.answer(
            get_text("admin.handlers.choose_action", language=lang),
            reply_markup=get_main_shift_menu(language),
            parse_mode="HTML"
        )

        await state.set_state(ShiftManagementStates.main_menu)
        
    except Exception as e:
        logger.error(f"Ошибка при открытии управления сменами: {e}")
        await message.answer(
            get_text("admin.handlers.shift_management_unavailable", language=lang),
            parse_mode="HTML",
            reply_markup=get_manager_main_keyboard(language=lang)
        )


@router.callback_query(F.data.startswith("purchase_return_to_work_"))
async def handle_return_to_work(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка возврата заявки из закупа в работу"""
    try:
        lang = language
        logger.info(f"Возврат заявки из закупа в работу менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return
        
        request_number = callback.data.replace("purchase_return_to_work_", "")

        svc = AdminHandlerService(db)
        # Получаем заявку
        request = svc.get_request_by_number(request_number)
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем, что заявка в статусе "Закуп" (UX-предчек; канон ре-валидирует)
        if request.status != REQUEST_STATUS_PURCHASE:
            await callback.answer(get_text("admin.handlers.request_not_in_purchase", language=lang), show_alert=True)
            return

        # PR2c: разделитель «--закуплено DATE--» в requested_materials (workflow-
        # поле канона) вычисляем ЛОКАЛЬНО и передаём в payload; purchase_history
        # (вне workflow-полей) пишем post-commit. Итог-статус Закуп→В работе —
        # канон MANAGER_PURCHASE_DONE.
        final_materials = None
        history_entry = None
        if request.requested_materials:
            current_date = datetime.now().strftime('%d.%m.%Y %H:%M')
            procurement_separator = f"--закуплено {current_date}--"
            final_materials = request.requested_materials + f"\n{procurement_separator}\n"

            manager_comment = (request.manager_materials_comment
                               or get_text("admin.handlers.no_comments", language=lang))
            materials_val = final_materials.split(f'{procurement_separator}')[0].strip()
            history_entry = (
                get_text("admin.handlers.purchase_history_completed_header", language=lang) + "\n"
                + get_text("admin.handlers.purchase_history_materials_label", language=lang).format(materials=materials_val) + "\n"
                + get_text("admin.handlers.purchase_history_comment_label", language=lang).format(comment=manager_comment) + "\n"
                + get_text("admin.handlers.purchase_history_date_label", language=lang).format(date=current_date)
            )

        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        payload = {}
        if final_materials is not None:
            payload["requested_materials"] = final_materials
        try:
            run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                ActionCommand(callback.id, Action.MANAGER_PURCHASE_DONE, payload),
            )
        except RequestNotFound:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return
        except WorkflowError as e:
            logger.info(f"MANAGER_PURCHASE_DONE отклонён для {request_number}: {e}")
            await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)
            return

        # Post-commit: purchase_history (вне workflow-полей). run_command писал
        # в своей сессии → перечитываем свежей.
        svc.expire_all()
        request = svc.get_request_by_number(request_number)
        if request is not None and history_entry is not None:
            svc.append_purchase_history(request, history_entry)

        await callback.answer(get_text("admin.handlers.request_returned_to_work_short", language=lang))

        # Загружаем обновленный список заявок в закупе
        requests = svc.list_purchase_requests(limit=10)

        if not requests:
            await callback.message.edit_text(get_text("admin.handlers.no_procurement_requests", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
            return

        # Показываем обновленный список заявок в закупе
        text = get_text("admin.handlers.procurement_updated_list", language=lang) + "\n\n"
        for i, r in enumerate(requests, 1):
            addr = r.address[:40] + ("…" if len(r.address) > 40 else "")
            text += f"{i}. #{r.request_number} - {r.category}\n"
            text += f"   📍 {addr}\n\n"
        
        await callback.message.edit_text(text, reply_markup=get_manager_main_keyboard(language=lang))
        
        logger.info(f"Заявка {request_number} возвращена в работу менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка возврата заявки из закупа в работу: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("edit_materials_"))
async def handle_edit_materials(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка редактирования списка материалов для закупа"""
    try:
        lang = language
        logger.info(f"Редактирование списка материалов менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return
        
        request_number = callback.data.replace("edit_materials_", "")

        # Получаем заявку
        request = AdminHandlerService(db).get_request_by_number(request_number)
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем, что заявка в статусе "Закуп"
        if request.status != REQUEST_STATUS_PURCHASE:
            await callback.answer(get_text("admin.handlers.request_not_in_purchase", language=lang), show_alert=True)
            return

        # Сохраняем номер заявки в состоянии
        await state.update_data(edit_materials_request_number=request_number)
        await state.set_state(ManagerStates.waiting_for_materials_edit)

        # Показываем запрошенные материалы от исполнителя и текущий комментарий менеджера
        requested = request.requested_materials or get_text("admin.handlers.not_specified", language=lang)
        manager_comment = request.manager_materials_comment or ""

        text = get_text("admin.handlers.edit_materials_prompt", language=lang).format(
            request_number=request_number,
            requested=requested
        )

        if manager_comment:
            text += get_text("admin.handlers.edit_materials_current_comment", language=lang).format(comment=manager_comment) + "\n\n"

        text += get_text("admin.handlers.edit_materials_enter", language=lang)
        
        await callback.message.answer(text)
        
        await callback.answer()
        
        logger.info(f"Начато редактирование материалов для заявки {request_number} менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка редактирования списка материалов: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.message(ManagerStates.waiting_for_materials_edit)
async def handle_materials_edit_text(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка нового текста списка материалов"""
    try:
        lang = language

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await message.answer(get_text("admin.handlers.no_access_actions", language=lang))
            await state.clear()
            return

        data = await state.get_data()
        request_number = data.get("edit_materials_request_number")

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

        # Обновляем комментарий менеджера к материалам (запрошенные материалы НЕ изменяем)
        old_comment = request.manager_materials_comment
        new_comment = message.text.strip()

        # Обновляем историю закупов для сохранения данных
        requested_materials = request.requested_materials or get_text("admin.handlers.not_specified", language=lang)
        purchase_history_entry = (
            get_text("admin.handlers.purchase_history_entry_materials", language=lang).format(materials=requested_materials) + "\n"
            + get_text("admin.handlers.purchase_history_entry_comment", language=lang).format(comment=new_comment) + "\n"
            + get_text("admin.handlers.purchase_history_entry_updated", language=lang).format(date=datetime.now().strftime('%d.%m.%Y %H:%M'))
        )

        svc.update_materials_comment(
            request, new_comment, purchase_history_entry, datetime.now(timezone.utc)
        )

        await message.answer(get_text("admin.handlers.materials_comment_updated", language=lang).format(request_number=request_number), reply_markup=get_manager_main_keyboard(language=lang))
        
        # Добавляем комментарий об изменении
        if user:
            try:
                from uk_management_bot.services.comment_service import CommentService
                comment_service = CommentService(db)
                comment_text = get_text("admin.handlers.comment_changed_text", language=lang).format(
                    old_comment=old_comment or get_text("admin.handlers.comment_absent", language=lang),
                    new_comment=new_comment
                )
                comment_service.add_status_change_comment(
                    request_id=request_number,
                    user_id=user.id,
                    old_status=REQUEST_STATUS_PURCHASE,
                    new_status=REQUEST_STATUS_PURCHASE,
                    comment=comment_text
                )
            except Exception as e:
                logger.error(f"Ошибка добавления комментария: {e}")
                # Не критично, продолжаем
        
        await state.clear()

        logger.info(f"Список материалов для заявки {request_number} обновлен менеджером {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обновления списка материалов: {e}")
        await message.answer(get_text("admin.handlers.error_updating_materials", language=lang))
        await state.clear()


