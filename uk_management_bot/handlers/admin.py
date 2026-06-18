from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.orm import Session

from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.keyboards.admin import (
    get_manager_main_keyboard,
    get_manager_request_list_kb,
    get_invite_role_keyboard,
    get_invite_specialization_keyboard,
    get_invite_expiry_keyboard,
    get_invite_confirmation_keyboard,
    get_completed_requests_submenu,
    get_assignment_type_keyboard,
    get_executors_by_category_keyboard,
)
from uk_management_bot.keyboards.base import get_user_contextual_keyboard
from uk_management_bot.constants.categories import CATEGORY_TO_SPECIALIZATION
from uk_management_bot.services.invite_service import InviteService
from uk_management_bot.services.notification_service import async_notify_request_status_changed
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_CANCELLED,
)
from uk_management_bot.utils.workflow_predicates import (
    is_awaiting_applicant,
    is_awaiting_manager,
)

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.status_display import get_status_display, get_status_with_emoji
from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display, get_urgency_display
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.utils.auth_helpers import has_admin_access, legacy_primary_role
from uk_management_bot.filters import RoleFilter
from datetime import datetime, timezone
from uk_management_bot.services.request_number_service import REQUEST_NUMBER_CORE
from uk_management_bot.utils.button_texts import (
    get_admin_panel_texts,
    get_test_middleware_texts,
    get_admin_user_management_texts,
    get_admin_employee_management_texts,
    get_admin_new_requests_texts,
    get_admin_active_requests_texts,
    get_admin_completed_requests_texts,
    get_admin_awaiting_review_texts,
    get_admin_returned_texts,
    get_admin_not_accepted_texts,
    get_admin_back_to_menu_texts,
    get_admin_archive_texts,
    get_admin_purchase_texts,
    get_admin_create_invite_texts,
    get_admin_shifts_texts,
)
from uk_management_bot.states.invite_creation import InviteCreationStates

router = Router()
logger = logging.getLogger(__name__)

# PR-25 (BUG-BOT-034): manager accept_/purchase_ actions bound to the shared
# request-number core (strict regex) instead of open-set startswith+exclusion
# lambdas, so accept_request_/purchase_materials_ and any future accept_*/
# purchase_* callbacks fall through to their own handlers.
_ACCEPT_REQUEST_NUMBER_RE = rf"^accept_{REQUEST_NUMBER_CORE}$"
_PURCHASE_REQUEST_NUMBER_RE = rf"^purchase_{REQUEST_NUMBER_CORE}$"

# Single Source of Truth for button texts - TASK 17
ADMIN_PANEL_TEXTS = get_admin_panel_texts()
TEST_MIDDLEWARE_TEXTS = get_test_middleware_texts()
ADMIN_USER_MANAGEMENT_TEXTS = get_admin_user_management_texts()
ADMIN_EMPLOYEE_MANAGEMENT_TEXTS = get_admin_employee_management_texts()
ADMIN_NEW_REQUESTS_TEXTS = get_admin_new_requests_texts()
ADMIN_ACTIVE_REQUESTS_TEXTS = get_admin_active_requests_texts()
ADMIN_COMPLETED_REQUESTS_TEXTS = get_admin_completed_requests_texts()
ADMIN_AWAITING_REVIEW_TEXTS = get_admin_awaiting_review_texts()
ADMIN_RETURNED_TEXTS = get_admin_returned_texts()
ADMIN_NOT_ACCEPTED_TEXTS = get_admin_not_accepted_texts()
ADMIN_BACK_TO_MENU_TEXTS = get_admin_back_to_menu_texts()
ADMIN_ARCHIVE_TEXTS = get_admin_archive_texts()
ADMIN_PURCHASE_TEXTS = get_admin_purchase_texts()
ADMIN_CREATE_INVITE_TEXTS = get_admin_create_invite_texts()
ADMIN_SHIFTS_TEXTS = get_admin_shifts_texts()

