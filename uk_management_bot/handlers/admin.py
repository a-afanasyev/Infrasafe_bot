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

router = Router()
logger = logging.getLogger(__name__)

class ManagerStates(StatesGroup):
    cancel_reason = State()
    clarify_reason = State()

from uk_management_bot.states.invite_creation import InviteCreationStates


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

