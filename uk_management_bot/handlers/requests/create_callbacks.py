"""Создание заявки: callback-кнопки inline (категория/отмена/срочность/подтверждение)."""

from aiogram import F
from aiogram.types import CallbackQuery, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from uk_management_bot.keyboards.requests import (
    get_media_keyboard,
)
from uk_management_bot.keyboards.base import get_user_contextual_keyboard
import logging
from typing import Optional

# Localization imports - TASK 17 Phase 2
from uk_management_bot.utils.helpers import get_text
# Single Source of Truth for button texts - TASK 17 Entry Handler Fix

from ._router import router

from .shared import (
    _db_scope,
    _get_user_language,
    _deny_if_pending_callback,
    RequestStates,
    _load_user_request_addresses,
    _has_any_address,
)

from .create import save_request

logger = logging.getLogger(__name__)


# =====================================
# ОБРАБОТЧИКИ CALLBACK_QUERY ДЛЯ INLINE КЛАВИАТУР
# =====================================

@router.callback_query(F.data.startswith("category_"))
async def handle_category_selection(callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None):
    """Обработка выбора категории заявки через inline клавиатуру"""
    # Get user language
    lang = await _get_user_language(callback=callback)

    if await _deny_if_pending_callback(callback, user_status):
        return

    try:
        logger.info(f"Обработка выбора категории для пользователя {callback.from_user.id}")

        # Извлекаем внутренний ключ категории из callback данных
        category_internal_key = callback.data.replace("category_", "")

        # Импортируем CATEGORY_INTERNAL_KEYS из keyboards
        from uk_management_bot.keyboards.requests import CATEGORY_INTERNAL_KEYS, CATEGORY_KEYS

        # Валидируем категорию (теперь проверяем внутренний ключ)
        if category_internal_key not in CATEGORY_INTERNAL_KEYS:
            await callback.answer(
                get_text("errors.invalid_category", language=lang),
                show_alert=True
            )
            logger.warning(f"Неверная категория '{category_internal_key}' от пользователя {callback.from_user.id}")
            return

        # Сохраняем внутренний ключ в FSM
        await state.update_data(category=category_internal_key)
        logger.info(f"Категория '{category_internal_key}' сохранена в state для пользователя {callback.from_user.id}")

        # Получаем локализованное название категории для отображения
        category_locale_key = CATEGORY_KEYS[category_internal_key]
        category_display = get_text(category_locale_key, language=lang)

        # Переходим к следующему состоянию
        await state.set_state(RequestStates.address)

        # Информационное редактирование исходного сообщения
        await callback.message.edit_text(
            get_text("requests.category_selected", language=lang, category=category_display)
        )

        # Отправляем inline-кнопки выбора адреса (callback addr:<type>:<id>),
        # строго из набора жителя. Свободный текст/глобальный поиск убран (R17).
        try:
            from uk_management_bot.keyboards.requests import build_request_address_inline_keyboard

            addresses = _load_user_request_addresses(callback.from_user.id)
            if not _has_any_address(addresses):
                await callback.message.answer(
                    get_text("requests.no_available_addresses", language=lang)
                )
                await state.clear()
                await callback.answer()
                return
            # Прячем ReplyKeyboard главного меню на время выбора.
            await callback.message.answer(
                get_text("requests.select_address", language=lang),
                reply_markup=ReplyKeyboardRemove(),
            )
            await callback.message.answer(
                get_text("requests.choose_address_prompt", language=lang),
                reply_markup=build_request_address_inline_keyboard(addresses, page=0, language=lang),
            )
            logger.info(f"Inline-клавиатура адресов отправлена пользователю {callback.from_user.id}")
        except Exception as keyboard_error:
            logger.error(f"Ошибка создания клавиатуры адресов: {keyboard_error}", exc_info=True)
            await callback.message.answer(get_text("errors.default", language=lang))
            await state.clear()
            await callback.answer()
            return

        await callback.answer()  # Убираем "часики" на кнопке
        logger.info(f"Пользователь {callback.from_user.id} выбрал категорию: {category_internal_key}")

    except Exception as e:
        logger.error(f"Ошибка обработки выбора категории: {e}", exc_info=True)
        await callback.answer(
            get_text("errors.default", language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "cancel_create")
async def handle_cancel_create(callback: CallbackQuery, state: FSMContext):
    """Отмена создания заявки из выбора категории (inline)."""
    lang = await _get_user_language(callback=callback)

    try:
        user_id = callback.from_user.id
        logger.info(f"[CANCEL_CREATE] Пользователь {user_id} отменил создание заявки через inline-кнопку")

        await state.clear()
        await callback.message.edit_text(get_text("requests.request_creation_cancelled", language=lang))
        await callback.message.answer(
            get_text("requests.return_to_main", language=lang),
            reply_markup=get_user_contextual_keyboard(callback.from_user.id)
        )
        await callback.answer()

        logger.info(f"[CANCEL_CREATE] Состояние очищено для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка отмены создания заявки: {e}")
        await callback.answer(get_text("errors.default", language=lang), show_alert=True)

@router.callback_query(F.data.startswith("urgency_"))
async def handle_urgency_selection(callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None):
    """Обработка выбора уровня срочности через inline клавиатуру"""
    lang = await _get_user_language(callback=callback)

    if await _deny_if_pending_callback(callback, user_status):
        return
    try:
        logger.info(f"Обработка выбора срочности для пользователя {callback.from_user.id}")

        urgency_internal_key = callback.data.replace("urgency_", "")

        from uk_management_bot.keyboards.requests import URGENCY_INTERNAL_KEYS, URGENCY_KEYS

        if urgency_internal_key not in URGENCY_INTERNAL_KEYS:
            await callback.answer(get_text("errors.invalid_urgency", language=lang), show_alert=True)
            logger.warning(f"Неверная срочность '{urgency_internal_key}' от пользователя {callback.from_user.id}")
            return

        # Сохраняем внутренний ключ срочности в FSM
        await state.update_data(urgency=urgency_internal_key)
        logger.info(f"Срочность '{urgency_internal_key}' сохранена в state для пользователя {callback.from_user.id}")

        # Переходим к следующему состоянию
        await state.set_state(RequestStates.media)

        # Получаем локализованное отображение срочности
        urgency_locale_key = URGENCY_KEYS[urgency_internal_key]
        urgency_display = get_text(urgency_locale_key, language=lang)

        # Редактируем исходное сообщение
        await callback.message.edit_text(
            get_text("requests.urgency_selected", language=lang, urgency=urgency_display)
        )

        # Отправляем новое сообщение с клавиатурой для медиа
        try:
            keyboard = get_media_keyboard(language=lang)
            await callback.message.answer(
                get_text("requests.send_photo_or_video", language=lang),
                reply_markup=keyboard
            )
            logger.info(f"Клавиатура медиа отправлена пользователю {callback.from_user.id}")
        except Exception as keyboard_error:
            logger.error(f"Ошибка создания клавиатуры медиа: {keyboard_error}", exc_info=True)
            # Fallback - показываем простую клавиатуру с кнопками
            fallback_keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text=get_text("buttons.continue", language=lang))],
                    [KeyboardButton(text=get_text("buttons.cancel", language=lang))]
                ],
                resize_keyboard=True
            )
            await callback.message.answer(
                get_text("requests.send_photo_or_video", language=lang),
                reply_markup=fallback_keyboard
            )

        await callback.answer()  # Убираем "часики" на кнопке
        logger.info(f"Пользователь {callback.from_user.id} выбрал срочность: {urgency_internal_key}, переход к медиа")

    except Exception as e:
        logger.error(f"Ошибка обработки выбора срочности: {e}", exc_info=True)
        await callback.answer(get_text("errors.default", language=lang), show_alert=True)

