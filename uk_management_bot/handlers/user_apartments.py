"""
Обработчики для управления квартирами пользователя

Функционал:
- Просмотр всех квартир пользователя
- Запрос привязки к дополнительной квартире
- Смена основной квартиры
- Просмотр истории модерации
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from uk_management_bot.database.session import get_db
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.keyboards.address_management import (
    get_user_apartment_selection_keyboard
)

logger = logging.getLogger(__name__)
router = Router()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР КВАРТИР ПОЛЬЗОВАТЕЛЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_apartments")
async def show_my_apartments(callback: CallbackQuery, state: FSMContext):
    """Показать список квартир пользователя"""
    await state.clear()

    db = next(get_db())
    try:
        # Получаем пользователя
        from uk_management_bot.database.models import User
        from sqlalchemy import select

        user = db.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        ).scalar_one_or_none()

        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        # Получаем все квартиры пользователя (одобренные, ожидающие, отклоненные)
        user_apartments = await AddressService.get_user_apartments(
            session=db,
            user_id=user.id,
            only_approved=False
        )

        if not user_apartments:
            await callback.message.edit_text(
                "📭 <b>У вас пока нет квартир</b>\n\n"
                "Вы можете добавить квартиру, выбрав её из справочника.\n"
                "После проверки администратором вы сможете создавать заявки на этот адрес.",
                reply_markup=get_my_apartments_empty_keyboard()
            )
            return

        # Формируем текст со списком квартир
        text = "🏠 <b>Мои квартиры</b>\n\n"

        # Группируем по статусам
        approved = [ua for ua in user_apartments if ua.status == 'approved']
        pending = [ua for ua in user_apartments if ua.status == 'pending']
        rejected = [ua for ua in user_apartments if ua.status == 'rejected']

        if approved:
            text += "✅ <b>Одобренные:</b>\n"
            for ua in approved:
                apartment = ua.apartment
                address = AddressService.format_apartment_address(apartment)
                primary_mark = " ⭐" if ua.is_primary else ""
                owner_mark = " (Владелец)" if ua.is_owner else ""
                text += f"  • {address}{primary_mark}{owner_mark}\n"
            text += "\n"

        if pending:
            text += "⏳ <b>На рассмотрении:</b>\n"
            for ua in pending:
                apartment = ua.apartment
                address = AddressService.format_apartment_address(apartment)
                text += f"  • {address}\n"
            text += "\n"

        if rejected:
            text += "❌ <b>Отклоненные:</b>\n"
            for ua in rejected:
                apartment = ua.apartment
                address = AddressService.format_apartment_address(apartment)
                reason = f" ({ua.admin_comment})" if ua.admin_comment else ""
                text += f"  • {address}{reason}\n"
            text += "\n"

        text += "Выберите действие:"

        await callback.message.edit_text(
            text,
            reply_markup=get_my_apartments_keyboard(user_apartments)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке квартир пользователя {callback.from_user.id}: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ДОБАВЛЕНИЕ НОВОЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "add_apartment")
async def start_add_apartment(callback: CallbackQuery, state: FSMContext):
    """Начать процесс добавления квартиры"""
    # Используем тот же flow, что и при регистрации
    from uk_management_bot.handlers.user_apartment_selection import start_apartment_selection_for_profile

    await start_apartment_selection_for_profile(callback, state)


# ═══════════════════════════════════════════════════════════════════════════════
# СМЕНА ОСНОВНОЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("set_primary:"))
async def set_primary_apartment(callback: CallbackQuery, state: FSMContext):
    """Установить квартиру как основную"""
    user_apartment_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        # Проверяем, что квартира одобрена
        from uk_management_bot.database.models import UserApartment
        from sqlalchemy import select

        user_apartment = db.execute(
            select(UserApartment).where(UserApartment.id == user_apartment_id)
        ).scalar_one_or_none()

        if not user_apartment:
            await callback.answer("❌ Квартира не найдена", show_alert=True)
            return

        if user_apartment.user.telegram_id != callback.from_user.id:
            await callback.answer("❌ Доступ запрещен", show_alert=True)
            return

        if user_apartment.status != 'approved':
            await callback.answer("❌ Можно установить основной только одобренную квартиру", show_alert=True)
            return

        # Снимаем флаг is_primary со всех квартир пользователя
        db.execute(
            """
            UPDATE user_apartments
            SET is_primary = false
            WHERE user_id = :user_id
            """,
            {"user_id": user_apartment.user_id}
        )

        # Устанавливаем новую основную квартиру
        user_apartment.is_primary = True
        db.commit()

        await callback.answer("✅ Основная квартира изменена", show_alert=True)

        # Обновляем отображение
        await show_my_apartments(callback, state)

    except Exception as e:
        logger.error(f"Ошибка установки основной квартиры {user_apartment_id}: {e}")
        db.rollback()
        await callback.answer("❌ Ошибка обновления", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЕЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("view_apartment:"))
async def view_apartment_details(callback: CallbackQuery, state: FSMContext):
    """Показать детальную информацию о квартире"""
    user_apartment_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        from uk_management_bot.database.models import UserApartment
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        user_apartment = db.execute(
            select(UserApartment)
            .options(
                joinedload(UserApartment.user),
                joinedload(UserApartment.apartment).joinedload(UserApartment.apartment.property.mapper.class_.building).joinedload(UserApartment.apartment.property.mapper.class_.building.property.mapper.class_.yard),
                joinedload(UserApartment.reviewer)
            )
            .where(UserApartment.id == user_apartment_id)
        ).scalar_one_or_none()

        if not user_apartment:
            await callback.answer("❌ Квартира не найдена", show_alert=True)
            return

        if user_apartment.user.telegram_id != callback.from_user.id:
            await callback.answer("❌ Доступ запрещен", show_alert=True)
            return

        # Формируем детальную информацию
        apartment = user_apartment.apartment
        address = AddressService.format_apartment_address(apartment)

        status_emoji = {
            'approved': '✅',
            'pending': '⏳',
            'rejected': '❌'
        }

        status_text = {
            'approved': 'Одобрена',
            'pending': 'На рассмотрении',
            'rejected': 'Отклонена'
        }

        text = f"🏠 <b>Детали квартиры</b>\n\n"
        text += f"<b>Адрес:</b> {address}\n"
        text += f"<b>Статус:</b> {status_emoji.get(user_apartment.status, '❓')} {status_text.get(user_apartment.status, user_apartment.status)}\n"

        if user_apartment.is_primary:
            text += f"<b>Основная:</b> Да ⭐\n"

        if user_apartment.is_owner:
            text += f"<b>Владелец:</b> Да\n"

        # Детали квартиры
        if apartment.entrance or apartment.floor or apartment.rooms_count or apartment.area:
            text += f"\n<b>Характеристики:</b>\n"
            if apartment.entrance:
                text += f"  • Подъезд: {apartment.entrance}\n"
            if apartment.floor:
                text += f"  • Этаж: {apartment.floor}\n"
            if apartment.rooms_count:
                text += f"  • Комнат: {apartment.rooms_count}\n"
            if apartment.area:
                text += f"  • Площадь: {apartment.area} м²\n"

        # История модерации
        text += f"\n<b>История:</b>\n"
        text += f"  • Заявка подана: {user_apartment.requested_at.strftime('%d.%m.%Y %H:%M')}\n"

        if user_apartment.reviewed_at:
            text += f"  • Рассмотрена: {user_apartment.reviewed_at.strftime('%d.%m.%Y %H:%M')}\n"

        if user_apartment.reviewer:
            reviewer_name = user_apartment.reviewer.first_name or user_apartment.reviewer.username or "Администратор"
            text += f"  • Проверил: {reviewer_name}\n"

        if user_apartment.admin_comment:
            text += f"\n<b>Комментарий администратора:</b>\n{user_apartment.admin_comment}\n"

        await callback.message.edit_text(
            text,
            reply_markup=get_apartment_details_keyboard(user_apartment)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке деталей квартиры {user_apartment_id}: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ КЛАВИАТУР
# ═══════════════════════════════════════════════════════════════════════════════

def get_my_apartments_empty_keyboard():
    """Клавиатура для пустого списка квартир"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = [
        [InlineKeyboardButton(text="➕ Добавить квартиру", callback_data="add_apartment")],
        [InlineKeyboardButton(text="🔙 Назад к профилю", callback_data="back_to_profile")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_my_apartments_keyboard(user_apartments):
    """Клавиатура для списка квартир"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = []

    # Кнопки для квартир (только одобренные показываем для действий)
    approved = [ua for ua in user_apartments if ua.status == 'approved']

    for ua in approved[:5]:  # Максимум 5 кнопок
        apartment = ua.apartment
        address = AddressService.format_apartment_address(apartment)
        # Укорачиваем для кнопки
        button_text = address[:30] + "..." if len(address) > 30 else address
        if ua.is_primary:
            button_text = "⭐ " + button_text

        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"view_apartment:{ua.id}"
            )
        ])

    # Кнопки действий
    keyboard.append([InlineKeyboardButton(text="➕ Добавить квартиру", callback_data="add_apartment")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад к профилю", callback_data="back_to_profile")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_apartment_details_keyboard(user_apartment):
    """Клавиатура для деталей квартиры"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = []

    # Кнопка "Сделать основной" только если квартира одобрена и не основная
    if user_apartment.status == 'approved' and not user_apartment.is_primary:
        keyboard.append([
            InlineKeyboardButton(
                text="⭐ Сделать основной",
                callback_data=f"set_primary:{user_apartment.id}"
            )
        ])

    # Кнопка возврата
    keyboard.append([
        InlineKeyboardButton(text="🔙 Назад к списку", callback_data="my_apartments")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ═══════════════════════════════════════════════════════════════════════════════
# ВОЗВРАТ К ПРОФИЛЮ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery, state: FSMContext):
    """Вернуться к редактированию профиля"""
    await state.clear()

    # Импортируем обработчик профиля
    from uk_management_bot.handlers.profile_editing import handle_edit_profile_start

    # Вызываем показ меню редактирования профиля
    db = next(get_db())
    try:
        await handle_edit_profile_start(callback, state, db)
    finally:
        db.close()

# ═══════════════════════════════════════════════════════════════════════════════
# АДМИН: УПРАВЛЕНИЕ КВАРТИРАМИ ПОЛЬЗОВАТЕЛЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("admin_manage_apartments_"))
async def admin_manage_user_apartments(callback: CallbackQuery, state: FSMContext):
    """Админ: просмотр и управление квартирами пользователя"""
    await state.clear()

    try:
        user_telegram_id = int(callback.data.split("_")[-1])

        db = next(get_db())
        try:
            # Получаем пользователя
            from uk_management_bot.database.models import User
            from sqlalchemy import select

            user = db.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            ).scalar_one_or_none()

            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return

            # Получаем все квартиры пользователя
            user_apartments = await AddressService.get_user_apartments(
                session=db,
                user_id=user.id,
                only_approved=False
            )

            # Формируем текст
            text = f"🏠 <b>Управление квартирами пользователя</b>\n\n"
            text += f"👤 <b>Пользователь:</b> {user.first_name or ''} {user.last_name or ''}\n"
            text += f"📱 <b>Telegram ID:</b> {user_telegram_id}\n\n"

            if not user_apartments:
                text += "📭 <i>У пользователя пока нет квартир</i>\n\n"
            else:
                # Группируем по статусам
                approved = [ua for ua in user_apartments if ua.status == 'approved']
                pending = [ua for ua in user_apartments if ua.status == 'pending']
                rejected = [ua for ua in user_apartments if ua.status == 'rejected']

                if approved:
                    text += "✅ <b>Одобренные квартиры:</b>\n"
                    for ua in approved:
                        apartment = ua.apartment
                        address = AddressService.format_apartment_address(apartment)
                        owner_status = "👤 Владелец" if ua.is_owner else "🏘️ Жилец"
                        primary_mark = " ⭐" if ua.is_primary else ""
                        text += f"  • {address}\n"
                        text += f"    {owner_status}{primary_mark}\n"
                    text += "\n"

                if pending:
                    text += "⏳ <b>На рассмотрении:</b>\n"
                    for ua in pending:
                        apartment = ua.apartment
                        address = AddressService.format_apartment_address(apartment)
                        owner_status = "👤 Владелец" if ua.is_owner else "🏘️ Жилец"
                        text += f"  • {address} ({owner_status})\n"
                    text += "\n"

                if rejected:
                    text += "❌ <b>Отклоненные:</b>\n"
                    for ua in rejected:
                        apartment = ua.apartment
                        address = AddressService.format_apartment_address(apartment)
                        reason = f" - {ua.admin_comment}" if ua.admin_comment else ""
                        text += f"  • {address}{reason}\n"
                    text += "\n"

            text += "Выберите действие:"

            await callback.message.edit_text(
                text,
                reply_markup=get_admin_apartments_keyboard(user_apartments, user_telegram_id, user.id),
                parse_mode="HTML"
            )
            await callback.answer()

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка при загрузке квартир пользователя {callback.data}: {e}")
        import traceback
        traceback.print_exc()
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)


@router.callback_query(F.data.startswith("admin_apartment_detail_"))
async def admin_apartment_detail(callback: CallbackQuery, state: FSMContext):
    """Админ: просмотр деталей квартиры"""
    await state.clear()

    try:
        parts = callback.data.split("_")
        user_apartment_id = int(parts[-1])

        db = next(get_db())
        try:
            from uk_management_bot.database.models import UserApartment
            from sqlalchemy import select

            user_apartment = db.execute(
                select(UserApartment).where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                await callback.answer("❌ Квартира не найдена", show_alert=True)
                return

            apartment = user_apartment.apartment
            address = AddressService.format_apartment_address(apartment)

            # Формируем детальную информацию
            text = f"🏠 <b>Детали квартиры</b>\n\n"
            text += f"📍 <b>Адрес:</b> {address}\n"
            text += f"📊 <b>Статус:</b> "
            
            if user_apartment.status == 'approved':
                text += "✅ Одобрено\n"
            elif user_apartment.status == 'pending':
                text += "⏳ На рассмотрении\n"
            elif user_apartment.status == 'rejected':
                text += "❌ Отклонено\n"
            
            text += f"👤 <b>Тип проживания:</b> {'Владелец' if user_apartment.is_owner else 'Жилец'}\n"
            text += f"⭐ <b>Основная:</b> {'Да' if user_apartment.is_primary else 'Нет'}\n\n"

            if user_apartment.requested_at:
                text += f"📅 <b>Запрошено:</b> {user_apartment.requested_at.strftime('%d.%m.%Y %H:%M')}\n"
            
            if user_apartment.reviewed_at:
                text += f"📅 <b>Проверено:</b> {user_apartment.reviewed_at.strftime('%d.%m.%Y %H:%M')}\n"
            
            if user_apartment.admin_comment:
                text += f"💬 <b>Комментарий:</b> {user_apartment.admin_comment}\n"

            await callback.message.edit_text(
                text,
                reply_markup=get_admin_apartment_detail_keyboard(user_apartment),
                parse_mode="HTML"
            )
            await callback.answer()

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка при загрузке деталей квартиры: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)


@router.callback_query(F.data.startswith("admin_approve_apartment_"))
async def admin_approve_apartment(callback: CallbackQuery, state: FSMContext):
    """Админ: одобрить квартиру"""
    try:
        user_apartment_id = int(callback.data.split("_")[-1])

        db = next(get_db())
        try:
            from uk_management_bot.database.models import UserApartment, User
            from sqlalchemy import select
            from datetime import datetime

            user_apartment = db.execute(
                select(UserApartment).where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                await callback.answer("❌ Квартира не найдена", show_alert=True)
                return

            # Получаем администратора
            admin = db.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            ).scalar_one_or_none()

            if not admin:
                await callback.answer("❌ Администратор не найден", show_alert=True)
                return

            # Одобряем квартиру
            user_apartment.status = 'approved'
            user_apartment.reviewed_at = datetime.now()
            user_apartment.reviewed_by = admin.id
            user_apartment.admin_comment = f"Одобрено администратором {admin.first_name or callback.from_user.id}"

            db.commit()

            await callback.answer("✅ Квартира одобрена", show_alert=True)
            
            # Возвращаемся к деталям
            await admin_apartment_detail(callback, state)

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка одобрения квартиры: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("admin_reject_apartment_"))
async def admin_reject_apartment(callback: CallbackQuery, state: FSMContext):
    """Админ: отклонить квартиру"""
    try:
        user_apartment_id = int(callback.data.split("_")[-1])

        db = next(get_db())
        try:
            from uk_management_bot.database.models import UserApartment, User
            from sqlalchemy import select
            from datetime import datetime

            user_apartment = db.execute(
                select(UserApartment).where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                await callback.answer("❌ Квартира не найдена", show_alert=True)
                return

            # Получаем администратора
            admin = db.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            ).scalar_one_or_none()

            if not admin:
                await callback.answer("❌ Администратор не найден", show_alert=True)
                return

            # Отклоняем квартиру
            user_apartment.status = 'rejected'
            user_apartment.reviewed_at = datetime.now()
            user_apartment.reviewed_by = admin.id
            user_apartment.admin_comment = f"Отклонено администратором {admin.first_name or callback.from_user.id}"

            db.commit()

            await callback.answer("❌ Квартира отклонена", show_alert=True)
            
            # Возвращаемся к деталям
            await admin_apartment_detail(callback, state)

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка отклонения квартиры: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("admin_toggle_owner_"))
async def admin_toggle_owner_status(callback: CallbackQuery, state: FSMContext):
    """Админ: переключить статус владелец/жилец"""
    try:
        user_apartment_id = int(callback.data.split("_")[-1])

        db = next(get_db())
        try:
            from uk_management_bot.database.models import UserApartment
            from sqlalchemy import select

            user_apartment = db.execute(
                select(UserApartment).where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                await callback.answer("❌ Квартира не найдена", show_alert=True)
                return

            # Переключаем статус
            user_apartment.is_owner = not user_apartment.is_owner
            db.commit()

            new_status = "владельцем" if user_apartment.is_owner else "жильцом"
            await callback.answer(f"✅ Статус изменен на: {new_status}", show_alert=True)
            
            # Обновляем детали
            await admin_apartment_detail(callback, state)

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка переключения статуса владельца: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


def get_admin_apartments_keyboard(user_apartments, user_telegram_id, user_internal_id=None):
    """Клавиатура управления квартирами для админа"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = []

    # Кнопки для квартир
    for ua in user_apartments[:10]:  # Максимум 10
        apartment = ua.apartment
        address = AddressService.format_apartment_address(apartment)
        
        # Укорачиваем для кнопки
        button_text = address[:35] + "..." if len(address) > 35 else address
        
        # Добавляем иконки статуса
        if ua.status == 'approved':
            button_text = "✅ " + button_text
        elif ua.status == 'pending':
            button_text = "⏳ " + button_text
        elif ua.status == 'rejected':
            button_text = "❌ " + button_text

        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"admin_apartment_detail_{ua.id}"
            )
        ])

    # Кнопка возврата
    keyboard.append([InlineKeyboardButton(
        text="🔙 Назад к пользователю", 
        callback_data=f"user_mgmt_user_{user_internal_id if user_internal_id else user_telegram_id}"
    )])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_admin_apartment_detail_keyboard(user_apartment):
    """Клавиатура деталей квартиры для админа"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = []

    # Кнопки действий в зависимости от статуса
    if user_apartment.status == 'pending':
        keyboard.append([
            InlineKeyboardButton(
                text="✅ Одобрить",
                callback_data=f"admin_approve_apartment_{user_apartment.id}"
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"admin_reject_apartment_{user_apartment.id}"
            )
        ])

    # Переключение статуса владелец/жилец
    owner_text = "🏘️ Сделать жильцом" if user_apartment.is_owner else "👤 Сделать владельцем"
    keyboard.append([
        InlineKeyboardButton(
            text=owner_text,
            callback_data=f"admin_toggle_owner_{user_apartment.id}"
        )
    ])

    # Кнопка возврата
    user = user_apartment.user
    keyboard.append([
        InlineKeyboardButton(
            text="🔙 Назад к списку",
            callback_data=f"admin_manage_apartments_{user.telegram_id}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
