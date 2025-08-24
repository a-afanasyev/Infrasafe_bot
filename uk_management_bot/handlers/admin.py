from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session

from uk_management_bot.keyboards.admin import (
    get_manager_main_keyboard,
    get_manager_requests_inline,
    get_manager_request_list_kb,
)
from uk_management_bot.keyboards.base import get_main_keyboard, get_user_contextual_keyboard
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.request_service import RequestService
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
    has_access = has_admin_access(roles=roles, user=user)
    print(f"🔍 DEBUG: has_admin_access() вернул: {has_access}")
    
    if not has_access:
        print(f"❌ DEBUG: Доступ запрещен - roles={roles}, user.role={user.role if user else 'None'}")
        await message.answer(
            get_text('errors.permission_denied', language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    print(f"✅ DEBUG: Доступ разрешен")
    
    try:
        # Импортируем сервис и клавиатуры
        from uk_management_bot.services.user_management_service import UserManagementService
        from uk_management_bot.keyboards.user_management import get_user_management_main_keyboard
        
        # Получаем статистику пользователей
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_user_stats()
        
        # Показываем панель управления пользователями
        await message.answer(
            get_text('user_management.main_title', language=lang),
            reply_markup=get_user_management_main_keyboard(stats, lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка открытия панели управления пользователями: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang),
            reply_markup=get_manager_main_keyboard()
        )


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

    # Простая выборка: все со статусом "Новая"
    from uk_management_bot.database.models.request import Request
    q = db.query(Request).filter(Request.status == "Новая").order_by(Request.created_at.desc())
    requests = q.limit(10).all()

    if not requests:
        await message.answer("Нет новых заявок", reply_markup=get_manager_main_keyboard())
        return

    text = "🆕 Новые заявки (первые 10):"
    items = [{"id": r.id, "category": r.category, "address": r.address} for r in requests]
    await message.answer(text, reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text == "💰 Закуп")
async def list_purchase_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать заявки в закупе"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    q = (
        db.query(Request)
        .filter(Request.status == "Закуп")
        .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
    )
    requests = q.limit(10).all()
    if not requests:
        await message.answer("Заявок в закупе нет", reply_markup=get_manager_main_keyboard())
        return
    items = [{"id": r.id, "category": r.category, "address": r.address, "status": r.status} for r in requests]
    await message.answer("💰 Заявки в закупе:", reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.callback_query(F.data.startswith("mview_"))
async def manager_view_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Подробности заявки + действия для менеджера"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(
            get_text("errors.permission_denied", language=lang),
            show_alert=True
        )
        return

    req_id = int(callback.data.replace("mview_", ""))
    r = db.query(Request).filter(Request.id == req_id).first()
    if not r:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    text = (
        f"📋 Заявка #{r.id}\n"
        f"Категория: {r.category}\n"
        f"Статус: {r.status}\n"
        f"Адрес: {r.address}\n"
        f"Срочность: {r.urgency}\n"
        f"Описание: {r.description[:500]}{'…' if len(r.description) > 500 else ''}\n"
    )
    if r.notes:
        text += f"\nДиалог:\n{r.notes}"

    # Кнопки действий: принять в работу / уточнение / закуп / отмена
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ В работу", callback_data=f"maccept_{r.id}")],
        [InlineKeyboardButton(text="❓ Уточнение", callback_data=f"mclarify_{r.id}")],
        [InlineKeyboardButton(text="💰 Закуп", callback_data=f"mpurchase_{r.id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"mcancel_{r.id}")],
    ])

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("maccept_"))
async def manager_accept(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Принять заявку в работу"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(
            get_text("errors.permission_denied", language=lang),
            show_alert=True
        )
        return
    
    req_id = int(callback.data.replace("maccept_", ""))
    service = RequestService(db)
    result = service.update_status_by_actor(
        request_id=req_id,
        new_status="В работе",
        actor_telegram_id=callback.from_user.id,
    )
    if not result.get("success"):
        await callback.answer(result.get("message", "Ошибка"), show_alert=True)
        return
    r = result.get("request")
    text = (
        f"📋 Заявка #{r.id}\n"
        f"Категория: {r.category}\n"
        f"Статус: {r.status}\n"
        f"Адрес: {r.address}\n"
    )
    if r.notes:
        text += f"\nДиалог:\n{r.notes}"
    await callback.message.edit_text(text)
    await callback.answer("Принята в работу")


