"""
Обработчики онбординга новых пользователей

AUD3-07/AUD5-ARCH-1 (A2-хвост, волна 7): DB-фаза ЖИВЫХ хендлеров — цельный
sync unit-of-work, исполняемый в worker-потоке через ``run_db``; наружу выходят
примитивы, а не ORM-строки (у ORM-объекта вне потока нет живой сессии).
Сеть (загрузка документа в Media Service) вынесена МЕЖДУ юнитами, в async-слой.

Инвентарь живости (волна 7). ЖИВЫЕ: ``start_phone_input`` (кнопку
«📱 Указать телефон» рисует base.handle_regular_start), ``process_contact`` и
``process_manual_phone`` (FSM waiting_for_phone), весь кластер документов —
``process_document_type_selection`` / ``process_document_file`` /
``process_document_confirmation`` / ``save_document`` / ``cancel_document_upload``
/ ``skip_documents`` / ``start_document_upload`` / ``complete_onboarding_with_documents``
/ ``add_more_documents`` / ``complete_onboarding_final`` (вход даёт
handlers/user_apartment_selection.py: ставит OnboardingStates.waiting_for_document_type
и показывает get_document_type_keyboard()).

BUG-158 (ретайр 2026-08-19): четыре мёртвых хендлера удалены —
``start_onboarding`` (``F.text == "/start"`` был перекрыт ``base.cmd_start``:
``start_router`` включается ПЕРВЫМ), ``complete_onboarding`` (ноль вызывающих),
``complete_onboarding_without_documents`` (генератор триггера жил внутри
мёртвой ``complete_onboarding``) и ``start_address_input`` (текста
«🏠 Указать адрес» не рождал никто). Что на их триггеры больше никто не
отвечает, пиннит ``tests/handlers/test_dead_handlers_retired.py``.
"""
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db
from uk_management_bot.services.user_verification_service import UserVerificationService
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.base import get_main_keyboard_for_role
from uk_management_bot.keyboards.documents_entry import UPLOAD_DOCUMENTS_CB, get_upload_documents_inline
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
    get_select_apartment_texts,
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
SELECT_APARTMENT_TEXTS = get_select_apartment_texts()
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


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# Наружу — только примитивы и словари-сводки, ORM-строки за границу не выходят.
#
# Запрос пользователя по telegram_id — тело ``AuthService.get_user_by_telegram_id``
# 1:1 (``self.db.query(User).filter(User.telegram_id == telegram_id).first()``).
# Метод объявлен ``async def``, хотя внутри чистый sync-SQL, поэтому из sync-юнита
# его не await'нуть; сам SQL сохранён байт-в-байт.
# ==========================================================================


def _apply_phone(db, telegram_id: int, phone_number: str) -> bool:
    """Сохраняет телефон. -> True | False (пользователя нет в БД)."""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if not user:
        return False

    user.phone = phone_number
    db.commit()
    return True


def _load_document_owner_id(db, telegram_id: int) -> Optional[int]:
    """-> user.id | None (пользователя нет в БД). Только id: ORM-строка наружу
    из потока не выходит."""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if not user:
        return None

    return user.id


def _apply_document(db, user_id: int, document_type: DocumentType,
                    file_id: str, file_name: Optional[str], file_size: Optional[int]) -> None:
    """Сохраняет документ пользователя (коммитит сам сервис)."""
    verification_service = UserVerificationService(db)
    verification_service.save_user_document(
        user_id=user_id,
        document_type=document_type,
        file_id=file_id,
        file_name=file_name,
        file_size=file_size
    )


def _load_documents_completion(db, telegram_id: int) -> Optional[tuple]:
    """-> (user_status, documents_summary) | None (пользователя нет в БД).

    ``documents_summary`` — словарь примитивов (см.
    UserVerificationService.get_user_documents_summary), безопасен вне сессии.
    """
    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if not user:
        return None

    verification_service = UserVerificationService(db)
    documents_summary = verification_service.get_user_documents_summary(user.id)
    return user.status, documents_summary


