"""Локализованное отображение статусов заявок.

Значения REQUEST_STATUS_* — это ключи БД (русские строки), они НЕ меняются.
Эта утилита маппит их на локализованные display-строки.
"""
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_EXECUTED, REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_APPROVED, REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_RETURNED,
)

STATUS_DISPLAY_KEYS = {
    REQUEST_STATUS_NEW: "statuses.new",
    REQUEST_STATUS_IN_PROGRESS: "statuses.in_progress",
    REQUEST_STATUS_PURCHASE: "statuses.purchase",
    REQUEST_STATUS_CLARIFICATION: "statuses.clarification",
    REQUEST_STATUS_EXECUTED: "statuses.executed",
    REQUEST_STATUS_COMPLETED: "statuses.completed",
    # «Возвращена» — канон cutover (PR3+4); внутренний рендер бота (менеджер
    # видит канон-статус). Наружу (API/TWA) проецируется как «Исполнено».
    REQUEST_STATUS_RETURNED: "statuses.returned",
    REQUEST_STATUS_APPROVED: "statuses.approved",
    REQUEST_STATUS_CANCELLED: "statuses.cancelled",
}

STATUS_EMOJI = {
    REQUEST_STATUS_NEW: "🆕",
    REQUEST_STATUS_IN_PROGRESS: "🛠️",
    REQUEST_STATUS_PURCHASE: "💰",
    REQUEST_STATUS_CLARIFICATION: "❓",
    REQUEST_STATUS_EXECUTED: "✅",
    REQUEST_STATUS_COMPLETED: "⭐",
    REQUEST_STATUS_RETURNED: "↩️",
    REQUEST_STATUS_APPROVED: "✔️",
    REQUEST_STATUS_CANCELLED: "❌",
}


def get_status_display(status: str, language: str = "ru") -> str:
    """Получить локализованное название статуса."""
    key = STATUS_DISPLAY_KEYS.get(status)
    if key:
        return get_text(key, language=language)
    return status


def get_status_with_emoji(status: str, language: str = "ru") -> str:
    """Получить статус с эмодзи."""
    emoji = STATUS_EMOJI.get(status, "📋")
    display = get_status_display(status, language)
    return f"{emoji} {display}"
