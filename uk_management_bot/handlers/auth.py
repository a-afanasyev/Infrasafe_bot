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

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "🔑 Войти")
async def login_via_button(message: Message, db: Session, user_status: str = None):
    auth = AuthService(db)
    user = await auth.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )
    if user.status == "approved":
        await message.answer("Вы уже авторизованы.", reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], user.status))
        return
    ok = await auth.approve_user(message.from_user.id, role="applicant")
    if ok:
        await message.answer(
            "✅ Авторизация выполнена. Вы вошли как заявитель.",
            reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], user.status),
        )
    else:
        await message.answer(
            "Не удалось выполнить авторизацию. Попробуйте позже или обратитесь к менеджеру.",
            reply_markup=get_cancel_keyboard(),
        )


@router.message(F.text == "/login")
async def login_command(message: Message, db: Session):
    # Аналог кнопки — одобряем пользователя как заявителя
    await login_via_button(message, db)


@router.message(Command("join"))
async def join_with_invite(message: Message, state: FSMContext, db: Session):
    """
    Обработчик команды /join <token>
    Открывает веб-приложение для регистрации по приглашению
    """
    logger.info(f"Команда /join получена от пользователя {message.from_user.id}: {message.text}")
    lang = message.from_user.language_code or "ru"
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
                get_text("invites.usage_help", language=lang),
                parse_mode="Markdown"
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
                    "📋 Ваша регистрация уже на рассмотрении. Пожалуйста, дождитесь решения администратора."
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
            invite_info += f"\n\n🛠️ Специализация: {', '.join(spec_names)}"
        
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
            f"{invite_info}\n\n📝 Пожалуйста, введите ваше полное имя (ФИО):"
        )
        
        logger.info(f"Пользователь {telegram_id} получил ссылку на веб-регистрацию с токеном {token}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки /join от {telegram_id}: {e}")
        await message.answer(
            get_text("errors.unknown_error", language=lang)
        )


# Обработчики пошаговой регистрации

@router.message(RegistrationStates.waiting_for_full_name)
async def handle_full_name_input(message: Message, state: FSMContext, db: Session):
    """Обработчик ввода ФИО"""
    logger.info(f"Обработчик ФИО вызван для пользователя {message.from_user.id}")
    
    # Проверяем текущее состояние
    current_state = await state.get_state()
    logger.info(f"Текущее состояние пользователя {message.from_user.id}: {current_state}")
    
    lang = message.from_user.language_code or "ru"
    
    try:
        full_name = message.text.strip()
        
        # Простая валидация ФИО (должно быть минимум 2 слова)
        if len(full_name.split()) < 2:
            await message.answer("❌ Пожалуйста, введите полное имя (Фамилия Имя Отчество):")
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
        
        confirmation_text += "\n📝 Подтвердите, что вы согласны с указанной ролью и специализацией:"
        
        # Создаем клавиатуру для подтверждения
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data="confirm_position"
            )],
            [InlineKeyboardButton(
                text="❌ Отменить",
                callback_data="cancel_registration"
            )]
        ])
        
        await message.answer(confirmation_text, reply_markup=keyboard)
        
        # Переходим к следующему состоянию - запрос телефона
        await state.set_state(RegistrationStates.waiting_for_phone)
        
    except Exception as e:
        logger.error(f"Ошибка обработки ФИО: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте еще раз.")


@router.message(RegistrationStates.waiting_for_phone)
async def handle_phone_input(message: Message, state: FSMContext, db: Session):
    """Обработчик ввода номера телефона"""
    logger.info(f"Обработчик телефона вызван для пользователя {message.from_user.id}")
    lang = message.from_user.language_code or "ru"
    
    try:
        phone = message.text.strip()
        
        # Простая валидация телефона (должен содержать цифры и быть не короче 10 символов)
        if not phone.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '').isdigit():
            await message.answer("❌ Пожалуйста, введите корректный номер телефона (например: +7 999 123-45-67):")
            return
        
        phone_clean = phone.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        if len(phone_clean) < 10:
            await message.answer("❌ Номер телефона слишком короткий. Пожалуйста, введите полный номер:")
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
        
        confirmation_text += "\n📝 Подтвердите, что все данные указаны верно:"
        
        # Создаем клавиатуру для подтверждения
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data="confirm_position"
            )],
            [InlineKeyboardButton(
                text="❌ Отменить",
                callback_data="cancel_registration"
            )]
        ])
        
        await message.answer(confirmation_text, reply_markup=keyboard)
        
        # Переходим к состоянию подтверждения
        await state.set_state(RegistrationStates.waiting_for_position_confirmation)
        
    except Exception as e:
        logger.error(f"Ошибка обработки телефона: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте еще раз.")


@router.callback_query(F.data == "confirm_position")
async def handle_position_confirmation(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработчик подтверждения должности"""
    lang = callback.from_user.language_code or "ru"
    
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
        admin_message = f"📝 Новая заявка на регистрацию:\n\n"
        admin_message += f"👤 Пользователь: {full_name}\n"
        admin_message += f"📱 Телефон: {phone}\n"
        admin_message += f"🆔 Telegram ID: {callback.from_user.id}\n"
        admin_message += f"🎯 Роль: {get_text(f'roles.{role}', language='ru')}\n"
        
        if role == "executor" and specialization:
            specializations = specialization.split(",")
            spec_names = [get_text(f"specializations.{spec.strip()}", language='ru') for spec in specializations]
            admin_message += f"🛠️ Специализация: {', '.join(spec_names)}\n"
        
        admin_message += f"📅 Дата: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        
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
            f"✅ Регистрация завершена!\n\n"
            f"👤 ФИО: {full_name}\n"
            f"📱 Телефон: {phone}\n"
            f"🎯 Роль: {get_text(f'roles.{role}', language=lang)}\n\n"
            f"📋 Ваша заявка отправлена администратору на рассмотрение.\n"
            f"Вы получите уведомление, когда заявка будет рассмотрена."
        )
        
        # Очищаем состояние
        await state.clear()
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения должности: {e}")
        await callback.answer("❌ Произошла ошибка. Попробуйте еще раз.", show_alert=True)


@router.callback_query(F.data == "cancel_registration")
async def handle_registration_cancel(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены регистрации"""
    try:
        await callback.message.edit_text("❌ Регистрация отменена.")
        await state.clear()
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка отмены регистрации: {e}")
        await callback.answer("❌ Произошла ошибка.", show_alert=True)


