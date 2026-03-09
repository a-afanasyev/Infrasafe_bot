from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.orm import Session
from sqlalchemy import or_

from uk_management_bot.keyboards.admin import (
    get_manager_main_keyboard,
    get_manager_requests_inline,
    get_manager_request_list_kb,
    get_invite_role_keyboard,
    get_invite_specialization_keyboard,
    get_invite_expiry_keyboard,
    get_invite_confirmation_keyboard,
    get_completed_requests_submenu,
    get_assignment_type_keyboard,
    get_executors_by_category_keyboard,
)
from uk_management_bot.keyboards.base import get_main_keyboard, get_user_contextual_keyboard
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.request_service import RequestService
from uk_management_bot.services.invite_service import InviteService
from uk_management_bot.services.notification_service import async_notify_request_status_changed
from uk_management_bot.database.session import get_db
from uk_management_bot.utils.constants import (
    SPECIALIZATION_ELECTRIC,
    SPECIALIZATION_PLUMBING,
    SPECIALIZATION_SECURITY,
    SPECIALIZATION_CLEANING,
    SPECIALIZATION_OTHER,
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
)
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.status_display import get_status_display, get_status_with_emoji, STATUS_EMOJI
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.utils.auth_helpers import has_admin_access
from datetime import datetime

router = Router()
logger = logging.getLogger(__name__)

# Single Source of Truth for button texts - TASK 17
from uk_management_bot.utils.button_texts import get_admin_panel_texts

# Константа для фильтрации сообщений "Админ панель"
ADMIN_PANEL_TEXTS = get_admin_panel_texts()

class ManagerStates(StatesGroup):
    cancel_reason = State()
    clarify_reason = State()
    waiting_for_clarification_text = State()
    waiting_for_materials_edit = State()

from uk_management_bot.states.invite_creation import InviteCreationStates


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

async def auto_assign_request_by_category(request: Request, db: Session, manager: User):
    """
    Автоматически назначает заявку исполнителям по категории/специализации

    Args:
        request: Заявка для назначения
        db: Сессия базы данных
        manager: Менеджер, который назначает заявку
    """
    try:
        from uk_management_bot.database.models.request_assignment import RequestAssignment
        import json

        logger.info(f"[AUTO_ASSIGN] Начало автоматического назначения для заявки {request.request_number}, категория: {request.category}")

        # Маппинг категорий заявок на специализации
        category_to_specialization = {
            "Сантехника": "plumber",
            "Электрика": "electrician",
            "Благоустройство": "landscaping",
            "Уборка": "cleaning",
            "Безопасность": "security",
            "Ремонт": "repair",
            "Установка": "installation",
            "Обслуживание": "maintenance",
            "HVAC": "hvac",
            "Отопление": "hvac",
            "Вентиляция": "hvac"
        }

        # Определяем специализацию по категории заявки
        specialization = category_to_specialization.get(request.category)
        logger.info(f"[AUTO_ASSIGN] Категория '{request.category}' → специализация: {specialization}")

        if not specialization:
            logger.warning(f"[AUTO_ASSIGN] Неизвестная категория заявки: {request.category}, доступные: {list(category_to_specialization.keys())}")
            return
        
        # Находим исполнителей с нужной специализацией
        logger.info(f"[AUTO_ASSIGN] Выполнение запроса к таблице users...")

        # Сначала проверим всех пользователей с ролью executor
        all_executors = db.query(User).filter(User.active_role == "executor").all()
        logger.info(f"[AUTO_ASSIGN] Всего пользователей с active_role='executor': {len(all_executors)}")

        approved_executors = db.query(User).filter(
            User.active_role == "executor",
            User.status == "approved"
        ).all()
        logger.info(f"[AUTO_ASSIGN] Из них со status='approved': {len(approved_executors)}")

        for ex in all_executors:
            logger.debug(f"[AUTO_ASSIGN]   User {ex.id} ({ex.first_name}): active_role={ex.active_role}, status={ex.status}")

        executors = approved_executors
        logger.info(f"[AUTO_ASSIGN] Найдено {len(executors)} активных исполнителей")

        matching_executors = []
        for executor in executors:
            if executor.specialization:
                try:
                    # Парсим специализации исполнителя
                    if isinstance(executor.specialization, str):
                        executor_specializations = json.loads(executor.specialization)
                    else:
                        executor_specializations = executor.specialization

                    # Проверяем, есть ли нужная специализация
                    if specialization in executor_specializations:
                        matching_executors.append(executor)
                        logger.debug(f"[AUTO_ASSIGN] Исполнитель {executor.id} ({executor.first_name}) подходит (специализации: {executor_specializations})")
                    else:
                        logger.debug(f"[AUTO_ASSIGN] Исполнитель {executor.id} не подходит (специализации: {executor_specializations}, требуется: {specialization})")
                except (json.JSONDecodeError, TypeError):
                    # Если специализация - просто строка
                    if executor.specialization == specialization:
                        matching_executors.append(executor)
                        logger.debug(f"[AUTO_ASSIGN] Исполнитель {executor.id} подходит (специализация строка: {executor.specialization})")

        logger.info(f"[AUTO_ASSIGN] Найдено {len(matching_executors)} подходящих исполнителей для специализации '{specialization}'")

        if not matching_executors:
            logger.warning(f"[AUTO_ASSIGN] Не найдено исполнителей для специализации {specialization}")
            return
        
        # Проверяем, есть ли уже назначение для этой заявки
        existing_assignment = db.query(RequestAssignment).filter(
            RequestAssignment.request_number == request.request_number,
            RequestAssignment.status == "active"
        ).first()

        if existing_assignment:
            logger.info(f"[AUTO_ASSIGN] Заявка {request.request_number} уже назначена (ID: {existing_assignment.id}), пропускаем")
            return

        # Дополнительная проверка на групповые назначения для той же специализации
        existing_group_assignment = db.query(RequestAssignment).filter(
            RequestAssignment.request_number == request.request_number,
            RequestAssignment.assignment_type == "group",
            RequestAssignment.group_specialization == specialization,
            RequestAssignment.status == "active"
        ).first()

        if existing_group_assignment:
            logger.info(f"[AUTO_ASSIGN] Заявка {request.request_number} уже назначена группе {specialization}, пропускаем")
            return

        logger.info(f"[AUTO_ASSIGN] Назначений для заявки {request.request_number} не найдено, создаем новое групповое назначение")
        
        # Создаем групповое назначение
        logger.info(f"[AUTO_ASSIGN] Создание группового назначения для заявки {request.request_number}")

        assignment = RequestAssignment(
            request_number=request.request_number,
            assignment_type="group",
            group_specialization=specialization,
            status="active",
            created_by=manager.id
        )

        db.add(assignment)
        logger.info(f"[AUTO_ASSIGN] Объект RequestAssignment добавлен в сессию (request_number={assignment.request_number}, type={assignment.assignment_type})")

        # Обновляем поля заявки
        request.assignment_type = "group"
        request.assigned_group = specialization
        request.assigned_at = datetime.now()
        request.assigned_by = manager.id
        logger.info(f"[AUTO_ASSIGN] Поля заявки обновлены (assignment_type={request.assignment_type}, assigned_group={request.assigned_group})")

        # ВАЖНО: Сохраняем изменения в базу данных
        logger.info(f"[AUTO_ASSIGN] Выполнение db.commit()...")
        db.commit()
        logger.info(f"[AUTO_ASSIGN] db.commit() успешно выполнен")

        db.refresh(assignment)
        db.refresh(request)
        logger.info(f"[AUTO_ASSIGN] Объекты обновлены из базы (assignment.id={assignment.id})")

        logger.info(f"[AUTO_ASSIGN] ✅ Заявка {request.request_number} автоматически назначена группе {specialization} ({len(matching_executors)} исполнителей)")

        # Отправляем уведомления исполнителям в активных сменах
        from uk_management_bot.database.models.shift import Shift
        from datetime import datetime as dt
        from aiogram import Bot
        from uk_management_bot.config.settings import settings

        bot = Bot(token=settings.BOT_TOKEN)
        now = dt.now()

        # Находим исполнителей в активных сменах с нужной специализацией
        for executor in matching_executors:
            # Проверяем активную смену
            active_shift = db.query(Shift).filter(
                Shift.user_id == executor.id,
                Shift.status == "active",
                Shift.start_time <= now,
                or_(Shift.end_time.is_(None), Shift.end_time >= now)
            ).first()

            if active_shift:
                try:
                    notification_text = get_text("admin.handlers.new_request_for_duty", language="ru").format(
                        specialization=specialization,
                        request_number=request.request_number,
                        category=request.category,
                        address=request.address,
                        urgency=request.urgency,
                        description=request.description
                    )
                    await bot.send_message(
                        chat_id=executor.telegram_id,
                        text=notification_text,
                        parse_mode="HTML"
                    )
                    logger.info(f"Уведомление о групповом назначении отправлено исполнителю {executor.id} (смена {active_shift.id})")
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления исполнителю {executor.id}: {e}")
        
    except Exception as e:
        logger.error(f"Ошибка автоматического назначения заявки {request.request_number}: {e}")


# ===== ОБРАБОТЧИКИ ПРОСМОТРА ЗАЯВОК ДЛЯ МЕНЕДЖЕРОВ =====

