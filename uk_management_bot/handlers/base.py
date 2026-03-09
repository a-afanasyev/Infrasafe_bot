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
from uk_management_bot.utils.helpers import get_text, get_user_language
from uk_management_bot.utils.callback_factories import RoleSwitchCB
from uk_management_bot.middlewares.auth import require_role
import logging

logger = logging.getLogger(__name__)

router = Router()

# Single Source of Truth for button texts - TASK 17
from uk_management_bot.utils.button_texts import (
    get_profile_texts,
    get_switch_role_texts,
    get_active_requests_texts,
    get_archive_texts,
    get_shift_texts,
    get_help_texts,
    get_back_texts,
)
from uk_management_bot.utils.helpers import get_user_language

# Константы для фильтрации сообщений
PROFILE_TEXTS = get_profile_texts()
SWITCH_ROLE_TEXTS = get_switch_role_texts()
ACTIVE_REQUESTS_TEXTS = get_active_requests_texts()
ARCHIVE_TEXTS = get_archive_texts()
SHIFT_TEXTS = get_shift_texts()
HELP_TEXTS = get_help_texts()
BACK_TEXTS = get_back_texts()

# NOTE: auth_middleware and role_mode_middleware are registered globally in main.py
# Do NOT register them again at router level to avoid double execution.

class AdminPasswordStates(StatesGroup):
    """Состояния для ввода пароля администратора"""
    waiting_for_password = State()

@router.message(Command("start"))
async def cmd_start(message: Message, db: Session, state: FSMContext = None, roles: list[str] = None, active_role: str = None, user_status: str = None, language: str = "ru"):
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
                lang = language
            
            try:
                # Проверяем rate limiting
                if not await InviteRateLimiter.is_allowed(message.from_user.id):
                    remaining_minutes = await InviteRateLimiter.get_remaining_time(message.from_user.id) // 60
                    await message.answer(
                        get_text("invites.rate_limited", language=lang, minutes=remaining_minutes)
                    )
                    logger.warning(f"Превышен rate limit для /start с токеном от пользователя {message.from_user.id}")
                    return
                
                # Валидируем токен
                invite_service = InviteService(db)
                
                try:
                    # Atomically validate and mark nonce as used in one transaction
                    invite_data = invite_service.validate_invite(token, mark_used_by=message.from_user.id)
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
                    success_message += "\n" + get_text("base.handlers.specialization_label", language=lang) + ": " + ", ".join(spec_names)
                
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
            missing_items.append(get_text("base.handlers.btn_specify_phone", language=lang))
        if not has_approved_apartment:
            missing_items.append(get_text("base.handlers.btn_select_apartment", language=lang))
        
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
async def handle_restart_bot(callback: CallbackQuery, db: Session, roles: list[str] = None, active_role: str = None, user_status: str = None, language: str = "ru"):
    """Обработчик кнопки перезапуска бота"""
    try:
        # Получаем пользователя
        auth_service = AuthService(db)
        user = await auth_service.get_user_by_telegram_id(callback.from_user.id)
        
        if not user:
            lang = language
            await callback.answer(get_text("base.handlers.error_user_not_found", language=lang), show_alert=True)
            return
        
        # Обновляем язык пользователя
        if callback.from_user.language_code:
            await auth_service.update_user_language(
                callback.from_user.id, 
                callback.from_user.language_code
            )
        
        lang = language
        welcome_text = get_text("bot.restarted", language=lang)
        
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
        
        lang = language
        await callback.answer(get_text("base.handlers.bot_restarted", language=lang))
        logger.info(f"Пользователь {callback.from_user.id} перезапустил бота через кнопку")
        
    except Exception as e:
        logger.error(f"Ошибка перезапуска бота: {e}")
        await callback.answer(get_text("base.handlers.error_restart", language=language), show_alert=True)

@router.message(Command("help"))
async def cmd_help(message: Message, language: str = "ru"):
    """Обработчик команды /help"""
    lang = language
    help_text = get_text("base.handlers.help_text", language=lang)

    await message.answer(help_text, reply_markup=get_user_contextual_keyboard(message.from_user.id))

