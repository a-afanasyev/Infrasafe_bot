"""
Управление дополнительными дворами пользователей

Позволяет администраторам добавлять/удалять дополнительные дворы для жителей
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import Session

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models import User, Yard
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)
router = Router()


class UserYardsStates(StatesGroup):
    """Состояния FSM для управления дворами пользователя"""
    selecting_yard = State()  # Выбор двора для добавления


# ============= КЛАВИАТУРЫ =============

def get_user_yards_keyboard(user_telegram_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура управления дворами пользователя

    Args:
        user_telegram_id: Telegram ID пользователя

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
                    [InlineKeyboardButton(text="❌ Пользователь не найден", callback_data="noop")]
                ])

            # Дополнительные дворы
            additional_yards = AddressService.get_user_additional_yards(db, user_telegram_id)

            # Все доступные дворы
            all_yards = AddressService.get_user_available_yards(db, user_telegram_id)

            buttons = []

            # Заголовок
            buttons.append([InlineKeyboardButton(
                text=f"🏘️ Дворы пользователя ({len(all_yards)})",
                callback_data="noop"
            )])

            # Дополнительные дворы (можно удалить)
            if additional_yards:
                buttons.append([InlineKeyboardButton(
                    text="➕ Дополнительные дворы:",
                    callback_data="noop"
                )])
                for yard in additional_yards:
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"🏘️ {yard.name}",
                            callback_data="noop"
                        ),
                        InlineKeyboardButton(
                            text="❌ Удалить",
                            callback_data=f"remove_user_yard_{user_telegram_id}_{yard.id}"
                        )
                    ])

            # Кнопка добавления
            buttons.append([InlineKeyboardButton(
                text="➕ Добавить двор",
                callback_data=f"add_user_yard_{user_telegram_id}"
            )])

            # Назад - используем внутренний ID пользователя для возврата
            buttons.append([InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"user_mgmt_user_{user.id}"
            )])

            return InlineKeyboardMarkup(inline_keyboard=buttons)

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры дворов пользователя {user_telegram_id}: {e}")
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Ошибка", callback_data="noop")]
        ])


def get_yard_selection_keyboard(user_telegram_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора двора для добавления пользователю

    Args:
        user_telegram_id: Telegram ID пользователя

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
                text="📍 Выберите двор для добавления:",
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
                    text="ℹ️ Все дворы уже добавлены",
                    callback_data="noop"
                )])

            # Отмена
            buttons.append([InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"manage_user_yards_{user_telegram_id}"
            )])

            return InlineKeyboardMarkup(inline_keyboard=buttons)

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры выбора двора: {e}")
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Ошибка", callback_data="noop")]
        ])


# ============= ОБРАБОТЧИКИ =============

@router.callback_query(F.data.startswith("manage_user_yards_"))
async def handle_manage_user_yards(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Показать управление дворами пользователя"""
    lang = callback.from_user.language_code or 'ru'

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
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        user_name = f"{target_user.first_name or ''} {target_user.last_name or ''}".strip() or f"ID: {user_telegram_id}"

        await callback.message.edit_text(
            f"🏘️ **Управление дворами пользователя**\n\n"
            f"👤 Пользователь: {user_name}\n"
            f"📱 Telegram ID: {user_telegram_id}\n\n"
            f"ℹ️ Здесь вы можете добавить дополнительные дворы для создания заявок.\n"
            f"По умолчанию житель имеет доступ только к двору своей квартиры.",
            reply_markup=get_user_yards_keyboard(user_telegram_id),
            parse_mode="Markdown"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка отображения управления дворами: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("add_user_yard_"))
async def handle_add_user_yard(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Показать список дворов для добавления"""
    lang = callback.from_user.language_code or 'ru'

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
            f"➕ **Добавление двора пользователю**\n\n"
            f"Выберите двор из списка:",
            reply_markup=get_yard_selection_keyboard(user_telegram_id),
            parse_mode="Markdown"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка показа списка дворов: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("user_yard_add_confirm_"))
async def handle_confirm_add_yard(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Подтвердить добавление двора"""
    lang = callback.from_user.language_code or 'ru'

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
            await callback.answer("❌ Администратор не найден", show_alert=True)
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
            await callback.answer("✅ Двор успешно добавлен", show_alert=True)
            # Возвращаемся к управлению дворами
            await handle_manage_user_yards(callback, db, roles, user)
        else:
            await callback.answer("❌ Не удалось добавить двор", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка добавления двора: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("remove_user_yard_"))
async def handle_remove_user_yard(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Удалить дополнительный двор у пользователя"""
    lang = callback.from_user.language_code or 'ru'

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
            await callback.answer("✅ Двор успешно удален", show_alert=True)
            # Обновляем интерфейс
            await handle_manage_user_yards(callback, db, roles, user)
        else:
            await callback.answer("❌ Не удалось удалить двор", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка удаления двора: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
