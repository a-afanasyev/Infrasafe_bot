"""
Клавиатуры для функционала передачи смен
"""

from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import get_text


def shift_selection_keyboard(shifts: List[Shift], language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора смены для передачи

    Args:
        shifts: Список доступных смен
        language: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    for shift in shifts:
        shift_date = shift.start_time.strftime("%d.%m")
        shift_time = shift.start_time.strftime("%H:%M")

        # Маппинг статусов
        status = get_text(
            f"shift_transfer.keyboards.status_{shift.status}",
            language=language
        ) if shift.status in ("planned", "active", "paused") else shift.status

        shift_text = get_text(
            "shift_transfer.keyboards.shift_info",
            language=language
        ).format(date=shift_date, time=shift_time, status=status)

        builder.row(
            InlineKeyboardButton(
                text=shift_text,
                callback_data=f"transfer_shift:{shift.id}"
            )
        )

    # Кнопка назад
    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.back", language=language),
            callback_data="shift_transfer:back"
        )
    )

    return builder.as_markup()


def transfer_reason_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора причины передачи

    Args:
        language: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    reason_keys = ["illness", "emergency", "workload", "vacation", "other"]

    # Создаем кнопки причин
    for reason_key in reason_keys:
        builder.row(
            InlineKeyboardButton(
                text=get_text(
                    f"shift_transfer.keyboards.reason_{reason_key}",
                    language=language
                ),
                callback_data=f"transfer_reason:{reason_key}"
            )
        )

    # Кнопка назад
    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.back", language=language),
            callback_data="transfer_step:back"
        )
    )

    return builder.as_markup()


def urgency_level_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора уровня срочности

    Args:
        language: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    level_keys = ["low", "normal", "high", "critical"]

    for level_key in level_keys:
        builder.row(
            InlineKeyboardButton(
                text=get_text(
                    f"shift_transfer.keyboards.urgency_{level_key}",
                    language=language
                ),
                callback_data=f"transfer_urgency:{level_key}"
            )
        )

    # Кнопка назад
    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.back", language=language),
            callback_data="transfer_step:back"
        )
    )

    return builder.as_markup()


def confirm_transfer_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для подтверждения передачи

    Args:
        language: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.confirm_transfer", language=language),
            callback_data="transfer_confirm:yes"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.edit", language=language),
            callback_data="transfer_confirm:edit"
        ),
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.cancel", language=language),
            callback_data="transfer_confirm:cancel"
        )
    )

    return builder.as_markup()


def executor_selection_keyboard(users: List[User], language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора исполнителя (для менеджеров)

    Args:
        users: Список доступных исполнителей
        language: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    for user in users:
        # Формируем имя пользователя
        display_name = user.first_name or get_text(
            "shift_transfer.keyboards.unknown_user", language=language
        )
        if user.last_name:
            display_name += f" {user.last_name}"

        # Добавляем информацию о специализации если есть
        if hasattr(user, 'specialization') and user.specialization:
            import json
            try:
                specializations = json.loads(user.specialization)
                if specializations:
                    spec_text = ", ".join(specializations[:2])  # Первые 2 специализации
                    display_name += f" ({spec_text})"
            except:
                pass

        builder.row(
            InlineKeyboardButton(
                text=f"👤 {display_name}",
                callback_data=f"assign_executor:{user.telegram_id}"
            )
        )

    # Кнопка автоназначения
    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.auto_assign", language=language),
            callback_data="assign_executor:auto"
        )
    )

    # Кнопка назад
    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.back", language=language),
            callback_data="assign_step:back"
        )
    )

    return builder.as_markup()


def transfer_response_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для ответа на передачу смены

    Args:
        language: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.accept", language=language),
            callback_data="transfer_response:accept"
        ),
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.reject", language=language),
            callback_data="transfer_response:reject"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.details", language=language),
            callback_data="transfer_response:details"
        )
    )

    return builder.as_markup()


def transfers_list_keyboard(transfers: List[ShiftTransfer], language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура со списком передач

    Args:
        transfers: Список передач
        language: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    for transfer in transfers:
        # Формируем текст кнопки
        date_str = transfer.created_at.strftime("%d.%m")
        status_text = get_text(
            f"shift_transfer.keyboards.transfer_status_{transfer.status}",
            language=language
        ) if transfer.status in (
            "pending", "assigned", "accepted", "rejected", "cancelled", "completed"
        ) else transfer.status

        button_text = f"{date_str} - {status_text}"

        builder.row(
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"view_transfer:{transfer.id}"
            )
        )

    # Кнопка назад
    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.back", language=language),
            callback_data="transfers:back"
        )
    )

    return builder.as_markup()


def skip_comment_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура с возможностью пропустить комментарий

    Args:
        language: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.skip", language=language),
            callback_data="transfer_comment:skip"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.back", language=language),
            callback_data="transfer_step:back"
        )
    )

    return builder.as_markup()
