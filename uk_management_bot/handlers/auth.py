from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy.orm import Session

from services.auth_service import AuthService
from services.invite_service import InviteService, InviteRateLimiter
from utils.helpers import get_text
from keyboards.base import get_main_keyboard, get_cancel_keyboard, get_main_keyboard_for_role
import logging
import json

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "🔑 Войти")
async def login_via_button(message: Message, db: Session):
    auth = AuthService(db)
    user = await auth.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )
    if user.status == "approved":
        await message.answer("Вы уже авторизованы.", reply_markup=get_main_keyboard())
        return
    ok = await auth.approve_user(message.from_user.id, role="applicant")
    if ok:
        await message.answer(
            "✅ Авторизация выполнена. Вы вошли как заявитель.",
            reply_markup=get_main_keyboard(),
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
async def join_with_invite(message: Message, db: Session):
    """
    Обработчик команды /join <token>
    Позволяет пользователям присоединяться по токену приглашения
    """
    lang = message.from_user.language_code or "ru"
    telegram_id = message.from_user.id
    
    try:
        # Проверяем rate limiting
        if not InviteRateLimiter.is_allowed(telegram_id):
            remaining_minutes = InviteRateLimiter.get_remaining_time(telegram_id) // 60
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
        
        # Обрабатываем присоединение
        auth_service = AuthService(db)
        
        user = await auth_service.process_invite_join(
            telegram_id=telegram_id,
            invite_data=invite_data,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        
        # Отмечаем nonce как использованный
        invite_service.mark_nonce_used(
            invite_data["nonce"], 
            telegram_id, 
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
        
        # Получаем роли для клавиатуры
        roles = []
        if user.roles:
            try:
                roles = json.loads(user.roles)
            except json.JSONDecodeError:
                roles = [role]  # fallback
        else:
            roles = [role]
        
        active_role = user.active_role or role
        
        await message.answer(
            success_message,
            reply_markup=get_main_keyboard_for_role(active_role, roles)
        )
        
        logger.info(f"Пользователь {telegram_id} успешно присоединился по инвайту с ролью {role}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки /join от {telegram_id}: {e}")
        await message.answer(
            get_text("errors.unknown_error", language=lang)
        )


