from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session

from uk_management_bot.keyboards.admin import (
    get_manager_main_keyboard,
    get_manager_requests_inline,
    get_manager_request_list_kb,
    get_invite_role_keyboard,
    get_invite_specialization_keyboard,
    get_invite_expiry_keyboard,
    get_invite_confirmation_keyboard,
)
from uk_management_bot.keyboards.base import get_main_keyboard, get_user_contextual_keyboard
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.request_service import RequestService
from uk_management_bot.services.invite_service import InviteService
from uk_management_bot.database.session import get_db
from uk_management_bot.utils.constants import (
    SPECIALIZATION_ELECTRIC,
    SPECIALIZATION_PLUMBING,
    SPECIALIZATION_SECURITY,
    SPECIALIZATION_CLEANING,
    SPECIALIZATION_OTHER,
)
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.utils.auth_helpers import has_admin_access
from datetime import datetime

router = Router()
logger = logging.getLogger(__name__)

class ManagerStates(StatesGroup):
    cancel_reason = State()
    clarify_reason = State()
    waiting_for_clarification_text = State()

from uk_management_bot.states.invite_creation import InviteCreationStates


# ===== ОБРАБОТЧИКИ ПРОСМОТРА ЗАЯВОК ДЛЯ МЕНЕДЖЕРОВ =====

