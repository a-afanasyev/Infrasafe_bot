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
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import session_scope
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)
router = Router()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР КВАРТИР ПОЛЬЗОВАТЕЛЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_apartments")
async def show_my_apartments(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Показать список квартир пользователя"""
    await state.clear()
    lang = language

    try:
        with session_scope() as db:
            # Получаем пользователя
            from uk_management_bot.database.models import User
            from sqlalchemy import select

            user = db.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            ).scalar_one_or_none()

            if not user:
                await callback.answer(get_text("user_apartments.user_not_found", language=lang), show_alert=True)
                return

            # Получаем все квартиры пользователя (одобренные, ожидающие, отклоненные)
            user_apartments = AddressService.get_user_apartments(
                session=db,
                user_id=user.id,
                only_approved=False
            )

            if not user_apartments:
                await callback.message.edit_text(
                    get_text("user_apartments.no_apartments", language=lang),
                    reply_markup=get_my_apartments_empty_keyboard(lang)
                )
                return

            # Формируем текст со списком квартир
            text = get_text("user_apartments.my_apartments_title", language=lang) + "\n\n"

            # Группируем по статусам
            approved = [ua for ua in user_apartments if ua.status == 'approved']
            pending = [ua for ua in user_apartments if ua.status == 'pending']
            rejected = [ua for ua in user_apartments if ua.status == 'rejected']

            if approved:
                text += get_text("user_apartments.approved_header", language=lang) + "\n"
                for ua in approved:
                    apartment = ua.apartment
                    address = AddressService.format_apartment_address(apartment)
                    primary_mark = " ⭐" if ua.is_primary else ""
                    owner_mark = " " + get_text("user_apartments.owner_label", language=lang) if ua.is_owner else ""
                    text += f"  • {address}{primary_mark}{owner_mark}\n"
                text += "\n"

            if pending:
                text += get_text("user_apartments.pending_header", language=lang) + "\n"
                for ua in pending:
                    apartment = ua.apartment
                    address = AddressService.format_apartment_address(apartment)
                    text += f"  • {address}\n"
                text += "\n"

            if rejected:
                text += get_text("user_apartments.rejected_header", language=lang) + "\n"
                for ua in rejected:
                    apartment = ua.apartment
                    address = AddressService.format_apartment_address(apartment)
                    reason = f" ({ua.admin_comment})" if ua.admin_comment else ""
                    text += f"  • {address}{reason}\n"
                text += "\n"

            text += get_text("user_apartments.choose_action", language=lang)

            await callback.message.edit_text(
                text,
                reply_markup=get_my_apartments_keyboard(user_apartments, lang)
            )

    except Exception as e:
        logger.error(f"Ошибка при загрузке квартир пользователя {callback.from_user.id}: {e}")
        await callback.answer(get_text("user_apartments.error_loading", language=lang), show_alert=True)


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
async def set_primary_apartment(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Установить квартиру как основную"""
    user_apartment_id = int(callback.data.split(":")[1])
    lang = language

    with session_scope() as db:
        try:
            # Проверяем, что квартира одобрена
            from uk_management_bot.database.models import UserApartment
            from sqlalchemy import select

            user_apartment = db.execute(
                select(UserApartment).where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                await callback.answer(get_text("user_apartments.apartment_not_found", language=lang), show_alert=True)
                return

            if user_apartment.user.telegram_id != callback.from_user.id:
                await callback.answer(get_text("user_apartments.access_denied", language=lang), show_alert=True)
                return

            if user_apartment.status != 'approved':
                await callback.answer(get_text("user_apartments.only_approved_primary", language=lang), show_alert=True)
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

            await callback.answer(get_text("user_apartments.primary_changed", language=lang), show_alert=True)

            # Обновляем отображение
            await show_my_apartments(callback, state)

        except Exception as e:
            logger.error(f"Ошибка установки основной квартиры {user_apartment_id}: {e}")
            db.rollback()
            await callback.answer(get_text("user_apartments.error_update", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЕЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("view_apartment:"))
async def view_apartment_details(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Показать детальную информацию о квартире"""
    user_apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        with session_scope() as db:
            # BUG-BOT-027: исходный joinedload(UserApartment.apartment.property.mapper.class_.building...)
            # был некорректным SQLAlchemy-выражением и валил handler в except → юзер видел
            # generic "ошибка загрузки данных". Заменено на корректные nested joinedload.
            from uk_management_bot.database.models import UserApartment, Apartment, Building
            from sqlalchemy import select
            from sqlalchemy.orm import joinedload

            user_apartment = db.execute(
                select(UserApartment)
                .options(
                    joinedload(UserApartment.user),
                    joinedload(UserApartment.apartment)
                        .joinedload(Apartment.building)
                        .joinedload(Building.yard),
                    joinedload(UserApartment.reviewer),
                )
                .where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                # BUG-BOT-027: контекст-specific сообщение, а не generic "Заявка не найдена"
                await callback.answer(get_text("user_apartments.apartment_not_found", language=lang), show_alert=True)
                return

            if user_apartment.user.telegram_id != callback.from_user.id:
                await callback.answer(get_text("user_apartments.access_denied", language=lang), show_alert=True)
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
                'approved': get_text("user_apartments.status_approved", language=lang),
                'pending': get_text("user_apartments.status_pending", language=lang),
                'rejected': get_text("user_apartments.status_rejected", language=lang)
            }

            text = get_text("user_apartments.details_title", language=lang) + "\n\n"
            text += get_text("user_apartments.address_label", language=lang).format(address=address) + "\n"
            text += get_text("user_apartments.status_label", language=lang).format(
                emoji=status_emoji.get(user_apartment.status, '❓'),
                status=status_text.get(user_apartment.status, user_apartment.status)
            ) + "\n"

            if user_apartment.is_primary:
                text += get_text("user_apartments.is_primary_yes", language=lang) + "\n"

            if user_apartment.is_owner:
                text += get_text("user_apartments.is_owner_yes", language=lang) + "\n"

            # Детали квартиры
            if apartment.entrance or apartment.floor or apartment.rooms_count or apartment.area:
                text += "\n" + get_text("user_apartments.characteristics_header", language=lang) + "\n"
                if apartment.entrance:
                    text += get_text("user_apartments.entrance_label", language=lang).format(value=apartment.entrance) + "\n"
                if apartment.floor:
                    text += get_text("user_apartments.floor_label", language=lang).format(value=apartment.floor) + "\n"
                if apartment.rooms_count:
                    text += get_text("user_apartments.rooms_label", language=lang).format(value=apartment.rooms_count) + "\n"
                if apartment.area:
                    text += get_text("user_apartments.area_label", language=lang).format(value=apartment.area) + "\n"

            # История модерации
            text += "\n" + get_text("user_apartments.history_header", language=lang) + "\n"
            text += get_text("user_apartments.requested_at_label", language=lang).format(
                date=user_apartment.requested_at.strftime('%d.%m.%Y %H:%M')
            ) + "\n"

            if user_apartment.reviewed_at:
                text += get_text("user_apartments.reviewed_at_label", language=lang).format(
                    date=user_apartment.reviewed_at.strftime('%d.%m.%Y %H:%M')
                ) + "\n"

            if user_apartment.reviewer:
                reviewer_name = user_apartment.reviewer.first_name or user_apartment.reviewer.username or get_text("user_apartments.admin_default_name", language=lang)
                text += get_text("user_apartments.reviewed_by_label", language=lang).format(name=reviewer_name) + "\n"

            if user_apartment.admin_comment:
                text += "\n" + get_text("user_apartments.admin_comment_label", language=lang).format(comment=user_apartment.admin_comment) + "\n"

            await callback.message.edit_text(
                text,
                reply_markup=get_apartment_details_keyboard(user_apartment, lang)
            )

    except Exception as e:
        logger.error(f"Ошибка при загрузке деталей квартиры {user_apartment_id}: {e}")
        await callback.answer(get_text("user_apartments.error_loading", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ КЛАВИАТУР
# ═══════════════════════════════════════════════════════════════════════════════

def get_my_apartments_empty_keyboard(lang: str = "ru"):
    """Клавиатура для пустого списка квартир"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = [
        [InlineKeyboardButton(text=get_text("user_apartments.btn_add_apartment", language=lang), callback_data="add_apartment")],
        [InlineKeyboardButton(text=get_text("user_apartments.btn_back_to_profile", language=lang), callback_data="back_to_profile")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_my_apartments_keyboard(user_apartments, lang: str = "ru"):
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
    keyboard.append([InlineKeyboardButton(text=get_text("user_apartments.btn_add_apartment", language=lang), callback_data="add_apartment")])
    keyboard.append([InlineKeyboardButton(text=get_text("user_apartments.btn_back_to_profile", language=lang), callback_data="back_to_profile")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_apartment_details_keyboard(user_apartment, lang: str = "ru"):
    """Клавиатура для деталей квартиры"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = []

    # Кнопка "Сделать основной" только если квартира одобрена и не основная
    if user_apartment.status == 'approved' and not user_apartment.is_primary:
        keyboard.append([
            InlineKeyboardButton(
                text=get_text("user_apartments.btn_set_primary", language=lang),
                callback_data=f"set_primary:{user_apartment.id}"
            )
        ])

    # Кнопка возврата
    keyboard.append([
        InlineKeyboardButton(text=get_text("user_apartments.btn_back_to_list", language=lang), callback_data="my_apartments")
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
    with session_scope() as db:
        await handle_edit_profile_start(callback, state, db)

# ═══════════════════════════════════════════════════════════════════════════════
# АДМИН: УПРАВЛЕНИЕ КВАРТИРАМИ ПОЛЬЗОВАТЕЛЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("admin_manage_apartments_"))
async def admin_manage_user_apartments(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Админ: просмотр и управление квартирами пользователя"""
    await state.clear()
    lang = language

    try:
        user_telegram_id = int(callback.data.split("_")[-1])

        with session_scope() as db:
            # Получаем пользователя
            from uk_management_bot.database.models import User
            from sqlalchemy import select

            user = db.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            ).scalar_one_or_none()

            if not user:
                await callback.answer(get_text("user_apartments.user_not_found", language=lang), show_alert=True)
                return

            # Получаем все квартиры пользователя
            user_apartments = AddressService.get_user_apartments(
                session=db,
                user_id=user.id,
                only_approved=False
            )

            # Формируем текст
            text = get_text("user_apartments.admin_manage_title", language=lang) + "\n\n"
            text += get_text("user_apartments.admin_user_info", language=lang).format(
                first_name=user.first_name or '',
                last_name=user.last_name or ''
            ) + "\n"
            text += get_text("user_apartments.admin_telegram_id", language=lang).format(telegram_id=user_telegram_id) + "\n\n"

            if not user_apartments:
                text += get_text("user_apartments.admin_no_apartments", language=lang) + "\n\n"
            else:
                # Группируем по статусам
                approved = [ua for ua in user_apartments if ua.status == 'approved']
                pending = [ua for ua in user_apartments if ua.status == 'pending']
                rejected = [ua for ua in user_apartments if ua.status == 'rejected']

                if approved:
                    text += get_text("user_apartments.admin_approved_header", language=lang) + "\n"
                    for ua in approved:
                        apartment = ua.apartment
                        address = AddressService.format_apartment_address(apartment)
                        owner_status = get_text("user_apartments.owner_status_owner", language=lang) if ua.is_owner else get_text("user_apartments.owner_status_resident", language=lang)
                        primary_mark = " ⭐" if ua.is_primary else ""
                        text += f"  • {address}\n"
                        text += f"    {owner_status}{primary_mark}\n"
                    text += "\n"

                if pending:
                    text += get_text("user_apartments.pending_header", language=lang) + "\n"
                    for ua in pending:
                        apartment = ua.apartment
                        address = AddressService.format_apartment_address(apartment)
                        owner_status = get_text("user_apartments.owner_status_owner", language=lang) if ua.is_owner else get_text("user_apartments.owner_status_resident", language=lang)
                        text += f"  • {address} ({owner_status})\n"
                    text += "\n"

                if rejected:
                    text += get_text("user_apartments.rejected_header", language=lang) + "\n"
                    for ua in rejected:
                        apartment = ua.apartment
                        address = AddressService.format_apartment_address(apartment)
                        reason = f" - {ua.admin_comment}" if ua.admin_comment else ""
                        text += f"  • {address}{reason}\n"
                    text += "\n"

            text += get_text("user_apartments.choose_action", language=lang)

            await callback.message.edit_text(
                text,
                reply_markup=get_admin_apartments_keyboard(user_apartments, user_telegram_id, user.id, lang),
                parse_mode="HTML"
            )
            await callback.answer()


    except Exception as e:
        logger.error(f"Ошибка при загрузке квартир пользователя {callback.data}: {e}")
        import traceback
        traceback.print_exc()
        await callback.answer(get_text("user_apartments.error_loading", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("admin_apartment_detail_"))
async def admin_apartment_detail(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Админ: просмотр деталей квартиры"""
    await state.clear()
    lang = language

    try:
        parts = callback.data.split("_")
        user_apartment_id = int(parts[-1])

        with session_scope() as db:
            from uk_management_bot.database.models import UserApartment
            from sqlalchemy import select

            user_apartment = db.execute(
                select(UserApartment).where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                await callback.answer(get_text("user_apartments.apartment_not_found", language=lang), show_alert=True)
                return

            apartment = user_apartment.apartment
            address = AddressService.format_apartment_address(apartment)

            # Формируем детальную информацию
            text = get_text("user_apartments.details_title", language=lang) + "\n\n"
            text += get_text("user_apartments.admin_detail_address", language=lang).format(address=address) + "\n"
            text += get_text("user_apartments.admin_detail_status_label", language=lang) + " "

            if user_apartment.status == 'approved':
                text += get_text("user_apartments.admin_status_approved", language=lang) + "\n"
            elif user_apartment.status == 'pending':
                text += get_text("user_apartments.admin_status_pending", language=lang) + "\n"
            elif user_apartment.status == 'rejected':
                text += get_text("user_apartments.admin_status_rejected", language=lang) + "\n"

            residence_type = get_text("user_apartments.residence_owner", language=lang) if user_apartment.is_owner else get_text("user_apartments.residence_resident", language=lang)
            text += get_text("user_apartments.admin_detail_residence", language=lang).format(type=residence_type) + "\n"

            is_primary_text = get_text("user_apartments.yes", language=lang) if user_apartment.is_primary else get_text("user_apartments.no", language=lang)
            text += get_text("user_apartments.admin_detail_primary", language=lang).format(value=is_primary_text) + "\n\n"

            if user_apartment.requested_at:
                text += get_text("user_apartments.admin_detail_requested", language=lang).format(
                    date=user_apartment.requested_at.strftime('%d.%m.%Y %H:%M')
                ) + "\n"

            if user_apartment.reviewed_at:
                text += get_text("user_apartments.admin_detail_reviewed", language=lang).format(
                    date=user_apartment.reviewed_at.strftime('%d.%m.%Y %H:%M')
                ) + "\n"

            if user_apartment.admin_comment:
                text += get_text("user_apartments.admin_detail_comment", language=lang).format(
                    comment=user_apartment.admin_comment
                ) + "\n"

            await callback.message.edit_text(
                text,
                reply_markup=get_admin_apartment_detail_keyboard(user_apartment, lang),
                parse_mode="HTML"
            )
            await callback.answer()


    except Exception as e:
        logger.error(f"Ошибка при загрузке деталей квартиры: {e}")
        await callback.answer(get_text("user_apartments.error_loading", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("admin_approve_apartment_"))
async def admin_approve_apartment(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Админ: одобрить квартиру"""
    lang = language
    try:
        user_apartment_id = int(callback.data.split("_")[-1])

        with session_scope() as db:
            from uk_management_bot.database.models import UserApartment, User
            from sqlalchemy import select
            from datetime import datetime, timezone

            user_apartment = db.execute(
                select(UserApartment).where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                await callback.answer(get_text("user_apartments.apartment_not_found", language=lang), show_alert=True)
                return

            # Получаем администратора
            admin = db.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            ).scalar_one_or_none()

            if not admin:
                await callback.answer(get_text("user_apartments.admin_not_found", language=lang), show_alert=True)
                return

            # Одобряем квартиру
            user_apartment.status = 'approved'
            user_apartment.reviewed_at = datetime.now(timezone.utc)
            user_apartment.reviewed_by = admin.id
            user_apartment.admin_comment = f"Одобрено администратором {admin.first_name or callback.from_user.id}"

            db.commit()

            await callback.answer(get_text("user_apartments.apartment_approved", language=lang), show_alert=True)

            # Возвращаемся к деталям
            await admin_apartment_detail(callback, state)


    except Exception as e:
        logger.error(f"Ошибка одобрения квартиры: {e}")
        await callback.answer(get_text("user_apartments.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("admin_reject_apartment_"))
async def admin_reject_apartment(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Админ: отклонить квартиру"""
    lang = language
    try:
        user_apartment_id = int(callback.data.split("_")[-1])

        with session_scope() as db:
            from uk_management_bot.database.models import UserApartment, User
            from sqlalchemy import select
            from datetime import datetime, timezone

            user_apartment = db.execute(
                select(UserApartment).where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                await callback.answer(get_text("user_apartments.apartment_not_found", language=lang), show_alert=True)
                return

            # Получаем администратора
            admin = db.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            ).scalar_one_or_none()

            if not admin:
                await callback.answer(get_text("user_apartments.admin_not_found", language=lang), show_alert=True)
                return

            # Отклоняем квартиру
            user_apartment.status = 'rejected'
            user_apartment.reviewed_at = datetime.now(timezone.utc)
            user_apartment.reviewed_by = admin.id
            user_apartment.admin_comment = f"Отклонено администратором {admin.first_name or callback.from_user.id}"

            db.commit()

            await callback.answer(get_text("user_apartments.apartment_rejected", language=lang), show_alert=True)

            # Возвращаемся к деталям
            await admin_apartment_detail(callback, state)


    except Exception as e:
        logger.error(f"Ошибка отклонения квартиры: {e}")
        await callback.answer(get_text("user_apartments.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("admin_toggle_owner_"))
async def admin_toggle_owner_status(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Админ: переключить статус владелец/жилец"""
    lang = language
    try:
        user_apartment_id = int(callback.data.split("_")[-1])

        with session_scope() as db:
            from uk_management_bot.database.models import UserApartment
            from sqlalchemy import select

            user_apartment = db.execute(
                select(UserApartment).where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                await callback.answer(get_text("user_apartments.apartment_not_found", language=lang), show_alert=True)
                return

            # Переключаем статус
            user_apartment.is_owner = not user_apartment.is_owner
            db.commit()

            new_status = get_text("user_apartments.toggle_to_owner", language=lang) if user_apartment.is_owner else get_text("user_apartments.toggle_to_resident", language=lang)
            await callback.answer(get_text("user_apartments.status_changed_to", language=lang).format(status=new_status), show_alert=True)

            # Обновляем детали
            await admin_apartment_detail(callback, state)


    except Exception as e:
        logger.error(f"Ошибка переключения статуса владельца: {e}")
        await callback.answer(get_text("user_apartments.error_generic", language=lang), show_alert=True)


def get_admin_apartments_keyboard(user_apartments, user_telegram_id, user_internal_id=None, lang: str = "ru"):
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
        text=get_text("user_apartments.btn_back_to_user", language=lang),
        callback_data=f"user_mgmt_user_{user_internal_id if user_internal_id else user_telegram_id}"
    )])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_admin_apartment_detail_keyboard(user_apartment, lang: str = "ru"):
    """Клавиатура деталей квартиры для админа"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = []

    # Кнопки действий в зависимости от статуса
    if user_apartment.status == 'pending':
        keyboard.append([
            InlineKeyboardButton(
                text=get_text("user_apartments.btn_approve", language=lang),
                callback_data=f"admin_approve_apartment_{user_apartment.id}"
            ),
            InlineKeyboardButton(
                text=get_text("user_apartments.btn_reject", language=lang),
                callback_data=f"admin_reject_apartment_{user_apartment.id}"
            )
        ])

    # Переключение статуса владелец/жилец
    owner_text = get_text("user_apartments.btn_make_resident", language=lang) if user_apartment.is_owner else get_text("user_apartments.btn_make_owner", language=lang)
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
            text=get_text("user_apartments.btn_back_to_list", language=lang),
            callback_data=f"admin_manage_apartments_{user.telegram_id}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
