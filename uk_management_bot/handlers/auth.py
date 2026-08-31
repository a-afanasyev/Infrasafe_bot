"""Вход по кнопке/команде и регистрация по инвайт-токену (/join → анкета).

AUD3-07/AUD5-ARCH-1 (A2-хвост, волна 7): DB-фаза каждого хендлера — цельный
sync unit-of-work под ``run_db``; наружу выходят только примитивы. Telegram-IO
(уведомления админам, ответы пользователю) — вне сессии.

Инвентарь живости: все семь функций живые. ``/join`` и ``/login`` — команды;
``confirm_position`` / ``cancel_registration`` рождают внутрифайловые
клавиатуры анкеты; ``waiting_for_full_name`` / ``waiting_for_phone`` —
FSM-состояния той же цепочки. Мёртвых нет.

⚠️ Регистрация ``login_via_button`` по тексту кнопки «🔑 Войти»
(``auth.login_button``) МЁРТВАЯ: генератора этой кнопки в репозитории нет
вовсе. Сама функция живая — её напрямую зовёт ``login_command`` (/login),
поэтому она сконвертирована, а не заморожена.
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ..states.registration import RegistrationStates

from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.invite_service import InviteService, InviteRateLimiter, TokenAlreadyUsedError
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.keyboards.base import get_cancel_keyboard, get_main_keyboard_for_role
import logging

from uk_management_bot.utils.button_texts import get_login_texts

logger = logging.getLogger(__name__)
router = Router()

LOGIN_TEXTS = get_login_texts()


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# ==========================================================================


def _apply_login(db, telegram_id: int, username, first_name, last_name):
    """-> ('already_approved'|'ok'|'failed', статус пользователя).

    Статус читается ПОСЛЕ попытки авто-одобрения: auto_approve_user правит ту
    же строку в identity map, и исходный код брал ``user.status`` уже после неё.
    """
    auth = AuthService(db)
    user = auth.get_or_create_user_sync(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )
    if user.status == "approved":
        return ("already_approved", user.status)

    ok = auth.auto_approve_user_sync(telegram_id, role="applicant")
    return ("ok" if ok else "failed", user.status)


def _load_join_gate(db, token: str, telegram_id: int):
    """-> ('invalid', текст ошибки) | ('already_registered', None)
       | ('registration_pending', None) | ('ok', invite_data).

    ``validate_invite`` здесь БЕЗ ``mark_used_by`` — только чтение, nonce
    гасится позже, в ``_apply_registration``.
    """
    # Валидируем токен
    invite_service = InviteService(db)

    try:
        invite_data = invite_service.validate_invite(token)
    except ValueError as e:
        logger.info(f"Невалидный токен от {telegram_id}: {e}")
        return ("invalid", str(e))

    # Проверяем, не зарегистрирован ли уже пользователь. Запрос — тело
    # AuthService.get_user_by_telegram_id 1:1 (метод объявлен async при чистом
    # sync-SQL, из юнита его не await'нуть).
    existing_user = db.query(User).filter(User.telegram_id == telegram_id).first()
    logger.info(f"Проверка существующего пользователя {telegram_id}: {existing_user.status if existing_user else 'не найден'}")

    if existing_user:
        # Если пользователь уже одобрен, запрещаем повторную регистрацию
        if existing_user.status == "approved":
            logger.info(f"Пользователь {telegram_id} уже одобрен, регистрация запрещена")
            return ("already_registered", None)
        # Пользователь в статусе pending:
        # само-онбординговый кандидат (roles ровно ["applicant"], создан
        # обычным /start) ещё НЕ проходил инвайт — разрешаем апгрейд роли по
        # инвайту. Иначе инструкция «нажмите Начать, затем /join <token>»
        # ведёт в тупик: /start создаёт pending-applicant, а /join его же
        # отвергает. Кандидатов, уже поднявших роль по инвайту и ждущих
        # одобрения (в roles есть роль сверх applicant), не пускаем повторно.
        elif existing_user.status == "pending":
            existing_roles = parse_roles_safe(existing_user.roles)
            if existing_roles != ["applicant"]:
                logger.info(f"Пользователь {telegram_id} уже зарегистрирован со статусом pending, регистрация запрещена")
                return ("registration_pending", None)
            logger.info(f"Pending-applicant {telegram_id} проходит апгрейд роли по инвайту")
        # Для других статусов (blocked и т.д.) разрешаем повторную регистрацию
        else:
            logger.info(f"Пользователь {telegram_id} имеет статус {existing_user.status}, разрешаем повторную регистрацию")

    return ("ok", invite_data)


def _apply_registration(db, token: str, telegram_id: int, username, first_name, last_name,
                        full_name, phone):
    """-> ('used', None) | ('invalid', текст ошибки) | ('ok', DTO-кортеж).

    DTO: (role, specialization, user_id, created_at_str, [telegram_id админов]).

    Гашение nonce и присоединение по инвайту живут в ОДНОЙ транзакции
    осознанно: ``_use_nonce_atomically`` лишь flush'ит INSERT nonce внутри
    SAVEPOINT, а коммитит его ``commit`` из ``process_invite_join``. Разнеси
    их по двум сессиям — nonce откатится, и одноразовый токен перестанет быть
    одноразовым.
    """
    auth_service = AuthService(db)

    # Атомарно гасим nonce и получаем свежие данные инвайта (single-use):
    # раньше завершение звало no-op sync_legacy_role — роль не добавлялась и
    # nonce не гасился (токен переиспользуем). Валидация тут же ловит
    # истёкший/погашенный токен, если он «протух» за время анкеты.
    invite_service = InviteService(db)
    try:
        invite_data = invite_service.validate_invite(
            token, mark_used_by=telegram_id
        )
    except TokenAlreadyUsedError:
        return ("used", None)
    except ValueError as e:
        return ("invalid", str(e))

    # Свежие роль/специализация из подписанного токена — источник истины.
    role = invite_data["role"]
    specialization = invite_data.get("specialization", "")

    # Присоединяем по инвайту: добавляет роль в user.roles, ставит active_role,
    # специализацию, статус pending (та же логика, что и deep-link /start).
    user = auth_service.process_invite_join_sync(
        telegram_id=telegram_id,
        invite_data=invite_data,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )

    # Перезаписываем ФИО/телефон из данных анкеты (точнее телеграмных).
    name_parts = (full_name or "").split()
    user.first_name = name_parts[0] if name_parts else ""
    user.last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    user.phone = phone
    db.commit()

    # Получаем список админов
    admin_users = auth_service.get_users_by_role_sync("admin")

    return (
        "ok",
        (
            role,
            specialization,
            user.id,
            user.created_at.strftime('%d.%m.%Y %H:%M'),
            [admin.telegram_id for admin in admin_users],
        ),
    )


# ⚠️ Регистрация по тексту «🔑 Войти» мертва (генератора кнопки в репозитории
# нет), но САМА функция живая: её напрямую зовёт login_command (/login).
@router.message(F.text.in_(LOGIN_TEXTS))
async def login_via_button(message: Message, user_status: str = None, language: str = "ru", *, _db=None):
    # language injected by middleware

    verdict, status = await run_db(
        lambda s: _apply_login(
            s,
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name,
        ),
        db=_db,
    )
    if verdict == "already_approved":
        await message.answer(
            get_text("auth.already_authorized", language=language),
            reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], status, language=language)
        )
        return
    if verdict == "ok":
        await message.answer(
            get_text("auth.login_success", language=language),
            reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], status, language=language),
        )
    else:
        await message.answer(
            get_text("auth.login_failed", language=language),
            reply_markup=get_cancel_keyboard(language=language),
        )


@router.message(F.text == "/login")
async def login_command(message: Message, language: str = "ru", *, _db=None):
    # Аналог кнопки — одобряем пользователя как заявителя. language — из
    # aiogram-DI: без протяжки ответ рендерился бы на "ru" (BUG-165).
    await login_via_button(message, language=language, _db=_db)


async def start_invite_registration(message: Message, state: FSMContext, token: str,
                                    language: str = "ru", *, staff_only: bool = False, _db=None):
    """Проверить инвайт-токен и запустить анкету. -> (вердикт, роль|None).

    Вердикты: ok | applicant_token | rate_limited | invalid | already_registered |
    registration_pending | error. Роль возвращается при ``ok`` и ``applicant_token``.

    ``staff_only`` — для ветки «Я сотрудник»: приглашение с ролью «Заявитель»
    (она есть в клавиатуре выдачи инвайтов) роли сотрудника не даёт, анкету по
    нему запускать незачем — иначе человек её пройдёт, сожжёт токен и останется
    жителем, то есть ровно там, откуда и пришёл.

    Общее тело для двух входов: команды ``/join <token>`` и шага ввода токена
    после «Я сотрудник» на экране /start. Живёт ИМЕННО в этом модуле — тесты
    (test_invite_token_logging, test_invite_pending_applicant) патчат
    ``handlers.auth.{InviteService,AuthService,InviteRateLimiter}`` и проверяют
    имя логгера; переезд в сервис-слой сломал бы их без единой правки поведения.
    """
    lang = language
    telegram_id = message.from_user.id

    try:
        # Проверяем rate limiting
        if not await InviteRateLimiter.is_allowed(telegram_id):
            remaining_minutes = await InviteRateLimiter.get_remaining_time(telegram_id) // 60
            await message.answer(
                get_text("invites.rate_limited", language=lang, minutes=remaining_minutes)
            )
            logger.warning(f"Превышен rate limit для инвайта от пользователя {telegram_id}")
            return "rate_limited", None

        verdict, payload = await run_db(
            lambda s: _load_join_gate(s, token, telegram_id), db=_db
        )

        if verdict == "invalid":
            error_msg = payload.lower()
            if "expired" in error_msg:
                await message.answer(get_text("invites.expired_token", language=lang))
            elif "already used" in error_msg:
                await message.answer(get_text("invites.used_token", language=lang))
            else:
                await message.answer(get_text("invites.invalid_token", language=lang))

            return "invalid", None

        if verdict == "already_registered":
            await message.answer(
                get_text("invites.already_registered", language=lang)
            )
            return "already_registered", None

        if verdict == "registration_pending":
            await message.answer(
                get_text("auth.registration_pending", language=lang)
            )
            return "registration_pending", None

        invite_data = payload

        # Получаем информацию о приглашении для отображения
        role = invite_data["role"]

        if staff_only and role == "applicant":
            await message.answer(get_text("start_role.applicant_token", language=lang))
            logger.info(f"Пользователю {telegram_id} пришёл applicant-инвайт на ветке сотрудника")
            return "applicant_token", role

        role_name = get_text(f"roles.{role}", language=lang)
        
        # Формируем сообщение о начале регистрации
        invite_info = get_text("invites.registration_started", language=lang).format(
            role=role_name
        )
        
        # Добавляем информацию о специализации
        if role == "executor" and invite_data.get("specialization"):
            specializations = invite_data["specialization"].split(",")
            spec_names = [get_text(f"specializations.{spec.strip()}", language=lang) for spec in specializations]
            invite_info += "\n\n🛠️ " + get_text("auth.handlers.specialization_label", language=lang) + ": " + ", ".join(spec_names)
        
        # Короткий идентификатор токена для логов/FSM-состояния (не
        # криптография — верификация инвайта идёт по HMAC в invite_service).
        # AUD5-SEC-NEW-2: sha256 вместо md5. Смысл не в стойкости этого
        # усечённого значения, а в том, чтобы md5 не всплывал в SAST-отчётах и
        # не приходилось каждый раз доказывать, что здесь он безобиден.
        # Значение живёт только в FSM-состоянии, никуда не сохраняется —
        # смена алгоритма ничего не ломает.
        import hashlib
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        
        # Сохраняем данные в состоянии
        await state.update_data(
            invite_token=token,
            invite_role=role,
            invite_specialization=invite_data.get("specialization", ""),
            token_hash=token_hash
        )
        
        # Переходим к первому шагу - ввод ФИО
        from ..states.registration import RegistrationStates
        await state.set_state(RegistrationStates.waiting_for_full_name)
        logger.info(f"Установлено состояние waiting_for_full_name для пользователя {telegram_id}")
        
        # Проверяем, что состояние установлено
        current_state = await state.get_state()
        logger.info(f"Текущее состояние пользователя {telegram_id}: {current_state}")
        
        # Отправляем сообщение с запросом ФИО
        await message.answer(
            f"{invite_info}\n\n{get_text('auth.enter_full_name', language=lang)}"
        )
        
        # SEC-08: токен (даже префикс) в логи не пишем — см. test_invite_token_logging.py
        logger.info(f"Пользователь {telegram_id} получил ссылку на веб-регистрацию по инвайт-токену")

        return "ok", role

    except Exception as e:
        logger.error(f"Ошибка обработки инвайта от {telegram_id}: {e}")
        await message.answer(
            get_text("errors.unknown_error", language=lang)
        )
        return "error", None


@router.message(Command("join"))
async def join_with_invite(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """
    Обработчик команды /join <token>
    Открывает веб-приложение для регистрации по приглашению
    """
    # FIX-006: НЕ логировать полный токен. message.text начинается с "/join <token>",
    # маскируем второй аргумент той же схемой что и на выходе хендлера.
    _join_parts = (message.text or "").split(maxsplit=1)
    _token_arg = _join_parts[1] if len(_join_parts) > 1 else ""
    _masked = f"{_token_arg[:8]}…" if _token_arg else "(empty)"
    logger.info(f"Команда /join получена от пользователя {message.from_user.id}: /join {_masked}")
    lang = language

    # Извлекаем токен из команды (None-safe — Command("join") фильтр
    # обычно гарантирует .text, но защищаемся от forwarded/media-only маршрутов)
    text_parts = (message.text or "").split(maxsplit=1)
    if len(text_parts) < 2:
        await message.answer(
            get_text("invites.usage_help", language=lang)
        )
        return

    await start_invite_registration(
        message, state, text_parts[1].strip(), language=lang, _db=_db
    )


# Обработчики пошаговой регистрации

@router.message(RegistrationStates.waiting_for_full_name)
async def handle_full_name_input(message: Message, state: FSMContext, language: str = "ru"):
    """Обработчик ввода ФИО"""
    logger.info(f"Обработчик ФИО вызван для пользователя {message.from_user.id}")
    
    # Проверяем текущее состояние
    current_state = await state.get_state()
    logger.info(f"Текущее состояние пользователя {message.from_user.id}: {current_state}")
    
    lang = language
    
    try:
        full_name = message.text.strip()
        
        # Простая валидация ФИО (должно быть минимум 2 слова)
        if len(full_name.split()) < 2:
            await message.answer(get_text("auth.full_name_invalid", language=lang))
            return
        
        # Сохраняем ФИО
        await state.update_data(full_name=full_name)
        
        # Получаем данные о роли и специализации
        data = await state.get_data()
        role = data.get("invite_role")
        specialization = data.get("invite_specialization", "")
        
        # Формируем сообщение для подтверждения должности
        role_name = get_text(f"roles.{role}", language=lang)
        confirmation_text = f"✅ ФИО: {full_name}\n\n"
        confirmation_text += f"🎯 Роль: {role_name}\n"
        
        if role == "executor" and specialization:
            specializations = specialization.split(",")
            spec_names = [get_text(f"specializations.{spec.strip()}", language=lang) for spec in specializations]
            confirmation_text += f"🛠️ Специализация: {', '.join(spec_names)}\n"
        
        confirmation_text += f"\n{get_text('auth.confirm_position_prompt', language=lang)}"

        # Создаем клавиатуру для подтверждения
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=get_text("auth.confirm_button", language=lang),
                callback_data="confirm_position"
            )],
            [InlineKeyboardButton(
                text=get_text("auth.cancel_button", language=lang),
                callback_data="cancel_registration"
            )]
        ])
        
        await message.answer(confirmation_text, reply_markup=keyboard)
        
        # Переходим к следующему состоянию - запрос телефона
        await state.set_state(RegistrationStates.waiting_for_phone)
        
    except Exception as e:
        logger.error(f"Ошибка обработки ФИО: {e}")
        await message.answer(get_text("auth.error_try_again", language=lang))


@router.message(RegistrationStates.waiting_for_phone)
async def handle_phone_input(message: Message, state: FSMContext, language: str = "ru"):
    """Обработчик ввода номера телефона"""
    logger.info(f"Обработчик телефона вызван для пользователя {message.from_user.id}")
    lang = language
    
    try:
        phone = message.text.strip()
        
        # Простая валидация телефона (должен содержать цифры и быть не короче 10 символов)
        if not phone.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '').isdigit():
            await message.answer(get_text("auth.phone_invalid", language=lang))
            return

        phone_clean = phone.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        if len(phone_clean) < 10:
            await message.answer(get_text("auth.phone_too_short", language=lang))
            return
        
        # Сохраняем телефон
        await state.update_data(phone=phone)
        
        # Получаем все данные
        data = await state.get_data()
        full_name = data.get("full_name")
        role = data.get("invite_role")
        specialization = data.get("invite_specialization", "")
        
        # Формируем сообщение для подтверждения
        role_name = get_text(f"roles.{role}", language=lang)
        confirmation_text = f"✅ ФИО: {full_name}\n"
        confirmation_text += f"📱 Телефон: {phone}\n\n"
        confirmation_text += f"🎯 Роль: {role_name}\n"
        
        if role == "executor" and specialization:
            specializations = specialization.split(",")
            spec_names = [get_text(f"specializations.{spec.strip()}", language=lang) for spec in specializations]
            confirmation_text += f"🛠️ Специализация: {', '.join(spec_names)}\n"
        
        confirmation_text += f"\n{get_text('auth.confirm_data_prompt', language=lang)}"

        # Создаем клавиатуру для подтверждения
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=get_text("auth.confirm_button", language=lang),
                callback_data="confirm_position"
            )],
            [InlineKeyboardButton(
                text=get_text("auth.cancel_button", language=lang),
                callback_data="cancel_registration"
            )]
        ])
        
        await message.answer(confirmation_text, reply_markup=keyboard)
        
        # Переходим к состоянию подтверждения
        await state.set_state(RegistrationStates.waiting_for_position_confirmation)
        
    except Exception as e:
        logger.error(f"Ошибка обработки телефона: {e}")
        await message.answer(get_text("auth.error_try_again", language=lang))


@router.callback_query(F.data == "confirm_position")
async def handle_position_confirmation(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработчик подтверждения должности"""
    lang = language

    try:
        # Получаем все данные
        data = await state.get_data()
        full_name = data.get("full_name")
        phone = data.get("phone")
        role = data.get("invite_role")
        specialization = data.get("invite_specialization", "")

        token = data.get("invite_token")

        verdict, payload = await run_db(
            lambda s: _apply_registration(
                s, token, callback.from_user.id,
                callback.from_user.username,
                callback.from_user.first_name,
                callback.from_user.last_name,
                full_name, phone,
            ),
            db=_db,
        )

        if verdict == "used":
            await callback.answer(get_text("invites.used_token", language=lang), show_alert=True)
            await state.clear()
            return
        if verdict == "invalid":
            msg_key = "invites.expired_token" if "expired" in payload.lower() else "invites.invalid_token"
            await callback.answer(get_text(msg_key, language=lang), show_alert=True)
            await state.clear()
            return

        # Свежие роль/специализация из подписанного токена — источник истины.
        role, specialization, user_id, created_at_display, admin_telegram_ids = payload

        # Отправляем заявку администратору
        from ..keyboards.admin import get_user_approval_keyboard

        # Формируем сообщение для админа
        admin_message = f"{get_text('auth.registration_admin_title', language='ru')}\n\n"
        admin_message += f"{get_text('auth.user_field', language='ru')} {full_name}\n"
        admin_message += f"{get_text('auth.phone_field', language='ru')} {phone}\n"
        admin_message += f"{get_text('auth.telegram_id_field', language='ru')} {callback.from_user.id}\n"
        admin_message += f"{get_text('auth.role_field', language='ru')} {get_text(f'roles.{role}', language='ru')}\n"
        
        if role == "executor" and specialization:
            specializations = specialization.split(",")
            spec_names = [get_text(f"specializations.{spec.strip()}", language='ru') for spec in specializations]
            admin_message += f"{get_text('auth.specialization_field', language='ru')} {', '.join(spec_names)}\n"

        admin_message += f"{get_text('auth.date_field', language='ru')} {created_at_display}\n"

        # Отправляем уведомление всем админам (сеть — вне сессии; список
        # telegram_id собран в юните)
        for admin_telegram_id in admin_telegram_ids:
            try:
                keyboard = get_user_approval_keyboard(user_id)
                await callback.bot.send_message(
                    admin_telegram_id,
                    admin_message,
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление админу {admin_telegram_id}: {e}")
        
        # Отправляем подтверждение пользователю
        await callback.message.edit_text(
            f"{get_text('auth.registration_complete', language=lang)}\n\n"
            f"{get_text('auth.full_name_field', language=lang)} {full_name}\n"
            f"{get_text('auth.phone_field', language=lang)} {phone}\n"
            f"{get_text('auth.role_field', language=lang)} {get_text(f'roles.{role}', language=lang)}\n\n"
            f"{get_text('auth.registration_submitted', language=lang)}"
        )
        
        # Очищаем состояние
        await state.clear()
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения должности: {e}")
        lang = language
        await callback.answer(get_text("auth.error_try_again", language=lang), show_alert=True)


@router.callback_query(F.data == "cancel_registration")
async def handle_registration_cancel(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Обработчик отмены регистрации"""
    lang = language
    try:
        await callback.message.edit_text(get_text("auth.registration_cancelled", language=lang))
        await state.clear()
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка отмены регистрации: {e}")
        await callback.answer(get_text("auth.error_try_again", language=lang), show_alert=True)


