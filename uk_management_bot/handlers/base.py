from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import Session
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.invite_service import InviteService, InviteRateLimiter
from uk_management_bot.keyboards.base import (
    get_main_keyboard,
    get_cancel_keyboard,
    get_main_keyboard_for_role,
    get_role_switch_inline,
    get_user_contextual_keyboard,
)
from uk_management_bot.keyboards.shifts import get_shifts_main_keyboard
from uk_management_bot.services.notification_service import async_notify_role_switched
from uk_management_bot.utils.helpers import get_text
import logging

logger = logging.getLogger(__name__)

router = Router()

# Добавляем middleware в роутер
from uk_management_bot.middlewares.auth import auth_middleware, role_mode_middleware
router.message.middleware(auth_middleware)
router.message.middleware(role_mode_middleware)
router.callback_query.middleware(auth_middleware)
router.callback_query.middleware(role_mode_middleware)

class AdminPasswordStates(StatesGroup):
    """Состояния для ввода пароля администратора"""
    waiting_for_password = State()

@router.message(Command("start"))
async def cmd_start(message: Message, db: Session, state: FSMContext = None, roles: list[str] = None, active_role: str = None, user_status: str = None):
    """Обработчик команды /start"""
    logger.info(f"Получена команда /start от пользователя {message.from_user.id}. Текст: '{message.text}'")
    
    # Очищаем состояние FSM при команде /start (помогает выйти из зависших состояний)
    if state:
        await state.clear()
        logger.info(f"[CMD_START] Очищено состояние FSM для пользователя {message.from_user.id}")
    
    auth_service = AuthService(db)
    
    # Проверяем, есть ли параметр с токеном приглашения
    if message.text and len(message.text.split()) > 1:
        param = message.text.split()[1].strip()
        
        # Если это команда join с токеном
        if param.startswith("join_"):
            token = param.replace("join_", "")
            
            # Если это токен приглашения, обрабатываем его
            if token.startswith("invite_v1:"):
                lang = message.from_user.language_code or "ru"
            
            try:
                # Проверяем rate limiting
                if not InviteRateLimiter.is_allowed(message.from_user.id):
                    remaining_minutes = InviteRateLimiter.get_remaining_time(message.from_user.id) // 60
                    await message.answer(
                        get_text("invites.rate_limited", language=lang, minutes=remaining_minutes)
                    )
                    logger.warning(f"Превышен rate limit для /start с токеном от пользователя {message.from_user.id}")
                    return
                
                # Валидируем токен
                invite_service = InviteService(db)
                
                try:
                    invite_data = invite_service.validate_invite(token)
                except ValueError as e:
                    error_msg = str(e).lower()
                    if "expired" in error_msg:
                        await message.answer(get_text("invites.expired_token", language=lang))
                    elif "already used" in error_msg:
                        await message.answer(get_text("invites.used_token", language=lang))
                    else:
                        await message.answer(get_text("invites.invalid_token", language=lang))
                    
                    logger.info(f"Невалидный токен в /start от {message.from_user.id}: {e}")
                    return
                
                # Обрабатываем присоединение
                user = await auth_service.process_invite_join(
                    telegram_id=message.from_user.id,
                    invite_data=invite_data,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name
                )
                
                # Отмечаем nonce как использованный
                invite_service.mark_nonce_used(
                    invite_data["nonce"], 
                    message.from_user.id, 
                    invite_data
                )
                
                # Отправляем подтверждение
                role = invite_data["role"]
                role_name = get_text(f"roles.{role}", language=lang)
                
                success_message = get_text(
                    "invites.success_joined", 
                    language=lang, 
                    role=role_name
                )
                
                # Добавляем информацию о специализации
                if role == "executor" and invite_data.get("specialization"):
                    specializations = invite_data["specialization"].split(",")
                    spec_names = [get_text(f"specializations.{spec.strip()}", language=lang) for spec in specializations]
                    success_message += f"\nСпециализация: {', '.join(spec_names)}"
                
                await message.answer(success_message)
                logger.info(f"Пользователь {message.from_user.id} присоединился по токену через /start")
                return
                
            except Exception as e:
                logger.error(f"Ошибка обработки токена в /start от {message.from_user.id}: {e}")
                await message.answer(get_text("invites.invalid_token", language=lang))
                return
    
    # Если нет токена, продолжаем обычную обработку /start
    await handle_regular_start(message, db, roles, active_role, user_status)

