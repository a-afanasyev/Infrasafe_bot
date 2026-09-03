"""Базовые хендлеры: /start, /menu, /help, /admin, профиль, переключение ролей.

AUD3-07/AUD5-ARCH-1 (A2-хвост, волна 7): DB-фаза каждого хендлера — цельный
sync unit-of-work, исполняемый в worker-потоке через ``run_db``; наружу выходят
только примитивы/DTO, ORM-строки за границу потока не идут (у них там нет живой
сессии). Telegram-IO (ответы, уведомление о смене режима) — вне сессии.
``@require_role``-хендлер объявляет ``user``/``roles`` (DI для декоратора),
но НЕ ``db``: иначе aiogram DI снова инъецирует middleware-сессию.
Тестовый seam — keyword-only ``_db``.

Инвентарь живости: все 15 хендлеров живые. ``cmd_start`` — на ``start_router``,
который main.py включает ПЕРВЫМ (он же перекрывает onboarding.start_onboarding);
``restart_bot`` рождают api/residents/notify.py, user_management/panels.py,
user_management/fsm.py и user_verification/access_decision.py; текстовые триггеры
(профиль, смена роли, смена, помощь, назад, отмена, активные, архив) — кнопки
главного меню из keyboards/base.py; ``RoleSwitchCB`` — get_role_switch_inline;
/menu, /help, /admin — команды. Мёртвых нет.
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dataclasses import dataclass
from typing import Optional
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.invite_service import InviteService, InviteRateLimiter
from uk_management_bot.keyboards.base import (
    get_cancel_keyboard,
    get_main_keyboard_for_role,
    get_role_switch_inline,
    get_start_role_choice_inline,
    get_user_contextual_keyboard,
)
from uk_management_bot.keyboards.shifts import get_shifts_main_keyboard
from uk_management_bot.services.notification_service import (
    build_role_switched_message,
    send_to_user,
)
from uk_management_bot.utils.helpers import get_text, get_user_language
from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.utils.callback_factories import RoleSwitchCB
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.filters import RoleFilter
from uk_management_bot.config.settings import settings
from uk_management_bot.utils.button_texts import (
    get_profile_texts,
    get_switch_role_texts,
    get_active_requests_texts,
    get_archive_texts,
    get_shift_texts,
    get_help_texts,
    get_back_texts,
    get_cancel_texts,
)
import logging

logger = logging.getLogger(__name__)

router = Router()

# Dedicated router for /start — registered FIRST in main.py to catch /start from any FSM state.
# This ensures /start always works, even when the user is stuck in a FSM state
# owned by another router (e.g., RequestStates, ManagerStates, ShiftManagementStates).
start_router = Router(name="start")

# Single Source of Truth for button texts - TASK 17
# Константы для фильтрации сообщений
PROFILE_TEXTS = get_profile_texts()
SWITCH_ROLE_TEXTS = get_switch_role_texts()
ACTIVE_REQUESTS_TEXTS = get_active_requests_texts()
ARCHIVE_TEXTS = get_archive_texts()
SHIFT_TEXTS = get_shift_texts()
HELP_TEXTS = get_help_texts()
BACK_TEXTS = get_back_texts()
CANCEL_TEXTS = get_cancel_texts()

# NOTE: auth_middleware and role_mode_middleware are registered globally in main.py
# Do NOT register them again at router level to avoid double execution.

class AdminPasswordStates(StatesGroup):
    """Состояния для ввода пароля администратора"""
    waiting_for_password = State()


# ==========================================================================
# DTO + sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке
# через run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# Наружу — примитивы и готовые InlineKeyboardMarkup: user_apartments (lazy-связь),
# ProfileService и парсеры ролей читают ORM, поэтому живут внутри юнитов.
# ==========================================================================


@dataclass(frozen=True)
class _MenuContext:
    """Всё, что нужно для сборки главного меню — только примитивы."""
    status: Optional[str]
    phone: Optional[str]
    has_approved_apartment: bool
    has_any_apartment: bool
    db_roles: list
    active_role: Optional[str]


def _menu_context(user) -> _MenuContext:
    """ORM-строка → DTO. Вызывается ТОЛЬКО внутри юнита (lazy-связи, парсеры)."""
    # ОБНОВЛЕНО: Проверяем полноту профиля с новой системой квартир
    has_approved_apartment = any(ua.status == 'approved' for ua in user.user_apartments) if user.user_apartments else False
    return _MenuContext(
        status=user.status,
        phone=user.phone,
        has_approved_apartment=has_approved_apartment,
        # Заявка на квартиру в ЛЮБОМ статусе = регистрация жителя уже начата.
        # Полноту профиля по-прежнему определяет только approved (поле выше);
        # это — признак «человек уже сделал выбор», для развилки первого входа.
        has_any_apartment=bool(user.user_apartments),
        # COD-01: канонический парсер ролей (JSON+CSV)
        db_roles=parse_roles_safe(getattr(user, "roles", None)),
        active_role=getattr(user, "active_role", None),
    )


def _needs_role_choice(ctx: _MenuContext) -> bool:
    """Первый вход: человек ещё никак себя не обозначил.

    Развилку «житель / сотрудник» показываем только здесь. Как только он оставил
    телефон, подал заявку на квартиру (в любом статусе) или получил роль сверх
    applicant — выбор считается сделанным, и вопрос больше не задаём.
    """
    return (
        ctx.status == "pending"
        and not ctx.phone
        and not ctx.has_any_apartment
        and (ctx.db_roles or ["applicant"]) == ["applicant"]
    )


def _load_start_context(db, telegram_id: int, username, first_name, last_name) -> _MenuContext:
    """Получает или создаёт пользователя и отдаёт DTO для меню."""
    auth_service = AuthService(db)

    # Получаем или создаем пользователя
    user = auth_service.get_or_create_user_sync(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name
    )
    return _menu_context(user)


def _load_menu_context(db, telegram_id: int) -> Optional[_MenuContext]:
    """-> DTO меню | None (пользователя нет в БД).

    Запрос — тело ``AuthService.get_user_by_telegram_id`` 1:1: метод объявлен
    ``async def`` при чистом sync-SQL, из юнита его не await'нуть.
    """
    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if not user:
        return None

    return _menu_context(user)


def _apply_invite_start(db, token: str, telegram_id: int, username, first_name, last_name):
    """-> ('invalid', текст ошибки) | ('ok', invite_data).

    Валидация токена и присоединение живут в ОДНОЙ транзакции осознанно:
    ``_use_nonce_atomically`` только flush'ит INSERT nonce внутри SAVEPOINT, а
    коммитит его тот самый ``commit`` из ``process_invite_join``. Разнеси их по
    двум сессиям — nonce откатится при закрытии первой, и одноразовый токен
    перестанет быть одноразовым.
    """
    # Валидируем токен
    invite_service = InviteService(db)

    try:
        # Atomically validate and mark nonce as used in one transaction
        invite_data = invite_service.validate_invite(token, mark_used_by=telegram_id)
    except ValueError as e:
        return ("invalid", str(e))

    # Обрабатываем присоединение
    auth_service = AuthService(db)
    auth_service.process_invite_join_sync(
        telegram_id=telegram_id,
        invite_data=invite_data,
        username=username,
        first_name=first_name,
        last_name=last_name
    )
    return ("ok", invite_data)


def _lang(db, telegram_id: int) -> str:
    """Язык пользователя из БД (тот же helper, что и раньше)."""
    return get_user_language(telegram_id, db)


def _load_profile_screen(db, telegram_id: int):
    """-> (текст профиля, готовая клавиатура) | None (данных профиля нет).

    ProfileService читает ORM, поэтому и выборка, и форматирование, и сборка
    клавиатуры происходят внутри сессии; наружу уходит готовый markup.
    """
    from uk_management_bot.services.profile_service import ProfileService
    profile_service = ProfileService(db)

    # Получаем полные данные профиля
    profile_data = profile_service.get_user_profile_data(telegram_id)

    if not profile_data:
        return None

    # Получаем язык пользователя из базы данных
    from uk_management_bot.utils.helpers import get_user_language
    lang = get_user_language(telegram_id, db)

    # Форматируем текст профиля
    profile_text = profile_service.format_profile_text(profile_data, language=lang)

    # Отправляем профиль с клавиатурой переключения ролей
    user_roles = profile_data.get('roles', ['applicant'])
    user_active_role = profile_data.get('active_role', 'applicant')

    # Парсим роли (COD-01: канонический парсер, JSON+CSV+list)
    user_roles = parse_roles_safe(user_roles) or ['applicant']

    # Добавляем кнопку редактирования к профилю
    keyboard = get_role_switch_inline(user_roles, user_active_role, language=lang)
    rows = list(keyboard.inline_keyboard)
    rows.append([{"text": get_text("profile.edit", language=lang), "callback_data": "edit_profile"}])

    from aiogram.types import InlineKeyboardMarkup
    new_keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    return profile_text, new_keyboard


def _load_roles_fallback(db, telegram_id: int):
    """-> (roles, active_role) | None. Фолбэк из БД, если roles пришли усечёнными.

    Исходный ``except Exception: pass`` сохранён 1:1 — при любой ошибке
    хендлер остаётся на ролях из DI.
    """
    try:
        from uk_management_bot.utils.auth_helpers import get_user_roles, get_active_role
        # Запрос — тело AuthService.get_user_by_telegram_id 1:1 (метод объявлен
        # async при чистом sync-SQL, из юнита его не await'нуть).
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            # Используем универсальную функцию парсинга ролей (поддерживает CSV и JSON)
            return get_user_roles(user), get_active_role(user)
    except Exception:
        pass
    return None


def _apply_active_role(db, telegram_id: int, target: str):
    """Переключает активную роль. -> (True, текст уведомления) | (False, None).

    Текст уведомления собирается здесь: ``build_role_switched_message`` читает
    ``user.language`` у ORM-строки, а она за границу потока не выходит.
    """
    # Обновляем активную роль в базе данных
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return False, None

    user.active_role = target
    db.commit()
    return True, build_role_switched_message(user, target)


def _apply_admin_password(db, telegram_id: int, password: str):
    """Проверяет пароль и назначает администратора.

    -> (success, roles_list, active_role). При неудачной проверке роли не
    читаются вовсе — как и раньше.
    """
    auth_service = AuthService(db)

    # Проверяем пароль и назначаем администратора
    success = auth_service.make_admin_by_password_sync(
        telegram_id=telegram_id,
        password=password
    )

    if not success:
        return False, ["applicant"], "applicant"

    # Перечитываем пользователя и строим меню в соответствии с активной ролью
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        # Роли и активная роль — через единый резолвер (ARCH-07)
        roles_list = ["applicant"]
        active_role = "applicant"
        if user:
            from uk_management_bot.utils.auth_helpers import (
                get_user_roles,
                get_active_role,
            )
            roles_list = get_user_roles(user)
            active_role = get_active_role(user)
            if active_role not in roles_list:
                active_role = roles_list[0] if roles_list else "applicant"
    except Exception:
        roles_list = ["applicant"]
        active_role = "applicant"

    return True, roles_list, active_role


@start_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext = None, roles: list[str] = None, active_role: str = None, user_status: str = None, language: str = "ru", *, _db=None):
    """Обработчик команды /start"""
    logger.info(f"Получена команда /start от пользователя {message.from_user.id}. Текст: '{message.text}'")
    
    # Очищаем состояние FSM при команде /start (помогает выйти из зависших состояний)
    if state:
        await state.clear()
        logger.info(f"[CMD_START] Очищено состояние FSM для пользователя {message.from_user.id}")

    # Проверяем, есть ли параметр с токеном приглашения
    if message.text and len(message.text.split()) > 1:
        param = message.text.split()[1].strip()

        # Если это команда join с токеном
        if param.startswith("join_"):
            token = param.replace("join_", "")
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

                # Валидация токена + присоединение — ОДИН юнит, одна транзакция
                # (см. docstring _apply_invite_start про SAVEPOINT на nonce).
                verdict, payload = await run_db(
                    lambda s: _apply_invite_start(
                        s, token, message.from_user.id,
                        message.from_user.username,
                        message.from_user.first_name,
                        message.from_user.last_name,
                    ),
                    db=_db,
                )

                if verdict == "invalid":
                    error_msg = payload.lower()
                    if "expired" in error_msg:
                        await message.answer(get_text("invites.expired_token", language=lang))
                    elif "already used" in error_msg:
                        await message.answer(get_text("invites.used_token", language=lang))
                    else:
                        await message.answer(get_text("invites.invalid_token", language=lang))

                    logger.info(f"Невалидный токен в /start от {message.from_user.id}: {payload}")
                    return

                invite_data = payload

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
    await handle_regular_start(message, roles, active_role, user_status, language=language,
                               offer_role_choice=True, _db=_db)

def _build_onboarding_screen(ctx: _MenuContext, lang: str):
    """-> (текст, клавиатура) онбординга жителя, либо (текст, None).

    Вынесено из handle_regular_start дословно, чтобы экран у жителя был ОДИН:
    колбэк «Я житель» зовёт эту же сборку. Собственная копия экрана незаметно
    потеряла бы WebApp-кнопку регистрации при следующей правке.
    """
    welcome_text = get_text("onboarding.welcome_new_user", language=lang)
    welcome_text += f"\n\n{get_text('onboarding.profile_incomplete', language=lang)}"

    # Создаём клавиатуру онбординга
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    missing_items = []
    if not ctx.phone:
        missing_items.append(get_text("base.handlers.btn_specify_phone", language=lang))
    if not ctx.has_approved_apartment:
        missing_items.append(get_text("base.handlers.btn_select_apartment", language=lang))

    if not missing_items:
        return welcome_text, None

    keyboard_rows = [[KeyboardButton(text=item)] for item in missing_items]
    # Дополнительная кнопка: регистрация через WebApp-форму (если задан FRONTEND_URL).
    # Текстовая, БЕЗ web_app: reply web_app не передаёт initData — ссылку шлёт
    # handlers/webapp_buttons.py inline-кнопкой по нажатию.
    if settings.FRONTEND_URL:
        keyboard_rows.append([
            KeyboardButton(text=get_text("base.handlers.btn_register_webapp", language=lang))
        ])
    return welcome_text, ReplyKeyboardMarkup(
        keyboard=keyboard_rows,
        resize_keyboard=True,
        one_time_keyboard=False
    )


async def handle_regular_start(message: Message, roles: list[str] = None, active_role: str = None, user_status: str = None, language: str = "ru", *, offer_role_choice: bool = False, _db=None):
    """Обработка обычного /start без токена.

    ``offer_role_choice`` включает развилку «житель / сотрудник» и передаётся
    ТОЛЬКО из cmd_start: /menu переспрашивать роль не должен.
    """
    ctx = await run_db(
        lambda s: _load_start_context(
            s, message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name,
        ),
        db=_db,
    )

    # Проверяем, нужен ли онбординг
    lang = language

    has_approved_apartment = ctx.has_approved_apartment
    is_profile_complete = ctx.phone and has_approved_apartment

    if offer_role_choice and _needs_role_choice(ctx):
        # Первый вход: пока не спросим, человек молча уйдёт в жители — ровно то,
        # что случалось с приглашёнными сотрудниками.
        choice_text = get_text("start_role.title", language=lang)
        choice_text += f"\n\n{get_text('start_role.hint', language=lang)}"
        await message.answer(choice_text, reply_markup=get_start_role_choice_inline(lang))
        logger.info(f"Пользователю {message.from_user.id} показана развилка роли")
        return

    if not is_profile_complete and ctx.status == "pending":
        # Новый пользователь - показываем онбординг
        welcome_text, onboarding_keyboard = _build_onboarding_screen(ctx, lang)
        if onboarding_keyboard is not None:
            await message.answer(welcome_text, reply_markup=onboarding_keyboard)
            logger.info(f"Новый пользователь {message.from_user.id} начал онбординг")
            return

    # Обычное приветствие
    welcome_text = get_text("welcome", language=lang)

    if ctx.status == "pending":
        welcome_text += f"\n\n{get_text('auth.pending', language=lang)}"
    elif ctx.status == "blocked":
        welcome_text += f"\n\n{get_text('auth.blocked', language=lang)}"
    else:
        welcome_text += f"\n\n{get_text('auth.approved', language=lang)}"

    # Формируем клавиатуру в зависимости от роли
    # Фолбэк: если middleware не передал корректные roles/active_role — берём из БД пользователя
    roles = roles or ["applicant"]
    active_role = active_role or roles[0]
    db_roles = ctx.db_roles
    if db_roles:
        roles = db_roles
    if ctx.active_role:
        active_role = ctx.active_role if ctx.active_role in roles else roles[0]

    await message.answer(welcome_text, reply_markup=get_main_keyboard_for_role(active_role, roles, ctx.status, language=lang))
    logger.info(f"Пользователь {message.from_user.id} запустил бота")

@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, roles: list[str] = None, active_role: str = None, user_status: str = None, language: str = "ru", *, _db=None):
    """Обработчик команды /menu - возврат в главное меню с очисткой состояния"""
    logger.info(f"Получена команда /menu от пользователя {message.from_user.id}")
    
    # Очищаем состояние FSM
    await state.clear()
    logger.info(f"[CMD_MENU] Очищено состояние FSM для пользователя {message.from_user.id}")
    
    # Показываем главное меню
    await handle_regular_start(message, roles, active_role, user_status, language=language, _db=_db)

# Удаляем этот обработчик, так как он не нужен
# Telegram автоматически обрабатывает кнопку "Начать" и отправляет /start

@router.callback_query(F.data == "restart_bot")
async def handle_restart_bot(callback: CallbackQuery, roles: list[str] = None, active_role: str = None, user_status: str = None, language: str = "ru", *, _db=None):
    """Обработчик кнопки перезапуска бота"""
    try:
        # Получаем пользователя
        ctx = await run_db(
            lambda s: _load_menu_context(s, callback.from_user.id), db=_db
        )

        if ctx is None:
            lang = language
            await callback.answer(get_text("base.handlers.error_user_not_found", language=lang), show_alert=True)
            return

        lang = language
        welcome_text = get_text("bot.restarted", language=lang)

        # Формируем клавиатуру в зависимости от роли
        roles = roles or ["applicant"]
        active_role = active_role or roles[0]
        db_roles = ctx.db_roles
        if db_roles:
            roles = db_roles
        if ctx.active_role:
            active_role = ctx.active_role if ctx.active_role in roles else roles[0]

        # Отправляем новое сообщение с обновленным меню
        await callback.message.answer(
            welcome_text,
            reply_markup=get_main_keyboard_for_role(active_role, roles, ctx.status, language=language)
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

    await message.answer(help_text, reply_markup=await get_user_contextual_keyboard(message.from_user.id))

@router.message(F.text.in_(CANCEL_TEXTS))
async def cancel_action(message: Message, state: FSMContext, roles: list[str] = None, active_role: str = None, language: str = "ru"):
    """Отмена текущего действия"""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        lang = language
        await message.answer(
            get_text("cancel", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        logger.info(f"Пользователь {message.from_user.id} отменил действие в состоянии {current_state}")
    else:
        lang = language
        await message.answer(
            get_text("cancel", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )

@router.message(F.text.in_(BACK_TEXTS))
async def go_back(message: Message, state: FSMContext, roles: list[str] = None, active_role: str = None, *, _db=None):
    """Возврат в главное меню"""
    await state.clear()
    lang = await run_db(lambda s: _lang(s, message.from_user.id), db=_db)
    await message.answer(get_text("back", language=lang), reply_markup=await get_user_contextual_keyboard(message.from_user.id))


# Обработчики меню исполнителя
@router.message(F.text.in_(ACTIVE_REQUESTS_TEXTS))
async def executor_active_requests(message: Message, state: FSMContext):
    """Открывает список заявок пользователя с фильтром Активные."""
    await state.update_data(my_requests_status="active", my_requests_page=1)
    from uk_management_bot.handlers.requests import show_my_requests
    await show_my_requests(message, state)


# BUG-BOT-019: text "📦 Архив" is shared with admin panel — gate by active_role
# so this handler only fires when the user is acting as executor/applicant.
# Without this filter, the admin archive handler (registered earlier) wins.
@router.message(F.text.in_(ARCHIVE_TEXTS), RoleFilter(["executor", "applicant"]))
async def executor_archive_requests(message: Message, state: FSMContext):
    """Открывает список заявок пользователя с фильтром Архив."""
    await state.update_data(my_requests_status="archive", my_requests_page=1)
    from uk_management_bot.handlers.requests import show_my_requests
    await show_my_requests(message, state)


@router.message(F.text.in_(SHIFT_TEXTS))
@require_role(['executor'])
async def executor_shift_menu(message: Message, user: User = None, roles: list[str] = None, active_role: str = None, *, _db=None):
    """Показывает клавиатуру управления сменой.

    ``user``/``roles`` объявлены ради DI декоратора require_role (он читает их
    из kwargs); ``db`` НЕ объявляется — канон AUD3-37, иначе aiogram снова
    инъецирует middleware-сессию.
    """
    lang = await run_db(lambda s: _lang(s, message.from_user.id), db=_db)
    menu_text = get_text("shifts.menu_shifts", language=lang)
    if "." in menu_text:
        menu_text = get_text("base.handlers.shift_menu", language=lang)
    await message.answer(menu_text, reply_markup=get_shifts_main_keyboard(language=lang))


@router.message(F.text.in_(HELP_TEXTS))
async def show_help(message: Message, language: str = "ru", *, _db=None):
    """Показывает справку по использованию бота."""
    lang = await run_db(lambda s: _lang(s, message.from_user.id), db=_db)
    help_text = get_text("help.usage_help", language=lang)
    await message.answer(help_text)


@router.message(F.text.in_(PROFILE_TEXTS))
async def show_profile(message: Message, roles: list[str] = None, active_role: str = None, user_status: str = None, language: str = "ru", *, _db=None):
    """Показывает расширенный профиль пользователя"""

    try:
        loaded = await run_db(
            lambda s: _load_profile_screen(s, message.from_user.id), db=_db
        )

        if loaded is None:
            # Ошибка получения данных
            lang = language
            await message.answer(
                get_text("errors.unknown_error", language=lang),
                reply_markup=get_main_keyboard_for_role(active_role or "applicant", roles or ["applicant"], user_status, language=lang)
            )
            return

        profile_text, new_keyboard = loaded

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
            reply_markup=get_main_keyboard_for_role(active_role or "applicant", roles or ["applicant"], "approved", language=lang)
        )


@router.message(F.text.in_(SWITCH_ROLE_TEXTS))
async def choose_role(message: Message, roles: list[str] = None, active_role: str = None, language: str = "ru", *, _db=None):
    """Открывает inline‑переключатель ролей из главного меню.

    Показывается только если у пользователя более одной роли.
    """
    roles = roles or ["applicant"]
    active_role = active_role or roles[0]
    # Фолбэк из БД, если roles пришли усечёнными
    fallback = await run_db(
        lambda s: _load_roles_fallback(s, message.from_user.id), db=_db
    )
    if fallback is not None:
        roles, active_role = fallback
    role_name = get_text(f"roles.{active_role}", language=language)
    text = get_text("role.switch_title", language=language, role=role_name)
    await message.answer(text, reply_markup=get_role_switch_inline(roles, active_role, language=language))


@router.callback_query(RoleSwitchCB.filter())
async def switch_role(cb: CallbackQuery, callback_data: RoleSwitchCB, roles: list[str] = None, active_role: str = None, user_status: str = None, language: str = "ru", *, _db=None):
    """Переключение роли пользователя"""
    roles = roles or ["applicant"]
    target = callback_data.target

    # Проверяем, что целевая роль доступна пользователю
    if target not in roles:
        lang = language
        await cb.answer(get_text("role.not_allowed", language=lang), show_alert=True)
        return

    try:
        switched, notify_text = await run_db(
            lambda s: _apply_active_role(s, cb.from_user.id, target), db=_db
        )
        if not switched:
            lang = language
            await cb.answer(get_text("errors.user_not_found", language=lang), show_alert=True)
            return

        # Уведомляем пользователя
        await cb.answer(get_text("role.switched", language=language))
        
        # Пересобираем меню с новой активной ролью
        lang = language
        await cb.message.answer(
            get_text("base.handlers.main_menu", language=lang), 
            reply_markup=get_main_keyboard_for_role(target, roles, "approved", language=lang)
        )

        # Отправляем уведомление о смене режима. B3-раскрой: текст собран в
        # юните (build_role_switched_message читает user.language у ORM-строки),
        # отправка — здесь, вне сессии. Best-effort, как и раньше.
        try:
            from aiogram import Bot
            bot: Bot = cb.message.bot
            await send_to_user(bot, cb.from_user.id, notify_text)
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
        reply_markup=get_cancel_keyboard(language=lang)
    )

@router.message(AdminPasswordStates.waiting_for_password)
async def process_admin_password(message: Message, state: FSMContext, user_status: str = None, language: str = "ru", *, _db=None):
    """Обработка введенного пароля администратора"""
    from uk_management_bot.utils.safe_localization import safe_get_text
    lang = language

    if message.text in CANCEL_TEXTS:
        await state.clear()
        await message.answer(safe_get_text("errors.cancelled", language=lang), reply_markup=await get_user_contextual_keyboard(message.from_user.id))
        return

    # SEC-01: rate-limit на перебор пароля — 5 попыток за 5 минут с аккаунта.
    from uk_management_bot.utils.redis_rate_limiter import is_rate_limited
    if await is_rate_limited(f"admin_pwd:{message.from_user.id}", 5, 300):
        await state.clear()
        logger.warning(f"Rate-limit на ввод admin-пароля для пользователя {message.from_user.id}")
        await message.answer(
            safe_get_text("admin.too_many_attempts", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Проверяем пароль и назначаем администратора (и, при успехе, сразу
    # перечитываем роли — обе фазы в одном юните, как и раньше в одной сессии)
    success, roles_list, active_role = await run_db(
        lambda s: _apply_admin_password(s, message.from_user.id, message.text), db=_db
    )

    await state.clear()

    if success:
        await message.answer(
            safe_get_text("admin.assigned_successfully", language=lang),
            reply_markup=get_main_keyboard_for_role(active_role, roles_list, "approved", language=lang)
        )
        logger.info(f"Пользователь {message.from_user.id} назначен администратором")
    else:
        await message.answer(
            safe_get_text("admin.assignment_failed", language=lang),
            reply_markup=await get_user_contextual_keyboard(message.from_user.id)
        )
        logger.warning(f"Неверная попытка назначения администратора от {message.from_user.id}")
