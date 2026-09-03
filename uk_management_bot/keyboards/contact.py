"""Reply-клавиатура «Поделиться контактом» — единственный способ дать телефон.

Ручной ввод номера убран (спека 2026-09-03): телефон только из Telegram-контакта,
чужой пересланный контакт отклоняют хендлеры.
"""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from uk_management_bot.utils.helpers import get_text


def get_share_contact_keyboard(language: str, *, with_cancel: bool) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(
        text=get_text("onboarding.share_contact", language=language), request_contact=True,
    )]]
    if with_cancel:
        rows.append([KeyboardButton(text=get_text("buttons.cancel", language=language))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)
