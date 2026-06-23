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


def executor_selection_keyboard(
    target_id: int,
    users: List[User],
    language: str = "ru",
    *,
    mode: str = "transfer",
    back_callback: str = "assign_step:back",
) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора исполнителя (для менеджеров).

    Два режима (REG-02), оба передают ВНУТРЕННИЙ ``user.id`` (НЕ telegram_id):
      * ``mode="transfer"`` — назначение получателя по передаче:
        callback ``transfer_assign_executor:{target_id}:{user.id}`` (target_id = transfer_id);
      * ``mode="reassign"`` — прямой менеджерский reassign:
        callback ``reassign_executor:{target_id}:{user.id}`` (target_id = shift_id).

    Префиксы уникальны (не ``assign_executor:`` — занят shift_management.py:119).
    Кнопка автоназначения убрана (детерминированный явный выбор).
    """
    from uk_management_bot.utils.specializations import parse_specializations

    prefix = "reassign_executor" if mode == "reassign" else "transfer_assign_executor"

    builder = InlineKeyboardBuilder()

    for user in users:
        display_name = user.first_name or get_text(
            "shift_transfer.keyboards.unknown_user", language=language
        )
        if user.last_name:
            display_name += f" {user.last_name}"

        specs = parse_specializations(user)
        if specs:
            spec_text = ", ".join(sorted(specs)[:2])
            display_name += f" ({spec_text})"

        builder.row(
            InlineKeyboardButton(
                text=f"👤 {display_name}",
                callback_data=f"{prefix}:{target_id}:{user.id}"
            )
        )

    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.back", language=language),
            callback_data=back_callback
        )
    )

    return builder.as_markup()


def transfer_response_keyboard(transfer_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура ответа получателя на передачу смены.

    REG-02: callback'и несут ``transfer_id`` (раньше его не было → у получателя
    без FSM было непонятно, на какую передачу отвечают).
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.accept", language=language),
            callback_data=f"transfer_response:accept:{transfer_id}"
        ),
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.reject", language=language),
            callback_data=f"transfer_response:reject:{transfer_id}"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=get_text("shift_transfer.keyboards.details", language=language),
            callback_data=f"transfer_response:details:{transfer_id}"
        )
    )

    return builder.as_markup()


def transfers_list_keyboard(
    transfers: List[ShiftTransfer],
    language: str = "ru",
    current_user_id: int = None,
) -> InlineKeyboardMarkup:
    """
    Клавиатура со списком передач.

    CR-8: если ``current_user_id`` — получатель переданной ему смены в статусе
    ``assigned``, под строкой передачи добавляются кнопки «Принять»/«Отклонить»
    (callback ``transfer_response:accept|reject:{id}``). Это делает приём
    достижимым независимо от канала назначения (бот ИЛИ web) и даже если
    push-уведомление получателю не дошло.
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

        # Получателю assigned-передачи — действия приёма/отклонения прямо в списке.
        if (
            current_user_id is not None
            and transfer.status == "assigned"
            and transfer.to_executor_id == current_user_id
        ):
            builder.row(
                InlineKeyboardButton(
                    text=get_text("shift_transfer.keyboards.accept", language=language),
                    callback_data=f"transfer_response:accept:{transfer.id}"
                ),
                InlineKeyboardButton(
                    text=get_text("shift_transfer.keyboards.reject", language=language),
                    callback_data=f"transfer_response:reject:{transfer.id}"
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
