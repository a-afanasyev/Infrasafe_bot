from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session

from keyboards.admin import (
    get_manager_main_keyboard,
    get_manager_requests_inline,
    get_manager_request_list_kb,
)
from keyboards.base import get_main_keyboard
from services.auth_service import AuthService
from services.request_service import RequestService
from database.session import get_db
from database.models.request import Request
from database.models.user import User
from utils.constants import (
    SPECIALIZATION_ELECTRIC,
    SPECIALIZATION_PLUMBING,
    SPECIALIZATION_SECURITY,
    SPECIALIZATION_CLEANING,
    SPECIALIZATION_OTHER,
)
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

import logging
from utils.helpers import get_text

router = Router()
logger = logging.getLogger(__name__)

class ManagerStates(StatesGroup):
    cancel_reason = State()
    clarify_reason = State()


@router.message(F.text == "🔧 Админ панель")
async def open_admin_panel(message: Message, user_status: str | None = None):
    # Pending — ранний отказ
    if user_status == "pending":
        await message.answer(get_text("auth.pending", language=message.from_user.language_code or "ru"), reply_markup=get_main_keyboard())
        return
    db_session: Session = next(get_db())
    auth = AuthService(db_session)
    if not await auth.is_user_manager(message.from_user.id):
        await message.answer(get_text("errors.permission_denied", language=message.from_user.language_code or "ru"), reply_markup=get_main_keyboard())
        return
    await message.answer("Панель менеджера", reply_markup=get_manager_main_keyboard())