@router.callback_query(F.data.startswith("mview_"))
async def handle_manager_view_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка просмотра деталей заявки для менеджеров"""
    try:
        logger.info(f"Обработка просмотра заявки менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для просмотра заявок", show_alert=True)
            return
        
        request_id = int(callback.data.replace("mview_", ""))
        
        # Получаем заявку из базы данных
        request = db.query(Request).filter(Request.id == request_id).first()
        
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
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
            user_info = " ".join(full_name_parts) if full_name_parts else f"Пользователь {request_user.telegram_id}"
        else:
            user_info = "Неизвестный пользователь"
        
        # Формируем детальную информацию о заявке
        message_text = f"📋 Заявка #{request.id}\n\n"
        message_text += f"👤 Заявитель: {user_info}\n"
        message_text += f"📱 Telegram ID: {request_user.telegram_id if request_user else 'N/A'}\n"
        message_text += f"📂 Категория: {request.category}\n"
        message_text += f"📊 Статус: {request.status}\n"
        message_text += f"📍 Адрес: {request.address}\n"
        message_text += f"📝 Описание: {request.description}\n"
        message_text += f"⚡ Срочность: {request.urgency}\n"
        if request.apartment:
            message_text += f"🏠 Квартира: {request.apartment}\n"
        message_text += f"📅 Создана: {request.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        if request.updated_at:
            message_text += f"🔄 Обновлена: {request.updated_at.strftime('%d.%m.%Y %H:%M')}\n"
        if request.notes:
            message_text += f"💬 Примечания: {request.notes}\n"
        
        # Создаем клавиатуру действий для менеджера
        from uk_management_bot.keyboards.admin import get_manager_request_actions_keyboard
        actions_kb = get_manager_request_actions_keyboard(request.id)
        
        # Добавляем кнопку "Назад к списку"
        rows = list(actions_kb.inline_keyboard)
        rows.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data="mreq_back_to_list")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
        logger.info(f"Показаны детали заявки {request.id} менеджеру {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки просмотра заявки менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("mreq_page_"))
async def handle_manager_request_pagination(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка пагинации списков заявок для менеджеров"""
    try:
        logger.info(f"Обработка пагинации заявок менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для просмотра заявок", show_alert=True)
            return
        
        # Парсим данные пагинации
        page_data = callback.data.replace("mreq_page_", "")
        
        if page_data == "curr":
            await callback.answer("Текущая страница")
            return
        
        current_page = int(page_data)
        
        # Определяем тип списка заявок (новые, активные, архив)
        # Пока что показываем активные заявки
        active_statuses = ["В работе", "Закуп", "Уточнение"]
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
            await callback.answer("Страница не найдена", show_alert=True)
            return
        
        # Получаем заявки для текущей страницы
        requests = q.offset((current_page - 1) * requests_per_page).limit(requests_per_page).all()
        
        if not requests:
            await callback.answer("Нет заявок на этой странице", show_alert=True)
            return
        
        items = [{"id": r.id, "category": r.category, "address": r.address, "status": r.status} for r in requests]
        
        # Обновляем сообщение с новой страницей
        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
        new_keyboard = get_manager_request_list_kb(items, current_page, total_pages)
        
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        
        logger.info(f"Показана страница {current_page} заявок менеджеру {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки пагинации заявок менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "mreq_back_to_list")
async def handle_manager_back_to_list(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Возврат из деталей заявки к списку для менеджеров"""
    try:
        logger.info(f"Возврат к списку заявок менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для просмотра заявок", show_alert=True)
            return
        
        # Определяем, из какого списка мы пришли, по статусу заявки
        # Получаем текущую заявку из сообщения
        message_text = callback.message.text
        if "Заявка #" in message_text:
            # Извлекаем ID заявки из текста сообщения
            import re
            match = re.search(r'Заявка #(\d+)', message_text)
            if match:
                request_id = int(match.group(1))
                request = db.query(Request).filter(Request.id == request_id).first()
                if request:
                    # Определяем тип списка по статусу заявки
                    if request.status == "Новая":
                        # Возвращаемся к новым заявкам
                        q = (
                            db.query(Request)
                            .filter(Request.status == "Новая")
                            .order_by(Request.created_at.desc())
                        )
                        requests = q.limit(10).all()
                        
                        if not requests:
                            await callback.message.edit_text("Нет новых заявок")
                            return
                        
                        items = [{"id": r.id, "category": r.category, "address": r.address, "status": r.status} for r in requests]
                        
                        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
                        keyboard = get_manager_request_list_kb(items, 1, 1)
                        
                        await callback.message.edit_text("🆕 Новые заявки:", reply_markup=keyboard)
                        return
                    elif request.status in ["В работе", "Закуп", "Уточнение"]:
                        # Возвращаемся к активным заявкам
                        active_statuses = ["В работе", "Закуп", "Уточнение"]
                        q = (
                            db.query(Request)
                            .filter(Request.status.in_(active_statuses))
                            .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
                        )
                        requests = q.limit(10).all()
                        
                        if not requests:
                            await callback.message.edit_text("Нет активных заявок")
                            return
                        
                        items = [{"id": r.id, "category": r.category, "address": r.address, "status": r.status} for r in requests]
                        
                        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
                        keyboard = get_manager_request_list_kb(items, 1, 1)
                        
                        await callback.message.edit_text("🔄 Активные заявки:", reply_markup=keyboard)
                        return
        
        # Если не удалось определить тип списка, показываем активные заявки по умолчанию
        active_statuses = ["В работе", "Закуп", "Уточнение"]
        q = (
            db.query(Request)
            .filter(Request.status.in_(active_statuses))
            .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
        )
        requests = q.limit(10).all()
        
        if not requests:
            await callback.message.edit_text("Нет активных заявок")
            return
        
        items = [{"id": r.id, "category": r.category, "address": r.address, "status": r.status} for r in requests]
        
        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
        keyboard = get_manager_request_list_kb(items, 1, 1)
        
        await callback.message.edit_text("🔄 Активные заявки:", reply_markup=keyboard)
        
        logger.info(f"Возврат к списку заявок выполнен для менеджера {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка возврата к списку заявок: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.message(F.text == "🧪 Тест middleware")
async def test_middleware(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, user_status: str = None):
    """Тестовый обработчик для проверки middleware"""
    
    # ОТЛАДКА: Проверяем все параметры
    print(f"🧪 TEST MIDDLEWARE:")
    print(f"🔍 roles={roles}")
    print(f"🔍 active_role={active_role}")
    print(f"🔍 user={user}")
    print(f"🔍 user_status={user_status}")
    print(f"🔍 message.from_user.id={message.from_user.id}")
    
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
    
    await message.answer(f"Тест middleware:\nroles={roles}\nactive_role={active_role}\nuser={'Есть' if user else 'Нет'}\nhas_access={'Да' if has_access else 'Нет'}")

@router.message(F.text == "🔧 Админ панель")
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
    
    await message.answer("Панель менеджера", reply_markup=get_manager_main_keyboard())


@router.message(F.text == "👥 Управление пользователями")  
async def open_user_management_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Открыть панель управления пользователями"""
    lang = message.from_user.language_code or 'ru'
    
    # ОТЛАДКА
    print(f"🔍 DEBUG: open_user_management_panel вызвана")
    print(f"🔍 DEBUG: roles={roles}, user={user}")
    print(f"🔍 DEBUG: message.from_user.id={message.from_user.id}")
    
    if user:
        print(f"🔍 DEBUG: user.role={user.role}")
        print(f"🔍 DEBUG: user.roles={user.roles}")
        print(f"🔍 DEBUG: user.active_role={user.active_role}")
        print(f"🔍 DEBUG: user.status={user.status}")
    
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
            "👷 Панель управления сотрудниками",
            reply_markup=get_employee_management_main_keyboard(stats, lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка открытия панели управления сотрудниками: {e}")
        await message.answer("Произошла ошибка при открытии панели управления сотрудниками")


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
        .filter(Request.status == "Новая")
        .order_by(Request.created_at.desc())
    )
    requests = q.limit(10).all()
    
    if not requests:
        await message.answer("Нет новых заявок", reply_markup=get_manager_main_keyboard())
        return
    
    items = [{"id": r.id, "category": r.category, "address": r.address, "status": r.status} for r in requests]
    await message.answer("🆕 Новые заявки:", reply_markup=get_manager_request_list_kb(items, 1, 1))


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
    
    active_statuses = ["В работе", "Закуп", "Уточнение"]
    q = (
        db.query(Request)
        .filter(Request.status.in_(active_statuses))
        .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
    )
    requests = q.limit(10).all()
    
    if not requests:
        await message.answer("Нет активных заявок", reply_markup=get_manager_main_keyboard())
        return
    
    items = [{"id": r.id, "category": r.category, "address": r.address, "status": r.status} for r in requests]
    await message.answer("🔄 Активные заявки:", reply_markup=get_manager_request_list_kb(items, 1, 1))


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
    
    # Архив: только Подтверждена (⭐) и Отменена (❌)
    archive_statuses = ["Подтверждена", "Отменена"]
    q = (
        db.query(Request)
        .filter(Request.status.in_(archive_statuses))
        .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
    )
    requests = q.limit(10).all()
    if not requests:
        await message.answer("Архив пуст", reply_markup=get_manager_main_keyboard())
        return
    def _icon(s: str) -> str:
        return {"Подтверждена": "⭐", "Отменена": "❌"}.get(s, "")
    # Каждую заявку отправляем отдельным сообщением
    for r in requests:
        addr = r.address[:60] + ("…" if len(r.address) > 60 else "")
        text = (
            f"{_icon(r.status)} #{r.id} • {r.category} • {r.status}\n"
            f"Адрес: {addr}\n"
            f"Создана: {r.created_at.strftime('%d.%m.%Y %H:%M')}"
        )
        if r.status == "Отменена" and r.notes:
            text += f"\nПричина отказа: {r.notes}"
        if r.notes:
            text += f"\n\nДиалог:\n{r.notes}"
        await message.answer(text)
    await message.answer("📦 Конец списка архива", reply_markup=get_manager_main_keyboard())





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
    await message.answer("Выберите роль для приглашения:", reply_markup=get_invite_role_keyboard())


@router.callback_query(F.data.startswith("invite_role_"))
async def handle_invite_role_selection(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработчик выбора роли для приглашения"""
    lang = callback.from_user.language_code or 'ru'
    
    # Извлекаем роль из callback_data
    role = callback.data.replace("invite_role_", "")
    
    if role not in ["applicant", "executor", "manager"]:
        await callback.answer("Неверная роль")
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
        1: "1 час",
        24: "24 часа",
        168: "7 дней"
    }.get(expiry_hours, "24 часа")
    
    # Формируем текст подтверждения
    role_name = get_text(f"roles.{role}", language=lang)
    confirmation_text = f"📋 Подтвердите создание приглашения:\n\n"
    confirmation_text += f"👤 Роль: {role_name}\n"
    
    if role == "executor" and specialization:
        spec_name = get_text(f"specializations.{specialization}", language=lang)
        confirmation_text += f"🛠️ Специализация: {spec_name}\n"
    
    confirmation_text += f"⏰ Срок действия: {expiry_text}\n\n"
    confirmation_text += "Нажмите 'Создать приглашение' для генерации токена."
    
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
            await callback.answer("Ошибка: роль не выбрана")
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
        
        success_text = f"✅ Приглашение создано!\n\n"
        success_text += f"👤 Роль: {role_name}\n"
        
        if role == "executor" and specialization:
            spec_name = get_text(f"specializations.{specialization}", language=lang)
            success_text += f"🛠️ Специализация: {spec_name}\n"
        
        success_text += f"⏰ Срок действия: {expiry_text}\n\n"
        success_text += f"🔗 Ссылка для регистрации:\n\n"
        success_text += f"`{invite_link}`\n\n"
        success_text += f"📋 Инструкция для кандидата:\n"
        success_text += f"1. Перейдите по ссылке\n"
        success_text += f"2. Нажмите кнопку «Начать»\n"
        success_text += f"3. Отправьте команду: `/join {token}`"
        
        await callback.message.edit_text(
            success_text
        )
        await callback.message.answer(
            "Вернуться в админ-панель:",
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
            "Вернуться в админ-панель:",
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

@router.callback_query(F.data.startswith("accept_"))
async def handle_accept_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка принятия заявки менеджером"""
    try:
        logger.info(f"Обработка принятия заявки менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_id = int(callback.data.replace("accept_", ""))
        
        # Получаем заявку
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Обновляем статус
        request.status = "В работе"
        request.updated_at = datetime.now()
        db.commit()
        
        await callback.answer("✅ Заявка принята в работу")
        
        # Возвращаемся к списку заявок
        await handle_manager_back_to_list(callback, db, roles, active_role, user)
        
        logger.info(f"Заявка {request_id} принята менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки принятия заявки менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("deny_"))
async def handle_deny_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка отклонения заявки менеджером"""
    try:
        logger.info(f"Обработка отклонения заявки менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_id = int(callback.data.replace("deny_", ""))
        
        # Получаем заявку
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Обновляем статус и добавляем примечание
        request.status = "Отменена"
        request.notes = f"{request.notes or ''}\n\nОтклонена менеджером {user.first_name or user.telegram_id} {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        request.updated_at = datetime.now()
        db.commit()
        
        await callback.answer("❌ Заявка отклонена")
        
        # Возвращаемся к списку заявок
        await handle_manager_back_to_list(callback, db, roles, active_role, user)
        
        logger.info(f"Заявка {request_id} отклонена менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки отклонения заявки менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("clarify_"))
async def handle_clarify_request(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка запроса уточнения по заявке"""
    try:
        logger.info(f"Обработка запроса уточнения по заявке менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_id = int(callback.data.replace("clarify_", ""))
        
        # Получаем заявку
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем, что заявка не отменена
        if request.status == "Отменена":
            await callback.answer("Нельзя задать уточнение по отмененной заявке", show_alert=True)
            return
        
        # Сохраняем ID заявки в состоянии
        await state.update_data(request_id=request_id)
        
        # Запрашиваем текст уточнения
        await callback.message.edit_text(
            f"❓ Введите текст уточнения для заявки #{request_id}:\n\n"
            f"📋 Заявка: {request.category}\n"
            f"📍 Адрес: {request.address}\n\n"
            f"💬 Введите ваш вопрос или уточнение:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_clarification")]
            ])
        )
        
        # Устанавливаем состояние ожидания текста уточнения
        await state.set_state(ManagerStates.waiting_for_clarification_text)
        
        logger.info(f"Запрошен текст уточнения для заявки {request_id} менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки запроса уточнения: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "cancel_clarification")
async def handle_cancel_clarification(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Отмена уточнения"""
    try:
        # Очищаем состояние
        await state.clear()
        
        # Возвращаемся к списку заявок
        await handle_manager_back_to_list(callback, db, roles, active_role, user)
        
        await callback.answer("❌ Уточнение отменено")
        
    except Exception as e:
        logger.error(f"Ошибка отмены уточнения: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("purchase_"))
async def handle_purchase_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка перевода заявки в статус 'Закуп' менеджером"""
    try:
        logger.info(f"Обработка перевода заявки в закуп менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_id = int(callback.data.replace("purchase_", ""))
        
        # Получаем заявку
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Обновляем статус
        request.status = "Закуп"
        request.updated_at = datetime.now()
        db.commit()
        
        await callback.answer("💰 Заявка переведена в закуп")
        
        # Возвращаемся к списку заявок
        await handle_manager_back_to_list(callback, db, roles, active_role, user)
        
        logger.info(f"Заявка {request_id} переведена в закуп менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки перевода в закуп менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("complete_"))
async def handle_complete_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка завершения заявки менеджером"""
    try:
        logger.info(f"Обработка завершения заявки менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_id = int(callback.data.replace("complete_", ""))
        
        # Получаем заявку
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Обновляем статус
        request.status = "Выполнена"
        request.completed_at = datetime.now()
        request.updated_at = datetime.now()
        db.commit()
        
        await callback.answer("✅ Заявка отмечена как выполненная")
        
        # Возвращаемся к списку заявок
        await handle_manager_back_to_list(callback, db, roles, active_role, user)
        
        logger.info(f"Заявка {request_id} отмечена как выполненная менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки завершения заявки менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("delete_"))
async def handle_delete_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка удаления заявки менеджером"""
    try:
        logger.info(f"Обработка удаления заявки менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_id = int(callback.data.replace("delete_", ""))
        
        # Получаем заявку
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Удаляем заявку
        db.delete(request)
        db.commit()
        
        await callback.answer("🗑️ Заявка удалена")
        
        # Возвращаемся к списку заявок
        await handle_manager_back_to_list(callback, db, roles, active_role, user)
        
        logger.info(f"Заявка {request_id} удалена менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки удаления заявки менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.message(ManagerStates.waiting_for_clarification_text)
async def handle_clarification_text(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка текста уточнения от менеджера"""
    try:
        logger.info(f"Получен текст уточнения от менеджера {message.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await message.answer("Нет прав для выполнения действий")
            await state.clear()
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        request_id = data.get("request_id")
        
        if not request_id:
            await message.answer("Ошибка: не найдена заявка")
            await state.clear()
            return
        
        # Получаем заявку
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await message.answer("Заявка не найдена")
            await state.clear()
            return
        
        # Получаем текст уточнения
        clarification_text = message.text.strip()
        
        if not clarification_text:
            await message.answer("Текст уточнения не может быть пустым. Попробуйте еще раз или нажмите 'Отмена'.")
            return
        
        # Формируем имя менеджера
        manager_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not manager_name:
            manager_name = f"Менеджер {user.telegram_id}"
        
        # Добавляем уточнение в примечания заявки
        timestamp = datetime.now().strftime('%d.%m.%Y %H:%M')
        new_note = f"\n\n--- УТОЧНЕНИЕ {timestamp} ---\n"
        new_note += f"👨‍💼 {manager_name}:\n"
        new_note += f"{clarification_text}\n"
        
        # Обновляем примечания
        if request.notes:
            request.notes += new_note
        else:
            request.notes = new_note
        
        # Обновляем статус на "Уточнение" если он еще не такой
        if request.status != "Уточнение":
            request.status = "Уточнение"
        
        request.updated_at = datetime.now()
        db.commit()
        
        # Отправляем уведомление заявителю
        try:
            from uk_management_bot.services.notification_service import NotificationService
            notification_service = NotificationService(db)
            
            notification_text = f"❓ По вашей заявке #{request.id} появилось уточнение:\n\n"
            notification_text += f"📋 Заявка: {request.category}\n"
            notification_text += f"📍 Адрес: {request.address}\n\n"
            notification_text += f"💬 Вопрос от менеджера:\n{clarification_text}\n\n"
            notification_text += f"💬 Для ответа используйте команду /reply_{request.id}"
            
            notification_service.send_notification_to_user(
                user_id=request.user_id,
                message=notification_text
            )
            
            logger.info(f"Уведомление об уточнении отправлено пользователю {request.user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об уточнении: {e}")
        
        # Подтверждаем менеджеру
        await message.answer(
            f"✅ Уточнение отправлено!\n\n"
            f"📋 Заявка #{request_id}\n"
            f"💬 Текст: {clarification_text[:100]}{'...' if len(clarification_text) > 100 else ''}\n\n"
            f"📱 Заявитель получил уведомление и сможет ответить."
        )
        
        # Очищаем состояние
        await state.clear()
        
        logger.info(f"Уточнение по заявке {request_id} добавлено менеджером {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки текста уточнения: {e}")
        await message.answer("Произошла ошибка при отправке уточнения")
        await state.clear()

