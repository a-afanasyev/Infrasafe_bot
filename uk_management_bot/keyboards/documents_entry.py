"""Inline-вход в загрузку документов (BUG-188).

Уведомление «Администратор запросил документы» раньше было голым текстом без
кнопки и без FSM-состояния, а фото вне состояния не ловил никто — документ
пропадал молча. Кнопка ведёт в выбор типа документа (handlers/onboarding.py).
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from uk_management_bot.utils.helpers import get_text

UPLOAD_DOCUMENTS_CB = "docs:upload"


def get_upload_documents_inline(language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=get_text("onboarding.documents.btn_upload_inline", language=language),
            callback_data=UPLOAD_DOCUMENTS_CB,
        )
    ]])