async def handle_regular_start(message: Message, db: Session, roles: list[str] = None, active_role: str = None, user_status: str = None):
    """Обработка обычного /start без токена"""
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
    
    # ОБНОВЛЕНО: Проверяем полноту профиля с новой системой квартир
    has_approved_apartment = any(ua.status == 'approved' for ua in user.user_apartments) if user.user_apartments else False
    is_profile_complete = user.phone and has_approved_apartment

    if not is_profile_complete and user.status == "pending":
        # Новый пользователь - показываем онбординг
        welcome_text = get_text("onboarding.welcome_new_user", language=lang)
        welcome_text += f"\n\n{get_text('onboarding.profile_incomplete', language=lang)}"

        # Создаём клавиатуру онбординга
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        missing_items = []
        if not user.phone:
            missing_items.append("📱 Указать телефон" if lang == "ru" else "📱 Telefon ko'rsatish")
        if not has_approved_apartment:
            missing_items.append("🏠 Выбрать квартиру" if lang == "ru" else "🏠 Kvartira tanlash")
        
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

    await message.answer(welcome_text, reply_markup=get_main_keyboard_for_role(active_role, roles, user.status))
    logger.info(f"Пользователь {message.from_user.id} запустил бота")

@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, db: Session, roles: list[str] = None, active_role: str = None, user_status: str = None):
    """Обработчик команды /menu - возврат в главное меню с очисткой состояния"""
    logger.info(f"Получена команда /menu от пользователя {message.from_user.id}")
    
    # Очищаем состояние FSM
    await state.clear()
    logger.info(f"[CMD_MENU] Очищено состояние FSM для пользователя {message.from_user.id}")
    
    # Показываем главное меню
    await handle_regular_start(message, db, roles, active_role, user_status)

# Удаляем этот обработчик, так как он не нужен
# Telegram автоматически обрабатывает кнопку "Начать" и отправляет /start

@router.callback_query(F.data == "restart_bot")
async def handle_restart_bot(callback: CallbackQuery, db: Session, roles: list[str] = None, active_role: str = None, user_status: str = None):
    """Обработчик кнопки перезапуска бота"""
    try:
        # Получаем пользователя
        auth_service = AuthService(db)
        user = await auth_service.get_user_by_telegram_id(callback.from_user.id)
        
        if not user:
            await callback.answer("Ошибка: пользователь не найден", show_alert=True)
            return
        
        # Обновляем язык пользователя
        if callback.from_user.language_code:
            await auth_service.update_user_language(
                callback.from_user.id, 
                callback.from_user.language_code
            )
        
        # Формируем простое сообщение об успешном перезапуске
        lang = callback.from_user.language_code or "ru"
        welcome_text = "✅ Бот успешно перезапущен!\n\nТеперь вы можете использовать все функции."
        
        # Формируем клавиатуру в зависимости от роли
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
        
        # Отправляем новое сообщение с обновленным меню
        await callback.message.answer(
            welcome_text,
            reply_markup=get_main_keyboard_for_role(active_role, roles, user.status)
        )
        
        await callback.answer("Бот перезапущен!")
        logger.info(f"Пользователь {callback.from_user.id} перезапустил бота через кнопку")
        
    except Exception as e:
        logger.error(f"Ошибка перезапуска бота: {e}")
        await callback.answer("Ошибка перезапуска", show_alert=True)

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
    from uk_management_bot.handlers.requests import show_my_requests
    await show_my_requests(message, state)


@router.message(F.text == "📦 Архив")
async def executor_archive_requests(message: Message, state: FSMContext):
    """Открывает список заявок пользователя с фильтром Архив."""
    await state.update_data(my_requests_status="archive", my_requests_page=1)
    from uk_management_bot.handlers.requests import show_my_requests
    await show_my_requests(message, state)


@router.message(F.text == "🔄 Смена")
async def executor_shift_menu(message: Message):
    """Показывает клавиатуру управления сменой."""
    await message.answer("Меню смены:", reply_markup=get_shifts_main_keyboard())


