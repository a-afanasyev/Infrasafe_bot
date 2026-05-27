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
from uk_management_bot.utils.language_helpers import get_language_for_user
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
from uk_management_bot.utils.button_texts import (
    get_specify_phone_texts,
    get_complete_without_docs_texts,
    get_specify_address_texts,
    get_upload_documents_texts,
    get_add_more_documents_texts,
    get_complete_onboarding_texts,
    get_skip_documents_texts,
    get_confirm_upload_texts,
    get_onboarding_cancel_texts,
    get_upload_another_document_texts,
    get_profile_texts,
    get_create_request_texts,
    get_my_requests_texts,
    get_help_texts,
    get_shift_texts,
    get_switch_role_texts,
    get_cancel_texts,
    get_my_shifts_texts,
    get_active_requests_texts,
    get_archive_texts,
    get_acceptance_texts,
    get_admin_panel_texts,
)

logger = logging.getLogger(__name__)
router = Router()

# Button text constants for filters
SPECIFY_PHONE_TEXTS = get_specify_phone_texts()
COMPLETE_WITHOUT_DOCS_TEXTS = get_complete_without_docs_texts()
SPECIFY_ADDRESS_TEXTS = get_specify_address_texts()
UPLOAD_DOCUMENTS_TEXTS = get_upload_documents_texts()
ADD_MORE_DOCUMENTS_TEXTS = get_add_more_documents_texts()
COMPLETE_ONBOARDING_TEXTS = get_complete_onboarding_texts()
SKIP_DOCUMENTS_TEXTS = get_skip_documents_texts()
CONFIRM_UPLOAD_TEXTS = get_confirm_upload_texts()
ONBOARDING_CANCEL_TEXTS = get_onboarding_cancel_texts()
UPLOAD_ANOTHER_DOCUMENT_TEXTS = get_upload_another_document_texts()
PROFILE_TEXTS = get_profile_texts()
CREATE_REQUEST_TEXTS = get_create_request_texts()
MY_REQUESTS_TEXTS = get_my_requests_texts()
HELP_TEXTS = get_help_texts()
SHIFT_TEXTS = get_shift_texts()
SWITCH_ROLE_TEXTS = get_switch_role_texts()
CANCEL_TEXTS = get_cancel_texts()
MY_SHIFTS_TEXTS = get_my_shifts_texts()
ACTIVE_REQUESTS_TEXTS = get_active_requests_texts()
ARCHIVE_TEXTS = get_archive_texts()
ACCEPTANCE_TEXTS = get_acceptance_texts()
ADMIN_PANEL_TEXTS = get_admin_panel_texts()

@router.message(F.text == "/start")
async def start_onboarding(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Начинает процесс онбординга для нового пользователя"""
    lang = language
    
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
                reply_markup=get_main_keyboard_for_role(user.active_role or user.role, user.roles or [user.role], user.status, language=lang)
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
                    [KeyboardButton(text=get_text("onboarding.handlers.btn_specify_phone", language=lang))]
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

@router.message(F.text.in_(SPECIFY_PHONE_TEXTS))
async def start_phone_input(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Начинает процесс ввода телефона"""
    lang = language
    
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
async def process_contact(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обрабатывает получение контакта"""
    lang = language
    
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
async def process_manual_phone(message: Message, state: FSMContext, db: Session, user_status: str = None, language: str = "ru"):
    """Обрабатывает ручной ввод телефона"""
    lang = language
    
    # Проверяем на отмену
    if message.text in CANCEL_TEXTS:
        await cancel_onboarding(message, state, db, user_status)
        return
    
    # Проверяем системные команды/кнопки - не обрабатываем их как телефон
    system_commands = ["/start", "/help"]
    for texts_list in [PROFILE_TEXTS, CREATE_REQUEST_TEXTS, MY_REQUESTS_TEXTS,
                       HELP_TEXTS, SHIFT_TEXTS, SWITCH_ROLE_TEXTS,
                       SPECIFY_ADDRESS_TEXTS, SPECIFY_PHONE_TEXTS,
                       MY_SHIFTS_TEXTS, ACTIVE_REQUESTS_TEXTS, ARCHIVE_TEXTS,
                       ACCEPTANCE_TEXTS, ADMIN_PANEL_TEXTS, CANCEL_TEXTS,
                       UPLOAD_DOCUMENTS_TEXTS, COMPLETE_WITHOUT_DOCS_TEXTS]:
        system_commands.extend(texts_list)
    
    if message.text in system_commands:
        # Очищаем состояние и пропускаем обработку
        await state.clear()
        return
    
    # Валидируем телефон
    phone_number = message.text.strip()
    lang = language
    is_valid, error_message = Validator.validate_phone(phone_number, language=lang)
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

async def complete_onboarding(message: Message, state: FSMContext, db: Session, user, user_status: str = None, language: str = "ru"):
    """Завершает процесс онбординга"""
    lang = language
    
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
            [KeyboardButton(text=get_text("onboarding.handlers.btn_upload_documents", language=lang))],
            [KeyboardButton(text=get_text("onboarding.handlers.btn_complete_without_docs", language=lang))]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        completion_text,
        reply_markup=completion_keyboard
    )
    
    await state.clear()
    logger.info(f"Онбординг завершен для пользователя {message.from_user.id}")

@router.message(F.text.in_(COMPLETE_WITHOUT_DOCS_TEXTS))
async def complete_onboarding_without_documents(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Завершает онбординг без документов"""
    lang = language
    
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
            reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], user.status, language=lang)
        )

        logger.info(f"Онбординг без документов завершен для пользователя {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка завершения онбординга без документов для {message.from_user.id}: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))

async def cancel_onboarding(message: Message, state: FSMContext, db: Session, user_status: str = None, language: str = "ru"):
    """Отменяет процесс онбординга"""
    lang = language
    
    await message.answer(
        get_text("onboarding.cancelled", language=lang),
        reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], "approved", language=lang)
    )

    await state.clear()
    logger.info(f"Онбординг отменен для пользователя {message.from_user.id}")