@router.callback_query(F.data.startswith("mview_"))
async def handle_manager_view_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка просмотра деталей заявки для менеджеров"""
    try:
        lang = callback.from_user.language_code or 'ru'
        logger.info(f"Обработка просмотра заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_requests", language=lang), show_alert=True)
            return
        
        request_number = callback.data.replace("mview_", "")
        
        # Получаем заявку из базы данных
        request = db.query(Request).filter(Request.request_number == request_number).first()
        
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Получаем информацию о пользователе, создавшем заявку
        request_user = db.query(User).filter(User.id == request.user_id).first()
        if request_user:
            # Формируем полное имя из first_name и last_name
            full_name_parts = []
            if request_user.first_name:
                full_name_parts.append(request_user.first_name)
            if request_user.last_name:
                full_name_parts.append(request_user.last_name)
            user_info = " ".join(full_name_parts) if full_name_parts else get_text("admin.handlers.user_by_id", language=lang).format(telegram_id=request_user.telegram_id)
        else:
            user_info = get_text("admin.handlers.unknown_user", language=lang)
        
        # Формируем детальную информацию о заявке
        message_text = get_text("admin.handlers.request_detail_header", language=lang).format(request_number=request.request_number) + "\n\n"
        message_text += get_text("admin.handlers.request_detail_applicant", language=lang).format(user_info=user_info) + "\n"
        message_text += get_text("admin.handlers.request_detail_telegram_id", language=lang).format(telegram_id=request_user.telegram_id if request_user else 'N/A') + "\n"
        message_text += get_text("admin.handlers.request_detail_category", language=lang).format(category=request.category) + "\n"
        message_text += get_text("admin.handlers.request_detail_status", language=lang).format(status=get_status_display(request.status, language=lang)) + "\n"
        message_text += get_text("admin.handlers.request_detail_address", language=lang).format(address=request.address) + "\n"
        message_text += get_text("admin.handlers.request_detail_description", language=lang).format(description=request.description) + "\n"
        message_text += get_text("admin.handlers.request_detail_urgency", language=lang).format(urgency=request.urgency) + "\n"
        if request.apartment:
            message_text += get_text("admin.handlers.request_detail_apartment", language=lang).format(apartment=request.apartment) + "\n"
        message_text += get_text("admin.handlers.request_detail_created", language=lang).format(created_at=request.created_at.strftime('%d.%m.%Y %H:%M')) + "\n"
        if request.updated_at:
            message_text += get_text("admin.handlers.request_detail_updated", language=lang).format(updated_at=request.updated_at.strftime('%d.%m.%Y %H:%M')) + "\n"

        # Добавляем информацию о назначении
        from uk_management_bot.database.models.request_assignment import RequestAssignment
        active_assignment = db.query(RequestAssignment).filter(
            RequestAssignment.request_number == request.request_number,
            RequestAssignment.status == "active"
        ).first()

        if active_assignment:
            if active_assignment.assignment_type == "group":
                # Групповое назначение (дежурному специалисту)
                spec_name = get_text(f"specializations.{active_assignment.group_specialization}", language=lang) if active_assignment.group_specialization else active_assignment.group_specialization
                message_text += get_text("admin.handlers.assigned_duty_specialist", language=lang).format(spec_name=spec_name) + "\n"
            elif active_assignment.assignment_type == "individual" and active_assignment.executor_id:
                # Индивидуальное назначение конкретному исполнителю
                assigned_executor = db.query(User).filter(User.id == active_assignment.executor_id).first()
                if assigned_executor:
                    executor_name = f"{assigned_executor.first_name or ''} {assigned_executor.last_name or ''}".strip()
                    if not executor_name:
                        executor_name = f"@{assigned_executor.username}" if assigned_executor.username else f"ID{assigned_executor.id}"
                    message_text += get_text("admin.handlers.assigned_executor", language=lang).format(executor_name=executor_name) + "\n"

        if request.notes:
            message_text += get_text("admin.handlers.request_detail_notes", language=lang).format(notes=request.notes) + "\n"

        # Проверяем наличие медиафайлов
        media_files = request.media_files if request.media_files else []
        completion_media = request.completion_media if request.completion_media else []
        has_media = len(media_files) > 0 or len(completion_media) > 0

        # Создаем клавиатуру действий для менеджера
        from uk_management_bot.keyboards.admin import (
            get_manager_request_actions_keyboard,
            get_manager_completed_request_actions_keyboard,
            get_unaccepted_request_actions_keyboard
        )

        # Для исполненных, но непринятых заявок - специальная клавиатура
        if request.status == REQUEST_STATUS_EXECUTED and request.manager_confirmed and not request.is_returned:
            # Добавляем информацию о времени ожидания принятия
            from datetime import datetime, timezone
            completed_at = request.completed_at if request.completed_at else request.updated_at
            if completed_at:
                if completed_at.tzinfo is None:
                    from datetime import timezone as dt_tz
                    completed_at = completed_at.replace(tzinfo=dt_tz.utc)
                now = datetime.now(timezone.utc)
                waiting_time = now - completed_at
                days = waiting_time.days
                hours = waiting_time.seconds // 3600
                minutes = (waiting_time.seconds % 3600) // 60

                if days > 0:
                    time_str = f"{days}д {hours}ч"
                elif hours > 0:
                    time_str = f"{hours}ч {minutes}м"
                else:
                    time_str = f"{minutes}м"

                message_text += "\n" + get_text("admin.handlers.waiting_acceptance", language=lang).format(time_str=time_str) + "\n"

            actions_kb = get_unaccepted_request_actions_keyboard(request.request_number)

            # Добавляем кнопку медиа если есть
            rows = list(actions_kb.inline_keyboard)
            if has_media:
                # Вставляем кнопку медиа перед кнопкой "Назад к списку"
                rows.insert(-1, [InlineKeyboardButton(text=get_text("admin.handlers.btn_media", language=lang), callback_data=f"media_{request.request_number}")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        # Для исполненных заявок (ожидающих подтверждения) - специальная клавиатура
        elif request.status == REQUEST_STATUS_EXECUTED:
            actions_kb = get_manager_completed_request_actions_keyboard(request.request_number, is_returned=request.is_returned)

            # Добавляем кнопку медиа если есть
            rows = list(actions_kb.inline_keyboard)
            if has_media:
                rows.append([InlineKeyboardButton(text=get_text("admin.handlers.btn_media", language=lang), callback_data=f"media_{request.request_number}")])
            rows.append([InlineKeyboardButton(text=get_text("admin.handlers.btn_back_to_list", language=lang), callback_data="mreq_back_to_list")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        else:
            # Для обычных заявок - стандартная клавиатура
            actions_kb = get_manager_request_actions_keyboard(request.request_number, has_media=has_media)

            # Добавляем кнопку "Назад к списку"
            rows = list(actions_kb.inline_keyboard)
            rows.append([InlineKeyboardButton(text=get_text("admin.handlers.btn_back_to_list", language=lang), callback_data="mreq_back_to_list")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
        logger.info(f"Показаны детали заявки {request.request_number} менеджеру {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки просмотра заявки менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("media_"))
async def handle_view_request_media(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка просмотра медиафайлов заявки"""
    try:
        from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument
        lang = callback.from_user.language_code or 'ru'

        logger.info(f"Просмотр медиафайлов заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_media", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("media_", "")

        # Получаем заявку из базы данных
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем наличие медиафайлов и парсим JSON
        import json

        media_files = []
        if request.media_files:
            try:
                media_files = json.loads(request.media_files) if isinstance(request.media_files, str) else request.media_files
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Ошибка парсинга media_files для заявки {request.request_number}: {e}")

        completion_media = []
        if request.completion_media:
            try:
                completion_media = json.loads(request.completion_media) if isinstance(request.completion_media, str) else request.completion_media
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Ошибка парсинга completion_media для заявки {request.request_number}: {e}")

        if not media_files and not completion_media:
            await callback.answer(get_text("admin.handlers.no_media_attached", language=lang), show_alert=True)
            return

        # Отправляем медиафайлы при создании заявки
        if media_files:
            await callback.message.answer(
                get_text("admin.handlers.media_creation_header", language=lang).format(request_number=request.request_number),
                parse_mode="HTML"
            )

            # Если файлов больше 1, отправляем группой
            if len(media_files) > 1:
                media_group = []
                for idx, media_item in enumerate(media_files):
                    # Извлекаем file_id из объекта или используем как строку
                    file_id = media_item.get("file_id") if isinstance(media_item, dict) else media_item

                    try:
                        # Пробуем как фото
                        if idx == 0:
                            media_group.append(InputMediaPhoto(media=file_id, caption=get_text("admin.handlers.photo_counter", language=lang).format(current=idx+1, total=len(media_files))))
                        else:
                            media_group.append(InputMediaPhoto(media=file_id))
                    except:
                        # Если не получилось как фото, пробуем как документ
                        if idx == 0:
                            media_group.append(InputMediaDocument(media=file_id, caption=get_text("admin.handlers.file_counter", language=lang).format(current=idx+1, total=len(media_files))))
                        else:
                            media_group.append(InputMediaDocument(media=file_id))

                if media_group:
                    await callback.message.answer_media_group(media=media_group)
            else:
                # Один файл - отправляем отдельно
                file_id = media_files[0].get("file_id") if isinstance(media_files[0], dict) else media_files[0]
                try:
                    await callback.message.answer_photo(photo=file_id)
                except:
                    try:
                        await callback.message.answer_document(document=file_id)
                    except Exception as e:
                        logger.error(f"Ошибка отправки медиафайла: {e}")
                        await callback.message.answer(get_text("admin.handlers.media_send_failed", language=lang))

        # Отправляем медиафайлы при завершении заявки
        if completion_media:
            await callback.message.answer(
                get_text("admin.handlers.media_completion_header", language=lang).format(request_number=request.request_number),
                parse_mode="HTML"
            )

            # Если файлов больше 1, отправляем группой
            if len(completion_media) > 1:
                media_group = []
                for idx, media_item in enumerate(completion_media):
                    # Извлекаем file_id из объекта или используем как строку
                    file_id = media_item.get("file_id") if isinstance(media_item, dict) else media_item

                    try:
                        # Пробуем как фото
                        if idx == 0:
                            media_group.append(InputMediaPhoto(media=file_id, caption=get_text("admin.handlers.photo_counter", language=lang).format(current=idx+1, total=len(completion_media))))
                        else:
                            media_group.append(InputMediaPhoto(media=file_id))
                    except:
                        # Если не получилось как фото, пробуем как документ
                        if idx == 0:
                            media_group.append(InputMediaDocument(media=file_id, caption=get_text("admin.handlers.file_counter", language=lang).format(current=idx+1, total=len(completion_media))))
                        else:
                            media_group.append(InputMediaDocument(media=file_id))

                if media_group:
                    await callback.message.answer_media_group(media=media_group)
            else:
                # Один файл - отправляем отдельно
                file_id = completion_media[0].get("file_id") if isinstance(completion_media[0], dict) else completion_media[0]
                try:
                    await callback.message.answer_photo(photo=file_id)
                except:
                    try:
                        await callback.message.answer_document(document=file_id)
                    except Exception as e:
                        logger.error(f"Ошибка отправки медиафайла при завершении: {e}")
                        await callback.message.answer(get_text("admin.handlers.media_send_failed", language=lang))

        await callback.answer(get_text("admin.handlers.media_sent", language=lang))
        logger.info(f"Отправлены медиафайлы заявки {request.request_number} менеджеру {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка просмотра медиафайлов заявки: {e}")
        await callback.answer(get_text("admin.handlers.error_loading_media", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("confirm_completed_"))
async def handle_manager_confirm_completed(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Менеджер подтверждает выполнение заявки"""
    try:
        from datetime import datetime
        from uk_management_bot.services.notification_service import NotificationService
        lang = callback.from_user.language_code or 'ru'

        logger.info(f"Подтверждение выполнения заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_confirm", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("confirm_completed_", "")
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Подтверждаем выполнение
        old_status = request.status
        request.status = REQUEST_STATUS_EXECUTED
        request.manager_confirmed = True
        request.manager_confirmed_by = user.id
        request.manager_confirmed_at = datetime.now()

        # Аудит
        from uk_management_bot.database.models.audit import AuditLog
        db.add(AuditLog(
            user_id=user.id,
            action="request_status_changed",
            details={
                "request_number": request.request_number,
                "old_status": old_status,
                "new_status": REQUEST_STATUS_EXECUTED,
                "actor": "manager_confirm",
            }
        ))
        db.commit()

        # Уведомление через сервис (отправит заявителю, исполнителю и в канал)
        try:
            from aiogram import Bot
            bot = Bot.get_current()
            await async_notify_request_status_changed(bot, db, request, old_status, REQUEST_STATUS_EXECUTED)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

        # Дополнительное уведомление заявителю с инструкцией
        applicant = request.user
        if applicant and applicant.telegram_id:
            try:
                from aiogram import Bot
                bot = Bot.get_current()

                notification_text = get_text("admin.handlers.notify_applicant_completed", language=lang).format(
                    request_number=request.format_number_for_display()
                )

                await bot.send_message(applicant.telegram_id, notification_text)
                logger.info(f"✅ Уведомление о подтверждении заявки {request.request_number} отправлено заявителю {applicant.telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления заявителю: {e}")

        await callback.message.edit_text(
            get_text("admin.handlers.request_confirmed", language=lang).format(request_number=request.request_number)
        )

        logger.info(f"Заявка {request.request_number} подтверждена менеджером {user.id}")

    except Exception as e:
        logger.error(f"Ошибка подтверждения выполнения заявки: {e}")
        if db:
            db.rollback()
        await callback.answer(get_text("admin.handlers.error_confirming", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("reconfirm_completed_"))
async def handle_manager_reconfirm_completed(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Менеджер повторно подтверждает выполнение возвратной заявки"""
    try:
        from datetime import datetime
        from uk_management_bot.services.notification_service import NotificationService
        lang = callback.from_user.language_code or 'ru'

        logger.info(f"Повторное подтверждение возвратной заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_confirm", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("reconfirm_completed_", "")
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Сбрасываем флаг возврата и повторно подтверждаем
        old_status = request.status
        request.status = REQUEST_STATUS_EXECUTED
        request.is_returned = False  # Снимаем флаг возврата
        request.manager_confirmed = True
        request.manager_confirmed_by = user.id
        request.manager_confirmed_at = datetime.now()

        # Аудит
        from uk_management_bot.database.models.audit import AuditLog
        db.add(AuditLog(
            user_id=user.id,
            action="request_status_changed",
            details={
                "request_number": request.request_number,
                "old_status": old_status,
                "new_status": REQUEST_STATUS_EXECUTED,
                "actor": "manager_reconfirm",
            }
        ))
        db.commit()

        # Уведомление через сервис (отправит заявителю, исполнителю и в канал)
        try:
            from aiogram import Bot
            bot = Bot.get_current()
            await async_notify_request_status_changed(bot, db, request, old_status, REQUEST_STATUS_EXECUTED)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

        # Дополнительное уведомление заявителю с инструкцией
        applicant = request.user
        if applicant and applicant.telegram_id:
            try:
                from aiogram import Bot
                bot = Bot.get_current()

                notification_text = get_text("admin.handlers.notify_applicant_reconfirmed", language=lang).format(
                    request_number=request.format_number_for_display()
                )

                await bot.send_message(applicant.telegram_id, notification_text)
                logger.info(f"✅ Уведомление о повторном подтверждении заявки {request.request_number} отправлено заявителю {applicant.telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления заявителю: {e}")

        await callback.message.edit_text(
            get_text("admin.handlers.request_reconfirmed", language=lang).format(request_number=request.request_number)
        )

        logger.info(f"Возвратная заявка {request.request_number} подтверждена повторно менеджером {user.id}")

    except Exception as e:
        logger.error(f"Ошибка повторного подтверждения заявки: {e}")
        if db:
            db.rollback()
        await callback.answer(get_text("admin.handlers.error_confirming", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("return_to_work_"))
async def handle_manager_return_to_work(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Менеджер возвращает заявку в работу"""
    try:
        lang = callback.from_user.language_code or 'ru'
        logger.info(f"Возврат заявки в работу менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_change_status", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("return_to_work_", "")
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Возвращаем в работу
        old_status = request.status
        request.status = REQUEST_STATUS_IN_PROGRESS
        request.is_returned = False  # Снимаем флаг возврата если был
        request.manager_confirmed = False

        # Аудит
        from uk_management_bot.database.models.audit import AuditLog
        db.add(AuditLog(
            user_id=user.id,
            action="request_status_changed",
            details={
                "request_number": request.request_number,
                "old_status": old_status,
                "new_status": REQUEST_STATUS_IN_PROGRESS,
                "actor": "manager_return_to_work",
            }
        ))
        db.commit()

        # Уведомление через сервис (отправит заявителю, исполнителю и в канал)
        try:
            from aiogram import Bot
            bot = Bot.get_current()
            await async_notify_request_status_changed(bot, db, request, old_status, REQUEST_STATUS_IN_PROGRESS)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

        await callback.message.edit_text(
            get_text("admin.handlers.request_returned_to_work", language=lang).format(request_number=request.request_number)
        )

        logger.info(f"Заявка {request.request_number} возвращена в работу менеджером {user.id}")

    except Exception as e:
        logger.error(f"Ошибка возврата заявки в работу: {e}")
        if db:
            db.rollback()
        await callback.answer(get_text("admin.handlers.error_changing_status", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("mreq_page_"))
async def handle_manager_request_pagination(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка пагинации списков заявок для менеджеров"""
    try:
        lang = callback.from_user.language_code or 'ru'
        logger.info(f"Обработка пагинации заявок менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_requests", language=lang), show_alert=True)
            return

        # Парсим данные пагинации
        page_data = callback.data.replace("mreq_page_", "")

        if page_data == "curr":
            await callback.answer(get_text("admin.handlers.current_page", language=lang))
            return
        
        current_page = int(page_data)
        
        # Определяем тип списка заявок (новые, активные, архив)
        # Пока что показываем активные заявки
        active_statuses = [REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION]
        q = (
            db.query(Request)
            .filter(Request.status.in_(active_statuses))
            .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
        )
        
        # Вычисляем общее количество страниц
        total_requests = q.count()
        requests_per_page = 10
        total_pages = max(1, (total_requests + requests_per_page - 1) // requests_per_page)
        
        if current_page < 1 or current_page > total_pages:
            await callback.answer(get_text("admin.handlers.page_not_found", language=lang), show_alert=True)
            return

        # Получаем заявки для текущей страницы
        requests = q.offset((current_page - 1) * requests_per_page).limit(requests_per_page).all()

        if not requests:
            await callback.answer(get_text("admin.handlers.no_requests_on_page", language=lang), show_alert=True)
            return
        
        items = [{"request_number": r.request_number, "category": r.category, "address": r.address, "status": r.status} for r in requests]
        
        # Обновляем сообщение с новой страницей
        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
        new_keyboard = get_manager_request_list_kb(items, current_page, total_pages)
        
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        
        logger.info(f"Показана страница {current_page} заявок менеджеру {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки пагинации заявок менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "mreq_back_to_list")
async def handle_manager_back_to_list(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Возврат из деталей заявки к списку для менеджеров"""
    try:
        lang = callback.from_user.language_code or 'ru'
        logger.info(f"Возврат к списку заявок менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_requests", language=lang), show_alert=True)
            return
        
        # Определяем, из какого списка мы пришли, по статусу заявки
        # Получаем текущую заявку из сообщения
        message_text = callback.message.text
        if "Заявка #" in message_text:
            # Извлекаем номер заявки из текста сообщения
            import re
            match = re.search(r'Заявка #(\d{6}-\d{3})', message_text)
            if match:
                request_number = match.group(1)
                request = db.query(Request).filter(Request.request_number == request_number).first()
                if request:
                    # Определяем тип списка по статусу заявки
                    if request.status == REQUEST_STATUS_NEW:
                        # Возвращаемся к новым заявкам
                        q = (
                            db.query(Request)
                            .filter(Request.status == REQUEST_STATUS_NEW)
                            .order_by(Request.created_at.desc())
                        )
                        requests = q.limit(10).all()
                        
                        if not requests:
                            await callback.message.edit_text(get_text("admin.handlers.no_new_requests", language=lang))
                            return

                        items = [{"request_number": r.request_number, "category": r.category, "address": r.address, "status": r.status} for r in requests]

                        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
                        keyboard = get_manager_request_list_kb(items, 1, 1)

                        await callback.message.edit_text(get_text("admin.handlers.new_requests_title", language=lang), reply_markup=keyboard)
                        return
                    elif request.status == REQUEST_STATUS_EXECUTED:
                        # Возвращаемся к исполненным заявкам
                        q = (
                            db.query(Request)
                            .filter(Request.status == REQUEST_STATUS_EXECUTED)
                            .order_by(
                                Request.is_returned.desc(),  # Возвратные заявки показываем первыми
                                Request.updated_at.desc().nullslast(),
                                Request.created_at.desc()
                            )
                        )
                        requests = q.limit(10).all()

                        if not requests:
                            await callback.message.edit_text(get_text("admin.handlers.no_completed_requests", language=lang))
                            return

                        # Добавляем пометку "возвратная" для возвратных заявок
                        items = []
                        for r in requests:
                            item = {
                                "request_number": r.request_number,
                                "category": r.category,
                                "address": r.address,
                                "status": r.status
                            }
                            if r.is_returned:
                                item["suffix"] = " 🔄"
                            items.append(item)

                        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
                        keyboard = get_manager_request_list_kb(items, 1, 1)

                        await callback.message.edit_text(get_text("admin.handlers.completed_requests_title", language=lang), reply_markup=keyboard)
                        return
                    elif request.status in [REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION]:
                        # Возвращаемся к активным заявкам
                        active_statuses = [REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION]
                        q = (
                            db.query(Request)
                            .filter(Request.status.in_(active_statuses))
                            .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
                        )
                        requests = q.limit(10).all()

                        if not requests:
                            await callback.message.edit_text(get_text("admin.handlers.no_active_requests", language=lang))
                            return

                        items = [{"request_number": r.request_number, "category": r.category, "address": r.address, "status": r.status} for r in requests]

                        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
                        keyboard = get_manager_request_list_kb(items, 1, 1)

                        await callback.message.edit_text(get_text("admin.handlers.active_requests_title", language=lang), reply_markup=keyboard)
                        return

        # Если не удалось определить тип списка, показываем активные заявки по умолчанию
        active_statuses = [REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION]
        q = (
            db.query(Request)
            .filter(Request.status.in_(active_statuses))
            .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
        )
        requests = q.limit(10).all()
        
        if not requests:
            await callback.message.edit_text(get_text("admin.handlers.no_active_requests", language=lang))
            return

        items = [{"request_number": r.request_number, "category": r.category, "address": r.address, "status": r.status} for r in requests]

        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
        keyboard = get_manager_request_list_kb(items, 1, 1)

        await callback.message.edit_text(get_text("admin.handlers.active_requests_title", language=lang), reply_markup=keyboard)

        logger.info(f"Возврат к списку заявок выполнен для менеджера {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка возврата к списку заявок: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.message(F.text == "🧪 Тест middleware")
async def test_middleware(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, user_status: str = None):
    """Тестовый обработчик для проверки middleware"""
    
    # Логирование параметров middleware для отладки
    logger.debug(f"Admin panel access check: roles={roles}, active_role={active_role}, user_id={message.from_user.id}")
    
    # Проверяем доступ к админ панели
    has_access = False
    if roles:
        has_access = any(role in ['admin', 'manager'] for role in roles)
    elif user and user.roles:
        try:
            import json
            user_roles = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
            has_access = any(role in ['admin', 'manager'] for role in user_roles)
        except:
            pass
    
    print(f"🔧 Доступ к админ панели: {'✅ Есть' if has_access else '❌ Нет'}")
    
    lang = message.from_user.language_code or 'ru'
    await message.answer(get_text("admin.handlers.test_middleware_result", language=lang).format(
        roles=roles, active_role=active_role,
        user_status=get_text("admin.handlers.yes", language=lang) if user else get_text("admin.handlers.no", language=lang),
        has_access=get_text("admin.handlers.yes", language=lang) if has_access else get_text("admin.handlers.no", language=lang)
    ))

@router.message(F.text.in_(ADMIN_PANEL_TEXTS))
async def open_admin_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, user_status: str = None):
    """Открыть админ панель"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    await message.answer(get_text("admin.handlers.manager_panel", language=lang), reply_markup=get_manager_main_keyboard())


@router.message(F.text == "👥 Управление пользователями")  
async def open_user_management_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Открыть панель управления пользователями"""
    lang = message.from_user.language_code or 'ru'
    
    # ОТЛАДКА
    logger.debug(f"User management panel opened: user_id={message.from_user.id}, roles={roles}, user_status={user.status if user else None}")
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Импортируем здесь, чтобы избежать циклических импортов
    try:
        from uk_management_bot.handlers.user_management import open_user_management
        await open_user_management(message, db, roles, active_role, user)
    except ImportError as e:
        logger.error(f"Ошибка импорта open_user_management: {e}")
        await message.answer(
            get_text("errors.unknown_error", language=lang)
        )
    except Exception as e:
        logger.error(f"Ошибка в open_user_management: {e}")
        await message.answer(
            get_text("errors.unknown_error", language=lang)
        )


@router.message(F.text == "👷 Управление сотрудниками")
async def open_employee_management_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Открыть панель управления сотрудниками"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    try:
        # Получаем статистику сотрудников
        from uk_management_bot.services.user_management_service import UserManagementService
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_employee_stats()
        
        # Показываем главное меню управления сотрудниками
        from uk_management_bot.keyboards.employee_management import get_employee_management_main_keyboard
        
        await message.answer(
            get_text("admin.handlers.employee_management_panel", language=lang),
            reply_markup=get_employee_management_main_keyboard(stats, lang)
        )

    except Exception as e:
        logger.error(f"Ошибка открытия панели управления сотрудниками: {e}")
        await message.answer(get_text("admin.handlers.error_opening_employee_panel", language=lang))


@router.message(F.text == "🆕 Новые заявки")
async def list_new_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать новые заявки"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Новые заявки: только "Новая" (🆕)
    q = (
        db.query(Request)
        .filter(Request.status == REQUEST_STATUS_NEW)
        .order_by(Request.created_at.desc())
    )
    requests = q.limit(10).all()
    
    if not requests:
        await message.answer(get_text("admin.handlers.no_new_requests", language=lang), reply_markup=get_manager_main_keyboard())
        return

    items = [{"request_number": r.request_number, "category": r.category, "address": r.address, "status": r.status} for r in requests]
    await message.answer(get_text("admin.handlers.new_requests_title", language=lang), reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text == "🔄 Активные заявки")
async def list_active_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать активные заявки"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    active_statuses = [REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION]
    q = (
        db.query(Request)
        .filter(Request.status.in_(active_statuses))
        .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
    )
    requests = q.limit(10).all()

    if not requests:
        await message.answer(get_text("admin.handlers.no_active_requests", language=lang), reply_markup=get_manager_main_keyboard())
        return

    items = [{"request_number": r.request_number, "category": r.category, "address": r.address, "status": r.status} for r in requests]
    await message.answer(get_text("admin.handlers.active_requests_title", language=lang), reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text == "✅ Исполненные заявки")
async def show_completed_requests_menu(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать подменю для исполненных заявок"""
    lang = message.from_user.language_code or 'ru'

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Получаем статистику
    # "Всего исполненных" = заявки ожидающие подтверждения менеджером (manager_confirmed = False)
    total_completed = db.query(Request).filter(
        Request.status == REQUEST_STATUS_EXECUTED,
        Request.manager_confirmed == False
    ).count()

    # Возвращённые = те, что были отправлены обратно исполнителю
    # Статус "Исполнено" - когда заявка возвращена заявителем на доработку
    returned_count = db.query(Request).filter(
        Request.status == REQUEST_STATUS_COMPLETED,
        Request.is_returned == True,
        Request.manager_confirmed == False  # Ещё не подтверждены после возврата
    ).count()

    # Не принятые = подтверждены менеджером, но не приняты заявителем
    unaccepted_count = db.query(Request).filter(
        Request.status == REQUEST_STATUS_EXECUTED,
        Request.manager_confirmed == True,
        Request.is_returned == False
    ).count()

    stats_text = get_text("admin.handlers.completed_requests_stats", language=lang).format(
        total_completed=total_completed,
        returned_count=returned_count,
        unaccepted_count=unaccepted_count
    )

    await message.answer(stats_text, reply_markup=get_completed_requests_submenu(), parse_mode="HTML")


@router.message(F.text.in_(["📋 Все исполненные", "📋 Ожидают проверки"]))
async def list_all_completed_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать заявки, ожидающие проверки менеджером"""
    lang = message.from_user.language_code or 'ru'

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Все исполненные заявки: статус "Выполнена" и НЕ подтверждены менеджером
    # (ожидают проверки и подтверждения менеджером)
    q = (
        db.query(Request)
        .filter(
            Request.status == REQUEST_STATUS_EXECUTED,
            Request.manager_confirmed == False  # Только НЕподтверждённые менеджером
        )
        .order_by(
            Request.is_returned.desc(),  # Возвратные заявки показываем первыми
            Request.updated_at.desc().nullslast(),
            Request.created_at.desc()
        )
    )
    requests = q.limit(10).all()

    if not requests:
        await message.answer(get_text("admin.handlers.no_completed_requests", language=lang), reply_markup=get_completed_requests_submenu())
        return

    # Добавляем пометку "возвратная" для возвратных заявок
    items = []
    for r in requests:
        item = {
            "request_number": r.request_number,
            "category": r.category,
            "address": r.address,
            "status": "🔄 " + get_text("admin.handlers.returned_label", language=lang) if r.is_returned else r.status
        }
        items.append(item)

    await message.answer(get_text("admin.handlers.all_completed_requests_title", language=lang), reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text == "🔄 Возвращённые")
async def list_returned_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать только возвращённые заявки"""
    lang = message.from_user.language_code or 'ru'

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Только возвращённые заявки
    # Статус "Исполнено" - когда заявка возвращена заявителем на доработку
    q = (
        db.query(Request)
        .filter(
            Request.status == REQUEST_STATUS_COMPLETED,
            Request.is_returned == True
        )
        .order_by(
            Request.returned_at.desc().nullslast(),
            Request.updated_at.desc().nullslast(),
            Request.created_at.desc()
        )
    )
    requests = q.limit(10).all()

    if not requests:
        await message.answer(
            get_text("admin.handlers.no_returned_requests", language=lang),
            reply_markup=get_completed_requests_submenu()
        )
        return

    items = []
    for r in requests:
        # Форматируем информацию о возврате
        return_info = ""
        if r.returned_at:
            return_info = f" • {r.returned_at.strftime('%d.%m %H:%M')}"

        item = {
            "request_number": r.request_number,
            "category": r.category,
            "address": r.address,
            "status": f"🔄 Возврат{return_info}"
        }
        items.append(item)

    await message.answer(
        get_text("admin.handlers.returned_requests_title", language=lang).format(count=len(requests)),
        reply_markup=get_manager_request_list_kb(items, 1, 1),
        parse_mode="HTML"
    )


@router.message(F.text == "⏳ Не принятые")
async def list_unaccepted_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать непринятые заявки (выполненные, но не принятые заявителем)"""
    lang = message.from_user.language_code or 'ru'

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Непринятые заявки: подтверждены менеджером (manager_confirmed = True), но не приняты заявителем (статус != "Принято")
    from datetime import datetime, timezone
    q = (
        db.query(Request)
        .filter(
            Request.status == REQUEST_STATUS_EXECUTED,
            Request.manager_confirmed == True,  # Подтверждено менеджером
            Request.is_returned == False  # Исключаем возвращённые
        )
        .order_by(
            Request.completed_at.desc().nullslast(),
            Request.updated_at.desc().nullslast(),
            Request.created_at.desc()
        )
    )
    requests = q.limit(20).all()

    if not requests:
        await message.answer(
            get_text("admin.handlers.no_unaccepted_requests", language=lang),
            reply_markup=get_completed_requests_submenu(),
            parse_mode="HTML"
        )
        return

    # Форматируем список заявок с указанием времени ожидания
    items = []
    now = datetime.now(timezone.utc)

    for r in requests:
        # Вычисляем время ожидания с момента завершения
        completed_at = r.completed_at if r.completed_at else r.updated_at
        if completed_at:
            # Обеспечиваем что completed_at timezone-aware
            if completed_at.tzinfo is None:
                from datetime import timezone as dt_tz
                completed_at = completed_at.replace(tzinfo=dt_tz.utc)

            waiting_time = now - completed_at
            days = waiting_time.days
            hours = waiting_time.seconds // 3600
            minutes = (waiting_time.seconds % 3600) // 60

            if days > 0:
                time_str = f"{days}д {hours}ч"
            elif hours > 0:
                time_str = f"{hours}ч {minutes}м"
            else:
                time_str = f"{minutes}м"
        else:
            time_str = get_text("admin.handlers.time_unknown", language=lang)

        item = {
            "request_number": r.request_number,
            "category": r.category,
            "address": r.address or get_text("admin.handlers.address_not_specified", language=lang),
            "status": f"⏳ {time_str}"
        }
        items.append(item)

    from uk_management_bot.keyboards.admin import get_manager_request_list_kb
    await message.answer(
        get_text("admin.handlers.unaccepted_requests_title", language=lang).format(count=len(requests)),
        reply_markup=get_manager_request_list_kb(items, 1, 1),
        parse_mode="HTML"
    )


@router.message(F.text == "🔙 Назад в меню")
async def back_to_main_menu(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Вернуться в главное меню"""
    lang = message.from_user.language_code or 'ru'

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Импортируем правильную функцию для главного меню
    from uk_management_bot.keyboards.base import get_main_keyboard_for_role

    # Используем универсальную клавиатуру для активной роли пользователя
    await message.answer(
        get_text("menu.main", language=lang),
        reply_markup=get_main_keyboard_for_role(active_role or user.role, roles or [user.role], user.status)
    )


@router.message(F.text == "📦 Архив")
async def list_archive_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать архивные заявки"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Архив: только завершенные статусы (Выполнена, Исполнено, Принято, Отменена)
    archive_statuses = [REQUEST_STATUS_EXECUTED, REQUEST_STATUS_COMPLETED, REQUEST_STATUS_APPROVED, REQUEST_STATUS_CANCELLED]
    q = (
        db.query(Request)
        .filter(Request.status.in_(archive_statuses))
        .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
    )
    requests = q.limit(10).all()
    if not requests:
        await message.answer(get_text("admin.handlers.archive_empty", language=lang), reply_markup=get_manager_main_keyboard())
        return
    # Каждую заявку отправляем отдельным сообщением
    for r in requests:
        addr = r.address[:60] + ("…" if len(r.address) > 60 else "")
        text = (
            f"{get_status_with_emoji(r.status, language=lang)} #{r.request_number} • {r.category}\n"
            + get_text("admin.handlers.archive_address", language=lang).format(address=addr) + "\n"
            + get_text("admin.handlers.archive_created", language=lang).format(created_at=r.created_at.strftime('%d.%m.%Y %H:%M'))
        )
        if r.notes and r.notes.strip():
            if r.status == REQUEST_STATUS_CANCELLED:
                text += "\n" + get_text("admin.handlers.archive_cancel_reason", language=lang).format(reason=r.notes.strip())
            else:
                text += "\n" + get_text("admin.handlers.archive_notes", language=lang).format(notes=r.notes.strip())
        await message.answer(text)
    await message.answer(get_text("admin.handlers.archive_end", language=lang), reply_markup=get_manager_main_keyboard())

@router.message(F.text == "💰 Закуп")
async def list_procurement_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать заявки в статусе закупа"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Получаем заявки в статусе "Закуп"
    q = (
        db.query(Request)
        .filter(Request.status == REQUEST_STATUS_PURCHASE)
        .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
    )
    requests = q.limit(10).all()

    if not requests:
        await message.answer(get_text("admin.handlers.no_procurement_requests", language=lang), reply_markup=get_manager_main_keyboard())
        return

    # Каждую заявку отправляем отдельным сообщением
    for r in requests:
        addr = r.address[:60] + ("…" if len(r.address) > 60 else "")
        text = (
            f"{get_status_with_emoji(r.status, language=lang)} #{r.request_number} • {r.category}\n"
            + get_text("admin.handlers.archive_address", language=lang).format(address=addr) + "\n"
            + get_text("admin.handlers.archive_created", language=lang).format(created_at=r.created_at.strftime('%d.%m.%Y %H:%M'))
        )
        # Показываем запрошенные материалы и комментарии менеджера
        if r.requested_materials:
            text += "\n" + get_text("admin.handlers.procurement_requested", language=lang).format(materials=r.requested_materials)
        if r.manager_materials_comment:
            text += "\n" + get_text("admin.handlers.procurement_manager_comment", language=lang).format(comment=r.manager_materials_comment)
        # Для совместимости со старыми записями
        if not r.requested_materials and r.purchase_materials:
            text += "\n" + get_text("admin.handlers.procurement_materials", language=lang).format(materials=r.purchase_materials)

        # Создаем инлайн клавиатуру для действий с заявкой
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("admin.handlers.btn_return_to_work", language=lang), callback_data=f"purchase_return_to_work_{r.request_number}")],
            [InlineKeyboardButton(text=get_text("admin.handlers.btn_manager_comment", language=lang), callback_data=f"edit_materials_{r.request_number}")]
        ])

        await message.answer(text, reply_markup=keyboard)

    await message.answer(get_text("admin.handlers.procurement_end", language=lang), reply_markup=get_manager_main_keyboard())
    logger.info(f"Показаны заявки в статусе закуп менеджеру {message.from_user.id}")






# ===== ОБРАБОТЧИКИ СОЗДАНИЯ ПРИГЛАШЕНИЙ =====

@router.message(F.text == "📨 Создать приглашение")
async def start_invite_creation(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Начать процесс создания приглашения"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа (только менеджеры могут создавать приглашения)
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("invites.manager_only", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    await message.answer(
        get_text("invites.select_role", language=lang),
        reply_markup=get_invite_role_keyboard()
    )


@router.callback_query(F.data.startswith("invite_role_"))
async def handle_invite_role_selection(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработчик выбора роли для приглашения"""
    lang = callback.from_user.language_code or 'ru'
    
    # Извлекаем роль из callback_data
    role = callback.data.replace("invite_role_", "")
    
    if role not in ["applicant", "executor", "manager"]:
        await callback.answer(get_text("admin.handlers.invalid_role", language=lang))
        return
    
    # Сохраняем роль в состоянии
    await state.update_data(role=role)
    
    # Если выбрана роль executor, нужно выбрать специализацию
    if role == "executor":
        await callback.message.edit_text(
            get_text("invites.select_specialization", language=lang),
            reply_markup=get_invite_specialization_keyboard()
        )
        await state.set_state(InviteCreationStates.waiting_for_specialization)
    else:
        # Для других ролей переходим к выбору срока действия
        await callback.message.edit_text(
            get_text("invites.select_expiry", language=lang),
            reply_markup=get_invite_expiry_keyboard()
        )
        await state.set_state(InviteCreationStates.waiting_for_expiry)
    
    await callback.answer()


@router.callback_query(F.data.startswith("invite_spec_"))
async def handle_invite_specialization_selection(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработчик выбора специализации для исполнителя"""
    lang = callback.from_user.language_code or 'ru'
    
    # Извлекаем специализацию из callback_data
    specialization = callback.data.replace("invite_spec_", "")
    
    # Сохраняем специализацию в состоянии
    await state.update_data(specialization=specialization)
    
    # Переходим к выбору срока действия
    await callback.message.edit_text(
        get_text("invites.select_expiry", language=lang),
        reply_markup=get_invite_expiry_keyboard()
    )
    await state.set_state(InviteCreationStates.waiting_for_expiry)
    
    await callback.answer()


@router.callback_query(F.data.startswith("invite_expiry_"))
async def handle_invite_expiry_selection(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработчик выбора срока действия приглашения"""
    lang = callback.from_user.language_code or 'ru'
    
    # Извлекаем срок действия из callback_data
    expiry = callback.data.replace("invite_expiry_", "")
    
    # Преобразуем в часы
    expiry_hours = {
        "1h": 1,
        "24h": 24,
        "7d": 168  # 7 дней * 24 часа
    }.get(expiry, 24)
    
    # Сохраняем срок действия в состоянии
    await state.update_data(expiry_hours=expiry_hours)
    
    # Получаем данные из состояния для подтверждения
    data = await state.get_data()
    role = data.get("role", "unknown")
    specialization = data.get("specialization", "")
    expiry_text = {
        1: get_text("admin.handlers.expiry_1h", language=lang),
        24: get_text("admin.handlers.expiry_24h", language=lang),
        168: get_text("admin.handlers.expiry_7d", language=lang)
    }.get(expiry_hours, get_text("admin.handlers.expiry_24h", language=lang))
    
    # Формируем текст подтверждения
    role_name = get_text(f"roles.{role}", language=lang)
    confirmation_text = get_text("admin.handlers.invite_confirm_header", language=lang) + "\n\n"
    confirmation_text += get_text("admin.handlers.invite_confirm_role", language=lang).format(role_name=role_name) + "\n"

    if role == "executor" and specialization:
        spec_name = get_text(f"specializations.{specialization}", language=lang)
        confirmation_text += get_text("admin.handlers.invite_confirm_spec", language=lang).format(spec_name=spec_name) + "\n"

    confirmation_text += get_text("admin.handlers.invite_confirm_expiry", language=lang).format(expiry_text=expiry_text) + "\n\n"
    confirmation_text += get_text("admin.handlers.invite_confirm_instruction", language=lang)
    
    await callback.message.edit_text(
        confirmation_text,
        reply_markup=get_invite_confirmation_keyboard()
    )
    await state.set_state(InviteCreationStates.waiting_for_confirmation)
    
    await callback.answer()


@router.callback_query(F.data == "invite_confirm")
async def handle_invite_confirmation(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработчик подтверждения создания приглашения"""
    lang = callback.from_user.language_code or 'ru'
    
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        role = data.get("role")
        specialization = data.get("specialization", "")
        expiry_hours = data.get("expiry_hours", 24)
        
        if not role:
            await callback.answer(get_text("admin.handlers.error_role_not_selected", language=lang))
            return
        
        # Создаем приглашение в виде ссылки
        invite_service = InviteService(db)
        invite_link = invite_service.generate_invite_link(
            role=role,
            created_by=callback.from_user.id,
            specialization=specialization if role == "executor" else None,
            hours=expiry_hours
        )
        
        # Генерируем токен отдельно для отображения
        token = invite_service.generate_invite(
            role=role,
            created_by=callback.from_user.id,
            specialization=specialization if role == "executor" else None,
            hours=expiry_hours
        )
        
        # Формируем текст с токеном
        role_name = get_text(f"roles.{role}", language=lang)
        expiry_text = {
            1: "1 час",
            24: "24 часа", 
            168: "7 дней"
        }.get(expiry_hours, "24 часа")
        
        success_text = get_text("admin.handlers.invite_created_header", language=lang) + "\n\n"
        success_text += get_text("admin.handlers.invite_confirm_role", language=lang).format(role_name=role_name) + "\n"

        if role == "executor" and specialization:
            spec_name = get_text(f"specializations.{specialization}", language=lang)
            success_text += get_text("admin.handlers.invite_confirm_spec", language=lang).format(spec_name=spec_name) + "\n"

        success_text += get_text("admin.handlers.invite_confirm_expiry", language=lang).format(expiry_text=expiry_text) + "\n\n"
        success_text += get_text("admin.handlers.invite_link_label", language=lang) + "\n\n"
        success_text += f"`{invite_link}`\n\n"
        success_text += get_text("admin.handlers.invite_instructions", language=lang).format(token=token)
        
        await callback.message.edit_text(
            success_text
        )
        await callback.message.answer(
            get_text("admin.handlers.back_to_admin_panel", language=lang),
            reply_markup=get_manager_main_keyboard()
        )
        
        # Очищаем состояние
        await state.clear()
        
        logger.info(f"Пользователь {callback.from_user.id} создал приглашение для роли {role}")
        
    except Exception as e:
        logger.error(f"Ошибка создания приглашения: {e}")
        await callback.message.edit_text(
            get_text("errors.unknown_error", language=lang)
        )
        await callback.message.answer(
            get_text("admin.handlers.back_to_admin_panel", language=lang),
            reply_markup=get_manager_main_keyboard()
        )
        await state.clear()
    
    await callback.answer()


@router.callback_query(F.data == "invite_cancel")
async def handle_invite_cancel(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработчик отмены создания приглашения"""
    lang = callback.from_user.language_code or 'ru'
    
    await callback.message.edit_text(
        get_text("buttons.operation_cancelled", language=lang)
    )
    await callback.message.answer(
        "Вернуться в админ-панель:",
        reply_markup=get_manager_main_keyboard()
    )
    
    # Очищаем состояние
    await state.clear()
    
    await callback.answer()


# ===== ОБРАБОТЧИКИ ДЕЙСТВИЙ С ЗАЯВКАМИ ДЛЯ МЕНЕДЖЕРОВ =====

@router.callback_query(lambda c: c.data.startswith("accept_") and not c.data.startswith("accept_request_"))
async def handle_accept_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка принятия заявки менеджером - показ выбора типа назначения"""
    try:
        lang = callback.from_user.language_code or 'ru'
        logger.info(f"Обработка принятия заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("accept_", "")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Обновляем статус на "В работе"
        old_status = request.status
        request.status = REQUEST_STATUS_IN_PROGRESS
        request.updated_at = datetime.now()

        # Аудит
        from uk_management_bot.database.models.audit import AuditLog
        db.add(AuditLog(
            user_id=user.id if user else None,
            action="request_status_changed",
            details={
                "request_number": request.request_number,
                "old_status": old_status,
                "new_status": REQUEST_STATUS_IN_PROGRESS,
                "actor": "manager_assign",
            }
        ))
        db.commit()

        # Показываем выбор типа назначения
        await callback.message.edit_text(
            get_text("admin.handlers.request_accepted_choose_assignment", language=lang).format(
                request_number=request_number,
                category=request.category,
                address=request.address
            ),
            reply_markup=get_assignment_type_keyboard(request_number),
            parse_mode="HTML"
        )

        logger.info(f"Заявка {request_number} принята менеджером {callback.from_user.id}, ожидание выбора типа назначения")

    except Exception as e:
        logger.error(f"Ошибка обработки принятия заявки менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("deny_"))
async def handle_deny_request(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка отклонения заявки менеджером"""
    try:
        lang = callback.from_user.language_code or 'ru'
        logger.info(f"Обработка отклонения заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("deny_", "")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Запрашиваем причину отклонения
        await callback.message.edit_text(
            get_text("admin.handlers.deny_request_prompt", language=lang).format(
                request_number=request_number,
                category=request.category,
                address=request.address
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_{request_number}")]
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
async def handle_clarify_request(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка запроса уточнения по заявке"""
    try:
        lang = callback.from_user.language_code or 'ru'
        logger.info(f"Обработка запроса уточнения по заявке менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("clarify_", "")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
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
                category=request.category,
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
        logger.error(f"Ошибка обработки запроса уточнения: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "cancel_clarification")
async def handle_cancel_clarification(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Отмена уточнения"""
    try:
        lang = callback.from_user.language_code or 'ru'
        # Очищаем состояние
        await state.clear()

        # Возвращаемся к списку заявок
        await handle_manager_back_to_list(callback, db, roles, active_role, user)

        await callback.answer(get_text("admin.handlers.clarification_cancelled", language=lang))

    except Exception as e:
        logger.error(f"Ошибка отмены уточнения: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(lambda c: c.data.startswith("purchase_") and not c.data.startswith("purchase_materials_"))
async def handle_purchase_request(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка перевода заявки в статус 'Закуп' менеджером"""
    try:
        lang = callback.from_user.language_code or 'ru'
        logger.info(f"Обработка перевода заявки в закуп менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("purchase_", "")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
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
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_{request_number}")]
            ])
        )
        
        # Сохраняем состояние
        from uk_management_bot.states.request_status import RequestStatusStates
        from aiogram.fsm.context import FSMContext
        
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


@router.callback_query(F.data.startswith("complete_"))
async def handle_complete_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка завершения заявки менеджером"""
    try:
        lang = callback.from_user.language_code or 'ru'
        logger.info(f"Обработка завершения заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("complete_", "")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return
        
        # Обновляем статус
        old_status = request.status
        request.status = REQUEST_STATUS_EXECUTED
        request.completed_at = datetime.now()
        request.updated_at = datetime.now()

        # Аудит
        from uk_management_bot.database.models.audit import AuditLog
        db.add(AuditLog(
            user_id=user.id if user else None,
            action="request_status_changed",
            details={
                "request_number": request.request_number,
                "old_status": old_status,
                "new_status": REQUEST_STATUS_EXECUTED,
                "actor": "manager_complete",
            }
        ))
        db.commit()

        await callback.answer(get_text("admin.handlers.request_marked_completed", language=lang))
        
        # Возвращаемся к списку заявок
        await handle_manager_back_to_list(callback, db, roles, active_role, user)
        
        logger.info(f"Заявка {request_number} отмечена как выполненная менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки завершения заявки менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(
    F.data.startswith("delete_") &
    ~F.data.startswith("delete_employee_")
)
async def handle_delete_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка удаления заявки администратором (только для админов!)"""
    try:
        lang = callback.from_user.language_code or 'ru'
        logger.info(f"Попытка удаления заявки пользователем {callback.from_user.id}")

        # Проверяем права доступа - ТОЛЬКО АДМИНИСТРАТОРЫ могут удалять заявки
        import os
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]

        if callback.from_user.id not in admin_ids:
            await callback.answer(get_text("admin.handlers.delete_admin_only", language=lang), show_alert=True)
            logger.warning(f"Пользователь {callback.from_user.id} попытался удалить заявку без прав администратора")
            return
        
        request_number = callback.data.replace("delete_", "")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Сначала удаляем все связанные записи
        from uk_management_bot.database.models.rating import Rating
        from uk_management_bot.database.models.request_comment import RequestComment
        from uk_management_bot.database.models.request_assignment import RequestAssignment

        # Удаляем рейтинги
        db.query(Rating).filter(Rating.request_number == request_number).delete()

        # Удаляем комментарии
        db.query(RequestComment).filter(RequestComment.request_number == request_number).delete()

        # Удаляем назначения
        db.query(RequestAssignment).filter(RequestAssignment.request_number == request_number).delete()

        # Теперь удаляем саму заявку
        db.delete(request)
        db.commit()
        
        await callback.answer(get_text("admin.handlers.request_deleted", language=lang))

        # Возвращаемся к списку заявок
        await handle_manager_back_to_list(callback, db, roles, active_role, user)

        logger.info(f"Заявка {request_number} удалена менеджером {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки удаления заявки менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.message(ManagerStates.waiting_for_clarification_text)
async def handle_clarification_text(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка текста уточнения от менеджера"""
    try:
        lang = message.from_user.language_code or 'ru'
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

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
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

        # Добавляем уточнение в примечания заявки
        timestamp = datetime.now().strftime('%d.%m.%Y %H:%M')
        new_note = f"--- УТОЧНЕНИЕ {timestamp} ---\n"
        new_note += f"👨‍💼 {manager_name}:\n"
        new_note += f"{clarification_text}"
        
        # Обновляем примечания
        if request.notes and request.notes.strip():
            request.notes = request.notes.strip() + "\n\n" + new_note
        else:
            request.notes = new_note
        
        # Обновляем статус на "Уточнение" если он еще не такой
        old_status = request.status
        if request.status != REQUEST_STATUS_CLARIFICATION:
            request.status = REQUEST_STATUS_CLARIFICATION

            # Аудит
            from uk_management_bot.database.models.audit import AuditLog
            db.add(AuditLog(
                user_id=user.id if user else None,
                action="request_status_changed",
                details={
                    "request_number": request.request_number,
                    "old_status": old_status,
                    "new_status": REQUEST_STATUS_CLARIFICATION,
                    "actor": "manager_clarification",
                }
            ))

        request.updated_at = datetime.now()
        db.commit()
        
        # Отправляем уведомление заявителю
        try:
            from uk_management_bot.services.notification_service import send_to_user
            from uk_management_bot.database.models.user import User as UserModel
            
            # Получаем telegram_id пользователя
            user_obj = db.query(UserModel).filter(UserModel.id == request.user_id).first()
            if user_obj and user_obj.telegram_id:
                notification_text = get_text("admin.handlers.notify_user_clarification", language=lang).format(
                    request_number=request.request_number,
                    category=request.category,
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
async def handle_cancel_reason_text(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка причины отклонения заявки"""
    try:
        lang = message.from_user.language_code or 'ru'
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
        request = db.query(Request).filter(Request.request_number == request_number).first()
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

        # Обновляем статус и добавляем примечание
        old_status = request.status
        request.status = REQUEST_STATUS_CANCELLED
        cancel_note = f"Отклонена менеджером {manager_name} {datetime.now().strftime('%d.%m.%Y %H:%M')}\nПричина: {cancel_reason}"
        
        if request.notes and request.notes.strip():
            request.notes = request.notes.strip() + "\n\n" + cancel_note
        else:
            request.notes = cancel_note
        # Аудит
        from uk_management_bot.database.models.audit import AuditLog
        db.add(AuditLog(
            user_id=user.id if user else None,
            action="request_status_changed",
            details={
                "request_number": request.request_number,
                "old_status": old_status,
                "new_status": REQUEST_STATUS_CANCELLED,
                "actor": "manager_cancel",
            }
        ))

        request.updated_at = datetime.now()
        db.commit()

        await message.answer(
            get_text("admin.handlers.request_denied", language=lang).format(
                request_number=request_number,
                cancel_reason=cancel_reason
            ),
            reply_markup=get_manager_main_keyboard()
        )

        # Очищаем состояние
        await state.clear()

        logger.info(f"Заявка {request_number} отклонена менеджером {message.from_user.id} с причиной: {cancel_reason}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки причины отклонения: {e}")
        await message.answer(get_text("admin.handlers.error_denying_request", language=lang))
        await state.clear()


@router.message(F.text == "👥 Смены")
async def handle_admin_shifts_button(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработчик кнопки 'Смены' в админ панели"""
    lang = message.from_user.language_code or 'ru'
    
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
            reply_markup=get_manager_main_keyboard(),
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
            reply_markup=get_manager_main_keyboard()
        )


@router.callback_query(F.data.startswith("purchase_return_to_work_"))
async def handle_return_to_work(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка возврата заявки из закупа в работу"""
    try:
        lang = callback.from_user.language_code or 'ru'
        logger.info(f"Возврат заявки из закупа в работу менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return
        
        request_number = callback.data.replace("purchase_return_to_work_", "")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем, что заявка в статусе "Закуп"
        if request.status != REQUEST_STATUS_PURCHASE:
            await callback.answer(get_text("admin.handlers.request_not_in_purchase", language=lang), show_alert=True)
            return

        # Добавляем разделитель закупки к списку материалов
        if request.requested_materials:
            current_date = datetime.now().strftime('%d.%m.%Y %H:%M')
            procurement_separator = f"--закуплено {current_date}--"
            
            # Добавляем разделитель к существующим материалам
            request.requested_materials += f"\n{procurement_separator}\n"
            
            # Сохраняем информацию в историю для отчетности
            if request.manager_materials_comment:
                manager_comment = request.manager_materials_comment
            else:
                manager_comment = "Без комментариев"
            
            history_entry = (
                f"ЗАКУП ЗАВЕРШЕН:\n"
                f"Материалы: {request.requested_materials.split(f'{procurement_separator}')[0].strip()}\n"
                f"Комментарий менеджера: {manager_comment}\n"
                f"Дата завершения: {current_date}"
            )
            
            if request.purchase_history:
                request.purchase_history += f"\n\n===\n\n{history_entry}"
            else:
                request.purchase_history = history_entry
        
        # Обновляем статус на "В работе"
        old_status = request.status
        request.status = REQUEST_STATUS_IN_PROGRESS
        request.updated_at = datetime.now()

        # Аудит
        from uk_management_bot.database.models.audit import AuditLog
        db.add(AuditLog(
            user_id=user.id if user else None,
            action="request_status_changed",
            details={
                "request_number": request.request_number,
                "old_status": old_status,
                "new_status": REQUEST_STATUS_IN_PROGRESS,
                "actor": "manager_approve_purchase",
            }
        ))
        db.commit()

        await callback.answer(get_text("admin.handlers.request_returned_to_work_short", language=lang))

        # Загружаем обновленный список заявок в закупе
        q = (
            db.query(Request)
            .filter(Request.status == REQUEST_STATUS_PURCHASE)
            .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
        )
        requests = q.limit(10).all()
        
        if not requests:
            await callback.message.edit_text(get_text("admin.handlers.no_procurement_requests", language=lang), reply_markup=get_manager_main_keyboard())
            return

        # Показываем обновленный список заявок в закупе
        text = get_text("admin.handlers.procurement_updated_list", language=lang) + "\n\n"
        for i, r in enumerate(requests, 1):
            addr = r.address[:40] + ("…" if len(r.address) > 40 else "")
            text += f"{i}. #{r.request_number} - {r.category}\n"
            text += f"   📍 {addr}\n\n"
        
        await callback.message.edit_text(text, reply_markup=get_manager_main_keyboard())
        
        logger.info(f"Заявка {request_number} возвращена в работу менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка возврата заявки из закупа в работу: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("edit_materials_"))
async def handle_edit_materials(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка редактирования списка материалов для закупа"""
    try:
        lang = callback.from_user.language_code or 'ru'
        logger.info(f"Редактирование списка материалов менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return
        
        request_number = callback.data.replace("edit_materials_", "")
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
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
async def handle_materials_edit_text(message: Message, state: FSMContext, db: Session, user: User = None):
    """Обработка нового текста списка материалов"""
    try:
        lang = message.from_user.language_code or 'ru'
        data = await state.get_data()
        request_number = data.get("edit_materials_request_number")

        if not request_number:
            await message.answer(get_text("admin.handlers.error_request_not_found_state", language=lang))
            await state.clear()
            return

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await message.answer(get_text("admin.handlers.request_not_found", language=lang))
            await state.clear()
            return
        
        # Обновляем комментарий менеджера к материалам (запрошенные материалы НЕ изменяем)
        old_comment = request.manager_materials_comment
        new_comment = message.text.strip()
        request.manager_materials_comment = new_comment
        request.updated_at = datetime.now()
        
        # Обновляем историю закупов для сохранения данных
        requested_materials = request.requested_materials or "Не указано"
        purchase_history_entry = (
            f"Запрошенные материалы: {requested_materials}\n"
            f"Комментарий менеджера: {new_comment}\n"
            f"Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        if request.purchase_history:
            request.purchase_history += f"\n\n---\n\n{purchase_history_entry}"
        else:
            request.purchase_history = purchase_history_entry
            
        db.commit()
        
        await message.answer(get_text("admin.handlers.materials_comment_updated", language=lang).format(request_number=request_number), reply_markup=get_manager_main_keyboard())
        
        # Добавляем комментарий об изменении
        if user:
            try:
                from uk_management_bot.services.comment_service import CommentService
                comment_service = CommentService(db)
                comment_text = f"Комментарии к материалам изменены менеджером:\n\nБыло: {old_comment or 'Комментарий отсутствовал'}\n\nСтало: {new_comment}"
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


# ===== ОБРАБОТЧИКИ НАЗНАЧЕНИЯ ИСПОЛНИТЕЛЕЙ =====

@router.callback_query(F.data.startswith("assign_duty_"))
async def handle_assign_duty_executor_admin(callback: CallbackQuery, db: Session, user: User = None):
    """Назначение дежурного специалиста (автоматическое по сменам)"""
    try:
        lang = callback.from_user.language_code or 'ru'
        request_number = callback.data.replace("assign_duty_", "")
        logger.info(f"Назначение дежурного специалиста для заявки {request_number}")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
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
                await callback.answer("✅ Назначение выполнено успешно", show_alert=False)
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
async def handle_assign_specific_executor_admin(callback: CallbackQuery, db: Session):
    """Показать список исполнителей для ручного выбора"""
    try:
        lang = callback.from_user.language_code or 'ru'
        request_number = callback.data.replace("assign_specific_", "")
        logger.info(f"Выбор конкретного исполнителя для заявки {request_number}")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Получаем исполнителей с нужной специализацией
        category_to_spec = {
            "Сантехника": "plumber",
            "Электрика": "electrician",
            "Благоустройство": "landscaping",
            "Уборка": "cleaning",
            "Безопасность": "security",
            "Охрана": "security",  # Дубликат для совместимости
            "Ремонт": "repair",
            "Установка": "installation",
            "Обслуживание": "maintenance",
            "HVAC": "hvac",
            "Отопление": "hvac",
            "Вентиляция": "hvac"
        }

        spec = category_to_spec.get(request.category, "other")

        logger.info(f"[SPECIFIC_ASSIGN] Категория '{request.category}' → специализация: '{spec}'")

        # Получаем всех исполнителей с данной специализацией
        import json

        # ИСПРАВЛЕНО: проверяем наличие роли "executor" в массиве roles
        # Используем JSONB operator @> для проверки вхождения элемента в массив
        from sqlalchemy import cast, String
        executors = db.query(User).filter(
            User.roles.cast(String).contains('"executor"'),
            User.status == "approved"
        ).all()

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
                category=request.category,
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
async def handle_final_executor_assignment_admin(callback: CallbackQuery, db: Session, user: User = None):
    """Финальное назначение конкретного исполнителя"""
    try:
        lang = callback.from_user.language_code or 'ru'
        # Парсим данные: assign_executor_251013-001_123
        parts = callback.data.replace("assign_executor_", "").split("_")
        request_number = parts[0]
        executor_id = int(parts[1])

        logger.info(f"Финальное назначение исполнителя {executor_id} на заявку {request_number}")

        # Получаем заявку и исполнителя
        request = db.query(Request).filter(Request.request_number == request_number).first()
        executor = db.query(User).filter(User.id == executor_id).first()

        if not request or not executor:
            await callback.answer(get_text("admin.handlers.request_or_executor_not_found", language=lang), show_alert=True)
            return

        # Получаем менеджера (текущий пользователь)
        if not user:
            user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
            if not user:
                await callback.answer(get_text("admin.handlers.error_user_not_found", language=lang), show_alert=True)
                return

        # Назначаем исполнителя через новую систему AssignmentService
        from uk_management_bot.services.assignment_service import AssignmentService
        assignment_service = AssignmentService(db)

        try:
            # Используем индивидуальное назначение с user.id вместо telegram_id
            assignment = assignment_service.assign_to_executor(
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
            category=request.category,
            address=address_display
        )

        try:
            await callback.message.edit_text(success_message, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                await callback.answer("✅ Назначение выполнено успешно", show_alert=False)
                logger.info(f"Сообщение не изменилось для заявки {request_number}")
            else:
                # Отправляем новое сообщение
                await callback.message.answer(success_message, parse_mode="HTML")
                await callback.answer()

        # Отправляем уведомление исполнителю
        try:
            from aiogram import Bot
            bot = Bot.get_current()

            # Ограничиваем длину текста для предотвращения MESSAGE_TOO_LONG
            # Telegram лимит: 4096 символов
            # Уменьшаем лимиты ещё больше для безопасности
            MAX_ADDRESS_LENGTH = 150
            MAX_DESCRIPTION_LENGTH = 300

            address = request.address[:MAX_ADDRESS_LENGTH] + "..." if len(request.address) > MAX_ADDRESS_LENGTH else request.address
            description = request.description[:MAX_DESCRIPTION_LENGTH] + "..." if len(request.description) > MAX_DESCRIPTION_LENGTH else request.description

            notification_text = get_text("admin.handlers.notify_executor_assigned", language=lang).format(
                request_number=request.format_number_for_display(),
                category=request.category,
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
async def handle_back_to_assignment_type_admin(callback: CallbackQuery, db: Session):
    """Возврат к выбору типа назначения"""
    try:
        lang = callback.from_user.language_code or 'ru'
        request_number = callback.data.replace("back_to_assignment_type_", "")

        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        await callback.message.edit_text(
            get_text("admin.handlers.request_accepted_choose_assignment", language=lang).format(
                request_number=request_number,
                category=request.category,
                address=request.address
            ),
            reply_markup=get_assignment_type_keyboard(request_number),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к выбору типа назначения: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)

