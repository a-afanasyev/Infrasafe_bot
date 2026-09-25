"""Inline web_app-кнопки на экраны TWA из адресных уведомлений бота.

Не в `keyboards/`: разметку шлёт и сервисный слой (workflow_notifications),
а ему импорт UI-пакета бота запрещён гейтом A9-P2-10.
"""
from __future__ import annotations

from typing import Optional, Sequence
from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from uk_management_bot.config.settings import settings
from uk_management_bot.utils.helpers import get_text

# Карточка заявки исполнителя в TWA (маршрут `/twa/exec/tasks/:number`, SPA под /uk).
EXECUTOR_TASK_PATH = "/uk/twa/exec/tasks/{number}"
# «Готово» по заявке: редирект на экран камеры (простой режим) или на отчёт —
# решает фронт; бот ссылается только сюда (контракт маршрутов TWA, Фаза 2).
EXECUTOR_TASK_DONE_QUERY = "?action=done"
# Список «Мои» исполнителя (простой режим фронт перенаправит на `/twa/s`).
EXECUTOR_TASKS_PATH = "/uk/twa/exec"


def executor_task_url(request_number: str, *, done: bool = False) -> Optional[str]:
    """URL карточки заявки исполнителя (``done`` — сразу «Готово»); None без FRONTEND_URL."""
    if not settings.FRONTEND_URL:
        return None
    path = EXECUTOR_TASK_PATH.format(number=quote(str(request_number), safe=""))
    return f"{settings.FRONTEND_URL}{path}{EXECUTOR_TASK_DONE_QUERY if done else ''}"


def executor_tasks_url() -> Optional[str]:
    """URL списка заявок исполнителя; None без FRONTEND_URL."""
    if not settings.FRONTEND_URL:
        return None
    return f"{settings.FRONTEND_URL}{EXECUTOR_TASKS_PATH}"


def executor_done_links_markup(
    tasks: Sequence[tuple[str, str]], language: str = "ru"
) -> Optional[InlineKeyboardMarkup]:
    """web_app-кнопки «Готово» по заявкам + «Все» (список «Мои»).

    ``tasks`` — пары (номер, подпись кнопки); подпись — простой текст кнопки,
    не HTML. Без FRONTEND_URL — None (web_app без origin не построить).
    Только личка: web_app-кнопки в группах Telegram не принимает.
    """
    all_url = executor_tasks_url()
    if all_url is None:
        return None
    rows = [
        [InlineKeyboardButton(
            text=label,
            web_app=WebAppInfo(url=executor_task_url(number, done=True)),
        )]
        for number, label in tasks
    ]
    rows.append([InlineKeyboardButton(
        text=get_text("executor_done.btn_all", language=language),
        web_app=WebAppInfo(url=all_url),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def executor_task_open_markup(request_number: str, language: str = "ru") -> Optional[InlineKeyboardMarkup]:
    """web_app «Открыть» → карточка заявки исполнителя в TWA.

    FRONTEND_URL — bare origin (путь добавляем сами); пуст → кнопки нет.
    web_app-кнопка допустима только в личном чате — слать лишь в личку.
    """
    url = executor_task_url(request_number)
    if url is None:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=get_text("notifications.workflow.btn_open_request", language=language),
            web_app=WebAppInfo(url=url),
        )
    ]])