@router.message(F.text.in_(SPECIFY_ADDRESS_TEXTS))
async def start_address_input(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """
    LEGACY HANDLER: Обработка устаревшего ручного ввода адреса

    TASK 17: Локализованная версия - адреса управляются через систему квартир.
    """
    lang = await get_language_for_user(message.from_user.id)

    await state.clear()

    message_text = (
        f"{get_text('requests.address_system_updated_title', language=lang)}\n\n"
        f"{get_text('requests.address_system_updated_message', language=lang)}"
    )

    await message.answer(
        message_text,
        reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], "approved", language=lang)
    )

    logger.warning(
        f"{get_text('requests.legacy_address_handler_warning', language=lang)} "
        f"(user_id={message.from_user.id})"
    )

# ═══ ОБРАБОТЧИКИ ЗАГРУЗКИ ДОКУМЕНТОВ ═══

@router.message(F.text.in_(UPLOAD_DOCUMENTS_TEXTS))
async def start_document_upload(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Начинает процесс загрузки документов"""
    lang = language
    
    await message.answer(
        get_text("onboarding.documents.title", language=lang) + "\n\n" +
        get_text("onboarding.documents.description", language=lang),
        reply_markup=get_document_type_keyboard(lang)
    )
    await state.set_state(OnboardingStates.waiting_for_document_type)
    logger.info(f"Пользователь {message.from_user.id} начал загрузку документов")

@router.message(OnboardingStates.waiting_for_document_type, F.text)
async def process_document_type_selection(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обрабатывает выбор типа документа"""
    lang = language
    
    # Проверяем специальные команды
    if message.text in SKIP_DOCUMENTS_TEXTS:
        await skip_documents(message, state, db)
        return
    elif message.text in COMPLETE_ONBOARDING_TEXTS:
        await complete_onboarding_with_documents(message, state, db)
        return
    
    # Определяем тип документа
    document_type = get_document_type_from_text(message.text, language=lang)

    if document_type is None:
        await message.answer(
            get_text("onboarding.documents.unknown_type", language=lang),
            reply_markup=get_document_type_keyboard(lang)
        )
        return

    # Сохраняем выбранный тип в состоянии
    await state.update_data(selected_document_type=document_type.value)
    
    # Запрашиваем файл
    document_type_name = get_document_type_name(document_type, lang)
    await message.answer(
        f"📤 {get_text('onboarding.documents.upload_file', language=lang)}\n\n" +
        get_text("onboarding.handlers.document_type_label", language=lang).format(document_type_name=document_type_name),
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(OnboardingStates.waiting_for_document_file)
    logger.info(f"Пользователь {message.from_user.id} выбрал тип документа: {document_type.value}")

@router.message(OnboardingStates.waiting_for_document_file)
async def process_document_file(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обрабатывает загрузку файла документа"""
    lang = language
    
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
        f"{get_text('onboarding.handlers.doc_type_field', language=lang)}: {document_type_name}\n"
        f"{get_text('onboarding.handlers.file_field', language=lang)}: {file_name}\n"
        f"{get_text('onboarding.handlers.size_field', language=lang)}: {file_size // 1024} KB"
    )
    
    await message.answer(
        confirmation_text,
        reply_markup=get_document_confirmation_keyboard(lang)
    )
    await state.set_state(OnboardingStates.waiting_for_document_confirmation)

@router.message(OnboardingStates.waiting_for_document_confirmation, F.text)
async def process_document_confirmation(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обрабатывает подтверждение загрузки документа"""
    lang = language
    
    if message.text in CONFIRM_UPLOAD_TEXTS:
        await save_document(message, state, db)
    elif message.text in ONBOARDING_CANCEL_TEXTS:
        await cancel_document_upload(message, state, db)
    elif message.text in UPLOAD_ANOTHER_DOCUMENT_TEXTS:
        await start_document_upload(message, state, db)
    else:
        await message.answer(get_text("errors.unknown_error", language=lang))

async def save_document(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Сохраняет документ в базе данных"""
    lang = language
    
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
            media_result = await upload_document_to_media_service(
                bot=message.bot,
                file_id=file_id,
                user_telegram_id=message.from_user.id,
                description=f"Документ пользователя: {document_type_value}"
            )
            if media_result is not None:
                logger.info(f"Документ пользователя {message.from_user.id} загружен в Media Service")
            else:
                logger.warning(f"Документ пользователя {message.from_user.id} НЕ загружен в Media Service (см. предыдущие ошибки)")
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
            f"{get_text('onboarding.handlers.type_short_field', language=lang)}: {document_type_name}\n"
            f"{get_text('onboarding.handlers.file_field', language=lang)}: {file_name}",
            reply_markup=get_onboarding_completion_keyboard(lang)
        )
        
        # Очищаем состояние
        await state.clear()
        logger.info(f"Документ сохранен для пользователя {message.from_user.id}: {document_type.value}")
        
    except Exception as e:
        logger.error(f"Ошибка сохранения документа для {message.from_user.id}: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()

async def cancel_document_upload(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Отменяет загрузку документа"""
    lang = language
    
    await message.answer(
        get_text("onboarding.documents.upload_cancelled", language=lang),
        reply_markup=get_onboarding_completion_keyboard(lang)
    )
    await state.clear()

async def skip_documents(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Пропускает загрузку документов"""
    lang = language
    
    await message.answer(
        f"⏭️ {get_text('onboarding.documents.skip_documents', language=lang)}\n\n" +
        get_text("onboarding.handlers.can_upload_later", language=lang),
        reply_markup=get_onboarding_completion_keyboard(lang)
    )
    await state.clear()

async def complete_onboarding_with_documents(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Завершает онбординг с документами"""
    lang = language
    
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
            completion_text += f"\n📄 {get_text('onboarding.handlers.total_documents', language=lang)}: {documents_summary['total_documents']}"
            
            for doc_type, count in documents_summary['documents_by_type'].items():
                doc_type_name = get_document_type_name(DocumentType(doc_type), lang)
                completion_text += f"\n- {doc_type_name}: {count}"
        else:
            completion_text += f"\n\n{get_text('onboarding.documents.no_documents', language=lang)}"
        
        completion_text += f"\n\n{get_text('onboarding.pending_approval', language=lang)}"
        
        await message.answer(
            completion_text,
            reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], user.status, language=lang)
        )

        await state.clear()
        logger.info(f"Онбординг с документами завершен для пользователя {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка завершения онбординга с документами для {message.from_user.id}: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()

# ═══ ОБРАБОТЧИКИ КНОПОК ЗАВЕРШЕНИЯ ОНБОРДИНГА ═══

@router.message(F.text.in_(ADD_MORE_DOCUMENTS_TEXTS))
async def add_more_documents(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обрабатывает нажатие кнопки 'Добавить еще документы'"""
    lang = language
    
    await message.answer(
        get_text("onboarding.documents.title", language=lang) + "\n\n" +
        get_text("onboarding.documents.description", language=lang),
        reply_markup=get_document_type_keyboard(lang)
    )
    await state.set_state(OnboardingStates.waiting_for_document_type)
    logger.info(f"Пользователь {message.from_user.id} решил добавить еще документы")

@router.message(F.text.in_(COMPLETE_ONBOARDING_TEXTS))
async def complete_onboarding_final(message: Message, state: FSMContext, db: Session):
    """Обрабатывает нажатие кнопки 'Завершить онбординг'"""
    await complete_onboarding_with_documents(message, state, db)
