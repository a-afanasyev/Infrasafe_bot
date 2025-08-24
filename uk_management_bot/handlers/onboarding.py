"""
Обработчики онбординга новых пользователей
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import Session
from services.auth_service import AuthService
from services.profile_service import ProfileService
from utils.helpers import get_text
from utils.validators import Validator
from keyboards.base import get_main_keyboard_for_role

logger = logging.getLogger(__name__)
router = Router()

class OnboardingStates(StatesGroup):
    """Состояния онбординга нового пользователя"""
    waiting_for_phone = State()
    waiting_for_home_address = State()

@router.message(F.text == "📱 Указать телефон")
async def start_phone_input(message: Message, state: FSMContext, db: Session):
    """Начинает процесс ввода телефона"""
    lang = message.from_user.language_code or "ru"
    
    # Создаем клавиатуру для запроса контакта
    contact_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text("onboarding.share_contact", language=lang), request_contact=True)],
            [KeyboardButton(text=get_text("buttons.cancel", language=lang))]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await message.answer(
        get_text("onboarding.phone_request", language=lang),
        reply_markup=contact_keyboard
    )
    await state.set_state(OnboardingStates.waiting_for_phone)
    logger.info(f"Пользователь {message.from_user.id} начал ввод телефона")

@router.message(OnboardingStates.waiting_for_phone, F.contact)
async def process_contact(message: Message, state: FSMContext, db: Session):
    """Обрабатывает получение контакта"""
    lang = message.from_user.language_code or "ru"
    
    try:
        # Получаем номер телефона
        phone_number = message.contact.phone_number
        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number
        
        # Сохраняем телефон в базе данных
        auth_service = AuthService(db)
        user = await auth_service.get_user_by_telegram_id(message.from_user.id)
        
        if user:
            user.phone = phone_number
            db.commit()
            logger.info(f"Сохранен телефон {phone_number} для пользователя {message.from_user.id}")
            
            await message.answer(
                get_text("onboarding.phone_saved", language=lang, phone=phone_number),
                reply_markup=ReplyKeyboardRemove()
            )
            
            # Переходим к вводу адреса
            await message.answer(get_text("onboarding.address_request", language=lang))
            await state.set_state(OnboardingStates.waiting_for_home_address)
        else:
            await message.answer(
                get_text("errors.unknown_error", language=lang),
                reply_markup=ReplyKeyboardRemove()
            )
            await state.clear()
            
    except Exception as e:
        logger.error(f"Ошибка обработки контакта для {message.from_user.id}: {e}")
        await message.answer(
            get_text("errors.unknown_error", language=lang),
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()

@router.message(OnboardingStates.waiting_for_phone, F.text)
async def process_manual_phone(message: Message, state: FSMContext, db: Session, user_status: str = None):
    """Обрабатывает ручной ввод телефона"""
    lang = message.from_user.language_code or "ru"
    
    # Проверяем на отмену
    if message.text == get_text("buttons.cancel", language=lang):
        await cancel_onboarding(message, state, db, user_status)
        return
    
    # Валидируем телефон
    phone_number = message.text.strip()
    is_valid, error_message = Validator.validate_phone(phone_number)
    if not is_valid:
        await message.answer(get_text("onboarding.phone_invalid", language=lang))
        return
    
    # Нормализуем номер
    if not phone_number.startswith('+'):
        phone_number = '+' + phone_number.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    
    try:
        # Сохраняем телефон
        auth_service = AuthService(db)
        user = await auth_service.get_user_by_telegram_id(message.from_user.id)
        
        if user:
            user.phone = phone_number
            db.commit()
            logger.info(f"Сохранен телефон {phone_number} для пользователя {message.from_user.id}")
            
            await message.answer(
                get_text("onboarding.phone_saved", language=lang, phone=phone_number),
                reply_markup=ReplyKeyboardRemove()
            )
            
            # Переходим к вводу адреса
            await message.answer(get_text("onboarding.address_request", language=lang))
            await state.set_state(OnboardingStates.waiting_for_home_address)
        else:
            await message.answer(get_text("errors.unknown_error", language=lang))
            await state.clear()
            
    except Exception as e:
        logger.error(f"Ошибка сохранения телефона для {message.from_user.id}: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()

@router.message(OnboardingStates.waiting_for_home_address, F.text)
async def process_home_address(message: Message, state: FSMContext, db: Session, user_status: str = None):
    """Обрабатывает ввод домашнего адреса"""
    lang = message.from_user.language_code or "ru"
    
    # Проверяем на отмену
    if message.text == get_text("buttons.cancel", language=lang):
        await cancel_onboarding(message, state, db, user_status)
        return
    
    address = message.text.strip()
    
    # Валидируем адрес
    is_valid, error_message = Validator.validate_address(address)
    if not is_valid:
        await message.answer(get_text("onboarding.address_invalid", language=lang))
        return
    
    try:
        # Сохраняем адрес
        auth_service = AuthService(db)
        user = await auth_service.get_user_by_telegram_id(message.from_user.id)
        
        if user:
            user.home_address = address
            # Устанавливаем статус pending если это первый адрес
            if user.status == "pending" and not user.phone:
                # Если еще нет телефона, оставляем pending
                pass
            elif user.phone and not user.home_address:
                # Если есть телефон и это первый адрес - полный онбординг завершен
                user.status = "pending"
            
            db.commit()
            logger.info(f"Сохранен адрес для пользователя {message.from_user.id}: {address}")
            
            # Завершаем онбординг
            await complete_onboarding(message, state, db, user, user_status)
            
    except Exception as e:
        logger.error(f"Ошибка сохранения адреса для {message.from_user.id}: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()

async def complete_onboarding(message: Message, state: FSMContext, db: Session, user, user_status: str = None):
    """Завершает процесс онбординга"""
    lang = message.from_user.language_code or "ru"
    
    # Показываем сводку онбординга
    profile_service = ProfileService(db)
    profile_data = profile_service.get_user_profile_data(message.from_user.id)
    
    completion_text = get_text("onboarding.completed", language=lang)
    
    if profile_data:
        phone = profile_data.get('phone', get_text("profile.phone_not_set", language=lang))
        home_addr = profile_data.get('home_address', get_text("profile.address_not_set", language=lang))
        
        completion_text += f"\n\n📱 {get_text('profile.phone', language=lang)} {phone}"
        completion_text += f"\n🏠 {get_text('profile.home_address', language=lang)} {home_addr}"
    
    completion_text += f"\n\n{get_text('onboarding.pending_approval', language=lang)}"
    
    await message.answer(
        completion_text,
        reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], user_status)
    )
    
    await state.clear()
    logger.info(f"Онбординг завершен для пользователя {message.from_user.id}")

async def cancel_onboarding(message: Message, state: FSMContext, db: Session, user_status: str = None):
    """Отменяет процесс онбординга"""
    lang = message.from_user.language_code or "ru"
    
    await message.answer(
        get_text("onboarding.cancelled", language=lang),
        reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], user_status)
    )
    
    await state.clear()
    logger.info(f"Онбординг отменен для пользователя {message.from_user.id}")

@router.message(F.text == "🏠 Указать адрес")
async def start_address_input(message: Message, state: FSMContext, db: Session):
    """Начинает процесс ввода домашнего адреса"""
    lang = message.from_user.language_code or "ru"
    
    await message.answer(get_text("onboarding.address_request", language=lang))
    await state.set_state(OnboardingStates.waiting_for_home_address)
    logger.info(f"Пользователь {message.from_user.id} начал ввод адреса")
