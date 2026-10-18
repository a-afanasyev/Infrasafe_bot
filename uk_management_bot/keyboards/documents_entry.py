"""Inline-вход в загрузку документов (BUG-188).

Уведомление «Администратор запросил документы» раньше было голым текстом без
кнопки и без FSM-состояния, а фото вне состояния не ловил никто — документ
пропадал молча. Кнопка ведёт в выбор типа документа (handlers/onboarding.py).
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from uk_management_bot.constants.document_callbacks import RESUBMIT_CB, UPLOAD_DOCUMENTS_CB
from uk_management_bot.utils.helpers import get_text

__all__ = ["RESUBMIT_CB", "UPLOAD_DOCUMENTS_CB", "get_resubmit_inline", "get_upload_documents_inline"]


def get_resubmit_inline(language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=get_text("verification_resubmit.btn", language=language),
            callback_data=RESUBMIT_CB,
        )
    ]])


def get_upload_documents_inline(language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=get_text("onboarding.documents.btn_upload_inline", language=language),
            callback_data=UPLOAD_DOCUMENTS_CB,
        )
    ]])
