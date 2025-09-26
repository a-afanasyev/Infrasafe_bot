"""
Клавиатуры для функционала передачи смен
"""

from typing import List, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User


def shift_selection_keyboard(shifts: List[Shift], user_lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора смены для передачи

    Args:
        shifts: Список доступных смен
        user_lang: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    texts = {
        "ru": {
            "select_shift": "🔄 Передать смену",
            "shift_info": "📅 {date} {time} ({status})",
            "back": "⬅️ Назад"
        },
        "uz": {
            "select_shift": "🔄 Smena o'tkazish",
            "shift_info": "📅 {date} {time} ({status})",
            "back": "⬅️ Ortga"
        }
    }

    t = texts.get(user_lang, texts["ru"])

    for shift in shifts:
        shift_date = shift.start_time.strftime("%d.%m")
        shift_time = shift.start_time.strftime("%H:%M")

        # Маппинг статусов
        status_map = {
            "planned": "Запланирована" if user_lang == "ru" else "Rejalashtirilgan",
            "active": "Активна" if user_lang == "ru" else "Faol",
            "paused": "Пауза" if user_lang == "ru" else "Pauza"
        }

        status = status_map.get(shift.status, shift.status)

        shift_text = t["shift_info"].format(
            date=shift_date,
            time=shift_time,
            status=status
        )

        builder.row(
            InlineKeyboardButton(
                text=shift_text,
                callback_data=f"transfer_shift:{shift.id}"
            )
        )

    # Кнопка назад
    builder.row(
        InlineKeyboardButton(
            text=t["back"],
            callback_data="shift_transfer:back"
        )
    )

    return builder.as_markup()


def transfer_reason_keyboard(user_lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора причины передачи

    Args:
        user_lang: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    reasons = {
        "ru": {
            "illness": "🤒 Болезнь",
            "emergency": "🚨 Экстренная ситуация",
            "workload": "📊 Перегрузка",
            "vacation": "🏖️ Отпуск",
            "other": "❓ Другое"
        },
        "uz": {
            "illness": "🤒 Kasallik",
            "emergency": "🚨 Favqulodda holat",
            "workload": "📊 Ortiqcha ish",
            "vacation": "🏖️ Ta'til",
            "other": "❓ Boshqa"
        }
    }

    reason_texts = reasons.get(user_lang, reasons["ru"])

    # Создаем кнопки причин
    for reason_key, reason_text in reason_texts.items():
        builder.row(
            InlineKeyboardButton(
                text=reason_text,
                callback_data=f"transfer_reason:{reason_key}"
            )
        )

    # Кнопка назад
    back_text = "⬅️ Назад" if user_lang == "ru" else "⬅️ Ortga"
    builder.row(
        InlineKeyboardButton(
            text=back_text,
            callback_data="transfer_step:back"
        )
    )

    return builder.as_markup()


def urgency_level_keyboard(user_lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора уровня срочности

    Args:
        user_lang: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    urgency_levels = {
        "ru": {
            "low": "🟢 Низкий приоритет",
            "normal": "🟡 Обычный приоритет",
            "high": "🟠 Высокий приоритет",
            "critical": "🔴 Критический приоритет"
        },
        "uz": {
            "low": "🟢 Past ustunlik",
            "normal": "🟡 Oddiy ustunlik",
            "high": "🟠 Yuqori ustunlik",
            "critical": "🔴 Kritik ustunlik"
        }
    }

    levels = urgency_levels.get(user_lang, urgency_levels["ru"])

    for level_key, level_text in levels.items():
        builder.row(
            InlineKeyboardButton(
                text=level_text,
                callback_data=f"transfer_urgency:{level_key}"
            )
        )

    # Кнопка назад
    back_text = "⬅️ Назад" if user_lang == "ru" else "⬅️ Ortga"
    builder.row(
        InlineKeyboardButton(
            text=back_text,
            callback_data="transfer_step:back"
        )
    )

    return builder.as_markup()


def confirm_transfer_keyboard(user_lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для подтверждения передачи

    Args:
        user_lang: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    texts = {
        "ru": {
            "confirm": "✅ Подтвердить передачу",
            "edit": "✏️ Изменить",
            "cancel": "❌ Отмена"
        },
        "uz": {
            "confirm": "✅ O'tkazishni tasdiqlash",
            "edit": "✏️ O'zgartirish",
            "cancel": "❌ Bekor qilish"
        }
    }

    t = texts.get(user_lang, texts["ru"])

    builder.row(
        InlineKeyboardButton(
            text=t["confirm"],
            callback_data="transfer_confirm:yes"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=t["edit"],
            callback_data="transfer_confirm:edit"
        ),
        InlineKeyboardButton(
            text=t["cancel"],
            callback_data="transfer_confirm:cancel"
        )
    )

    return builder.as_markup()


def executor_selection_keyboard(users: List[User], user_lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора исполнителя (для менеджеров)

    Args:
        users: Список доступных исполнителей
        user_lang: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    for user in users:
        # Формируем имя пользователя
        display_name = user.first_name or "Неизвестный"
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
    auto_text = "🤖 Автоназначение" if user_lang == "ru" else "🤖 Avtomatik tayinlash"
    builder.row(
        InlineKeyboardButton(
            text=auto_text,
            callback_data="assign_executor:auto"
        )
    )

    # Кнопка назад
    back_text = "⬅️ Назад" if user_lang == "ru" else "⬅️ Ortga"
    builder.row(
        InlineKeyboardButton(
            text=back_text,
            callback_data="assign_step:back"
        )
    )

    return builder.as_markup()


def transfer_response_keyboard(user_lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для ответа на передачу смены

    Args:
        user_lang: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    texts = {
        "ru": {
            "accept": "✅ Принять",
            "reject": "❌ Отклонить",
            "details": "ℹ️ Подробности"
        },
        "uz": {
            "accept": "✅ Qabul qilish",
            "reject": "❌ Rad etish",
            "details": "ℹ️ Tafsilotlar"
        }
    }

    t = texts.get(user_lang, texts["ru"])

    builder.row(
        InlineKeyboardButton(
            text=t["accept"],
            callback_data="transfer_response:accept"
        ),
        InlineKeyboardButton(
            text=t["reject"],
            callback_data="transfer_response:reject"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=t["details"],
            callback_data="transfer_response:details"
        )
    )

    return builder.as_markup()


def transfers_list_keyboard(transfers: List[ShiftTransfer], user_lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура со списком передач

    Args:
        transfers: Список передач
        user_lang: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    # Маппинг статусов
    status_map = {
        "ru": {
            "pending": "⏳ Ожидает",
            "assigned": "👤 Назначен",
            "accepted": "✅ Принята",
            "rejected": "❌ Отклонена",
            "cancelled": "🚫 Отменена",
            "completed": "✅ Завершена"
        },
        "uz": {
            "pending": "⏳ Kutmoqda",
            "assigned": "👤 Tayinlangan",
            "accepted": "✅ Qabul qilingan",
            "rejected": "❌ Rad etilgan",
            "cancelled": "🚫 Bekor qilingan",
            "completed": "✅ Tugallangan"
        }
    }

    statuses = status_map.get(user_lang, status_map["ru"])

    for transfer in transfers:
        # Формируем текст кнопки
        date_str = transfer.created_at.strftime("%d.%m")
        status_text = statuses.get(transfer.status, transfer.status)

        button_text = f"{date_str} - {status_text}"

        builder.row(
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"view_transfer:{transfer.id}"
            )
        )

    # Кнопка назад
    back_text = "⬅️ Назад" if user_lang == "ru" else "⬅️ Ortga"
    builder.row(
        InlineKeyboardButton(
            text=back_text,
            callback_data="transfers:back"
        )
    )

    return builder.as_markup()


def skip_comment_keyboard(user_lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура с возможностью пропустить комментарий

    Args:
        user_lang: Язык пользователя

    Returns:
        InlineKeyboardMarkup
    """
    builder = InlineKeyboardBuilder()

    skip_text = "⏭️ Пропустить" if user_lang == "ru" else "⏭️ O'tkazib yuborish"
    back_text = "⬅️ Назад" if user_lang == "ru" else "⬅️ Ortga"

    builder.row(
        InlineKeyboardButton(
            text=skip_text,
            callback_data="transfer_comment:skip"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=back_text,
            callback_data="transfer_step:back"
        )
    )

    return builder.as_markup()