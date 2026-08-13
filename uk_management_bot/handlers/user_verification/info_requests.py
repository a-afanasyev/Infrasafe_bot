"""Запрос дополнительной информации: выбор типа и комментарий (FSM).

AUD5-ARCH-3 (волна 11): перенос 1:1 из handlers/user_verification.py.
"""

import logging

from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.utils.telegram_client import SEND_TIMEOUT
from uk_management_bot.keyboards.user_verification import (
    get_verification_main_keyboard,
    get_cancel_keyboard
)
from uk_management_bot.states.user_verification import UserVerificationStates
from uk_management_bot.utils.helpers import get_text

from ._router import router
from ._units import _create_request_and_collect_notify, _load_verification_stats

logger = logging.getLogger(__name__)

@router.callback_query(F.data.startswith("request_info_"))
async def select_info_type(callback: CallbackQuery, state: FSMContext, roles: list = None, language: str = "ru"):
    """Выбрать тип запрашиваемой информации"""
    lang = language
    # AUD3-15: info_type сам содержит "_" (property_deed, rental_agreement,
    # utility_bill) — parts[3] обрезал его до первого сегмента. Префикс
    # request_info_{user_id}_ фиксирован, поэтому хвост склеиваем целиком.
    parts = callback.data.split("_")
    user_id = int(parts[2])
    info_type = "_".join(parts[3:])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        # Сохраняем данные в состоянии
        await state.update_data(
            target_user_id=user_id,
            info_type=info_type
        )

        # Переходим в состояние ввода комментария
        await state.set_state(UserVerificationStates.enter_request_comment)

        await callback.message.edit_text(
            get_text('verification.enter_request_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора типа информации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.message(UserVerificationStates.enter_request_comment)
async def process_request_comment(message: Message, state: FSMContext, roles: list = None, language: str = "ru", *, _db=None):
    """Обработать комментарий к запросу информации"""
    lang = language
    comment = message.text

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await message.answer(get_text('errors.permission_denied', language=lang))
        return

    try:
        # Получаем данные из состояния
        data = await state.get_data()
        user_id = data.get('target_user_id')
        info_type = data.get('info_type')

        # Создаем запрос верификации + fetch-фаза уведомления (одним юнитом)
        requested_info = {
            'type': info_type,
            'comment': comment
        }
        admin_id = message.from_user.id
        notify_pair = await run_db(
            lambda s: _create_request_and_collect_notify(s, user_id, admin_id, requested_info),
            db=_db,
        )

        # Отправляем уведомление пользователю (сеть — вне сессии; best-effort,
        # как в историческом send_verification_request_notification)
        if notify_pair is not None:
            telegram_id, text = notify_pair
            try:
                await message.bot.send_message(telegram_id, text, request_timeout=SEND_TIMEOUT)
                logger.info(f"Уведомление о запросе информации отправлено пользователю {user_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о запросе информации: {e}")

        # Очищаем состояние
        await state.clear()

        # BUG-144: статистику пересчитываем перед перерисовкой меню — с пустым
        # {} счётчики на кнопках обнулялись до следующего захода в панель.
        stats = await run_db(_load_verification_stats, db=_db)

        await message.answer(
            get_text('verification.request_sent_successfully', language=lang),
            reply_markup=get_verification_main_keyboard(stats, lang)
        )

    except Exception as e:
        logger.error(f"Ошибка обработки комментария запроса: {e}")
        await message.answer(get_text('errors.unknown_error', language=lang))

