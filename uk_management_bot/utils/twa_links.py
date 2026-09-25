"""Inline web_app-кнопки на экраны TWA из адресных уведомлений бота.

Не в `keyboards/`: разметку шлёт и сервисный слой (workflow_notifications),
а ему импорт UI-пакета бота запрещён гейтом A9-P2-10.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from uk_management_bot.config.settings import settings
from uk_management_bot.utils.helpers import get_text

# Карточка заявки исполнителя в TWA (маршрут `/twa/exec/tasks/:number`, SPA под /uk).
EXECUTOR_TASK_PATH = "/uk/twa/exec/tasks/{number}"


def executor_task_open_markup(request_number: str, language: str = "ru") -> Optional[InlineKeyboardMarkup]:
    """web_app «Открыть» → карточка заявки исполнителя в TWA.

    FRONTEND_URL — bare origin (путь добавляем сами); пуст → кнопки нет.
    web_app-кнопка допустима только в личном чате — слать лишь в личку.
    """
    if not settings.FRONTEND_URL:
        return None
    path = EXECUTOR_TASK_PATH.format(number=quote(str(request_number), safe=""))
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=get_text("notifications.workflow.btn_open_request", language=language),
            web_app=WebAppInfo(url=f"{settings.FRONTEND_URL}{path}"),
        )
    ]])
