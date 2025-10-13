"""
Обработчики онбординга новых пользователей
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, Document, PhotoSize
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.profile_service import ProfileService
from uk_management_bot.services.user_verification_service import UserVerificationService
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.validators import Validator
from uk_management_bot.keyboards.base import get_main_keyboard_for_role, get_main_keyboard
from uk_management_bot.keyboards.onboarding import (
    get_document_type_keyboard, 
    get_document_confirmation_keyboard,
    get_onboarding_completion_keyboard,
    get_document_type_from_text,
    get_document_type_name
)
from uk_management_bot.states.onboarding import OnboardingStates
from uk_management_bot.database.models.user_verification import DocumentType

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.text == "/start")
async def start_onboarding(message: Message, state: FSMContext, db: Session):
    """Начинает процесс онбординга для нового пользователя"""
    lang = message.from_user.language_code or "ru"
    
    try:
        # Проверяем, существует ли пользователь
        auth_service = AuthService(db)
        user = await auth_service.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        
        # Если пользователь уже одобрен, показываем главное меню
        if user.status == "approved":
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            await message.answer(
                get_text("welcome", language=lang),
                reply_markup=get_main_keyboard_for_role(user.active_role or user.role, user.roles or [user.role], user.status)
            )
            return
        
        # Если профиль не заполнен, начинаем онбординг
        # ОБНОВЛЕНО: Проверяем наличие телефона и одобренных квартир (вместо устаревшего home_address)
        has_approved_apartment = any(ua.status == 'approved' for ua in user.user_apartments) if user.user_apartments else False
        if not user.phone or not has_approved_apartment:
            await message.answer(
                get_text("onboarding.welcome_new_user", language=lang) + "\n\n" + 
                get_text("onboarding.profile_incomplete", language=lang)
            )
            
            # Создаем клавиатуру для начала онбординга
            from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
            onboarding_keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="📱 Указать телефон")]
                ],
                resize_keyboard=True
            )
            
            await message.answer(
                get_text("onboarding.phone_request", language=lang),
                reply_markup=onboarding_keyboard
            )
            await state.set_state(OnboardingStates.waiting_for_phone)
            logger.info(f"Начат онбординг для пользователя {message.from_user.id}")
        else:
            # Профиль заполнен, но статус pending - показываем ожидание
            await message.answer(
                get_text("auth.pending", language=lang)
            )
            
    except Exception as e:
        logger.error(f"Ошибка начала онбординга для {message.from_user.id}: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))

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
            
            # Переходим к выбору квартиры из справочника
            from uk_management_bot.handlers.user_apartment_selection import start_apartment_selection
            await start_apartment_selection(message, state)
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
    
    # Проверяем системные команды/кнопки - не обрабатываем их как телефон
    system_commands = [
        "👤 Профиль", "📝 Создать заявку", "📋 Мои заявки", "❓ Помощь",
        "🔄 Смена", "🔀 Выбрать роль", "/start", "/help",
        "🏠 Указать адрес", "📱 Указать телефон"
    ]
    
    if message.text in system_commands:
        # Очищаем состояние и пропускаем обработку
        await state.clear()
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
            
            # Переходим к выбору квартиры из справочника
            from uk_management_bot.handlers.user_apartment_selection import start_apartment_selection
            await start_apartment_selection(message, state)
        else:
            await message.answer(get_text("errors.unknown_error", language=lang))
            await state.clear()
            
    except Exception as e:
        logger.error(f"Ошибка сохранения телефона для {message.from_user.id}: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()

@router.message(OnboardingStates.waiting_for_home_address, F.text)
async def process_home_address(message: Message, state: FSMContext, db: Session, user_status: str = None):
    """
    УСТАРЕВШИЙ ОБРАБОТЧИК: Теперь адреса управляются через систему квартир.

    Этот обработчик больше не должен вызываться, так как выбор адреса происходит
    через user_apartment_selection. Если пользователь попал сюда, перенаправляем
    его на выбор квартиры из справочника.
    """
    lang = message.from_user.language_code or "ru"

    await state.clear()
    await message.answer(
        "⚠️ <b>Система адресов обновлена!</b>\n\n"
        "Теперь адрес выбирается из справочника квартир.\n"
        "Пожалуйста, используйте кнопку '🏘️ Мои квартиры' в профиле для добавления адреса.",
        reply_markup=get_main_keyboard()
    )

    logger.warning(f"Пользователь {message.from_user.id} попал в устаревший обработчик адреса")

async def complete_onboarding(message: Message, state: FSMContext, db: Session, user, user_status: str = None):
    """Завершает процесс онбординга"""
    lang = message.from_user.language_code or "ru"
    
    # Показываем сводку онбординга
    profile_service = ProfileService(db)
    profile_data = profile_service.get_user_profile_data(message.from_user.id)
    
    completion_text = get_text("onboarding.completed", language=lang)
    
    if profile_data:
        phone = profile_data.get('phone', get_text("profile.phone_not_set", language=lang))

        # ОБНОВЛЕНО: Используем новую систему квартир вместо home_address
        apartments = profile_data.get('apartments', [])
        if apartments:
            primary_apt = next((a for a in apartments if a.get('is_primary')), apartments[0] if apartments else None)
            home_addr = primary_apt['address'] if primary_apt else get_text("profile.address_not_set", language=lang)
        else:
            home_addr = get_text("profile.address_not_set", language=lang)

        completion_text += f"\n\n📱 {get_text('profile.phone', language=lang)} {phone}"
        completion_text += f"\n🏠 {get_text('profile.home_address', language=lang)} {home_addr}"
    
    # Предлагаем загрузить документы
    completion_text += f"\n\n📄 {get_text('onboarding.documents.title', language=lang)}"
    completion_text += f"\n{get_text('onboarding.documents.description', language=lang)}"
    
    # Создаем клавиатуру с опцией загрузки документов
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    completion_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📄 Загрузить документы")],
            [KeyboardButton(text="✅ Завершить без документов")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        completion_text,
        reply_markup=completion_keyboard
    )
    
    await state.clear()
    logger.info(f"Онбординг завершен для пользователя {message.from_user.id}")

@router.message(F.text == "✅ Завершить без документов")
async def complete_onboarding_without_documents(message: Message, state: FSMContext, db: Session):
    """Завершает онбординг без документов"""
    lang = message.from_user.language_code or "ru"
    
    try:
        # Получаем пользователя
        auth_service = AuthService(db)
        user = await auth_service.get_user_by_telegram_id(message.from_user.id)
        
        if not user:
            await message.answer(get_text("errors.unknown_error", language=lang))
            return
        
        completion_text = get_text("onboarding.completed", language=lang)
        completion_text += f"\n\n{get_text('onboarding.pending_approval', language=lang)}"
        
        await message.answer(
            completion_text,
            reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], user.status)
        )
        
        logger.info(f"Онбординг без документов завершен для пользователя {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка завершения онбординга без документов для {message.from_user.id}: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))

async def cancel_onboarding(message: Message, state: FSMContext, db: Session, user_status: str = None):
    """Отменяет процесс онбординга"""
    lang = message.from_user.language_code or "ru"
    
    await message.answer(
        get_text("onboarding.cancelled", language=lang),
        reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], "approved")
    )
    
    await state.clear()
    logger.info(f"Онбординг отменен для пользователя {message.from_user.id}")

@router.message(F.text == "🏠 Указать адрес")
async def start_address_input(message: Message, state: FSMContext, db: Session):
    """
    УСТАРЕВШИЙ ОБРАБОТЧИК: Теперь адреса управляются через систему квартир.
    """
    lang = message.from_user.language_code or "ru"

    await state.clear()
    await message.answer(
        "⚠️ <b>Система адресов обновлена!</b>\n\n"
        "Теперь адрес выбирается из справочника квартир.\n"
        "Пожалуйста, используйте кнопку '🏘️ Мои квартиры' в профиле для добавления адреса.",
        reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], "approved")
    )

    logger.warning(f"Пользователь {message.from_user.id} попал в устаревший обработчик ввода адреса")

# ═══ ОБРАБОТЧИКИ ЗАГРУЗКИ ДОКУМЕНТОВ ═══

@router.message(F.text == "📄 Загрузить документы")
async def start_document_upload(message: Message, state: FSMContext, db: Session):
    """Начинает процесс загрузки документов"""
    lang = message.from_user.language_code or "ru"
    
    await message.answer(
        get_text("onboarding.documents.title", language=lang) + "\n\n" +
        get_text("onboarding.documents.description", language=lang),
        reply_markup=get_document_type_keyboard(lang)
    )
    await state.set_state(OnboardingStates.waiting_for_document_type)
    logger.info(f"Пользователь {message.from_user.id} начал загрузку документов")

@router.message(OnboardingStates.waiting_for_document_type, F.text)
async def process_document_type_selection(message: Message, state: FSMContext, db: Session):
    """Обрабатывает выбор типа документа"""
    lang = message.from_user.language_code or "ru"
    
    # Проверяем специальные команды
    if message.text == "⏭️ Пропустить документы":
        await skip_documents(message, state, db)
        return
    elif message.text == "✅ Завершить онбординг":
        await complete_onboarding_with_documents(message, state, db)
        return
    
    # Определяем тип документа
    document_type = get_document_type_from_text(message.text)
    
    # Сохраняем выбранный тип в состоянии
    await state.update_data(selected_document_type=document_type.value)
    
    # Запрашиваем файл
    document_type_name = get_document_type_name(document_type, lang)
    await message.answer(
        f"📤 {get_text('onboarding.documents.upload_file', language=lang)}\n\n"
        f"Тип документа: {document_type_name}",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(OnboardingStates.waiting_for_document_file)
    logger.info(f"Пользователь {message.from_user.id} выбрал тип документа: {document_type.value}")

@router.message(OnboardingStates.waiting_for_document_file)
async def process_document_file(message: Message, state: FSMContext, db: Session):
    """Обрабатывает загрузку файла документа"""
    lang = message.from_user.language_code or "ru"
    
    # Получаем данные из состояния
    data = await state.get_data()
    document_type_value = data.get('selected_document_type')
    
    if not document_type_value:
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()
        return
    
    document_type = DocumentType(document_type_value)
    
    # Получаем информацию о файле
    file_id = None
    file_name = None
    file_size = None
    
    if message.document:
        # Документ
        file_id = message.document.file_id
        file_name = message.document.file_name
        file_size = message.document.file_size
    elif message.photo:
        # Фото
        photo = message.photo[-1]  # Берем самое большое фото
        file_id = photo.file_id
        file_name = f"photo_{photo.file_id}.jpg"
        file_size = photo.file_size
    else:
        await message.answer(get_text("onboarding.documents.file_invalid", language=lang))
        return
    
    # Валидируем файл
    verification_service = UserVerificationService(db)
    is_valid, error_message = verification_service.validate_document_file(file_id, file_name, file_size)
    
    if not is_valid:
        await message.answer(error_message)
        return
    
    # Сохраняем информацию о файле в состоянии
    await state.update_data({
        'file_id': file_id,
        'file_name': file_name,
        'file_size': file_size
    })
    
    # Показываем подтверждение
    document_type_name = get_document_type_name(document_type, lang)
    confirmation_text = (
        f"📄 {get_text('onboarding.documents.confirm_upload', language=lang)}\n\n"
        f"Тип документа: {document_type_name}\n"
        f"Файл: {file_name}\n"
        f"Размер: {file_size // 1024} KB"
    )
    
    await message.answer(
        confirmation_text,
        reply_markup=get_document_confirmation_keyboard(lang)
    )
    await state.set_state(OnboardingStates.waiting_for_document_confirmation)

@router.message(OnboardingStates.waiting_for_document_confirmation, F.text)
async def process_document_confirmation(message: Message, state: FSMContext, db: Session):
    """Обрабатывает подтверждение загрузки документа"""
    lang = message.from_user.language_code or "ru"
    
    if message.text == "✅ Подтвердить загрузку":
        await save_document(message, state, db)
    elif message.text == "❌ Отменить":
        await cancel_document_upload(message, state, db)
    elif message.text == "🔄 Загрузить другой документ":
        await start_document_upload(message, state, db)
    else:
        await message.answer(get_text("errors.unknown_error", language=lang))

async def save_document(message: Message, state: FSMContext, db: Session):
    """Сохраняет документ в базе данных"""
    lang = message.from_user.language_code or "ru"
    
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        document_type_value = data.get('selected_document_type')
        file_id = data.get('file_id')
        file_name = data.get('file_name')
        file_size = data.get('file_size')
        
        if not all([document_type_value, file_id]):
            await message.answer(get_text("errors.unknown_error", language=lang))
            await state.clear()
            return
        
        # Получаем пользователя
        auth_service = AuthService(db)
        user = await auth_service.get_user_by_telegram_id(message.from_user.id)
        
        if not user:
            await message.answer(get_text("errors.unknown_error", language=lang))
            await state.clear()
            return
        
        # Загружаем документ в Media Service (в канал ARCHIVE)
        from uk_management_bot.utils.media_helpers import upload_document_to_media_service
        try:
            await upload_document_to_media_service(
                bot=message.bot,
                file_id=file_id,
                user_telegram_id=message.from_user.id,
                description=f"Документ пользователя: {document_type_value}"
            )
            logger.info(f"Документ пользователя {message.from_user.id} загружен в Media Service")
        except Exception as e:
            logger.error(f"Ошибка загрузки документа в Media Service: {e}")
            # Продолжаем сохранение даже если загрузка не удалась

        # Сохраняем документ в базу данных
        verification_service = UserVerificationService(db)
        document_type = DocumentType(document_type_value)
        document = verification_service.save_user_document(
            user_id=user.id,
            document_type=document_type,
            file_id=file_id,
            file_name=file_name,
            file_size=file_size
        )

        # Показываем успешное сообщение
        document_type_name = get_document_type_name(document_type, lang)
        await message.answer(
            f"✅ {get_text('onboarding.documents.document_saved', language=lang)}\n\n"
            f"Тип: {document_type_name}\n"
            f"Файл: {file_name}",
            reply_markup=get_onboarding_completion_keyboard(lang)
        )
        
        # Очищаем состояние
        await state.clear()
        logger.info(f"Документ сохранен для пользователя {message.from_user.id}: {document_type.value}")
        
    except Exception as e:
        logger.error(f"Ошибка сохранения документа для {message.from_user.id}: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()

async def cancel_document_upload(message: Message, state: FSMContext, db: Session):
    """Отменяет загрузку документа"""
    lang = message.from_user.language_code or "ru"
    
    await message.answer(
        get_text("onboarding.documents.upload_cancelled", language=lang),
        reply_markup=get_onboarding_completion_keyboard(lang)
    )
    await state.clear()

async def skip_documents(message: Message, state: FSMContext, db: Session):
    """Пропускает загрузку документов"""
    lang = message.from_user.language_code or "ru"
    
    await message.answer(
        f"⏭️ {get_text('onboarding.documents.skip_documents', language=lang)}\n\n"
        f"Вы можете загрузить документы позже в настройках профиля.",
        reply_markup=get_onboarding_completion_keyboard(lang)
    )
    await state.clear()

async def complete_onboarding_with_documents(message: Message, state: FSMContext, db: Session):
    """Завершает онбординг с документами"""
    lang = message.from_user.language_code or "ru"
    
    try:
        # Получаем пользователя
        auth_service = AuthService(db)
        user = await auth_service.get_user_by_telegram_id(message.from_user.id)
        
        if not user:
            await message.answer(get_text("errors.unknown_error", language=lang))
            await state.clear()
            return
        
        # Получаем сводку документов
        verification_service = UserVerificationService(db)
        documents_summary = verification_service.get_user_documents_summary(user.id)
        
        # Формируем сообщение о завершении
        completion_text = get_text("onboarding.completed", language=lang)
        
        if documents_summary['total_documents'] > 0:
            completion_text += f"\n\n{get_text('onboarding.documents.documents_summary', language=lang)}"
            completion_text += f"\n📄 Всего документов: {documents_summary['total_documents']}"
            
            for doc_type, count in documents_summary['documents_by_type'].items():
                doc_type_name = get_document_type_name(DocumentType(doc_type), lang)
                completion_text += f"\n- {doc_type_name}: {count}"
        else:
            completion_text += f"\n\n{get_text('onboarding.documents.no_documents', language=lang)}"
        
        completion_text += f"\n\n{get_text('onboarding.pending_approval', language=lang)}"
        
        await message.answer(
            completion_text,
            reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], user.status)
        )
        
        await state.clear()
        logger.info(f"Онбординг с документами завершен для пользователя {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка завершения онбординга с документами для {message.from_user.id}: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()

# ═══ ОБРАБОТЧИКИ КНОПОК ЗАВЕРШЕНИЯ ОНБОРДИНГА ═══

@router.message(F.text == "📄 Добавить еще документы")
async def add_more_documents(message: Message, state: FSMContext, db: Session):
    """Обрабатывает нажатие кнопки 'Добавить еще документы'"""
    lang = message.from_user.language_code or "ru"
    
    await message.answer(
        get_text("onboarding.documents.title", language=lang) + "\n\n" +
        get_text("onboarding.documents.description", language=lang),
        reply_markup=get_document_type_keyboard(lang)
    )
    await state.set_state(OnboardingStates.waiting_for_document_type)
    logger.info(f"Пользователь {message.from_user.id} решил добавить еще документы")

@router.message(F.text == "✅ Завершить онбординг")
async def complete_onboarding_final(message: Message, state: FSMContext, db: Session):
    """Обрабатывает нажатие кнопки 'Завершить онбординг'"""
    await complete_onboarding_with_documents(message, state, db)