@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message, db: Session, roles: list[str] = None, active_role: str = None, user_status: str = None):
    """Показывает расширенный профиль пользователя"""

    
    try:
        from uk_management_bot.services.profile_service import ProfileService
        profile_service = ProfileService(db)
        
        # Получаем полные данные профиля
        profile_data = profile_service.get_user_profile_data(message.from_user.id)
        
        if not profile_data:
            # Ошибка получения данных
            lang = message.from_user.language_code or "ru"
            await message.answer(
                get_text("errors.unknown_error", language=lang),
                reply_markup=get_main_keyboard_for_role(active_role or "applicant", roles or ["applicant"], user_status)
            )
            return
        
        # Форматируем текст профиля
        lang = message.from_user.language_code or "ru"
        profile_text = profile_service.format_profile_text(profile_data, language=lang)
        
        # Отправляем профиль с клавиатурой переключения ролей
        user_roles = profile_data.get('roles', ['applicant'])
        user_active_role = profile_data.get('active_role', 'applicant')
        
        # Парсим роли из JSON строки, если это строка
        if isinstance(user_roles, str):
            try:
                import json
                user_roles = json.loads(user_roles)
            except Exception:
                user_roles = ['applicant']
        
        # Убеждаемся, что user_roles - это список
        if not isinstance(user_roles, list):
            user_roles = ['applicant']
        
        # Добавляем кнопку редактирования к профилю
        keyboard = get_role_switch_inline(user_roles, user_active_role)
        rows = list(keyboard.inline_keyboard)
        rows.append([{"text": "✏️ Редактировать профиль", "callback_data": "edit_profile"}])
        
        from aiogram.types import InlineKeyboardMarkup
        new_keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        
        await message.answer(
            profile_text, 
            reply_markup=new_keyboard
        )
        
        logger.info(f"Показан профиль пользователя {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка отображения профиля {message.from_user.id}: {e}")
        lang = message.from_user.language_code or "ru"
        await message.answer(
            get_text("errors.unknown_error", language=lang),
            reply_markup=get_main_keyboard_for_role(active_role or "applicant", roles or ["applicant"], "approved")
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
        from uk_management_bot.services.auth_service import AuthService
        from uk_management_bot.utils.auth_helpers import get_user_roles, get_active_role
        auth = AuthService(db)
        user = await auth.get_user_by_telegram_id(message.from_user.id)
        if user:
            # Используем универсальную функцию парсинга ролей (поддерживает CSV и JSON)
            roles = get_user_roles(user)
            active_role = get_active_role(user)
    except Exception:
        pass
    role_name = get_text(f"roles.{active_role}", language=message.from_user.language_code or "ru")
    text = get_text("role.switch_title", language=message.from_user.language_code or "ru", role=role_name)
    await message.answer(text, reply_markup=get_role_switch_inline(roles, active_role))


@router.callback_query(F.data.startswith("switch_role:"))
async def switch_role(cb: CallbackQuery, db: Session, roles: list[str] = None, active_role: str = None, user_status: str = None):
    """Переключение роли пользователя"""
    roles = roles or ["applicant"]
    target = cb.data.split(":", 1)[1]
    
    # Проверяем, что целевая роль доступна пользователю
    if target not in roles:
        lang = cb.from_user.language_code or "ru"
        await cb.answer(get_text("role.not_allowed", language=lang), show_alert=True)
        return
    
    try:
        # Обновляем активную роль в базе данных
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.telegram_id == cb.from_user.id).first()
        if not user:
            lang = cb.from_user.language_code or "ru"
            await cb.answer(get_text("errors.user_not_found", language=lang), show_alert=True)
            return
        
        old_active = user.active_role
        user.active_role = target
        db.commit()
        
        # Уведомляем пользователя
        await cb.answer(get_text("role.switched", language=cb.from_user.language_code or "ru"))
        
        # Пересобираем меню с новой активной ролью
        await cb.message.answer(
            "Главное меню:", 
            reply_markup=get_main_keyboard_for_role(target, roles, "approved")
        )
        
        # Отправляем уведомление о смене режима
        try:
            from aiogram import Bot
            bot: Bot = cb.message.bot
            await async_notify_role_switched(bot, db, user, old_active or "", target)
        except Exception:
            pass
            
    except Exception as e:
        logger.error(f"Ошибка при переключении роли: {e}")
        lang = cb.from_user.language_code or "ru"
        await cb.answer(get_text("errors.unknown_error", language=lang), show_alert=True)

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
async def process_admin_password(message: Message, state: FSMContext, db: Session, user_status: str = None):
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
            reply_markup=get_main_keyboard_for_role(active_role, roles_list, "approved")
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
