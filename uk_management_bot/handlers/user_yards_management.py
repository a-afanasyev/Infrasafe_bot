"""
Управление дополнительными дворами пользователей

Позволяет администраторам добавлять/удалять дополнительные дворы для жителей
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import Session

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models import User, Yard
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.utils.helpers import get_text, get_user_language

logger = logging.getLogger(__name__)
router = Router()


class UserYardsStates(StatesGroup):
    """Состояния FSM для управления дворами пользователя"""
    selecting_yard = State()  # Выбор двора для добавления


# ============= КЛАВИАТУРЫ =============

def get_user_yards_keyboard(user_telegram_id: int, lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура управления дворами пользователя

    Args:
        user_telegram_id: Telegram ID пользователя
        lang: Язык интерфейса

    Returns:
        InlineKeyboardMarkup: Клавиатура с дворами и кнопками управления
    """
    try:
        db = next(get_db())
        try:
            # Получаем основные дворы (через квартиры)
            user = db.query(User).filter(User.telegram_id == user_telegram_id).first()
            if not user:
                return InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("user_yards.user_not_found", language=lang), callback_data="noop")]
                ])

            # Дополнительные дворы
            additional_yards = AddressService.get_user_additional_yards(db, user_telegram_id)

            # Все доступные дворы
            all_yards = AddressService.get_user_available_yards(db, user_telegram_id)

            buttons = []

            # Заголовок
            buttons.append([InlineKeyboardButton(
                text=get_text("user_yards.yards_header", language=lang).format(count=len(all_yards)),
                callback_data="noop"
            )])

            # Дополнительные дворы (можно удалить)
            if additional_yards:
                buttons.append([InlineKeyboardButton(
                    text=get_text("user_yards.additional_yards_label", language=lang),
                    callback_data="noop"
                )])
                for yard in additional_yards:
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"🏘️ {yard.name}",
                            callback_data="noop"
                        ),
                        InlineKeyboardButton(
                            text=get_text("user_yards.remove_button", language=lang),
                            callback_data=f"remove_user_yard_{user_telegram_id}_{yard.id}"
                        )
                    ])

            # Кнопка добавления
            buttons.append([InlineKeyboardButton(
                text=get_text("user_yards.add_button", language=lang),
                callback_data=f"add_user_yard_{user_telegram_id}"
            )])

            # Назад - используем внутренний ID пользователя для возврата
            buttons.append([InlineKeyboardButton(
                text=get_text("common.back", language=lang),
                callback_data=f"user_mgmt_user_{user.id}"
            )])

            return InlineKeyboardMarkup(inline_keyboard=buttons)

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры дворов пользователя {user_telegram_id}: {e}")
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("common.error_short", language=lang), callback_data="noop")]
        ])