# Ручной ввод телефона и FSM-шаг waiting_for_phone удалены (спека 2026-09-03):
# телефон только из Telegram-контакта, который приходит без состояния и
# обрабатывается handlers/phone_share.py.


async def cancel_onboarding(message: Message, state: FSMContext, user_status: str = None, language: str = "ru"):
    """Отменяет процесс онбординга"""
    lang = language
    
    await message.answer(
        get_text("onboarding.cancelled", language=lang),
        reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], "approved", language=lang)
    )

    await state.clear()
    logger.info(f"Онбординг отменен для пользователя {message.from_user.id}")

# ═══ ОБРАБОТЧИКИ ЗАГРУЗКИ ДОКУМЕНТОВ ═══

# Регистрация по UPLOAD_DOCUMENTS_TEXTS мертва (генератор кнопки — мёртвая
# ``complete_onboarding``), но САМА функция живая: её напрямую зовёт
# ``process_document_confirmation`` по кнопке «загрузить ещё документ».
async def _begin_document_type_step(target: Message, state: FSMContext, lang: str) -> None:
    """Экран выбора типа документа + состояние. Общий для reply-кнопки,
    inline-кнопки «Загрузить документы» (BUG-188) и «загрузить ещё»."""
    await target.answer(
        get_text("onboarding.documents.title", language=lang) + "\n\n" +
        get_text("onboarding.documents.description", language=lang),
        reply_markup=get_document_type_keyboard(lang)
    )
    await state.set_state(OnboardingStates.waiting_for_document_type)


@router.message(F.text.in_(UPLOAD_DOCUMENTS_TEXTS))
async def start_document_upload(message: Message, state: FSMContext, language: str = "ru"):
    """Начинает процесс загрузки документов"""
    await _begin_document_type_step(message, state, language)
    logger.info(f"Пользователь {message.from_user.id} начал загрузку документов")


