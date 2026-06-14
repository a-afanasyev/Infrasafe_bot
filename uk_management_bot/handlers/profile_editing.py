"""
Обработчики для редактирования профиля пользователя
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.database.models.user import User
from uk_management_bot.states.profile_editing import ProfileEditingStates
from uk_management_bot.keyboards.profile import (
    get_profile_edit_keyboard,
    get_language_choice_keyboard,
    get_cancel_keyboard
)
from uk_management_bot.keyboards.base import get_role_switch_inline
from uk_management_bot.utils.helpers import get_text

router = Router()
logger = logging.getLogger(__name__)

def get_user_language(db: Session, telegram_id: int) -> str:
    """Получает язык пользователя из базы данных"""
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            language = user.language if user.language else "ru"
            logger.debug(f"Язык пользователя {telegram_id}: {language}")
            return language
        else:
            logger.warning(f"Пользователь {telegram_id} не найден в базе данных")
            return "ru"
    except Exception as e:
        logger.error(f"Ошибка получения языка пользователя {telegram_id}: {e}")
        return "ru"


@router.callback_query(F.data == "edit_profile")
async def handle_edit_profile_start(callback: CallbackQuery, state: FSMContext, db: Session):
    """Начало редактирования профиля"""
    try:
        lang = get_user_language(db, callback.from_user.id)

        # Получаем данные пользователя
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            lang = get_user_language(db, callback.from_user.id)
            await callback.answer(get_text("profile_editing.handlers.user_not_found", language=lang), show_alert=True)
            return

        # Показываем меню редактирования с текущими значениями
        await callback.message.edit_text(
            get_text("profile.edit_title", language=lang),
            reply_markup=get_profile_edit_keyboard(lang, user)
        )

        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка начала редактирования профиля: {e}")
        lang = get_user_language(db, callback.from_user.id) if db else "ru"
        await callback.answer(get_text("profile_editing.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "cancel_profile_edit")
async def handle_cancel_profile_edit(callback: CallbackQuery, state: FSMContext, db: Session):
    """Отмена редактирования профиля - возврат к профилю"""
    try:
        # Получаем данные пользователя для отображения профиля
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            lang = get_user_language(db, callback.from_user.id)
            await callback.answer(get_text("profile_editing.handlers.user_not_found", language=lang), show_alert=True)
            return
        
        # Парсим роли
        import json
        roles = ["applicant"]
        try:
            if user.roles:
                parsed_roles = json.loads(user.roles)
                if isinstance(parsed_roles, list):
                    roles = [str(r) for r in parsed_roles if isinstance(r, str)]
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            logger.warning(f"Ошибка парсинга ролей пользователя {user.id}: {e}")
            roles = ["applicant"]
        
        active_role = user.active_role or roles[0] if roles else "applicant"
        
        # Форматируем профиль
        from uk_management_bot.services.profile_service import ProfileService
        profile_service = ProfileService(db)
        profile_data = profile_service.get_user_profile_data(callback.from_user.id)
        
        if profile_data:
            lang = get_user_language(db, callback.from_user.id)
            profile_text = profile_service.format_profile_text(profile_data, language=lang)
            
            # Добавляем кнопку редактирования к профилю
            keyboard = get_role_switch_inline(roles, active_role, language=lang)
            rows = list(keyboard.inline_keyboard)
            rows.append([{"text": get_text("profile.edit", language=lang), "callback_data": "edit_profile"}])
            
            from aiogram.types import InlineKeyboardMarkup
            new_keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
            
            await callback.message.edit_text(profile_text, reply_markup=new_keyboard)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отмены редактирования профиля: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        logger.error(f"Детали ошибки: {str(e)}")
        lang = get_user_language(db, callback.from_user.id) if db else "ru"
        await callback.answer(get_text("profile_editing.handlers.error_cancel_edit", language=lang), show_alert=True)


# ===== РЕДАКТИРОВАНИЕ ТЕЛЕФОНА =====

@router.callback_query(F.data == "edit_phone")
async def handle_edit_phone(callback: CallbackQuery, state: FSMContext, db: Session):
    """Редактирование телефона"""
    try:
        lang = get_user_language(db, callback.from_user.id)
        
        await callback.message.edit_text(
            get_text("profile.enter_phone", language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await state.set_state(ProfileEditingStates.waiting_for_phone)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования телефона: {e}")
        lang = get_user_language(db, callback.from_user.id) if db else "ru"
        await callback.answer(get_text("profile_editing.handlers.error_occurred", language=lang), show_alert=True)


@router.message(ProfileEditingStates.waiting_for_phone)
async def handle_phone_input(message: Message, state: FSMContext, db: Session):
    """Обработка ввода телефона"""
    try:
        lang = get_user_language(db, message.from_user.id)
        phone = message.text.strip()
        
        if not phone:
            await message.answer(get_text("profile.phone_empty", language=lang))
            return
        
        # Простая валидация телефона
        phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not phone_clean.isdigit() or len(phone_clean) < 10:
            await message.answer(get_text("profile.phone_invalid", language=lang))
            return
        
        # Обновляем телефон в базе данных
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user:
            user.phone = phone
            db.commit()
            
            await message.answer(
                get_text("profile.phone_updated", language=lang),
                reply_markup=get_profile_edit_keyboard(lang)
            )
        else:
            await message.answer(get_text("errors.user_not_found", language=lang))
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения телефона: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()


# ===== РЕДАКТИРОВАНИЕ ЯЗЫКА =====

@router.callback_query(F.data == "edit_language")
async def handle_edit_language(callback: CallbackQuery, state: FSMContext, db: Session):
    """Редактирование языка"""
    try:
        lang = get_user_language(db, callback.from_user.id)
        
        await callback.message.edit_text(
            get_text("profile.select_language", language=lang),
            reply_markup=get_language_choice_keyboard(lang)
        )
        
        await state.set_state(ProfileEditingStates.waiting_for_language_choice)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования языка: {e}")
        lang = get_user_language(db, callback.from_user.id) if db else "ru"
        await callback.answer(get_text("profile_editing.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("set_language_"))
async def handle_language_choice(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработка выбора языка"""
    try:
        lang = get_user_language(db, callback.from_user.id)
        selected_lang = callback.data.replace("set_language_", "")
        
        if selected_lang not in ["ru", "uz"]:
            await callback.answer(get_text("profile_editing.handlers.unsupported_language", language=lang), show_alert=True)
            return
        
        # Обновляем язык в базе данных
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer(get_text("errors.user_not_found", language=lang), show_alert=True)
            return
        
        user.language = selected_lang
        db.commit()
        
        # Обновляем объект пользователя в сессии для получения актуальных данных
        db.refresh(user)
        
        # Используем новый язык для сообщения
        new_lang = selected_lang
        await callback.message.edit_text(
            get_text("profile.language_updated", language=new_lang),
            reply_markup=get_profile_edit_keyboard(new_lang, user)
        )
        
        await state.clear()
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения языка: {e}", exc_info=True)
        try:
            lang = get_user_language(db, callback.from_user.id) if db else "ru"
            await callback.answer(get_text("errors.unknown_error", language=lang), show_alert=True)
        except:
            await callback.answer(get_text("profile_editing.handlers.error_occurred", language="ru"), show_alert=True)
        await state.clear()