@router.message(F.text == "❌ Отмена")
async def cancel_action(message: Message, state: FSMContext, roles: list[str] = None, active_role: str = None, language: str = "ru"):
    """Отмена текущего действия"""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        lang = language
        await message.answer(
            get_text("cancel", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        logger.info(f"Пользователь {message.from_user.id} отменил действие в состоянии {current_state}")
    else:
        lang = language
        await message.answer(
            get_text("cancel", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )

@router.message(F.text.in_(BACK_TEXTS))
async def go_back(message: Message, state: FSMContext, db: Session = None, roles: list[str] = None, active_role: str = None):
    """Возврат в главное меню"""
    await state.clear()
    lang = get_user_language(message.from_user.id, db)
    await message.answer(get_text("back", language=lang), reply_markup=get_user_contextual_keyboard(message.from_user.id))


# Обработчики меню исполнителя
@router.message(F.text.in_(ACTIVE_REQUESTS_TEXTS))
async def executor_active_requests(message: Message, state: FSMContext):
    """Открывает список заявок пользователя с фильтром Активные."""
    await state.update_data(my_requests_status="active", my_requests_page=1)
    from uk_management_bot.handlers.requests import show_my_requests
    await show_my_requests(message, state)


@router.message(F.text.in_(ARCHIVE_TEXTS))
async def executor_archive_requests(message: Message, state: FSMContext):
    """Открывает список заявок пользователя с фильтром Архив."""
    await state.update_data(my_requests_status="archive", my_requests_page=1)
    from uk_management_bot.handlers.requests import show_my_requests
    await show_my_requests(message, state)


@router.message(F.text.in_(SHIFT_TEXTS))
@require_role(['executor'])
async def executor_shift_menu(message: Message, db: Session = None, roles: list[str] = None, active_role: str = None):
    """Показывает клавиатуру управления сменой."""
    lang = get_user_language(message.from_user.id, db)
    menu_text = get_text("shifts.menu_shifts", language=lang)
    if "." in menu_text:
        menu_text = get_text("base.handlers.shift_menu", language=lang)
    await message.answer(menu_text, reply_markup=get_shifts_main_keyboard(language=lang))


@router.message(F.text.in_(HELP_TEXTS))
async def show_help(message: Message, db: Session = None):
    """Показывает справку по использованию бота."""
    lang = get_user_language(message.from_user.id, db)
    help_text = get_text("help.usage_help", language=lang)
    if "." in help_text:
        help_text = get_text("base.handlers.help_text", language=lang)
    await message.answer(help_text)


@router.message(F.text.in_(PROFILE_TEXTS))
async def show_profile(message: Message, db: Session, roles: list[str] = None, active_role: str = None, user_status: str = None, language: str = "ru"):
    """Показывает расширенный профиль пользователя"""

    
    try:
        from uk_management_bot.services.profile_service import ProfileService
        profile_service = ProfileService(db)
        
        # Получаем полные данные профиля
        profile_data = profile_service.get_user_profile_data(message.from_user.id)
        
        if not profile_data:
            # Ошибка получения данных
            lang = language
            await message.answer(
                get_text("errors.unknown_error", language=lang),
                reply_markup=get_main_keyboard_for_role(active_role or "applicant", roles or ["applicant"], user_status)
            )
            return
        
        # Получаем язык пользователя из базы данных
        from uk_management_bot.utils.helpers import get_user_language
        lang = get_user_language(message.from_user.id, db)
        
        # Форматируем текст профиля
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
        keyboard = get_role_switch_inline(user_roles, user_active_role, language=lang)
        rows = list(keyboard.inline_keyboard)
        rows.append([{"text": get_text("profile.edit", language=lang), "callback_data": "edit_profile"}])
        
        from aiogram.types import InlineKeyboardMarkup
        new_keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        
        await message.answer(
            profile_text, 
            reply_markup=new_keyboard
        )
        
        logger.info(f"Показан профиль пользователя {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка отображения профиля {message.from_user.id}: {e}")
        lang = language
        await message.answer(
            get_text("errors.unknown_error", language=lang),
            reply_markup=get_main_keyboard_for_role(active_role or "applicant", roles or ["applicant"], "approved")
        )


@router.message(F.text.in_(SWITCH_ROLE_TEXTS))
async def choose_role(message: Message, db: Session, roles: list[str] = None, active_role: str = None, language: str = "ru"):
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
    role_name = get_text(f"roles.{active_role}", language=language)
    text = get_text("role.switch_title", language=language, role=role_name)
    await message.answer(text, reply_markup=get_role_switch_inline(roles, active_role))


@router.callback_query(RoleSwitchCB.filter())
async def switch_role(cb: CallbackQuery, callback_data: RoleSwitchCB, db: Session, roles: list[str] = None, active_role: str = None, user_status: str = None, language: str = "ru"):
    """Переключение роли пользователя"""
    roles = roles or ["applicant"]
    target = callback_data.target
    
    # Проверяем, что целевая роль доступна пользователю
    if target not in roles:
        lang = language
        await cb.answer(get_text("role.not_allowed", language=lang), show_alert=True)
        return
    
    try:
        # Обновляем активную роль в базе данных
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.telegram_id == cb.from_user.id).first()
        if not user:
            lang = language
            await cb.answer(get_text("errors.user_not_found", language=lang), show_alert=True)
            return
        
        old_active = user.active_role
        user.active_role = target
        db.commit()
        
        # Уведомляем пользователя
        await cb.answer(get_text("role.switched", language=language))
        
        # Пересобираем меню с новой активной ролью
        lang = language
        await cb.message.answer(
            get_text("base.handlers.main_menu", language=lang), 
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
        lang = language
        await cb.answer(get_text("errors.unknown_error", language=lang), show_alert=True)

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, language: str = "ru"):
    """Обработчик команды /admin - назначение администратора по паролю"""
    await state.set_state(AdminPasswordStates.waiting_for_password)
    lang = language
    await message.answer(
        get_text("base.handlers.admin_password_prompt", language=lang),
        reply_markup=get_cancel_keyboard()
    )

@router.message(AdminPasswordStates.waiting_for_password)
async def process_admin_password(message: Message, state: FSMContext, db: Session, user_status: str = None, language: str = "ru"):
    """Обработка введенного пароля администратора"""
    from uk_management_bot.utils.safe_localization import safe_get_text
    auth_service = AuthService(db)
    lang = language
    
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer(safe_get_text("errors.cancelled", language=lang), reply_markup=get_user_contextual_keyboard(message.from_user.id))
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
            safe_get_text("admin.assigned_successfully", language=lang),
            reply_markup=get_main_keyboard_for_role(active_role, roles_list, "approved")
        )
        logger.info(f"Пользователь {message.from_user.id} назначен администратором")
    else:
        await message.answer(
            safe_get_text("admin.assignment_failed", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        logger.warning(f"Неверная попытка назначения администратора от {message.from_user.id}")
