from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from ..states.registration import RegistrationStates

from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.invite_service import InviteService, InviteRateLimiter
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.base import get_main_keyboard, get_cancel_keyboard, get_main_keyboard_for_role
import logging
import json

from uk_management_bot.utils.button_texts import get_login_texts

logger = logging.getLogger(__name__)
router = Router()

LOGIN_TEXTS = get_login_texts()


@router.message(F.text.in_(LOGIN_TEXTS))
async def login_via_button(message: Message, db: Session, user_status: str = None, language: str = "ru"):
    # language injected by middleware

    auth = AuthService(db)
    user = await auth.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )
    if user.status == "approved":
        await message.answer(
            get_text("auth.already_authorized", language=language),
            reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], user.status, language=language)
        )
        return
    ok = await auth.auto_approve_user(message.from_user.id, role="applicant")
    if ok:
        await message.answer(
            get_text("auth.login_success", language=language),
            reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], user.status, language=language),
        )
    else:
        await message.answer(
            get_text("auth.login_failed", language=language),
            reply_markup=get_cancel_keyboard(language=language),
        )


@router.message(F.text == "/login")
async def login_command(message: Message, db: Session):
    # Аналог кнопки — одобряем пользователя как заявителя
    await login_via_button(message, db)


@router.message(Command("join"))
async def join_with_invite(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """
    Обработчик команды /join <token>
    Открывает веб-приложение для регистрации по приглашению
    """
    logger.info(f"Команда /join получена от пользователя {message.from_user.id}: {message.text}")
    lang = language
    telegram_id = message.from_user.id
    
    try:
        # Проверяем rate limiting
        if not await InviteRateLimiter.is_allowed(telegram_id):
            remaining_minutes = await InviteRateLimiter.get_remaining_time(telegram_id) // 60
            await message.answer(
                get_text("invites.rate_limited", language=lang, minutes=remaining_minutes)
            )
            logger.warning(f"Превышен rate limit для /join от пользователя {telegram_id}")
            return
        
        # Извлекаем токен из команды
        text_parts = message.text.split(maxsplit=1)
        if len(text_parts) < 2:
            await message.answer(
                get_text("invites.usage_help", language=lang)
            )
            return
        
        token = text_parts[1].strip()
        
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
            
            logger.info(f"Невалидный токен от {telegram_id}: {e}")
            return
        
        # Проверяем, не зарегистрирован ли уже пользователь
        auth_service = AuthService(db)
        existing_user = await auth_service.get_user_by_telegram_id(telegram_id)
        logger.info(f"Проверка существующего пользователя {telegram_id}: {existing_user.status if existing_user else 'не найден'}")
        
        if existing_user:
            # Если пользователь уже одобрен, запрещаем повторную регистрацию
            if existing_user.status == "approved":
                logger.info(f"Пользователь {telegram_id} уже одобрен, регистрация запрещена")
                await message.answer(
                    get_text("invites.already_registered", language=lang)
                )
                return
            # Если пользователь в статусе pending, запрещаем повторную регистрацию
            elif existing_user.status == "pending":
                logger.info(f"Пользователь {telegram_id} уже зарегистрирован со статусом pending, регистрация запрещена")
                await message.answer(
                    get_text("auth.registration_pending", language=lang)
                )
                return
            # Для других статусов (blocked и т.д.) разрешаем повторную регистрацию
            else:
                logger.info(f"Пользователь {telegram_id} имеет статус {existing_user.status}, разрешаем повторную регистрацию")
        
        # Получаем информацию о приглашении для отображения
        role = invite_data["role"]
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
        
        # Создаем короткий хеш токена для идентификации
        import hashlib
        token_hash = hashlib.md5(token.encode()).hexdigest()[:16]
        
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
        
        logger.info(f"Пользователь {telegram_id} получил ссылку на веб-регистрацию с токеном {token}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки /join от {telegram_id}: {e}")
        await message.answer(
            get_text("errors.unknown_error", language=lang)
        )


# Обработчики пошаговой регистрации

@router.message(RegistrationStates.waiting_for_full_name)
async def handle_full_name_input(message: Message, state: FSMContext, db: Session, language: str = "ru"):
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
async def handle_phone_input(message: Message, state: FSMContext, db: Session, language: str = "ru"):
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
async def handle_position_confirmation(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Обработчик подтверждения должности"""
    lang = language
    
    try:
        # Получаем все данные
        data = await state.get_data()
        full_name = data.get("full_name")
        phone = data.get("phone")
        token = data.get("invite_token")
        role = data.get("invite_role")
        specialization = data.get("invite_specialization", "")
        
        # Создаем пользователя
        auth_service = AuthService(db)
        user = await auth_service.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        
        # Обновляем данные пользователя
        # Разбиваем full_name на first_name и last_name
        name_parts = full_name.split()
        user.first_name = name_parts[0] if name_parts else ""
        user.last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
        user.phone = phone
        user.role = role
        user.status = "pending"
        
        # Если это исполнитель, добавляем специализацию
        if role == "executor" and specialization:
            user.specialization = specialization
        
        # Сохраняем в базу
        db.commit()
        
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

        admin_message += f"{get_text('auth.date_field', language='ru')} {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        # Получаем список админов
        admin_users = await auth_service.get_users_by_role("admin")
        
        # Отправляем уведомление всем админам
        for admin in admin_users:
            try:
                keyboard = get_user_approval_keyboard(user.id)
                await callback.bot.send_message(
                    admin.telegram_id,
                    admin_message,
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление админу {admin.telegram_id}: {e}")
        
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