@router.message(F.text == "👥 Управление пользователями")  
async def open_user_management_panel(message: Message, db: Session, roles: list = None, active_role: str = None):
    """Открыть панель управления пользователями"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not roles or 'manager' not in roles:
        await message.answer(
            get_text('errors.permission_denied', language=lang),
            reply_markup=get_main_keyboard()
        )
        return
    
    try:
        # Импортируем сервис и клавиатуры
        from services.user_management_service import UserManagementService
        from keyboards.user_management import get_user_management_main_keyboard
        
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
async def list_new_requests(message: Message, user_status: str | None = None):
    if user_status == "pending":
        await message.answer(get_text("auth.pending", language=message.from_user.language_code or "ru"), reply_markup=get_main_keyboard())
        return
    db_session: Session = next(get_db())
    auth = AuthService(db_session)
    if not await auth.is_user_manager(message.from_user.id):
        await message.answer(get_text("errors.permission_denied", language=message.from_user.language_code or "ru"), reply_markup=get_main_keyboard())
        return

    # Простая выборка: все со статусом "Новая"
    q = db_session.query(Request).filter(Request.status == "Новая").order_by(Request.created_at.desc())
    requests = q.limit(10).all()

    if not requests:
        await message.answer("Нет новых заявок", reply_markup=get_manager_main_keyboard())
        return

    text = "🆕 Новые заявки (первые 10):"
    items = [{"id": r.id, "category": r.category, "address": r.address} for r in requests]
    await message.answer(text, reply_markup=get_manager_request_list_kb(items, 1, 1))
@router.message(F.text == "💰 Закуп")
async def list_purchase_requests(message: Message, user_status: str | None = None):
    if user_status == "pending":
        await message.answer(get_text("auth.pending", language=message.from_user.language_code or "ru"), reply_markup=get_main_keyboard())
        return
    db_session: Session = next(get_db())
    auth = AuthService(db_session)
    if not await auth.is_user_manager(message.from_user.id):
        await message.answer(get_text("errors.permission_denied", language=message.from_user.language_code or "ru"), reply_markup=get_main_keyboard())
        return
    q = (
        db_session.query(Request)
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
async def manager_view_request(callback: CallbackQuery, user_status: str | None = None):
    if user_status == "pending":
        await callback.answer(get_text("auth.pending", language=callback.from_user.language_code or "ru"), show_alert=True)
        return
    """Подробности заявки + действия для менеджера."""
    db_session: Session = next(get_db())
    auth = AuthService(db_session)
    if not await auth.is_user_manager(callback.from_user.id):
        await callback.answer(get_text("errors.permission_denied", language=callback.from_user.language_code or "ru"), show_alert=True)
        return

    req_id = int(callback.data.replace("mview_", ""))
    r = db_session.query(Request).filter(Request.id == req_id).first()
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
async def manager_accept(callback: CallbackQuery, user_status: str | None = None):
    if user_status == "pending":
        await callback.answer(get_text("auth.pending", language=callback.from_user.language_code or "ru"), show_alert=True)
        return
    db_session: Session = next(get_db())
    auth = AuthService(db_session)
    if not await auth.is_user_manager(callback.from_user.id):
        await callback.answer(get_text("errors.permission_denied", language=callback.from_user.language_code or "ru"), show_alert=True)
        return
    req_id = int(callback.data.replace("maccept_", ""))
    service = RequestService(db_session)
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
async def manager_purchase(callback: CallbackQuery, user_status: str | None = None):
    if user_status == "pending":
        await callback.answer(get_text("auth.pending", language=callback.from_user.language_code or "ru"), show_alert=True)
        return
    db_session: Session = next(get_db())
    auth = AuthService(db_session)
    if not await auth.is_user_manager(callback.from_user.id):
        await callback.answer(get_text("errors.permission_denied", language=callback.from_user.language_code or "ru"), show_alert=True)
        return
    req_id = int(callback.data.replace("mpurchase_", ""))
    service = RequestService(db_session)
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
async def manager_clarify_ask(callback: CallbackQuery, state: FSMContext, user_status: str | None = None):
    if user_status == "pending":
        await callback.answer(get_text("auth.pending", language=callback.from_user.language_code or "ru"), show_alert=True)
        return
    await state.update_data(manager_target_request=int(callback.data.replace("mclarify_", "")))
    await state.set_state(ManagerStates.clarify_reason)
    await callback.message.answer("Укажите, что уточнить по заявке:")
    await callback.answer()


@router.message(ManagerStates.clarify_reason)
async def manager_clarify_save(message: Message, state: FSMContext, user_status: str | None = None):
    if user_status == "pending":
        await message.answer(get_text("auth.pending", language=message.from_user.language_code or "ru"), reply_markup=get_main_keyboard())
        return
    db_session: Session = next(get_db())
    service = RequestService(db_session)
    data = await state.get_data()
    req_id = int(data.get("manager_target_request"))
    reason = message.text.strip()
    # Если уже в Уточнение — просто дополним диалог; иначе переведем в Уточнение с первым сообщением
    req = db_session.query(Request).filter(Request.id == req_id).first()
    if req and req.status == "Уточнение":
        # дописываем без смены статуса
        service.update_status_by_actor(
            request_id=req_id,
            new_status=req.status,
            actor_telegram_id=message.from_user.id,
            notes=f"[Администратор] Уточнение: {reason}",
        )
        result = {"success": True, "request": req}
    else:
        result = service.update_status_by_actor(
            request_id=req_id,
            new_status="Уточнение",
            actor_telegram_id=message.from_user.id,
            notes=f"[Администратор] Уточнение: {reason}",
        )
    await state.clear()
    if not result.get("success"):
        await message.answer(f"Ошибка: {result.get('message')}")
        return
    r = result.get("request")
    out = f"Заявка #{r.id} — уточнение добавлено"
    if r and r.notes:
        out += f"\n\nДиалог:\n{r.notes}"
    await message.answer(out)


@router.callback_query(F.data.startswith("mcancel_"))
async def manager_cancel_ask(callback: CallbackQuery, state: FSMContext, user_status: str | None = None):
    if user_status == "pending":
        await callback.answer(get_text("auth.pending", language=callback.from_user.language_code or "ru"), show_alert=True)
        return
    await state.update_data(manager_target_request=int(callback.data.replace("mcancel_", "")))
    await state.set_state(ManagerStates.cancel_reason)
    await callback.message.answer("Укажите причину отмены заявки:")
    await callback.answer()


@router.message(ManagerStates.cancel_reason)
async def manager_cancel_save(message: Message, state: FSMContext, user_status: str | None = None):
    if user_status == "pending":
        await message.answer(get_text("auth.pending", language=message.from_user.language_code or "ru"), reply_markup=get_main_keyboard())
        return
    db_session: Session = next(get_db())
    service = RequestService(db_session)
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
async def list_active_requests(message: Message, user_status: str | None = None):
    if user_status == "pending":
        await message.answer(get_text("auth.pending", language=message.from_user.language_code or "ru"))
        return
    db_session: Session = next(get_db())
    auth = AuthService(db_session)
    if not await auth.is_user_manager(message.from_user.id):
        await message.answer(get_text("errors.permission_denied", language=message.from_user.language_code or "ru"))
        return
    active_statuses = ["В работе", "Закуп", "Уточнение"]
    q = (
        db_session.query(Request)
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
async def list_archive_requests(message: Message, user_status: str | None = None):
    if user_status == "pending":
        await message.answer(get_text("auth.pending", language=message.from_user.language_code or "ru"))
        return
    db_session: Session = next(get_db())
    auth = AuthService(db_session)
    if not await auth.is_user_manager(message.from_user.id):
        await message.answer(get_text("errors.permission_denied", language=message.from_user.language_code or "ru"))
        return
    # Архив: только Подтверждена (⭐) и Отменена (❌)
    archive_statuses = ["Подтверждена", "Отменена"]
    q = (
        db_session.query(Request)
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
async def list_employees(message: Message, user_status: str | None = None):
    if user_status == "pending":
        await message.answer(get_text("auth.pending", language=message.from_user.language_code or "ru"), reply_markup=get_main_keyboard())
        return
    """Список сотрудников по специализациям: Электрика, Сантехника, Охрана, Уборка, Разное."""
    db_session: Session = next(get_db())
    auth = AuthService(db_session)
    if not await auth.is_user_manager(message.from_user.id):
        await message.answer(get_text("errors.permission_denied", language=message.from_user.language_code or "ru"), reply_markup=get_main_keyboard())
        return
    # Загружаем сотрудников по специализациям
    groups = {
        "Электрика": db_session.query(User).filter(User.role.in_(["executor", "manager"]), User.specialization == SPECIALIZATION_ELECTRIC).all(),
        "Сантехника": db_session.query(User).filter(User.role.in_(["executor", "manager"]), User.specialization == SPECIALIZATION_PLUMBING).all(),
        "Охрана": db_session.query(User).filter(User.role.in_(["executor", "manager"]), User.specialization == SPECIALIZATION_SECURITY).all(),
        "Уборка": db_session.query(User).filter(User.role.in_(["executor", "manager"]), User.specialization == SPECIALIZATION_CLEANING).all(),
        "Разное": db_session.query(User).filter(User.role.in_(["executor", "manager"]), (User.specialization.is_(None)) | (User.specialization == SPECIALIZATION_OTHER)).all(),
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

