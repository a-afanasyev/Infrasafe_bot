"""
Обработчики для редактирования профиля пользователя
"""
import logging
from dataclasses import dataclass
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db
from uk_management_bot.states.profile_editing import ProfileEditingStates
from uk_management_bot.keyboards.profile import (
    get_profile_edit_keyboard,
    get_language_choice_keyboard,
    get_cancel_keyboard
)
from uk_management_bot.keyboards.base import get_role_switch_inline
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import parse_roles_safe

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


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки
# (у ORM-объекта за пределами worker-потока нет живой сессии).
# ==========================================================================

@dataclass(frozen=True)
class _ProfileUserView:
    """Ровно те атрибуты User, что читает get_profile_edit_keyboard."""
    phone: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    language: Optional[str]


@dataclass(frozen=True)
class _ProfileOverview:
    """Данные для возврата к карточке профиля (cancel_profile_edit)."""
    found: bool
    lang: Optional[str]
    roles: tuple
    active_role: Optional[str]
    profile_text: Optional[str]


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# ==========================================================================

def _user_view_from(user) -> Optional[_ProfileUserView]:
    if not user:
        return None
    return _ProfileUserView(
        phone=user.phone,
        first_name=user.first_name,
        last_name=user.last_name,
        language=user.language,
    )


def _load_profile_edit_view(db, telegram_id: int) -> tuple:
    """-> (lang, _ProfileUserView | None) для меню редактирования профиля."""
    lang = get_user_language(db, telegram_id)

    # Получаем данные пользователя
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        lang = get_user_language(db, telegram_id)
        return lang, None
    return lang, _user_view_from(user)


def _load_profile_overview(db, telegram_id: int) -> _ProfileOverview:
    """DB-фаза cancel_profile_edit: роли + отформатированный текст профиля."""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        lang = get_user_language(db, telegram_id)
        return _ProfileOverview(found=False, lang=lang, roles=(), active_role=None, profile_text=None)

    # Парсим роли (COD-01: канонический парсер, JSON+CSV)
    roles = parse_roles_safe(user.roles) or ["applicant"]

    active_role = user.active_role or roles[0] if roles else "applicant"

    # Форматируем профиль
    from uk_management_bot.services.profile_service import ProfileService
    profile_service = ProfileService(db)
    profile_data = profile_service.get_user_profile_data(telegram_id)

    lang = None
    profile_text = None
    if profile_data:
        lang = get_user_language(db, telegram_id)
        profile_text = profile_service.format_profile_text(profile_data, language=lang)

    return _ProfileOverview(
        found=True,
        lang=lang,
        roles=tuple(roles),
        active_role=active_role,
        profile_text=profile_text,
    )


def _load_cancel_input_view(db, telegram_id: int) -> tuple:
    """-> (lang, _ProfileUserView | None) для возврата из вложенного ввода."""
    lang = get_user_language(db, telegram_id)

    # BUG-BOT-020: перечитываем пользователя из БД, чтобы клавиатура отрисовала
    # актуальные значения (phone/first_name/last_name), а не stale "не указано".
    fresh_user = db.query(User).filter(User.telegram_id == telegram_id).first()
    return lang, _user_view_from(fresh_user)


def _update_user_phone(db, telegram_id: int, phone: str) -> Optional[_ProfileUserView]:
    """Обновляем телефон. -> свежий view для клавиатуры | None (не найден).

    BUG-151 п.8: view возвращается ИЗ ЮНИТА (рецепт BUG-BOT-020) — иначе
    клавиатура после сохранения рендерилась без user, все значения «не указано»."""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return None
    user.phone = phone
    db.commit()
    return _user_view_from(user)


def _update_user_first_name(db, telegram_id: int, first_name: str) -> Optional[_ProfileUserView]:
    """Обновляем имя. -> свежий view | None (не найден). См. _update_user_phone."""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return None
    user.first_name = first_name
    db.commit()
    return _user_view_from(user)


def _update_user_last_name(db, telegram_id: int, last_name: str) -> Optional[_ProfileUserView]:
    """Обновляем фамилию. -> свежий view | None (не найден). См. _update_user_phone."""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return None
    user.last_name = last_name
    db.commit()
    return _user_view_from(user)


