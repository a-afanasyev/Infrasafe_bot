"""Менеджер: назначение исполнителей (дежурный/конкретный)."""
from aiogram import F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.orm import Session

from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.keyboards.admin import (
    get_assignment_type_keyboard,
    get_executors_by_category_keyboard,
)
from uk_management_bot.constants.categories import CATEGORY_TO_SPECIALIZATION

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import has_admin_access

from ._router import router

from .shared import auto_assign_request_by_category

logger = logging.getLogger(__name__)


# ===== ОБРАБОТЧИКИ НАЗНАЧЕНИЯ ИСПОЛНИТЕЛЕЙ =====

@router.callback_query(F.data.startswith("assign_duty_"))
async def handle_assign_duty_executor_admin(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Назначение дежурного специалиста (автоматическое по сменам)"""
    try:
        lang = language

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("assign_duty_", "")
        logger.info(f"Назначение дежурного специалиста для заявки {request_number}")

        # Получаем заявку
        request = AdminHandlerService(db).get_request_by_number(request_number)
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Используем существующую логику auto_assign
        await auto_assign_request_by_category(request, db, user)

        # Пытаемся отредактировать сообщение
        success_message = get_text("admin.handlers.duty_assigned_success", language=lang).format(request_number=request_number)

        try:
            await callback.message.edit_text(
                success_message,
                parse_mode="HTML"
            )
        except TelegramBadRequest as telegram_error:
            # Если сообщение не изменилось, отправляем callback.answer вместо редактирования
            if "message is not modified" in str(telegram_error):
                await callback.answer(get_text("admin.handlers.assignment_done_success", language=lang), show_alert=False)
                logger.info(f"Сообщение не изменилось, использован callback.answer для заявки {request_number}")
            else:
                # Если другая ошибка Telegram - отправляем новое сообщение
                await callback.message.answer(success_message, parse_mode="HTML")
                await callback.answer()

        await callback.answer()  # Убираем "часики"
        logger.info(f"Заявка {request_number} назначена дежурному специалисту")

    except TelegramBadRequest as e:
        logger.error(f"Ошибка Telegram при назначении дежурного специалиста: {e}", exc_info=True)
        await callback.answer(get_text("admin.handlers.assignment_done_display_error", language=lang), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка назначения дежурного специалиста: {e}", exc_info=True)
        await callback.answer(get_text("admin.handlers.error_assigning", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("assign_specific_"))
async def handle_assign_specific_executor_admin(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать список исполнителей для ручного выбора"""
    try:
        lang = language

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("assign_specific_", "")
        logger.info(f"Выбор конкретного исполнителя для заявки {request_number}")

        svc = AdminHandlerService(db)
        # Получаем заявку
        request = svc.get_request_by_number(request_number)
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Получаем исполнителей с нужной специализацией
        category_to_spec = CATEGORY_TO_SPECIALIZATION

        spec = category_to_spec.get(request.category, "other")

        logger.info(f"[SPECIFIC_ASSIGN] Категория '{request.category}' → специализация: '{spec}'")

        # Получаем всех исполнителей с данной специализацией
        import json

        # ИСПРАВЛЕНО: проверяем наличие роли "executor" в массиве roles
        # Используем JSONB operator @> для проверки вхождения элемента в массив
        executors = svc.list_approved_executors()

        logger.info(f"[SPECIFIC_ASSIGN] Найдено {len(executors)} исполнителей (с ролью executor) со статусом 'approved'")

        # Фильтруем по специализации
        filtered_executors = []
        for ex in executors:
            if ex.specialization:
                try:
                    specializations = json.loads(ex.specialization) if isinstance(ex.specialization, str) else ex.specialization
                    logger.debug(f"[SPECIFIC_ASSIGN] Исполнитель {ex.id} ({ex.first_name}): специализации = {specializations}")

                    if spec in specializations or "other" in specializations:
                        filtered_executors.append(ex)
                        logger.info(f"[SPECIFIC_ASSIGN] ✅ Исполнитель {ex.id} ({ex.first_name}) подходит (есть '{spec}')")
                    else:
                        logger.debug(f"[SPECIFIC_ASSIGN] ❌ Исполнитель {ex.id} ({ex.first_name}) НЕ подходит (нет '{spec}')")
                except Exception as e:
                    logger.warning(f"[SPECIFIC_ASSIGN] Ошибка парсинга специализаций для исполнителя {ex.id}: {e}")
            else:
                logger.debug(f"[SPECIFIC_ASSIGN] Исполнитель {ex.id} ({ex.first_name}) БЕЗ специализаций")

        logger.info(f"[SPECIFIC_ASSIGN] Отфильтровано {len(filtered_executors)} исполнителей с специализацией '{spec}'")

        executors_text = get_text("admin.handlers.executors_found", language=lang).format(count=len(filtered_executors)) if filtered_executors else get_text("admin.handlers.no_executors_available", language=lang)

        await callback.message.edit_text(
            get_text("admin.handlers.choose_executor", language=lang).format(
                request_number=request_number,
                category=get_category_display(resolve_category_key(request.category), language=lang),
                spec=spec,
                executors_text=executors_text
            ),
            reply_markup=get_executors_by_category_keyboard(request_number, request.category, filtered_executors),
            parse_mode="HTML"
        )

        logger.info(f"Показан список из {len(filtered_executors)} исполнителей для заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка показа списка исполнителей: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("assign_executor_"))
async def handle_final_executor_assignment_admin(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Финальное назначение конкретного исполнителя"""
    try:
        lang = language

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        # Парсим данные: assign_executor_251013-001_123
        parts = callback.data.replace("assign_executor_", "").split("_")
        request_number = parts[0]
        executor_id = int(parts[1])

        logger.info(f"Финальное назначение исполнителя {executor_id} на заявку {request_number}")

        svc = AdminHandlerService(db)
        # Получаем заявку и исполнителя
        request = svc.get_request_by_number(request_number)
        executor = svc.get_user_by_id(executor_id)

        if not request or not executor:
            await callback.answer(get_text("admin.handlers.request_or_executor_not_found", language=lang), show_alert=True)
            return

        # Получаем менеджера (текущий пользователь)
        if not user:
            user = svc.get_user_by_telegram_id(callback.from_user.id)
            if not user:
                await callback.answer(get_text("admin.handlers.error_user_not_found", language=lang), show_alert=True)
                return

        # Назначаем исполнителя через новую систему AssignmentService
        from uk_management_bot.services.assignment_service import AssignmentService
        assignment_service = AssignmentService(db)

        try:
            # Используем индивидуальное назначение с user.id вместо telegram_id
            assignment_service.assign_to_executor(
                request_number=request_number,
                executor_id=executor_id,
                assigned_by=user.id  # ИСПРАВЛЕНО: используем id из таблицы users
            )
            logger.info(f"Заявка {request_number} назначена исполнителю {executor_id} через AssignmentService (менеджер: {user.id})")
        except Exception as e:
            logger.error(f"Ошибка назначения заявки: {e}", exc_info=True)
            await callback.answer(get_text("admin.handlers.error_assignment_detail", language=lang).format(error=str(e)), show_alert=True)
            return

        executor_name = f"{executor.first_name or ''} {executor.last_name or ''}".strip()
        if not executor_name:
            executor_name = f"@{executor.username}" if executor.username else f"ID{executor.id}"

        # Ограничиваем длину адреса в сообщении менеджеру
        MAX_ADDRESS_DISPLAY = 150
        address_display = request.address[:MAX_ADDRESS_DISPLAY] + "..." if len(request.address) > MAX_ADDRESS_DISPLAY else request.address

        success_message = get_text("admin.handlers.executor_assigned_success", language=lang).format(
            request_number=request_number,
            executor_name=executor_name,
            category=get_category_display(resolve_category_key(request.category), language=lang),
            address=address_display
        )

        try:
            await callback.message.edit_text(success_message, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                await callback.answer(get_text("admin.handlers.assignment_done_success", language=lang), show_alert=False)
                logger.info(f"Сообщение не изменилось для заявки {request_number}")
            else:
                # Отправляем новое сообщение
                await callback.message.answer(success_message, parse_mode="HTML")
                await callback.answer()

        # Отправляем уведомление исполнителю
        try:
            bot = callback.bot

            # Ограничиваем длину текста для предотвращения MESSAGE_TOO_LONG
            # Telegram лимит: 4096 символов
            # Уменьшаем лимиты ещё больше для безопасности
            MAX_ADDRESS_LENGTH = 150
            MAX_DESCRIPTION_LENGTH = 300

            address = request.address[:MAX_ADDRESS_LENGTH] + "..." if len(request.address) > MAX_ADDRESS_LENGTH else request.address
            description = request.description[:MAX_DESCRIPTION_LENGTH] + "..." if len(request.description) > MAX_DESCRIPTION_LENGTH else request.description

            notification_text = get_text("admin.handlers.notify_executor_assigned", language=lang).format(
                request_number=request.format_number_for_display(),
                category=get_category_display(resolve_category_key(request.category), language=lang),
                address=address,
                description=description
            )

            # Дополнительная проверка на общую длину (лимит Telegram - 4096 символов)
            # Обрезаем с запасом до 3500 символов
            if len(notification_text) > 3500:
                notification_text = notification_text[:3497] + "..."
                logger.warning(f"Уведомление для исполнителя было обрезано до 3500 символов (было {len(notification_text)} символов)")

            logger.info(f"Отправка уведомления исполнителю {executor.telegram_id} (длина: {len(notification_text)} символов)")
            await bot.send_message(executor.telegram_id, notification_text, parse_mode="HTML")
            logger.info(f"Уведомление о назначении отправлено исполнителю {executor.telegram_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления исполнителю: {e}", exc_info=True)

        logger.info(f"Заявка {request_number} назначена исполнителю {executor_id}")

    except Exception as e:
        logger.error(f"Ошибка финального назначения исполнителя: {e}")
        await callback.answer(get_text("admin.handlers.error_assigning", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("back_to_assignment_type_"))
async def handle_back_to_assignment_type_admin(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Возврат к выбору типа назначения"""
    try:
        lang = language

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("back_to_assignment_type_", "")

        request = AdminHandlerService(db).get_request_by_number(request_number)

        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        await callback.message.edit_text(
            get_text("admin.handlers.request_accepted_choose_assignment", language=lang).format(
                request_number=request_number,
                category=get_category_display(resolve_category_key(request.category), language=lang),
                address=request.address
            ),
            reply_markup=get_assignment_type_keyboard(request_number),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к выбору типа назначения: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)

