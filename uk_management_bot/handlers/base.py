from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import Session
from services.auth_service import AuthService
from keyboards.base import (
    get_main_keyboard,
    get_cancel_keyboard,
    get_main_keyboard_for_role,
    get_role_switch_inline,
    get_user_contextual_keyboard,
)
from keyboards.shifts import get_shifts_main_keyboard
from services.notification_service import async_notify_role_switched
from utils.helpers import get_text
import logging

logger = logging.getLogger(__name__)

router = Router()

class AdminPasswordStates(StatesGroup):
    """Состояния для ввода пароля администратора"""
    waiting_for_password = State()

@router.message(Command("start"))
async def cmd_start(message: Message, db: Session, roles: list[str] = None, active_role: str = None):
    """Обработчик команды /start"""
    auth_service = AuthService(db)
    
    # Получаем или создаем пользователя
    user = await auth_service.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    # Обновляем язык пользователя
    if message.from_user.language_code:
        await auth_service.update_user_language(
            message.from_user.id, 
            message.from_user.language_code
        )
    
    # Проверяем, нужен ли онбординг
    lang = message.from_user.language_code or "ru"
    
    # Проверяем полноту профиля
    is_profile_complete = user.phone and user.home_address
    
    if not is_profile_complete and user.status == "pending":
        # Новый пользователь - показываем онбординг
        welcome_text = get_text("onboarding.welcome_new_user", language=lang)
        welcome_text += f"\n\n{get_text('onboarding.profile_incomplete', language=lang)}"
        
        # Создаём клавиатуру онбординга
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        missing_items = []
        if not user.phone:
            missing_items.append("📱 Указать телефон" if lang == "ru" else "📱 Telefon ko'rsatish")
        if not user.home_address:
            missing_items.append("🏠 Указать адрес" if lang == "ru" else "🏠 Manzil ko'rsatish")
        
        if missing_items:
            onboarding_keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=item)] for item in missing_items],
                resize_keyboard=True,
                one_time_keyboard=False
            )
            await message.answer(welcome_text, reply_markup=onboarding_keyboard)
            logger.info(f"Новый пользователь {message.from_user.id} начал онбординг")
            return
    
    # Обычное приветствие
    welcome_text = get_text("welcome", language=lang)
    
    if user.status == "pending":
        welcome_text += f"\n\n{get_text('auth.pending', language=lang)}"
    elif user.status == "blocked":
        welcome_text += f"\n\n{get_text('auth.blocked', language=lang)}"
    else:
        welcome_text += f"\n\n{get_text('auth.approved', language=lang)}"
    
    # Формируем клавиатуру в зависимости от роли
    # Фолбэк: если middleware не передал корректные roles/active_role — берём из БД пользователя
    roles = roles or ["applicant"]
    active_role = active_role or roles[0]
    try:
        import json
        db_roles = []
        if getattr(user, "roles", None):
            parsed = json.loads(user.roles)
            if isinstance(parsed, list) and parsed:
                db_roles = [str(r) for r in parsed if isinstance(r, str)]
        if db_roles:
            roles = db_roles
        if getattr(user, "active_role", None):
            active_role = user.active_role if user.active_role in roles else roles[0]
    except Exception:
        pass
    await message.answer(welcome_text, reply_markup=get_main_keyboard_for_role(active_role, roles))
    logger.info(f"Пользователь {message.from_user.id} запустил бота")

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = """
🤖 **Справка по использованию бота**

📝 **Создание заявки:**
- Нажмите "Создать заявку"
- Выберите категорию
- Укажите адрес и описание
- Добавьте фото/видео (опционально)
- Выберите срочность

📋 **Просмотр заявок:**
- "Мои заявки" - ваши заявки
- "Все заявки" - все заявки (для исполнителей и менеджеров)

👤 **Профиль:**
- Просмотр и редактирование профиля
- Изменение языка

🔧 **Админ функции (для менеджеров):**
- Управление пользователями
- Назначение заявок
- Создание смен
- Статистика

❓ **Поддержка:**
Если у вас возникли вопросы, обратитесь к администратору.
    """
    
    await message.answer(help_text, reply_markup=get_user_contextual_keyboard(message.from_user.id))