def _set_user_language(db, telegram_id: int, selected_lang: str) -> Optional[_ProfileUserView]:
    """Обновляем язык в базе данных. -> None, если пользователь не найден."""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return None

    user.language = selected_lang
    db.commit()

    # Обновляем объект пользователя в сессии для получения актуальных данных
    db.refresh(user)
    return _user_view_from(user)


@router.callback_query(F.data == "edit_profile")
async def handle_edit_profile_start(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Начало редактирования профиля"""
    # WR-06 (класс): дефолт ДО try — если db-фаза бросит, except ниже
    # не должен упасть NameError'ом на несвязанном lang.
    lang = "ru"
    try:
        lang, user = await run_db(lambda s: _load_profile_edit_view(s, callback.from_user.id), db=_db)
        if user is None:
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
        await callback.answer(get_text("profile_editing.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "cancel_profile_edit")
async def handle_cancel_profile_edit(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Отмена редактирования профиля - возврат к профилю"""
    lang = "ru"
    try:
        overview = await run_db(lambda s: _load_profile_overview(s, callback.from_user.id), db=_db)
        if not overview.found:
            await callback.answer(get_text("profile_editing.handlers.user_not_found", language=overview.lang), show_alert=True)
            return

        if overview.profile_text is not None:
            lang = overview.lang

            # Добавляем кнопку редактирования к профилю
            keyboard = get_role_switch_inline(list(overview.roles), overview.active_role, language=lang)
            rows = list(keyboard.inline_keyboard)
            rows.append([{"text": get_text("profile.edit", language=lang), "callback_data": "edit_profile"}])

            from aiogram.types import InlineKeyboardMarkup
            new_keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

            await callback.message.edit_text(overview.profile_text, reply_markup=new_keyboard)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка отмены редактирования профиля: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        logger.error(f"Детали ошибки: {str(e)}")
        await callback.answer(get_text("profile_editing.handlers.error_cancel_edit", language=lang), show_alert=True)


# ===== РЕДАКТИРОВАНИЕ ТЕЛЕФОНА =====

@router.callback_query(F.data == "edit_phone")
async def handle_edit_phone(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Редактирование телефона"""
    lang = "ru"
    try:
        lang = await run_db(lambda s: get_user_language(s, callback.from_user.id), db=_db)

        await callback.message.edit_text(
            get_text("profile.enter_phone", language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )

        await state.set_state(ProfileEditingStates.waiting_for_phone)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка редактирования телефона: {e}")
        await callback.answer(get_text("profile_editing.handlers.error_occurred", language=lang), show_alert=True)


@router.message(ProfileEditingStates.waiting_for_phone)
async def handle_phone_input(message: Message, state: FSMContext, *, _db=None):
    """Обработка ввода телефона"""
    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        lang = await run_db(lambda s: get_user_language(s, message.from_user.id), db=_db)
        phone = message.text.strip()

        if not phone:
            await message.answer(get_text("profile.phone_empty", language=lang))
            return

        # Простая валидация телефона
        phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not phone_clean.isdigit() or len(phone_clean) < 10:
            await message.answer(get_text("profile.phone_invalid", language=lang))
            return

        updated = await run_db(lambda s: _update_user_phone(s, message.from_user.id, phone), db=_db)
        if updated:
            await message.answer(
                get_text("profile.phone_updated", language=lang),
                reply_markup=get_profile_edit_keyboard(lang, updated)
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
async def handle_edit_language(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Редактирование языка"""
    lang = "ru"
    try:
        lang = await run_db(lambda s: get_user_language(s, callback.from_user.id), db=_db)

        await callback.message.edit_text(
            get_text("profile.select_language", language=lang),
            reply_markup=get_language_choice_keyboard(lang)
        )

        await state.set_state(ProfileEditingStates.waiting_for_language_choice)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка редактирования языка: {e}")
        await callback.answer(get_text("profile_editing.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("set_language_"))
async def handle_language_choice(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Обработка выбора языка"""
    lang = "ru"
    try:
        lang = await run_db(lambda s: get_user_language(s, callback.from_user.id), db=_db)
        selected_lang = callback.data.replace("set_language_", "")

        if selected_lang not in ["ru", "uz"]:
            await callback.answer(get_text("profile_editing.handlers.unsupported_language", language=lang), show_alert=True)
            return

        user = await run_db(lambda s: _set_user_language(s, callback.from_user.id, selected_lang), db=_db)
        if user is None:
            await callback.answer(get_text("errors.user_not_found", language=lang), show_alert=True)
            return

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
            await callback.answer(get_text("errors.unknown_error", language=lang), show_alert=True)
        except Exception:
            await callback.answer(get_text("profile_editing.handlers.error_occurred", language="ru"), show_alert=True)
        await state.clear()


# ===== ОТМЕНА ОПЕРАЦИЙ =====

@router.callback_query(F.data == "cancel_input")
async def handle_cancel_input(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Отмена ввода - возврат к меню редактирования"""
    try:
        logger.info(f"Обработка отмены ввода для пользователя {callback.from_user.id}")

        # Получаем язык пользователя и свежие данные (BUG-BOT-020)
        lang, fresh_user = await run_db(lambda s: _load_cancel_input_view(s, callback.from_user.id), db=_db)
        logger.info(f"Язык пользователя: {lang}")

        # Получаем текст заголовка
        title_text = get_text("profile.edit_title", language=lang)
        logger.info(f"Текст заголовка: {title_text}")

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
        await callback.answer(get_text("profile_editing.handlers.error_cancel", language="ru"), show_alert=True)


@router.callback_query(F.data == "cancel_language_choice")
async def handle_cancel_language_choice(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Отмена выбора языка"""
    try:
        logger.info(f"Обработка отмены выбора языка для пользователя {callback.from_user.id}")
        await handle_cancel_input(callback, state, _db=_db)
    except Exception as e:
        logger.error(f"Ошибка отмены выбора языка: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        await callback.answer(get_text("profile_editing.handlers.error_cancel_language", language="ru"), show_alert=True)


# ===== РЕДАКТИРОВАНИЕ ФИО =====

@router.callback_query(F.data == "edit_first_name")
async def handle_edit_first_name(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Редактирование имени"""
    lang = "ru"
    try:
        lang = await run_db(lambda s: get_user_language(s, callback.from_user.id), db=_db)

        await callback.message.edit_text(
            get_text("profile.enter_first_name", language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )

        await state.set_state(ProfileEditingStates.waiting_for_first_name)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка редактирования имени: {e}")
        await callback.answer(get_text("profile_editing.handlers.error_occurred", language=lang), show_alert=True)


@router.message(ProfileEditingStates.waiting_for_first_name)
async def handle_first_name_input(message: Message, state: FSMContext, *, _db=None):
    """Обработка ввода имени"""
    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        lang = await run_db(lambda s: get_user_language(s, message.from_user.id), db=_db)
        first_name = message.text.strip()

        if not first_name:
            from uk_management_bot.utils.safe_localization import safe_get_text
            await message.answer(safe_get_text("errors.name_empty", language=lang))
            return

        updated = await run_db(lambda s: _update_user_first_name(s, message.from_user.id, first_name), db=_db)
        if updated:
            await message.answer(
                get_text("profile.first_name_updated", language=lang),
                reply_markup=get_profile_edit_keyboard(lang, updated)
            )
        else:
            await message.answer(get_text("errors.user_not_found", language=lang))

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка сохранения имени: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()


@router.callback_query(F.data == "edit_last_name")
async def handle_edit_last_name(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Редактирование фамилии"""
    try:
        lang = await run_db(lambda s: get_user_language(s, callback.from_user.id), db=_db)

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
async def handle_last_name_input(message: Message, state: FSMContext, *, _db=None):
    """Обработка ввода фамилии"""
    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        lang = await run_db(lambda s: get_user_language(s, message.from_user.id), db=_db)
        last_name = message.text.strip()

        if not last_name:
            from uk_management_bot.utils.safe_localization import safe_get_text
            await message.answer(safe_get_text("errors.last_name_empty", language=lang))
            return

        updated = await run_db(lambda s: _update_user_last_name(s, message.from_user.id, last_name), db=_db)
        if updated:
            await message.answer(
                get_text("profile.last_name_updated", language=lang),
                reply_markup=get_profile_edit_keyboard(lang, updated)
            )
        else:
            await message.answer(get_text("errors.user_not_found", language=lang))

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка сохранения фамилии: {e}")
        await message.answer(get_text("errors.unknown_error", language=lang))
        await state.clear()