# ===== ОТМЕНА ОПЕРАЦИЙ =====

@router.callback_query(F.data == "cancel_input")
async def handle_cancel_input(callback: CallbackQuery, state: FSMContext, db: Session):
    """Отмена ввода - возврат к меню редактирования"""
    try:
        logger.info(f"Обработка отмены ввода для пользователя {callback.from_user.id}")

        # Получаем язык пользователя
        lang = get_user_language(db, callback.from_user.id)
        logger.info(f"Язык пользователя: {lang}")

        # Получаем текст заголовка
        title_text = get_text("profile.edit_title", language=lang)
        logger.info(f"Текст заголовка: {title_text}")

        # BUG-BOT-020: перечитываем пользователя из БД, чтобы клавиатура отрисовала
        # актуальные значения (phone/first_name/last_name), а не stale "не указано".
        fresh_user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()

        # Получаем клавиатуру
        keyboard = get_profile_edit_keyboard(lang, fresh_user)
        logger.info(f"Клавиатура создана: {keyboard}")
        
        # Редактируем сообщение
        await callback.message.edit_text(
            title_text,
            reply_markup=keyboard
        )
        logger.info("Сообщение успешно отредактировано")
        
        # Очищаем состояние
        await state.clear()
        logger.info("Состояние очищено")
        
        await callback.answer()
        logger.info("Обработка отмены завершена успешно")
        
    except Exception as e:
        logger.error(f"Ошибка отмены ввода: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        logger.error(f"Детали ошибки: {str(e)}")
        
        # Показываем пользователю более информативное сообщение об ошибке
        lang = get_user_language(db, callback.from_user.id) if db else "ru"
        await callback.answer(get_text("profile_editing.handlers.error_cancel", language=lang), show_alert=True)


@router.callback_query(F.data == "cancel_language_choice")
async def handle_cancel_language_choice(callback: CallbackQuery, state: FSMContext, db: Session):
    """Отмена выбора языка"""
    try:
        logger.info(f"Обработка отмены выбора языка для пользователя {callback.from_user.id}")
        await handle_cancel_input(callback, state, db)
    except Exception as e:
        logger.error(f"Ошибка отмены выбора языка: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        await callback.answer(get_text("profile_editing.handlers.error_cancel_language", language="ru"), show_alert=True)


# ===== РЕДАКТИРОВАНИЕ ФИО =====

@router.callback_query(F.data == "edit_first_name")
async def handle_edit_first_name(callback: CallbackQuery, state: FSMContext, db: Session):
    """Редактирование имени"""
    try:
        lang = get_user_language(db, callback.from_user.id)
        
        await callback.message.edit_text(
            get_text("profile.enter_first_name", language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await state.set_state(ProfileEditingStates.waiting_for_first_name)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования имени: {e}")
        lang = get_user_language(db, callback.from_user.id) if db else "ru"
        await callback.answer(get_text("profile_editing.handlers.error_occurred", language=lang), show_alert=True)


@router.message(ProfileEditingStates.waiting_for_first_name)
async def handle_first_name_input(message: Message, state: FSMContext, db: Session):
    """Обработка ввода имени"""
    try:
        lang = get_user_language(db, message.from_user.id)
        first_name = message.text.strip()
        
        if not first_name:
            from uk_management_bot.utils.safe_localization import safe_get_text
            await message.answer(safe_get_text("errors.name_empty", language=lang))
            return
        
        # Обновляем имя в базе данных
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user:
            user.first_name = first_name
            db.commit()
            
            await message.answer(
                get_text("profile.first_name_updated", language=lang),
                reply_markup=get_profile_edit_keyboard(lang)
            )
        else:
            await message.answer(get_text("errors.user_not_found", language=lang))
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения имени: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()


@router.callback_query(F.data == "edit_last_name")
async def handle_edit_last_name(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Редактирование фамилии"""
    try:
        lang = get_user_language(db, callback.from_user.id)
        
        await callback.message.edit_text(
            get_text("profile.enter_last_name", language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await state.set_state(ProfileEditingStates.waiting_for_last_name)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования фамилии: {e}")
        from uk_management_bot.utils.safe_localization import safe_get_text
        lang = language
        await callback.answer(safe_get_text("errors.error_occurred", language=lang), show_alert=True)


@router.message(ProfileEditingStates.waiting_for_last_name)
async def handle_last_name_input(message: Message, state: FSMContext, db: Session):
    """Обработка ввода фамилии"""
    try:
        lang = get_user_language(db, message.from_user.id)
        last_name = message.text.strip()
        
        if not last_name:
            from uk_management_bot.utils.safe_localization import safe_get_text
            await message.answer(safe_get_text("errors.last_name_empty", language=lang))
            return
        
        # Обновляем фамилию в базе данных
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user:
            user.last_name = last_name
            db.commit()
            
            await message.answer(
                get_text("profile.last_name_updated", language=lang),
                reply_markup=get_profile_edit_keyboard(lang)
            )
        else:
            await message.answer(get_text("errors.user_not_found", language=lang))
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения фамилии: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()