def get_yard_selection_keyboard(user_telegram_id: int, lang: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура выбора двора для добавления пользователю

    Args:
        user_telegram_id: Telegram ID пользователя
        lang: Язык интерфейса

    Returns:
        InlineKeyboardMarkup: Список доступных дворов
    """
    try:
        db = next(get_db())
        try:
            # Получаем все активные дворы
            all_yards = db.query(Yard).filter(Yard.is_active == True).order_by(Yard.name).all()

            # Получаем уже добавленные дворы
            user_yards = AddressService.get_user_available_yards(db, user_telegram_id)
            user_yard_ids = {yard.id for yard in user_yards}

            # Фильтруем дворы, которых еще нет у пользователя
            available_yards = [y for y in all_yards if y.id not in user_yard_ids]

            buttons = []

            buttons.append([InlineKeyboardButton(
                text=get_text("user_yards.select_yard_prompt", language=lang),
                callback_data="noop"
            )])

            if available_yards:
                for yard in available_yards:
                    buttons.append([InlineKeyboardButton(
                        text=f"🏘️ {yard.name}",
                        callback_data=f"user_yard_add_confirm_{user_telegram_id}_{yard.id}"
                    )])
            else:
                buttons.append([InlineKeyboardButton(
                    text=get_text("user_yards.all_yards_added", language=lang),
                    callback_data="noop"
                )])

            # Отмена
            buttons.append([InlineKeyboardButton(
                text=get_text("common.cancel", language=lang),
                callback_data=f"manage_user_yards_{user_telegram_id}"
            )])

            return InlineKeyboardMarkup(inline_keyboard=buttons)

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры выбора двора: {e}")
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("common.error_short", language=lang), callback_data="noop")]
        ])


# ============= ОБРАБОТЧИКИ =============

@router.callback_query(F.data.startswith("manage_user_yards_"))
async def handle_manage_user_yards(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Показать управление дворами пользователя"""
    lang = get_user_language(callback.from_user.id, db)

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        user_telegram_id = int(callback.data.split("_")[-1])

        target_user = db.query(User).filter(User.telegram_id == user_telegram_id).first()
        if not target_user:
            await callback.answer(get_text("user_yards.user_not_found_alert", language=lang), show_alert=True)
            return

        user_name = f"{target_user.first_name or ''} {target_user.last_name or ''}".strip() or f"ID: {user_telegram_id}"

        await callback.message.edit_text(
            get_text("user_yards.manage_yards_message", language=lang).format(
                user_name=user_name,
                user_telegram_id=user_telegram_id
            ),
            reply_markup=get_user_yards_keyboard(user_telegram_id, lang)
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка отображения управления дворами: {e}")
        await callback.answer(get_text("common.error_short", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("add_user_yard_"))
async def handle_add_user_yard(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Показать список дворов для добавления"""
    lang = get_user_language(callback.from_user.id, db)

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        user_telegram_id = int(callback.data.split("_")[-1])

        await callback.message.edit_text(
            get_text("user_yards.add_yard_message", language=lang),
            reply_markup=get_yard_selection_keyboard(user_telegram_id, lang)
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка показа списка дворов: {e}")
        await callback.answer(get_text("common.error_short", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("user_yard_add_confirm_"))
async def handle_confirm_add_yard(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Подтвердить добавление двора"""
    lang = get_user_language(callback.from_user.id, db)

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        # Формат: user_yard_add_confirm_{user_telegram_id}_{yard_id}
        parts = callback.data.split("_")
        user_telegram_id = int(parts[4])
        yard_id = int(parts[5])

        # user параметр содержит текущего администратора
        if not user:
            await callback.answer(get_text("user_yards.admin_not_found", language=lang), show_alert=True)
            return

        # Добавляем двор
        success = AddressService.add_user_yard(
            db,
            user_telegram_id,
            yard_id,
            user.id,
            f"Добавлено администратором {user.first_name or callback.from_user.id}"
        )

        if success:
            await callback.answer(get_text("user_yards.yard_added_success", language=lang), show_alert=True)
            # Возвращаемся к управлению дворами
            await handle_manage_user_yards(callback, db, roles, user)
        else:
            await callback.answer(get_text("user_yards.yard_add_failed", language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка добавления двора: {e}")
        await callback.answer(get_text("common.error_short", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("remove_user_yard_"))
async def handle_remove_user_yard(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Удалить дополнительный двор у пользователя"""
    lang = get_user_language(callback.from_user.id, db)

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        parts = callback.data.split("_")
        user_telegram_id = int(parts[3])
        yard_id = int(parts[4])

        # Удаляем двор
        success = AddressService.remove_user_yard(db, user_telegram_id, yard_id)

        if success:
            await callback.answer(get_text("user_yards.yard_removed_success", language=lang), show_alert=True)
            # Обновляем интерфейс
            await handle_manage_user_yards(callback, db, roles, user)
        else:
            await callback.answer(get_text("user_yards.yard_remove_failed", language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка удаления двора: {e}")
        await callback.answer(get_text("common.error_short", language=lang), show_alert=True)