@router.callback_query(F.data == UPLOAD_DOCUMENTS_CB)
async def open_document_upload(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Inline-кнопка «📤 Загрузить документы» из уведомления о запросе (BUG-188).
    Работает из любого состояния онбординга-документов: повторное нажатие
    просто перерисовывает выбор типа."""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:  # noqa: BLE001 — старое/уже отредактированное сообщение
        logger.debug(f"Не удалось снять inline-кнопку загрузки документов: {e}")
    await _begin_document_type_step(callback.message, state, language)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} открыл загрузку документов по кнопке")


@router.message(OnboardingStates.waiting_for_document_type, F.photo | F.document)
async def document_before_type(message: Message, state: FSMContext, language: str = "ru"):
    """Фото/файл до выбора типа (BUG-188): раньше терялись молча — хендлер
    выбора типа ловил только текст. Состояние не трогаем."""
    await message.answer(
        get_text("onboarding.documents.choose_type_first", language=language),
        reply_markup=get_document_type_keyboard(language),
    )


@router.message(StateFilter(None), F.chat.type == "private", F.photo | F.document)
async def catch_stray_document(message: Message, language: str = "ru", **_kwargs):
    """Фото/файл вне какого-либо сценария (BUG-188). Все штатные приёмники
    медиа привязаны к FSM-состояниям, поэтому здесь — только подсказка с
    кнопкой входа в загрузку документов, вместо тишины."""
    await message.answer(
        get_text("onboarding.documents.send_after_button", language=language),
        reply_markup=get_upload_documents_inline(language),
    )

@router.message(OnboardingStates.waiting_for_document_type, F.text)
async def process_document_type_selection(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обрабатывает выбор типа документа"""
    lang = language

    # Проверяем специальные команды
    if message.text in SKIP_DOCUMENTS_TEXTS:
        await skip_documents(message, state, language=lang)
        return
    elif message.text in COMPLETE_ONBOARDING_TEXTS:
        await complete_onboarding_with_documents(message, state, language=lang,
                                                 _db=_db)
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
async def process_document_file(message: Message, state: FSMContext, language: str = "ru"):
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
    
    # Валидируем файл. run_db здесь НЕ нужен: validate_document_file —
    # чистая проверка file_id/размера/расширения, к self.db она не обращается
    # ни в одной ветке, поэтому сессия сервису не передаётся (открывать её
    # ради проверки строки — лишнее соединение из пула на каждый файл).
    verification_service = UserVerificationService(None)
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
async def process_document_confirmation(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обрабатывает подтверждение загрузки документа"""
    lang = language

    if message.text in CONFIRM_UPLOAD_TEXTS:
        await save_document(message, state, language=lang, _db=_db)
    elif message.text in ONBOARDING_CANCEL_TEXTS:
        await cancel_document_upload(message, state, language=lang)
    elif message.text in UPLOAD_ANOTHER_DOCUMENT_TEXTS:
        await start_document_upload(message, state, language=lang)
    else:
        await message.answer(get_text("errors.unknown_error", language=lang))

async def save_document(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Сохраняет документ в базе данных.

    Раскрой «БД → сеть → БД»: загрузка файла в Media Service — сетевой await,
    он обязан идти МЕЖДУ юнитами, а не внутри открытой сессии. Порядок шагов
    сохранён исходный (найти пользователя → выгрузить в Media → записать в БД).
    """
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
        user_id = await run_db(
            lambda s: _load_document_owner_id(s, message.from_user.id), db=_db
        )

        if user_id is None:
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
        document_type = DocumentType(document_type_value)
        await run_db(
            lambda s: _apply_document(s, user_id, document_type, file_id, file_name, file_size),
            db=_db,
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

async def cancel_document_upload(message: Message, state: FSMContext, language: str = "ru"):
    """Отменяет загрузку документа"""
    lang = language
    
    await message.answer(
        get_text("onboarding.documents.upload_cancelled", language=lang),
        reply_markup=get_onboarding_completion_keyboard(lang)
    )
    await state.clear()

async def skip_documents(message: Message, state: FSMContext, language: str = "ru"):
    """Пропускает загрузку документов"""
    lang = language
    
    await message.answer(
        f"⏭️ {get_text('onboarding.documents.skip_documents', language=lang)}\n\n" +
        get_text("onboarding.handlers.can_upload_later", language=lang),
        reply_markup=get_onboarding_completion_keyboard(lang)
    )
    await state.clear()

async def complete_onboarding_with_documents(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Завершает онбординг с документами"""
    lang = language

    try:
        # Получаем пользователя и сводку документов одним юнитом
        loaded = await run_db(
            lambda s: _load_documents_completion(s, message.from_user.id), db=_db
        )

        if loaded is None:
            await message.answer(get_text("errors.unknown_error", language=lang))
            await state.clear()
            return

        user_status, documents_summary = loaded

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
            reply_markup=get_main_keyboard_for_role("applicant", ["applicant"], user_status, language=lang)
        )

        await state.clear()
        logger.info(f"Онбординг с документами завершен для пользователя {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка завершения онбординга с документами для {message.from_user.id}: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()

# ═══ ОБРАБОТЧИКИ КНОПОК ЗАВЕРШЕНИЯ ОНБОРДИНГА ═══

@router.message(F.text.in_(ADD_MORE_DOCUMENTS_TEXTS))
async def add_more_documents(message: Message, state: FSMContext, language: str = "ru"):
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
async def complete_onboarding_final(message: Message, state: FSMContext,
                                    language: str = "ru", *, _db=None):
    """Обрабатывает нажатие кнопки 'Завершить онбординг'. language — из
    aiogram-DI: без протяжки финальный экран рендерился на "ru" (BUG-165)."""
    await complete_onboarding_with_documents(message, state, language=language,
                                             _db=_db)
