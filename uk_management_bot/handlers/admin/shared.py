"""Разделяемое для admin-пакета: SSOT-константы кнопок, ManagerStates, auto_assign_request_by_category (AUD3-06)."""
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session

from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.constants.categories import CATEGORY_TO_SPECIALIZATION

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display, get_urgency_display
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
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