@router.message(F.text == "❌ Отмена")
async def cancel_action(message: Message, state: FSMContext, roles: list[str] = None, active_role: str = None):
    """Отмена текущего действия"""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        lang = message.from_user.language_code or "ru"
        await message.answer(
            get_text("cancel", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        logger.info(f"Пользователь {message.from_user.id} отменил действие в состоянии {current_state}")
    else:
        lang = message.from_user.language_code or "ru"
        await message.answer(
            get_text("cancel", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )

@router.message(F.text == "🔙 Назад")
async def go_back(message: Message, state: FSMContext, roles: list[str] = None, active_role: str = None):
    """Возврат в главное меню"""
    await state.clear()
    lang = message.from_user.language_code or "ru"
    await message.answer(get_text("back", language=lang), reply_markup=get_user_contextual_keyboard(message.from_user.id))


# Обработчики меню исполнителя
@router.message(F.text == "🛠 Активные заявки")
async def executor_active_requests(message: Message, state: FSMContext):
    """Открывает список заявок пользователя с фильтром Активные."""
    await state.update_data(my_requests_status="active", my_requests_page=1)
    from handlers.requests import show_my_requests
    await show_my_requests(message, state)


@router.message(F.text == "📦 Архив")
async def executor_archive_requests(message: Message, state: FSMContext):
    """Открывает список заявок пользователя с фильтром Архив."""
    await state.update_data(my_requests_status="archive", my_requests_page=1)
    from handlers.requests import show_my_requests
    await show_my_requests(message, state)


@router.message(F.text == "🔄 Смена")
async def executor_shift_menu(message: Message):
    """Показывает клавиатуру управления сменой."""
    await message.answer("Меню смены:", reply_markup=get_shifts_main_keyboard())


@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message, db: Session, roles: list[str] = None, active_role: str = None):
    """Показывает расширенный профиль пользователя"""
    try:
        from services.profile_service import ProfileService
        profile_service = ProfileService(db)
        
        # Получаем полные данные профиля
        profile_data = profile_service.get_user_profile_data(message.from_user.id)
        
        if not profile_data:
            # Ошибка получения данных
            lang = message.from_user.language_code or "ru"
            await message.answer(
                get_text("errors.unknown_error", language=lang),
                reply_markup=get_main_keyboard_for_role(active_role or "applicant", roles or ["applicant"])
            )
            return
        
        # Форматируем текст профиля
        lang = message.from_user.language_code or "ru"
        profile_text = profile_service.format_profile_text(profile_data, language=lang)
        
        # Отправляем профиль с клавиатурой переключения ролей
        user_roles = profile_data.get('roles', ['applicant'])
        user_active_role = profile_data.get('active_role', 'applicant')
        
        await message.answer(
            profile_text, 
            reply_markup=get_role_switch_inline(user_roles, user_active_role)
        )
        
        logger.info(f"Показан профиль пользователя {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка отображения профиля {message.from_user.id}: {e}")
        lang = message.from_user.language_code or "ru"
        await message.answer(
            get_text("errors.unknown_error", language=lang),
            reply_markup=get_main_keyboard_for_role(active_role or "applicant", roles or ["applicant"])
        )


@router.message(F.text == "🔀 Выбрать роль")
async def choose_role(message: Message, db: Session, roles: list[str] = None, active_role: str = None):
    """Открывает inline‑переключатель ролей из главного меню.

    Показывается только если у пользователя более одной роли.
    """
    roles = roles or ["applicant"]
    active_role = active_role or roles[0]
    # Фолбэк из БД, если roles пришли усечёнными
    try:
        from services.auth_service import AuthService
        auth = AuthService(db)
        user = await auth.get_user_by_telegram_id(message.from_user.id)
        if user:
            import json
            if getattr(user, "roles", None):
                parsed = json.loads(user.roles)
                if isinstance(parsed, list) and parsed:
                    roles = [str(r) for r in parsed if isinstance(r, str)]
            if getattr(user, "active_role", None) and user.active_role in roles:
                active_role = user.active_role
    except Exception:
        pass
    role_name = get_text(f"roles.{active_role}", language=message.from_user.language_code or "ru")
    text = get_text("role.switch_title", language=message.from_user.language_code or "ru", role=role_name)
    await message.answer(text, reply_markup=get_role_switch_inline(roles, active_role))


@router.callback_query(F.data.startswith("switch_role:"))
async def switch_role(cb: CallbackQuery, db: Session, roles: list[str] = None, active_role: str = None):
    roles = roles or ["applicant"]
    target = cb.data.split(":", 1)[1]
    if target not in roles:
        # Фолбэк: перечитываем роли из БД, если middleware передал усечённый список
        try:
            auth_check = AuthService(db)
            db_user = await auth_check.get_user_by_telegram_id(cb.from_user.id)
            if db_user and getattr(db_user, "roles", None):
                import json
                parsed = json.loads(db_user.roles)
                if isinstance(parsed, list) and target in [str(r) for r in parsed if isinstance(r, str)]:
                    roles = [str(r) for r in parsed if isinstance(r, str)]
                else:
                    lang = cb.from_user.language_code or "ru"
                    await cb.answer(get_text("role.not_allowed", language=lang), show_alert=True)
                    return
            else:
                lang = cb.from_user.language_code or "ru"
                await cb.answer(get_text("role.not_allowed", language=lang), show_alert=True)
                return
        except Exception:
            lang = cb.from_user.language_code or "ru"
            await cb.answer(get_text("role.not_allowed", language=lang), show_alert=True)
            return
    auth = AuthService(db)
    old_active = active_role
    ok, reason = await auth.try_set_active_role_with_rate_limit(cb.from_user.id, target)
    if not ok:
        lang = cb.from_user.language_code or "ru"
        if reason == "rate_limited":
            # Локализованный отказ по лимиту
            await cb.answer(get_text("notify.reason.rate_limited", language=lang), show_alert=True)
        else:
            await cb.answer(get_text("errors.unknown_error", language=lang), show_alert=True)
        return
    await cb.answer(get_text("role.switched", language=cb.from_user.language_code or "ru"))
    # Пересобираем меню (актуальные роли из БД, если доступны)
    try:
        db_user2 = await auth.get_user_by_telegram_id(cb.from_user.id)
        if db_user2 and getattr(db_user2, "roles", None):
            import json
            parsed2 = json.loads(db_user2.roles)
            if isinstance(parsed2, list) and parsed2:
                roles = [str(r) for r in parsed2 if isinstance(r, str)]
    except Exception:
        pass
    new_roles = roles
    new_active = target
    await cb.message.answer("Главное меню:", reply_markup=get_main_keyboard_for_role(new_active, new_roles))

    # async уведомление о смене режима (best-effort)
    try:
        from aiogram import Bot
        bot: Bot = cb.message.bot
        user = await auth.get_user_by_telegram_id(cb.from_user.id)
        if user:
            await async_notify_role_switched(bot, db, user, old_active or "", new_active)
    except Exception:
        pass

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Обработчик команды /admin - назначение администратора по паролю"""
    await state.set_state(AdminPasswordStates.waiting_for_password)
    await message.answer(
        "🔐 **Назначение администратора**\n\n"
        "Введите пароль администратора для получения прав менеджера:\n"
        "_(Пароль: 12345)_",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AdminPasswordStates.waiting_for_password)
async def process_admin_password(message: Message, state: FSMContext, db: Session):
    """Обработка введенного пароля администратора"""
    auth_service = AuthService(db)
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_user_contextual_keyboard(message.from_user.id))
        return
    
    # Проверяем пароль и назначаем администратора
    success = await auth_service.make_admin_by_password(
        telegram_id=message.from_user.id,
        password=message.text
    )
    
    await state.clear()
    
    if success:
        # Перечитываем пользователя и строим меню в соответствии с активной ролью
        try:
            user = await auth_service.get_user_by_telegram_id(message.from_user.id)
            # Собираем список ролей из JSON, фолбэк к историческому полю role
            roles_list = ["applicant"]
            active_role = "applicant"
            if user:
                import json
                try:
                    if getattr(user, "roles", None):
                        parsed = json.loads(user.roles)
                        if isinstance(parsed, list) and parsed:
                            roles_list = [str(r) for r in parsed if isinstance(r, str)] or roles_list
                except Exception:
                    roles_list = [user.role] if getattr(user, "role", None) else roles_list
                if getattr(user, "active_role", None):
                    active_role = user.active_role
                else:
                    active_role = roles_list[0] if roles_list else "applicant"
                if active_role not in roles_list:
                    active_role = roles_list[0] if roles_list else "applicant"
        except Exception:
            roles_list = ["applicant"]
            active_role = "applicant"

        await message.answer(
            "✅ **Успешно!**\n\n"
            "Вы назначены администратором системы.\n"
            "Теперь у вас есть права менеджера для управления заявками и пользователями.",
            reply_markup=get_main_keyboard_for_role(active_role, roles_list)
        )
        logger.info(f"Пользователь {message.from_user.id} назначен администратором")
    else:
        await message.answer(
            "❌ **Ошибка!**\n\n"
            "Неверный пароль администратора.\n"
            "Попробуйте еще раз или обратитесь к разработчику.",
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        logger.warning(f"Неверная попытка назначения администратора от {message.from_user.id}")