class ManagerStates(StatesGroup):
    cancel_reason = State()
    clarify_reason = State()
    waiting_for_clarification_text = State()
    waiting_for_materials_edit = State()


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
        logger.info(f"[AUTO_ASSIGN] Начало автоматического назначения для заявки {request.request_number}, категория: {request.category}")

        category_to_specialization = CATEGORY_TO_SPECIALIZATION

        # Определяем специализацию по категории заявки
        specialization = category_to_specialization.get(request.category)
        logger.info(f"[AUTO_ASSIGN] Категория '{request.category}' → специализация: {specialization}")

        if not specialization:
            logger.warning(f"[AUTO_ASSIGN] Неизвестная категория заявки: {request.category}, доступные: {list(category_to_specialization.keys())}")
            return
        
        # Находим исполнителей с нужной специализацией
        logger.info("[AUTO_ASSIGN] Выполнение запроса к таблице users...")

        # AUD3-01: кандидаты — по roles-массиву (исполнитель может быть с активной
        # ролью applicant), НЕ по active_role; специализации — единый парсер
        # (JSON-list/CSV/скаляр) вместо локального json.loads.
        from uk_management_bot.utils.auth_helpers import get_user_roles
        from uk_management_bot.utils.constants import ROLE_EXECUTOR
        from uk_management_bot.utils.specializations import parse_specializations

        svc = AdminHandlerService(db)
        approved_users = svc.list_approved_users()
        logger.info(f"[AUTO_ASSIGN] Approved-пользователей всего: {len(approved_users)}")

        matching_executors = [
            ex for ex in approved_users
            if ROLE_EXECUTOR in get_user_roles(ex)
            and specialization in parse_specializations(ex)
        ]

        logger.info(f"[AUTO_ASSIGN] Найдено {len(matching_executors)} подходящих исполнителей для специализации '{specialization}'")

        if not matching_executors:
            logger.warning(f"[AUTO_ASSIGN] Не найдено исполнителей для специализации {specialization}")
            return
        
        # Проверяем, есть ли уже назначение для этой заявки
        existing_assignment = svc.get_active_assignment(request.request_number)

        if existing_assignment:
            logger.info(f"[AUTO_ASSIGN] Заявка {request.request_number} уже назначена (ID: {existing_assignment.id}), пропускаем")
            return

        # Дополнительная проверка на групповые назначения для той же специализации
        existing_group_assignment = svc.get_active_group_assignment(
            request.request_number, specialization
        )

        if existing_group_assignment:
            logger.info(f"[AUTO_ASSIGN] Заявка {request.request_number} уже назначена группе {specialization}, пропускаем")
            return

        logger.info(f"[AUTO_ASSIGN] Назначений для заявки {request.request_number} не найдено, создаем новое групповое назначение")

        # SSOT-кластер #1, PR2d: запись назначения (RequestAssignment +
        # request.assignment_type/assigned_group/assigned_at/assigned_by) через
        # allowlist-слой assignment_service вместо сырого ORM в хендлере.
        # _notify_group_assignment (in-app) — внутри сервиса; кастомный
        # on-shift Telegram-дути-нотифай ниже сохранён (другой канал/таргетинг).
        from uk_management_bot.services.assignment_service import AssignmentService
        AssignmentService(db).assign_to_group(request.request_number, specialization, manager.id)
        svc.refresh(request)

        logger.info(f"[AUTO_ASSIGN] ✅ Заявка {request.request_number} автоматически назначена группе {specialization} ({len(matching_executors)} исполнителей)")

        # Отправляем уведомления исполнителям в активных сменах
        from datetime import datetime as dt
        from uk_management_bot.services.notification_service import _get_shared_bot

        bot = _get_shared_bot()
        now = dt.now()

        # Находим исполнителей в активных сменах с нужной специализацией
        for executor in matching_executors:
            # Проверяем активную смену
            active_shift = svc.get_active_shift_for(executor.id, now)

            if active_shift:
                try:
                    notification_text = get_text("admin.handlers.new_request_for_duty", language="ru").format(
                        specialization=specialization,
                        request_number=request.request_number,
                        category=get_category_display(resolve_category_key(request.category), language="ru"),
                        address=request.address,
                        urgency=get_urgency_display(request.urgency, language="ru") if request.urgency else "",
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
async def handle_manager_view_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка просмотра деталей заявки для менеджеров"""
    try:
        lang = language
        logger.info(f"Обработка просмотра заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_requests", language=lang), show_alert=True)
            return
        
        request_number = callback.data.replace("mview_", "")

        svc = AdminHandlerService(db)
        # Получаем заявку из базы данных
        request = svc.get_request_by_number(request_number)

        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Получаем информацию о пользователе, создавшем заявку
        request_user = svc.get_user_by_id(request.user_id)
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
        category_display = get_category_display(resolve_category_key(request.category), language=lang)
        urgency_display = get_urgency_display(request.urgency, language=lang) if request.urgency else ""
        message_text += get_text("admin.handlers.request_detail_category", language=lang).format(category=category_display) + "\n"
        message_text += get_text("admin.handlers.request_detail_status", language=lang).format(status=get_status_display(request.status, language=lang)) + "\n"
        message_text += get_text("admin.handlers.request_detail_address", language=lang).format(address=request.address) + "\n"
        message_text += get_text("admin.handlers.request_detail_description", language=lang).format(description=request.description) + "\n"
        message_text += get_text("admin.handlers.request_detail_urgency", language=lang).format(urgency=urgency_display) + "\n"
        if request.apartment:
            message_text += get_text("admin.handlers.request_detail_apartment", language=lang).format(apartment=request.apartment) + "\n"
        message_text += get_text("admin.handlers.request_detail_created", language=lang).format(created_at=request.created_at.strftime('%d.%m.%Y %H:%M')) + "\n"
        if request.updated_at:
            message_text += get_text("admin.handlers.request_detail_updated", language=lang).format(updated_at=request.updated_at.strftime('%d.%m.%Y %H:%M')) + "\n"

        # Добавляем информацию о назначении
        active_assignment = svc.get_active_assignment(request.request_number)

        if active_assignment:
            if active_assignment.assignment_type == "group":
                # Групповое назначение (дежурному специалисту)
                spec_name = get_text(f"specializations.{active_assignment.group_specialization}", language=lang) if active_assignment.group_specialization else active_assignment.group_specialization
                message_text += get_text("admin.handlers.assigned_duty_specialist", language=lang).format(spec_name=spec_name) + "\n"
            elif active_assignment.assignment_type == "individual" and active_assignment.executor_id:
                # Индивидуальное назначение конкретному исполнителю
                assigned_executor = svc.get_user_by_id(active_assignment.executor_id)
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

        # Для исполненных, но непринятых заявок (ожидают приёмки заявителем) - специальная клавиатура
        if is_awaiting_applicant(request):
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

        # Для заявок, ожидающих подтверждения менеджером - специальная клавиатура
        elif is_awaiting_manager(request):
            actions_kb = get_manager_completed_request_actions_keyboard(request.request_number, is_returned=request.is_returned)

            # Добавляем кнопку медиа если есть
            rows = list(actions_kb.inline_keyboard)
            if has_media:
                rows.append([InlineKeyboardButton(text=get_text("admin.handlers.btn_media", language=lang), callback_data=f"media_{request.request_number}")])
            rows.append([InlineKeyboardButton(text=get_text("admin.handlers.btn_back_to_list", language=lang), callback_data=f"mreq_back_{request.request_number}")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        else:
            # Для обычных заявок - стандартная клавиатура
            actions_kb = get_manager_request_actions_keyboard(request.request_number, has_media=has_media)

            # Добавляем кнопку "Назад к списку"
            rows = list(actions_kb.inline_keyboard)
            rows.append([InlineKeyboardButton(text=get_text("admin.handlers.btn_back_to_list", language=lang), callback_data=f"mreq_back_{request.request_number}")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
        logger.info(f"Показаны детали заявки {request.request_number} менеджеру {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки просмотра заявки менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("media_"))
async def handle_view_request_media(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка просмотра медиафайлов заявки"""
    try:
        from aiogram.types import InputMediaPhoto, InputMediaDocument
        lang = language

        logger.info(f"Просмотр медиафайлов заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_media", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("media_", "")

        # Получаем заявку из базы данных
        request = AdminHandlerService(db).get_request_by_number(request_number)

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
                    except Exception:
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
                except Exception:
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
                    except Exception:
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
                except Exception:
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
async def handle_manager_confirm_completed(callback: CallbackQuery, db: Session, roles: list = None, user: User = None, language: str = "ru"):
    """Менеджер подтверждает выполнение заявки"""
    try:
        lang = language

        logger.info(f"Подтверждение выполнения заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_confirm", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("confirm_completed_", "")

        # Канонический переход через единый layer (PR2a): run_command владеет
        # своей транзакцией (свежая сессия + FOR UPDATE + ActorContext из БД +
        # patch/audit/outbox в одной tx). Пишет СРАЗУ канон: Выполнена→Исполнено.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        try:
            outcome = run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                ActionCommand(callback.id, Action.MANAGER_CONFIRM, {}),
            )
        except RequestNotFound:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return
        except WorkflowError as e:
            logger.info(f"MANAGER_CONFIRM отклонён для {request_number}: {e}")
            await callback.answer(get_text("admin.handlers.error_confirming", language=lang), show_alert=True)
            return

        # Best-effort post-commit (потеря допустима, PR0 Р7): уведомления + правка.
        # run_command работал в своей сессии → перечитываем заявку свежей.
        request = AdminHandlerService(db).get_request_by_number(request_number)

        # Уведомление через сервис (отправит заявителю, исполнителю и в канал)
        try:
            bot = callback.bot
            await async_notify_request_status_changed(bot, db, request, outcome.old_status, outcome.public_status)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

        # Дополнительное уведомление заявителю с инструкцией
        applicant = request.user if request else None
        if applicant and applicant.telegram_id:
            try:
                bot = callback.bot

                notification_text = get_text("admin.handlers.notify_applicant_completed", language=lang).format(
                    request_number=request.format_number_for_display()
                )

                await bot.send_message(applicant.telegram_id, notification_text)
                logger.info(f"✅ Уведомление о подтверждении заявки {request_number} отправлено заявителю {applicant.telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления заявителю: {e}")

        await callback.message.edit_text(
            get_text("admin.handlers.request_confirmed", language=lang).format(request_number=request_number)
        )

        logger.info(f"Заявка {request_number} подтверждена менеджером {user.id} (canon)")

    except Exception as e:
        logger.error(f"Ошибка подтверждения выполнения заявки: {e}")
        if db:
            AdminHandlerService(db).rollback()
        await callback.answer(get_text("admin.handlers.error_confirming", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("reconfirm_completed_"))
async def handle_manager_reconfirm_completed(callback: CallbackQuery, db: Session, roles: list = None, user: User = None, language: str = "ru"):
    """Менеджер повторно подтверждает выполнение возвратной заявки"""
    try:
        lang = language

        logger.info(f"Повторное подтверждение возвратной заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_confirm", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("reconfirm_completed_", "")

        # PR2a-2: под каноном (модель A) у статуса «Возвращена» нет ребра
        # обратно в «Исполнено». Кнопка reconfirm = MANAGER_FORCE_ACCEPT
        # (продуктовое решение 2026-06-10): менеджер отклоняет возврат →
        # заявка принимается терминально (Возвращена→Принято), повторной
        # приёмки заявителем больше нет.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        try:
            outcome = run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                ActionCommand(callback.id, Action.MANAGER_FORCE_ACCEPT, {}),
            )
        except RequestNotFound:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return
        except WorkflowError as e:
            logger.info(f"MANAGER_FORCE_ACCEPT (reconfirm) отклонён для {request_number}: {e}")
            await callback.answer(get_text("admin.handlers.error_confirming", language=lang), show_alert=True)
            return

        # Best-effort post-commit (PR0 Р7): уведомления + правка сообщения.
        request = AdminHandlerService(db).get_request_by_number(request_number)

        # Уведомление через сервис (отправит заявителю, исполнителю и в канал)
        try:
            bot = callback.bot
            await async_notify_request_status_changed(bot, db, request, outcome.old_status, outcome.public_status)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

        # Дополнительное уведомление заявителю: возврат рассмотрен, заявка принята
        applicant = request.user if request else None
        if applicant and applicant.telegram_id:
            try:
                bot = callback.bot

                notification_text = get_text("admin.handlers.notify_applicant_reconfirmed", language=lang).format(
                    request_number=request.format_number_for_display()
                )

                await bot.send_message(applicant.telegram_id, notification_text)
                logger.info(f"✅ Уведомление о принятии возвратной заявки {request_number} отправлено заявителю {applicant.telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления заявителю: {e}")

        await callback.message.edit_text(
            get_text("admin.handlers.request_reconfirmed", language=lang).format(request_number=request_number)
        )

        logger.info(f"Возврат по заявке {request_number} отклонён, принято менеджером {user.id} (canon force-accept)")

    except Exception as e:
        logger.error(f"Ошибка повторного подтверждения заявки: {e}")
        if db:
            AdminHandlerService(db).rollback()
        await callback.answer(get_text("admin.handlers.error_confirming", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("return_to_work_"))
async def handle_manager_return_to_work(callback: CallbackQuery, db: Session, roles: list = None, user: User = None, language: str = "ru"):
    """Менеджер возвращает заявку в работу"""
    try:
        lang = language
        logger.info(f"Возврат заявки в работу менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_change_status", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("return_to_work_", "")

        # Канонический переход (PR2a-2): Выполнена/Возвращена → В работе.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        try:
            outcome = run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                ActionCommand(callback.id, Action.MANAGER_RETURN_TO_WORK, {}),
            )
        except RequestNotFound:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return
        except WorkflowError as e:
            logger.info(f"MANAGER_RETURN_TO_WORK отклонён для {request_number}: {e}")
            await callback.answer(get_text("admin.handlers.error_changing_status", language=lang), show_alert=True)
            return

        # Best-effort post-commit (PR0 Р7): уведомление + правка сообщения.
        request = AdminHandlerService(db).get_request_by_number(request_number)
        try:
            bot = callback.bot
            await async_notify_request_status_changed(bot, db, request, outcome.old_status, outcome.public_status)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

        await callback.message.edit_text(
            get_text("admin.handlers.request_returned_to_work", language=lang).format(request_number=request_number)
        )

        logger.info(f"Заявка {request_number} возвращена в работу менеджером {user.id} (canon)")

    except Exception as e:
        logger.error(f"Ошибка возврата заявки в работу: {e}")
        if db:
            AdminHandlerService(db).rollback()
        await callback.answer(get_text("admin.handlers.error_changing_status", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("mreq_page_"))
async def handle_manager_request_pagination(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка пагинации списков заявок для менеджеров"""
    try:
        lang = language
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
        svc = AdminHandlerService(db)

        # Вычисляем общее количество страниц
        total_requests = svc.count_active_requests()
        requests_per_page = 10
        total_pages = max(1, (total_requests + requests_per_page - 1) // requests_per_page)

        if current_page < 1 or current_page > total_pages:
            await callback.answer(get_text("admin.handlers.page_not_found", language=lang), show_alert=True)
            return

        # Получаем заявки для текущей страницы
        requests = svc.page_active_requests(
            (current_page - 1) * requests_per_page, requests_per_page
        )

        if not requests:
            await callback.answer(get_text("admin.handlers.no_requests_on_page", language=lang), show_alert=True)
            return
        
        items = [{"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status} for r in requests]
        
        # Обновляем сообщение с новой страницей
        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
        new_keyboard = get_manager_request_list_kb(items, current_page, total_pages)
        
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        
        logger.info(f"Показана страница {current_page} заявок менеджеру {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки пагинации заявок менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


async def _render_manager_request_list(callback: CallbackQuery, db: Session, request_number, language: str = "ru"):
    """BUG-BOT-035: render-only — перерисовать список заявок менеджера в текущем
    сообщении по `request_number` (берётся аргументом, без парсинга callback.data).

    НЕ проверяет права и НЕ вызывает callback.answer() ни на одном пути — это
    ответственность caller'а. Может бросить исключение; caller оборачивает в
    try/except. Это позволяет звать рендер из cancel/complete/delete, чьи
    callback.data не имеют префикса `mreq_back_`.
    """
    lang = language
    from uk_management_bot.keyboards.admin import get_manager_request_list_kb

    svc = AdminHandlerService(db)
    request = svc.get_request_by_number(request_number)

    if request:
        if request.status == REQUEST_STATUS_NEW:
            requests = svc.list_new_requests(limit=10)
            if not requests:
                await callback.message.edit_text(get_text("admin.handlers.no_new_requests", language=lang))
                return
            items = [{"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status} for r in requests]
            keyboard = get_manager_request_list_kb(items, 1, 1)
            await callback.message.edit_text(get_text("admin.handlers.new_requests_title", language=lang), reply_markup=keyboard)
            return

        elif request.status == REQUEST_STATUS_EXECUTED:
            requests = svc.list_executed_requests(limit=10)
            if not requests:
                await callback.message.edit_text(get_text("admin.handlers.no_completed_requests", language=lang))
                return
            items = []
            for r in requests:
                item = {"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status}
                if r.is_returned:
                    item["suffix"] = " 🔄"
                items.append(item)
            keyboard = get_manager_request_list_kb(items, 1, 1)
            await callback.message.edit_text(get_text("admin.handlers.completed_requests_title", language=lang), reply_markup=keyboard)
            return

        elif request.status in [REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION]:
            requests = svc.list_active_requests(limit=10)
            if not requests:
                await callback.message.edit_text(get_text("admin.handlers.no_active_requests", language=lang))
                return
            items = [{"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status} for r in requests]
            keyboard = get_manager_request_list_kb(items, 1, 1)
            await callback.message.edit_text(get_text("admin.handlers.active_requests_title", language=lang), reply_markup=keyboard)
            return

    # Fallback: показываем активные заявки по умолчанию
    requests = svc.list_active_requests(limit=10)

    if not requests:
        await callback.message.edit_text(get_text("admin.handlers.no_active_requests", language=lang))
        return

    items = [{"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status} for r in requests]
    keyboard = get_manager_request_list_kb(items, 1, 1)
    await callback.message.edit_text(get_text("admin.handlers.active_requests_title", language=lang), reply_markup=keyboard)


@router.callback_query(F.data.startswith("mreq_back_"))
async def handle_manager_back_to_list(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Возврат из деталей заявки к списку для менеджеров (кнопка `mreq_back_<NNN>`).

    Тонкая обёртка: проверка прав + парсинг callback.data → render-only helper.
    """
    try:
        lang = language
        logger.info(f"Возврат к списку заявок менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_requests", language=lang), show_alert=True)
            return

        request_number = callback.data.split("mreq_back_")[1]
        await _render_manager_request_list(callback, db, request_number, lang)

        logger.info(f"Возврат к списку заявок выполнен для менеджера {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка возврата к списку заявок: {e}", exc_info=True)
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.message(F.text.in_(TEST_MIDDLEWARE_TEXTS))
async def test_middleware(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, user_status: str = None, language: str = "ru"):
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
        except Exception:
            pass
    
    print(f"🔧 Доступ к админ панели: {'✅ Есть' if has_access else '❌ Нет'}")
    
    lang = language
    await message.answer(get_text("admin.handlers.test_middleware_result", language=lang).format(
        roles=roles, active_role=active_role,
        user_status=get_text("admin.handlers.yes", language=lang) if user else get_text("admin.handlers.no", language=lang),
        has_access=get_text("admin.handlers.yes", language=lang) if has_access else get_text("admin.handlers.no", language=lang)
    ))

@router.message(F.text.in_(ADMIN_PANEL_TEXTS))
async def open_admin_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, user_status: str = None, language: str = "ru"):
    """Открыть админ панель"""
    lang = language
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    await message.answer(get_text("admin.handlers.manager_panel", language=lang), reply_markup=get_manager_main_keyboard(language=lang))


@router.message(F.text.in_(ADMIN_USER_MANAGEMENT_TEXTS))  
async def open_user_management_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Открыть панель управления пользователями"""
    lang = language
    
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


@router.message(F.text.in_(ADMIN_EMPLOYEE_MANAGEMENT_TEXTS))
async def open_employee_management_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Открыть панель управления сотрудниками"""
    lang = language
    
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


@router.message(F.text.in_(ADMIN_NEW_REQUESTS_TEXTS))
async def list_new_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать новые заявки"""
    lang = language
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Новые заявки: только "Новая" (🆕)
    requests = AdminHandlerService(db).list_new_requests(limit=10)

    if not requests:
        await message.answer(get_text("admin.handlers.no_new_requests", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
        return

    items = [{"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status} for r in requests]
    await message.answer(get_text("admin.handlers.new_requests_title", language=lang), reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text.in_(ADMIN_ACTIVE_REQUESTS_TEXTS))
async def list_active_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать активные заявки"""
    lang = language
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    requests = AdminHandlerService(db).list_active_requests(limit=10)

    if not requests:
        await message.answer(get_text("admin.handlers.no_active_requests", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
        return

    items = [{"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status} for r in requests]
    await message.answer(get_text("admin.handlers.active_requests_title", language=lang), reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text.in_(ADMIN_COMPLETED_REQUESTS_TEXTS))
async def show_completed_requests_menu(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать подменю для исполненных заявок"""
    lang = language

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Получаем статистику
    svc = AdminHandlerService(db)
    # "Всего исполненных" = заявки, ожидающие подтверждения менеджером
    total_completed = svc.count_awaiting_manager()

    # Возвращённые = заявка возвращена заявителем на доработку (ждёт разбора менеджером)
    returned_count = svc.count_returned_for_review()

    # Не принятые = подтверждены менеджером, но не приняты заявителем
    unaccepted_count = svc.count_awaiting_applicant()

    stats_text = get_text("admin.handlers.completed_requests_stats", language=lang).format(
        total_completed=total_completed,
        returned_count=returned_count,
        unaccepted_count=unaccepted_count
    )

    await message.answer(stats_text, reply_markup=get_completed_requests_submenu(language=lang), parse_mode="HTML")


@router.message(F.text.in_(ADMIN_AWAITING_REVIEW_TEXTS))
async def list_all_completed_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать заявки, ожидающие проверки менеджером"""
    lang = language

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Все исполненные заявки: статус "Выполнена" и НЕ подтверждены менеджером
    # (ожидают проверки и подтверждения менеджером)
    requests = AdminHandlerService(db).list_awaiting_manager(limit=10)

    if not requests:
        await message.answer(get_text("admin.handlers.no_completed_requests", language=lang), reply_markup=get_completed_requests_submenu(language=lang))
        return

    # Добавляем пометку "возвратная" для возвратных заявок
    items = []
    for r in requests:
        item = {
            "request_number": r.request_number,
            "category": get_category_display(resolve_category_key(r.category), language=lang),
            "address": r.address,
            "status": "🔄 " + get_text("admin.handlers.returned_label", language=lang) if r.is_returned else r.status
        }
        items.append(item)

    await message.answer(get_text("admin.handlers.all_completed_requests_title", language=lang), reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text.in_(ADMIN_RETURNED_TEXTS))
async def list_returned_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать только возвращённые заявки"""
    lang = language

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Только возвращённые заявки
    # Статус "Исполнено" - когда заявка возвращена заявителем на доработку
    requests = AdminHandlerService(db).list_returned_for_review(limit=10)

    if not requests:
        await message.answer(
            get_text("admin.handlers.no_returned_requests", language=lang),
            reply_markup=get_completed_requests_submenu(language=lang)
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
            "category": get_category_display(resolve_category_key(r.category), language=lang),
            "address": r.address,
            "status": get_text("admin.handlers.returned_status_label", language=lang) + return_info
        }
        items.append(item)

    await message.answer(
        get_text("admin.handlers.returned_requests_title", language=lang).format(count=len(requests)),
        reply_markup=get_manager_request_list_kb(items, 1, 1),
        parse_mode="HTML"
    )


@router.message(F.text.in_(ADMIN_NOT_ACCEPTED_TEXTS))
async def list_unaccepted_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать непринятые заявки (выполненные, но не принятые заявителем)"""
    lang = language

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Непринятые заявки: подтверждены менеджером (manager_confirmed = True), но не приняты заявителем (статус != "Принято")
    from datetime import datetime, timezone
    requests = AdminHandlerService(db).list_awaiting_applicant(limit=20)

    if not requests:
        await message.answer(
            get_text("admin.handlers.no_unaccepted_requests", language=lang),
            reply_markup=get_completed_requests_submenu(language=lang),
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
            "category": get_category_display(resolve_category_key(r.category), language=lang),
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


@router.message(F.text.in_(ADMIN_BACK_TO_MENU_TEXTS))
async def back_to_main_menu(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Вернуться в главное меню"""
    lang = language

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
        reply_markup=get_main_keyboard_for_role(active_role or legacy_primary_role(user), roles or [legacy_primary_role(user)], user.status, language=lang)
    )


# BUG-BOT-019: text "📦 Архив" is shared with the executor main menu. Gate by
# active_role so the admin archive only fires when the user is acting as
# manager/admin. has_admin_access() also runs below but only checks roles list,
# not active_role — RoleFilter is what prevents executor-mode mis-routing.
@router.message(F.text.in_(ADMIN_ARCHIVE_TEXTS), RoleFilter(["manager", "admin"]))
async def list_archive_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать архивные заявки"""
    lang = language
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Архив: только завершенные статусы (Выполнена, Исполнено, Принято, Отменена)
    requests = AdminHandlerService(db).list_archive_requests(limit=10)
    if not requests:
        await message.answer(get_text("admin.handlers.archive_empty", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
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
    await message.answer(get_text("admin.handlers.archive_end", language=lang), reply_markup=get_manager_main_keyboard(language=lang))

@router.message(F.text.in_(ADMIN_PURCHASE_TEXTS))
async def list_procurement_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать заявки в статусе закупа"""
    lang = language
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Получаем заявки в статусе "Закуп"
    requests = AdminHandlerService(db).list_purchase_requests(limit=10)

    if not requests:
        await message.answer(get_text("admin.handlers.no_procurement_requests", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
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

    await message.answer(get_text("admin.handlers.procurement_end", language=lang), reply_markup=get_manager_main_keyboard(language=lang))
    logger.info(f"Показаны заявки в статусе закуп менеджеру {message.from_user.id}")






# ===== ОБРАБОТЧИКИ СОЗДАНИЯ ПРИГЛАШЕНИЙ =====

@router.message(F.text.in_(ADMIN_CREATE_INVITE_TEXTS))
async def start_invite_creation(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Начать процесс создания приглашения"""
    lang = language
    
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
async def handle_invite_role_selection(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработчик выбора роли для приглашения"""
    lang = language

    # Проверяем права доступа (только менеджеры могут создавать приглашения)
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text("invites.manager_only", language=lang), show_alert=True)
        return

    # Извлекаем роль из callback_data
    role = callback.data.replace("invite_role_", "")
    
    if role not in ["applicant", "executor", "manager", "inspector"]:
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


@router.callback_query(F.data.startswith("invite_spec_"), InviteCreationStates.waiting_for_specialization)
async def handle_invite_specialization_selection(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработчик выбора специализации для исполнителя"""
    lang = language

    # Проверяем права доступа (только менеджеры могут создавать приглашения)
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text("invites.manager_only", language=lang), show_alert=True)
        return

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


@router.callback_query(F.data.startswith("invite_expiry_"), InviteCreationStates.waiting_for_expiry)
async def handle_invite_expiry_selection(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработчик выбора срока действия приглашения"""
    lang = language

    # Проверяем права доступа (только менеджеры могут создавать приглашения)
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text("invites.manager_only", language=lang), show_alert=True)
        return

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


@router.callback_query(F.data == "invite_confirm", InviteCreationStates.waiting_for_confirmation)
async def handle_invite_confirmation(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработчик подтверждения создания приглашения"""
    lang = language

    # Проверяем права доступа (только менеджеры могут создавать приглашения)
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text("invites.manager_only", language=lang), show_alert=True)
        return

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
            1: get_text("admin.handlers.expiry_1h", language=lang),
            24: get_text("admin.handlers.expiry_24h", language=lang),
            168: get_text("admin.handlers.expiry_7d", language=lang)
        }.get(expiry_hours, get_text("admin.handlers.expiry_24h", language=lang))

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
            reply_markup=get_manager_main_keyboard(language=lang)
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
            reply_markup=get_manager_main_keyboard(language=lang)
        )
        await state.clear()
    
    await callback.answer()


@router.callback_query(F.data == "invite_cancel")
async def handle_invite_cancel(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Обработчик отмены создания приглашения"""
    lang = language
    
    await callback.message.edit_text(
        get_text("buttons.operation_cancelled", language=lang)
    )
    await callback.message.answer(
        get_text("admin.handlers.back_to_admin_panel", language=lang),
        reply_markup=get_manager_main_keyboard(language=lang)
    )

    # Очищаем состояние
    await state.clear()
    
    await callback.answer()


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