@router.callback_query(F.data.startswith("mpurchase_"))
async def manager_purchase(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Перевести заявку в закуп"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(
            get_text("errors.permission_denied", language=lang),
            show_alert=True
        )
        return
    
    req_id = int(callback.data.replace("mpurchase_", ""))
    service = RequestService(db)
    result = service.update_status_by_actor(
        request_id=req_id,
        new_status="Закуп",
        actor_telegram_id=callback.from_user.id,
    )
    if not result.get("success"):
        await callback.answer(result.get("message", "Ошибка"), show_alert=True)
        return
    r = result.get("request")
    text = (
        f"📋 Заявка #{r.id}\n"
        f"Категория: {r.category}\n"
        f"Статус: {r.status}\n"
        f"Адрес: {r.address}\n"
    )
    if r.notes:
        text += f"\nДиалог:\n{r.notes}"
    await callback.message.edit_text(text)
    await callback.answer("Переведена в 'Закуп'")


@router.callback_query(F.data.startswith("mclarify_"))
async def manager_clarify_ask(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Запросить уточнение по заявке"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(
            get_text("errors.permission_denied", language=lang),
            show_alert=True
        )
        return
    
    await state.update_data(manager_target_request=int(callback.data.replace("mclarify_", "")))
    await state.set_state(ManagerStates.clarify_reason)
    await callback.message.answer("Укажите, что уточнить по заявке:")
    await callback.answer()


@router.message(ManagerStates.clarify_reason)
async def manager_clarify_save(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Сохранить уточнение по заявке"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    service = RequestService(db)
    data = await state.get_data()
    req_id = int(data.get("manager_target_request"))
    reason = message.text.strip()
    # Если уже в Уточнение — просто дополним диалог; иначе переведем в Уточнение с первым сообщением
    req = db.query(Request).filter(Request.id == req_id).first()
    if req and req.status == "Уточнение":
        # дописываем без смены статуса
        service.update_status_by_actor(
            request_id=req_id,
            new_status=req.status,
            actor_telegram_id=message.from_user.id,
            notes=f"[Администратор] Уточнение: {reason}",
        )
    else:
        # переводим в Уточнение
        service.update_status_by_actor(
            request_id=req_id,
            new_status="Уточнение",
            actor_telegram_id=message.from_user.id,
            notes=f"[Администратор] Уточнение: {reason}",
        )
    await message.answer("Уточнение отправлено", reply_markup=get_manager_main_keyboard())
    await state.clear()


@router.callback_query(F.data.startswith("mcancel_"))
async def manager_cancel_ask(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Запросить причину отмены заявки"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(
            get_text("errors.permission_denied", language=lang),
            show_alert=True
        )
        return
    
    await state.update_data(manager_target_request=int(callback.data.replace("mcancel_", "")))
    await state.set_state(ManagerStates.cancel_reason)
    await callback.message.answer("Укажите причину отмены заявки:")
    await callback.answer()


@router.message(ManagerStates.cancel_reason)
async def manager_cancel_save(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Сохранить причину отмены заявки"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    service = RequestService(db)
    data = await state.get_data()
    req_id = int(data.get("manager_target_request"))
    reason = message.text.strip()
    result = service.update_status_by_actor(
        request_id=req_id,
        new_status="Отменена",
        actor_telegram_id=message.from_user.id,
        notes=f"[Администратор] Отмена: {reason}",
    )
    await state.clear()
    if not result.get("success"):
        await message.answer(f"Ошибка: {result.get('message')}")
        return
    r = result.get("request")
    text = f"Заявка #{r.id} отменена. Причина: {reason}"
    if r and r.notes:
        text += f"\n\nДиалог:\n{r.notes}"
    await message.answer(text)


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


@router.message(F.text == "👤 Сотрудники")
async def list_employees(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать сотрудников по специализациям"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Загружаем сотрудников по специализациям
    groups = {
        "Электрика": db.query(User).filter(User.role.in_(["executor", "manager"]), User.specialization == SPECIALIZATION_ELECTRIC).all(),
        "Сантехника": db.query(User).filter(User.role.in_(["executor", "manager"]), User.specialization == SPECIALIZATION_PLUMBING).all(),
        "Охрана": db.query(User).filter(User.role.in_(["executor", "manager"]), User.specialization == SPECIALIZATION_SECURITY).all(),
        "Уборка": db.query(User).filter(User.role.in_(["executor", "manager"]), User.specialization == SPECIALIZATION_CLEANING).all(),
        "Разное": db.query(User).filter(User.role.in_(["executor", "manager"]), (User.specialization.is_(None)) | (User.specialization == SPECIALIZATION_OTHER)).all(),
    }

    lines = ["👤 Сотрудники по специализациям:"]
    role_display = {"executor": "Исполнитель", "manager": "Менеджер"}
    for title, users in groups.items():
        lines.append(f"\n— {title}:")
        if not users:
            lines.append("  (пока пусто)")
            continue
        for u in users[:20]:
            name = (u.first_name or "") + (f" {u.last_name}" if u.last_name else "")
            name = name.strip() or (u.username or str(u.telegram_id))
            lines.append(f"  • {role_display.get(u.role, u.role)} • {name} (tg_id={u.telegram_id})")
    await message.answer("\n".join(lines), reply_markup=get_manager_main_keyboard())