@router.callback_query(F.data.in_({"confirm_yes", "confirm_no"}))
async def handle_confirmation(callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None):
    """Обработка подтверждения заявки через inline клавиатуру"""
    lang = await _get_user_language(callback=callback)

    if await _deny_if_pending_callback(callback, user_status):
        return
    try:
        logger.info(f"Обработка подтверждения для пользователя {callback.from_user.id}")

        action = callback.data.replace("confirm_", "")

        if action == "yes":
            # Получаем данные из FSM
            data = await state.get_data()

            # Создаем заявку в базе данных
            with _db_scope(None) as db_session:
                request_number = await save_request(
                    data, callback.from_user.id, db_session, callback.bot, source="bot", role="applicant"
                )

            if request_number:
                # Get localized display values for category and urgency
                from uk_management_bot.keyboards.requests import CATEGORY_KEYS, URGENCY_KEYS

                category_key = data.get('category')
                if category_key in CATEGORY_KEYS:
                    category_display = get_text(CATEGORY_KEYS[category_key], language=lang)
                else:
                    category_display = category_key or get_text("common.not_specified", language=lang)

                urgency_key = data.get('urgency')
                if urgency_key in URGENCY_KEYS:
                    urgency_display = get_text(URGENCY_KEYS[urgency_key], language=lang)
                else:
                    urgency_display = urgency_key or get_text("urgency.low", language=lang)

                # Редактируем исходное сообщение без ReplyKeyboardMarkup
                await callback.message.edit_text(
                    get_text(
                        "requests.request_created_details",
                        language=lang,
                        request_number=request_number,
                        category=category_display,
                        address=data.get('address', get_text("common.not_specified", language=lang)),
                        urgency=urgency_display
                    )
                )
                # Отправляем отдельное сообщение с главной клавиатурой
                await callback.message.answer(
                    get_text("requests.return_to_main", language=lang),
                    reply_markup=get_user_contextual_keyboard(callback.from_user.id)
                )
                await state.clear()
                logger.info(f"Заявка создана пользователем {callback.from_user.id}")
            else:
                # Очищаем состояние и показываем главное меню, чтобы пользователь мог продолжить
                await state.clear()
                await callback.message.answer(
                    get_text("errors.request_save_failed", language=lang),
                    reply_markup=get_user_contextual_keyboard(callback.from_user.id)
                )
                await callback.answer(get_text("errors.request_save_failed", language=lang), show_alert=True)

        elif action == "no":
            await callback.message.edit_text(
                get_text("requests.request_creation_cancelled", language=lang)
            )
            await callback.message.answer(
                get_text("requests.return_to_main", language=lang),
                reply_markup=get_user_contextual_keyboard(callback.from_user.id)
            )
            await state.clear()
            logger.info(f"Создание заявки отменено пользователем {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки подтверждения: {e}")
        await callback.answer(get_text("errors.default", language=lang), show_alert=True)


