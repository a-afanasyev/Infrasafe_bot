"""
Обработчики для модерации заявок на квартиры (Apartment Moderation)

Функционал:
- Просмотр списка заявок на рассмотрении
- Просмотр детальной информации о заявке
- Подтверждение заявки (approve)
- Отклонение заявки (reject)
- Добавление комментариев к решению
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from uk_management_bot.database.session import get_db
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.states.address_management import ApartmentModerationStates
from uk_management_bot.keyboards.address_management import (
    get_moderation_requests_keyboard,
    get_moderation_request_details_keyboard,
    get_cancel_keyboard_inline
)
from uk_management_bot.keyboards.base import get_main_keyboard_for_role
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

router = Router()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА ЗАЯВОК
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_moderation_list")
async def show_moderation_list(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Показать список заявок на модерацию"""
    await state.clear()

    db = next(get_db())
    try:
        requests = AddressService.get_pending_requests(db, limit=50)

        if not requests:
            lang = language
            await callback.message.edit_text(
                get_text("address_moderation.handlers.moderation_list_empty", language=lang),
                reply_markup=get_moderation_requests_keyboard([], page=0)
            )
            return

        lang = language
        text = get_text("address_moderation.handlers.moderation_list", language=lang).format(count=len(requests))

        await callback.message.edit_text(
            text,
            reply_markup=get_moderation_requests_keyboard(requests, page=0)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке списка заявок: {e}")
        await callback.answer(get_text("address_moderation.handlers.error_loading_data", language=language), show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_moderation_page:"))
async def show_moderation_page(callback: CallbackQuery, language: str = "ru"):
    """Показать конкретную страницу списка заявок"""
    page = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        requests = AddressService.get_pending_requests(db, limit=50)

        lang = language
        text = get_text("address_moderation.handlers.moderation_list_page", language=lang).format(page=page + 1, total=len(requests))

        await callback.message.edit_text(
            text,
            reply_markup=get_moderation_requests_keyboard(requests, page=page)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы заявок: {e}")
        await callback.answer(get_text("address_moderation.handlers.error_loading_data", language=language), show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЬНОЙ ИНФОРМАЦИИ О ЗАЯВКЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_moderation_view:"))
async def show_moderation_details(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Показать детальную информацию о заявке"""
    user_apartment_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        from uk_management_bot.database.models import UserApartment, Apartment, Building
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        result = db.execute(
            select(UserApartment)
            .options(
                joinedload(UserApartment.user),
                joinedload(UserApartment.apartment).joinedload(Apartment.building).joinedload(Building.yard)
            )
            .where(UserApartment.id == user_apartment_id)
        )
        user_apartment = result.scalar_one_or_none()

        if not user_apartment:
            lang = language
            await callback.answer(get_text("address_moderation.handlers.request_not_found", language=lang), show_alert=True)
            return

        if user_apartment.status != 'pending':
            lang = language
            await callback.answer(
                get_text("address_moderation.handlers.request_already_processed", language=lang).format(status=user_apartment.status),
                show_alert=True
            )
            return

        # Информация о пользователе
        user = user_apartment.user
        user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not user_name:
            user_name = f"ID: {user.telegram_id}"

        lang = language
        username = f"@{user.username}" if user.username else get_text("address_moderation.handlers.no_username", language=lang)
        phone = user.phone if user.phone else get_text("address_moderation.handlers.not_specified", language=lang)

        # Информация о квартире
        apartment = user_apartment.apartment
        apartment_info = get_text("address_moderation.handlers.apartment_label", language=lang).format(number=apartment.apartment_number)

        if apartment.building:
            apartment_info = f"{apartment_info}, {apartment.building.address}"
            if apartment.building.yard:
                apartment_info = f"{apartment_info} ({apartment.building.yard.name})"

        # Дополнительная информация
        requested_date = user_apartment.requested_at.strftime('%d.%m.%Y %H:%M') if user_apartment.requested_at else get_text("address_moderation.handlers.unknown", language=lang)
        is_owner_text = get_text("address_moderation.handlers.yes_owner", language=lang) if user_apartment.is_owner else get_text("address_moderation.handlers.no_resident", language=lang)

        text = get_text("address_moderation.handlers.request_details", language=lang).format(
                user_name=user_name, username=username, phone=phone,
                telegram_id=user.telegram_id, apartment_info=apartment_info,
                is_owner_text=is_owner_text, requested_date=requested_date
            )

        # Сохраняем ID заявки в состояние
        await state.update_data(user_apartment_id=user_apartment_id)
        await state.set_state(ApartmentModerationStates.viewing_request_details)

        await callback.message.edit_text(
            text,
            reply_markup=get_moderation_request_details_keyboard(user_apartment_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке информации о заявке {user_apartment_id}: {e}")
        await callback.answer(get_text("address_moderation.handlers.error_loading_data", language=language), show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПОДТВЕРЖДЕНИЕ ЗАЯВКИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_moderation_approve:"))
async def start_approve_request(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать подтверждение заявки - запросить комментарий"""
    user_apartment_id = int(callback.data.split(":")[1])

    await state.update_data(user_apartment_id=user_apartment_id)
    await state.set_state(ApartmentModerationStates.waiting_for_approval_comment)

    lang = language
    await callback.message.edit_text(
        get_text("address_moderation.handlers.approve_comment_prompt", language=lang),
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(ApartmentModerationStates.waiting_for_approval_comment))
async def process_approve_comment(message: Message, state: FSMContext, language: str = "ru"):
    """Обработка комментария и подтверждение заявки"""
    comment = None if message.text == "/skip" else message.text.strip()

    data = await state.get_data()
    user_apartment_id = data['user_apartment_id']

    db = next(get_db())
    try:
        # Сначала получаем информацию о заявке для уведомления
        from uk_management_bot.database.models import UserApartment, Apartment, Building
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        result = db.execute(
            select(UserApartment)
            .options(
                joinedload(UserApartment.user),
                joinedload(UserApartment.apartment).joinedload(Apartment.building).joinedload(Building.yard)
            )
            .where(UserApartment.id == user_apartment_id)
        )
        user_apartment = result.scalar_one_or_none()

        if not user_apartment:
            lang = language
            await message.answer(
                get_text("address_moderation.handlers.request_not_found", language=lang),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # Сохраняем данные для уведомления
        lang = language
        user_telegram_id = user_apartment.user.telegram_id
        apartment = user_apartment.apartment
        apartment_address = get_text("address_moderation.handlers.apartment_label", language=lang).format(number=apartment.apartment_number)
        if apartment.building:
            apartment_address = f"{apartment_address}, {apartment.building.address}"
            if apartment.building.yard:
                apartment_address = f"{apartment_address} ({apartment.building.yard.name})"

        # Получаем reviewer.id из базы данных (не telegram_id!)
        from uk_management_bot.database.models.user import User
        reviewer = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not reviewer:
            await message.answer(
                get_text("address_moderation.handlers.admin_not_found", language=lang),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # Теперь подтверждаем заявку
        success, error = await AddressService.approve_apartment_request(
            session=db,
            user_apartment_id=user_apartment_id,
            reviewer_id=reviewer.id,  # ИСПРАВЛЕНО: используем reviewer.id из БД, а не telegram_id
            comment=comment
        )

        if not success:
            await message.answer(
                get_text("address_moderation.handlers.approve_error", language=lang).format(error=error),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # Отправляем уведомление пользователю
        await send_approval_notification(
            user_apartment_id=user_apartment_id,
            user_telegram_id=user_telegram_id,
            apartment_address=apartment_address,
            comment=comment,
            bot=message.bot
        )

        comment_text = "\n\n<b>" + get_text("address_moderation.handlers.comment_label", language=lang) + ":</b> " + comment if comment else ""

        await message.answer(
            get_text("address_moderation.handlers.approve_success", language=lang) + comment_text,
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )

        logger.info(f"Заявка {user_apartment_id} подтверждена администратором {reviewer.telegram_id} (DB ID: {reviewer.id})")

    except Exception:
        logger.exception("approve apartment request handler failed")
        await message.answer(
            get_text("address_moderation.handlers.approve_exception", language=lang),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
    finally:
        db.close()
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# ОТКЛОНЕНИЕ ЗАЯВКИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_moderation_reject:"))
async def start_reject_request(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать отклонение заявки - запросить причину"""
    user_apartment_id = int(callback.data.split(":")[1])

    await state.update_data(user_apartment_id=user_apartment_id)
    await state.set_state(ApartmentModerationStates.waiting_for_rejection_comment)

    lang = language
    await callback.message.edit_text(
        get_text("address_moderation.handlers.reject_reason_prompt", language=lang),
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(ApartmentModerationStates.waiting_for_rejection_comment))
async def process_reject_comment(message: Message, state: FSMContext, language: str = "ru"):
    """Обработка причины и отклонение заявки"""
    comment = message.text.strip()

    if len(comment) < 3:
        lang = language
        await message.answer(
            get_text("address_moderation.handlers.reject_reason_too_short", language=lang)
        )
        return

    data = await state.get_data()
    user_apartment_id = data['user_apartment_id']

    db = next(get_db())
    try:
        # Сначала получаем информацию о заявке для уведомления
        from uk_management_bot.database.models import UserApartment, Apartment, Building
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        result = db.execute(
            select(UserApartment)
            .options(
                joinedload(UserApartment.user),
                joinedload(UserApartment.apartment).joinedload(Apartment.building).joinedload(Building.yard)
            )
            .where(UserApartment.id == user_apartment_id)
        )
        user_apartment = result.scalar_one_or_none()

        if not user_apartment:
            lang = language
            await message.answer(
                get_text("address_moderation.handlers.request_not_found", language=lang),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # Сохраняем данные для уведомления
        lang = language
        user_telegram_id = user_apartment.user.telegram_id
        apartment = user_apartment.apartment
        apartment_address = get_text("address_moderation.handlers.apartment_label", language=lang).format(number=apartment.apartment_number)
        if apartment.building:
            apartment_address = f"{apartment_address}, {apartment.building.address}"
            if apartment.building.yard:
                apartment_address = f"{apartment_address} ({apartment.building.yard.name})"

        # Получаем reviewer.id из базы данных (не telegram_id!)
        from uk_management_bot.database.models.user import User
        reviewer = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not reviewer:
            await message.answer(
                get_text("address_moderation.handlers.admin_not_found", language=lang),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # Теперь отклоняем заявку
        success, error = await AddressService.reject_apartment_request(
            session=db,
            user_apartment_id=user_apartment_id,
            reviewer_id=reviewer.id,  # ИСПРАВЛЕНО: используем reviewer.id из БД, а не telegram_id
            comment=comment
        )

        if not success:
            await message.answer(
                get_text("address_moderation.handlers.reject_error", language=lang).format(error=error),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # Отправляем уведомление пользователю
        await send_rejection_notification(
            user_apartment_id=user_apartment_id,
            user_telegram_id=user_telegram_id,
            apartment_address=apartment_address,
            comment=comment,
            bot=message.bot
        )

        await message.answer(
            get_text("address_moderation.handlers.reject_success", language=lang).format(comment=comment),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )

        logger.info(f"Заявка {user_apartment_id} отклонена администратором {reviewer.telegram_id} (DB ID: {reviewer.id})")

    except Exception:
        logger.exception("reject apartment request handler failed")
        await message.answer(
            get_text("address_moderation.handlers.reject_exception", language=lang),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
    finally:
        db.close()
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# ОТМЕНА ДЕЙСТВИЙ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "cancel_action")
async def cancel_moderation_action(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена действия модерации"""
    current_state = await state.get_state()

    if current_state:
        await state.clear()
        lang = language
        await callback.message.edit_text(get_text("address_moderation.handlers.action_cancelled", language=lang))

        # Вернуться к списку заявок
        await show_moderation_list(callback, state)
    else:
        await callback.answer(get_text("address_moderation.handlers.no_active_actions", language=language))


# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def send_approval_notification(user_apartment_id: int, user_telegram_id: int, apartment_address: str, comment: str = None, bot=None):
    """
    Отправить уведомление пользователю об одобрении заявки на квартиру

    Args:
        user_apartment_id: ID заявки (UserApartment)
        user_telegram_id: Telegram ID пользователя
        apartment_address: Адрес квартиры
        comment: Комментарий администратора (необязательно)
        bot: Bot instance
    """
    try:
        from uk_management_bot.config.localization import get_text

        # Получаем язык пользователя
        db = next(get_db())
        try:
            from uk_management_bot.database.models import User
            from sqlalchemy import select

            user = db.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            ).scalar_one_or_none()

            if not user:
                logger.warning(f"Пользователь {user_telegram_id} не найден для отправки уведомления")
                return

            lang = user.language or 'ru'

            # Формируем текст уведомления
            notification_text = get_text("address_moderation.handlers.approval_notification", language=lang).format(apartment_address=apartment_address)

            if comment:
                notification_text += "\n\n💬 <b>" + get_text("address_moderation.handlers.admin_comment_label", language=lang) + ":</b>\n" + comment

            notification_text += "\n\n" + get_text("address_moderation.handlers.can_create_requests", language=lang)

            # Отправляем уведомление
            await bot.send_message(user_telegram_id, notification_text)
            logger.info(f"✅ Уведомление об одобрении заявки {user_apartment_id} отправлено пользователю {user_telegram_id}")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления об одобрении заявки {user_apartment_id}: {e}")


async def send_rejection_notification(user_apartment_id: int, user_telegram_id: int, apartment_address: str, comment: str, bot=None):
    """
    Отправить уведомление пользователю об отклонении заявки на квартиру

    Args:
        user_apartment_id: ID заявки (UserApartment)
        user_telegram_id: Telegram ID пользователя
        apartment_address: Адрес квартиры
        comment: Причина отклонения (обязательно)
        bot: Bot instance
    """
    try:
        from uk_management_bot.config.localization import get_text

        # Получаем язык пользователя
        db = next(get_db())
        try:
            from uk_management_bot.database.models import User
            from sqlalchemy import select

            user = db.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            ).scalar_one_or_none()

            if not user:
                logger.warning(f"Пользователь {user_telegram_id} не найден для отправки уведомления")
                return

            lang = user.language or 'ru'

            # Формируем текст уведомления
            notification_text = get_text("address_moderation.handlers.rejection_notification", language=lang).format(
                apartment_address=apartment_address, comment=comment
            )

            # Отправляем уведомление
            await bot.send_message(user_telegram_id, notification_text)
            logger.info(f"✅ Уведомление об отклонении заявки {user_apartment_id} отправлено пользователю {user_telegram_id}")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления об отклонении заявки {user_apartment_id}: {e}")
