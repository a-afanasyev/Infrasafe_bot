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

logger = logging.getLogger(__name__)

router = Router()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА ЗАЯВОК
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_moderation_list")
async def show_moderation_list(callback: CallbackQuery, state: FSMContext):
    """Показать список заявок на модерацию"""
    await state.clear()

    db = next(get_db())
    try:
        requests = await AddressService.get_pending_requests(db, limit=50)

        if not requests:
            await callback.message.edit_text(
                "📋 <b>Заявки на модерацию</b>\n\n"
                "✅ Нет заявок на рассмотрении.\n\n"
                "Все заявки обработаны!",
                reply_markup=get_moderation_requests_keyboard([], page=0)
            )
            return

        text = f"📋 <b>Заявки на модерацию</b>\n\n" \
               f"🔔 Заявок на рассмотрении: {len(requests)}\n\n" \
               f"Выберите заявку для просмотра:"

        await callback.message.edit_text(
            text,
            reply_markup=get_moderation_requests_keyboard(requests, page=0)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке списка заявок: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_moderation_page:"))
async def show_moderation_page(callback: CallbackQuery):
    """Показать конкретную страницу списка заявок"""
    page = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        requests = await AddressService.get_pending_requests(db, limit=50)

        text = f"📋 <b>Заявки на модерацию</b> (страница {page + 1})\n\n" \
               f"Всего заявок: {len(requests)}\n\n" \
               f"Выберите заявку для просмотра:"

        await callback.message.edit_text(
            text,
            reply_markup=get_moderation_requests_keyboard(requests, page=page)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы заявок: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЬНОЙ ИНФОРМАЦИИ О ЗАЯВКЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_moderation_view:"))
async def show_moderation_details(callback: CallbackQuery, state: FSMContext):
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
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return

        if user_apartment.status != 'pending':
            await callback.answer(
                f"⚠️ Заявка уже обработана (статус: {user_apartment.status})",
                show_alert=True
            )
            return

        # Информация о пользователе
        user = user_apartment.user
        user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not user_name:
            user_name = f"ID: {user.telegram_id}"

        username = f"@{user.username}" if user.username else "Нет username"
        phone = user.phone if user.phone else "Не указан"

        # Информация о квартире
        apartment = user_apartment.apartment
        apartment_info = f"Квартира {apartment.apartment_number}"

        if apartment.building:
            apartment_info = f"{apartment_info}, {apartment.building.address}"
            if apartment.building.yard:
                apartment_info = f"{apartment_info} ({apartment.building.yard.name})"

        # Дополнительная информация
        requested_date = user_apartment.requested_at.strftime('%d.%m.%Y %H:%M') if user_apartment.requested_at else "Неизвестно"
        is_owner_text = "Да (владелец)" if user_apartment.is_owner else "Нет (проживающий)"

        text = f"📋 <b>Заявка на квартиру</b>\n\n" \
               f"<b>👤 Пользователь:</b>\n" \
               f"• Имя: {user_name}\n" \
               f"• Username: {username}\n" \
               f"• Телефон: {phone}\n" \
               f"• Telegram ID: <code>{user.telegram_id}</code>\n\n" \
               f"<b>🏠 Квартира:</b>\n" \
               f"{apartment_info}\n\n" \
               f"<b>ℹ️ Дополнительно:</b>\n" \
               f"• Владелец: {is_owner_text}\n" \
               f"• Дата заявки: {requested_date}\n\n" \
               f"<b>Что делать?</b>\n" \
               f"✅ Подтвердить - пользователь получит доступ к квартире\n" \
               f"❌ Отклонить - заявка будет отклонена"

        # Сохраняем ID заявки в состояние
        await state.update_data(user_apartment_id=user_apartment_id)
        await state.set_state(ApartmentModerationStates.viewing_request_details)

        await callback.message.edit_text(
            text,
            reply_markup=get_moderation_request_details_keyboard(user_apartment_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке информации о заявке {user_apartment_id}: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПОДТВЕРЖДЕНИЕ ЗАЯВКИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_moderation_approve:"))
async def start_approve_request(callback: CallbackQuery, state: FSMContext):
    """Начать подтверждение заявки - запросить комментарий"""
    user_apartment_id = int(callback.data.split(":")[1])

    await state.update_data(user_apartment_id=user_apartment_id)
    await state.set_state(ApartmentModerationStates.waiting_for_approval_comment)

    await callback.message.edit_text(
        "✅ <b>Подтверждение заявки</b>\n\n"
        "Введите комментарий для пользователя (необязательно):\n\n"
        "Например:\n"
        "• \"Добро пожаловать!\"\n"
        "• \"Документы проверены\"\n\n"
        "Или отправьте <code>/skip</code> чтобы подтвердить без комментария.",
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(ApartmentModerationStates.waiting_for_approval_comment))
async def process_approve_comment(message: Message, state: FSMContext):
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
            await message.answer(
                "❌ Заявка не найдена",
                reply_markup=get_main_keyboard_for_role("manager", ["manager"])
            )
            await state.clear()
            return

        # Сохраняем данные для уведомления
        user_telegram_id = user_apartment.user.telegram_id
        apartment = user_apartment.apartment
        apartment_address = f"Квартира {apartment.apartment_number}"
        if apartment.building:
            apartment_address = f"{apartment_address}, {apartment.building.address}"
            if apartment.building.yard:
                apartment_address = f"{apartment_address} ({apartment.building.yard.name})"

        # Получаем reviewer.id из базы данных (не telegram_id!)
        from uk_management_bot.database.models.user import User
        reviewer = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not reviewer:
            await message.answer(
                "❌ Ошибка: администратор не найден",
                reply_markup=get_main_keyboard_for_role("manager", ["manager"])
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
                f"❌ Ошибка подтверждения заявки:\n{error}",
                reply_markup=get_main_keyboard_for_role("manager", ["manager"])
            )
            await state.clear()
            return

        # Отправляем уведомление пользователю
        await send_approval_notification(
            user_apartment_id=user_apartment_id,
            user_telegram_id=user_telegram_id,
            apartment_address=apartment_address,
            comment=comment
        )

        comment_text = f"\n\n<b>Комментарий:</b> {comment}" if comment else ""

        await message.answer(
            f"✅ <b>Заявка успешно подтверждена!</b>\n\n"
            f"Пользователь получит уведомление о подтверждении."
            f"{comment_text}",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )

        logger.info(f"Заявка {user_apartment_id} подтверждена администратором {reviewer.telegram_id} (DB ID: {reviewer.id})")

    except Exception as e:
        logger.error(f"Ошибка при подтверждении заявки: {e}")
        await message.answer(
            f"❌ Ошибка при подтверждении заявки: {str(e)}",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
    finally:
        db.close()
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# ОТКЛОНЕНИЕ ЗАЯВКИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_moderation_reject:"))
async def start_reject_request(callback: CallbackQuery, state: FSMContext):
    """Начать отклонение заявки - запросить причину"""
    user_apartment_id = int(callback.data.split(":")[1])

    await state.update_data(user_apartment_id=user_apartment_id)
    await state.set_state(ApartmentModerationStates.waiting_for_rejection_comment)

    await callback.message.edit_text(
        "❌ <b>Отклонение заявки</b>\n\n"
        "Введите причину отклонения для пользователя:\n\n"
        "Например:\n"
        "• \"Адрес не подтвержден\"\n"
        "• \"Неверные документы\"\n"
        "• \"Обратитесь в офис для уточнения\"",
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(ApartmentModerationStates.waiting_for_rejection_comment))
async def process_reject_comment(message: Message, state: FSMContext):
    """Обработка причины и отклонение заявки"""
    comment = message.text.strip()

    if len(comment) < 3:
        await message.answer(
            "❌ Причина отклонения должна содержать минимум 3 символа.\n\n"
            "Попробуйте еще раз:"
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
            await message.answer(
                "❌ Заявка не найдена",
                reply_markup=get_main_keyboard_for_role("manager", ["manager"])
            )
            await state.clear()
            return

        # Сохраняем данные для уведомления
        user_telegram_id = user_apartment.user.telegram_id
        apartment = user_apartment.apartment
        apartment_address = f"Квартира {apartment.apartment_number}"
        if apartment.building:
            apartment_address = f"{apartment_address}, {apartment.building.address}"
            if apartment.building.yard:
                apartment_address = f"{apartment_address} ({apartment.building.yard.name})"

        # Получаем reviewer.id из базы данных (не telegram_id!)
        from uk_management_bot.database.models.user import User
        reviewer = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not reviewer:
            await message.answer(
                "❌ Ошибка: администратор не найден",
                reply_markup=get_main_keyboard_for_role("manager", ["manager"])
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
                f"❌ Ошибка отклонения заявки:\n{error}",
                reply_markup=get_main_keyboard_for_role("manager", ["manager"])
            )
            await state.clear()
            return

        # Отправляем уведомление пользователю
        await send_rejection_notification(
            user_apartment_id=user_apartment_id,
            user_telegram_id=user_telegram_id,
            apartment_address=apartment_address,
            comment=comment
        )

        await message.answer(
            f"✅ <b>Заявка успешно отклонена</b>\n\n"
            f"<b>Причина:</b> {comment}\n\n"
            f"Пользователь получит уведомление об отклонении.",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )

        logger.info(f"Заявка {user_apartment_id} отклонена администратором {reviewer.telegram_id} (DB ID: {reviewer.id})")

    except Exception as e:
        logger.error(f"Ошибка при отклонении заявки: {e}")
        await message.answer(
            f"❌ Ошибка при отклонении заявки: {str(e)}",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
    finally:
        db.close()
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# ОТМЕНА ДЕЙСТВИЙ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "cancel_action")
async def cancel_moderation_action(callback: CallbackQuery, state: FSMContext):
    """Отмена действия модерации"""
    current_state = await state.get_state()

    if current_state:
        await state.clear()
        await callback.message.edit_text("❌ Действие отменено")

        # Вернуться к списку заявок
        await show_moderation_list(callback, state)
    else:
        await callback.answer("Нет активных действий")


# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def send_approval_notification(user_apartment_id: int, user_telegram_id: int, apartment_address: str, comment: str = None):
    """
    Отправить уведомление пользователю об одобрении заявки на квартиру

    Args:
        user_apartment_id: ID заявки (UserApartment)
        user_telegram_id: Telegram ID пользователя
        apartment_address: Адрес квартиры
        comment: Комментарий администратора (необязательно)
    """
    try:
        from aiogram import Bot
        from uk_management_bot.config.localization import get_text

        bot = Bot.get_current()

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
            notification_text = (
                f"✅ <b>Ваша заявка на квартиру одобрена!</b>\n\n"
                f"🏠 <b>Квартира:</b> {apartment_address}\n"
            )

            if comment:
                notification_text += f"\n💬 <b>Комментарий администратора:</b>\n{comment}\n"

            notification_text += (
                f"\nТеперь вы можете создавать заявки с этим адресом."
            )

            # Отправляем уведомление
            await bot.send_message(user_telegram_id, notification_text)
            logger.info(f"✅ Уведомление об одобрении заявки {user_apartment_id} отправлено пользователю {user_telegram_id}")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления об одобрении заявки {user_apartment_id}: {e}")


async def send_rejection_notification(user_apartment_id: int, user_telegram_id: int, apartment_address: str, comment: str):
    """
    Отправить уведомление пользователю об отклонении заявки на квартиру

    Args:
        user_apartment_id: ID заявки (UserApartment)
        user_telegram_id: Telegram ID пользователя
        apartment_address: Адрес квартиры
        comment: Причина отклонения (обязательно)
    """
    try:
        from aiogram import Bot
        from uk_management_bot.config.localization import get_text

        bot = Bot.get_current()

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
            notification_text = (
                f"❌ <b>Ваша заявка на квартиру отклонена</b>\n\n"
                f"🏠 <b>Квартира:</b> {apartment_address}\n\n"
                f"📝 <b>Причина отклонения:</b>\n{comment}\n\n"
                f"Для уточнения информации обратитесь к администратору."
            )

            # Отправляем уведомление
            await bot.send_message(user_telegram_id, notification_text)
            logger.info(f"✅ Уведомление об отклонении заявки {user_apartment_id} отправлено пользователю {user_telegram_id}")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления об отклонении заявки {user_apartment_id}: {e}")
