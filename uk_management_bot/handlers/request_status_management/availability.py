"""Вспомогательные функции управления статусами: доступные статусы, промпты.

AUD5-ARCH-3 (волна 12): перенос 1:1 из handlers/request_status_management.py.
"""

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.constants import (
    ROLE_MANAGER, ROLE_EXECUTOR, ROLE_APPLICANT,
    REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_COMPLETED, REQUEST_STATUS_APPROVED
)

# Вспомогательные функции

def get_available_statuses(user: User, request: Request) -> list:
    """Получение доступных статусов в зависимости от роли пользователя и текущего статуса"""
    available_statuses = []

    # Проверяем роли пользователя
    user_roles = user.roles if user.roles else []

    current_status = request.status

    # Менеджеры могут изменять статусы
    if ROLE_MANAGER in user_roles:
        if current_status == REQUEST_STATUS_NEW:
            available_statuses.extend([REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_CLARIFICATION])
        elif current_status == REQUEST_STATUS_IN_PROGRESS:
            available_statuses.extend([REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED])
        elif current_status == REQUEST_STATUS_PURCHASE:
            available_statuses.append(REQUEST_STATUS_IN_PROGRESS)
        elif current_status == REQUEST_STATUS_CLARIFICATION:
            available_statuses.append(REQUEST_STATUS_IN_PROGRESS)
        elif current_status == REQUEST_STATUS_EXECUTED:
            available_statuses.append(REQUEST_STATUS_APPROVED)
        elif current_status == REQUEST_STATUS_COMPLETED:
            available_statuses.append(REQUEST_STATUS_APPROVED)

    # Исполнители могут изменять статусы своих заявок
    elif ROLE_EXECUTOR in user_roles and request.executor_id == user.id:
        if current_status == REQUEST_STATUS_IN_PROGRESS:
            available_statuses.extend([REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED])
        elif current_status == REQUEST_STATUS_PURCHASE:
            available_statuses.append(REQUEST_STATUS_IN_PROGRESS)

    # Заявители могут принимать выполненные заявки
    elif ROLE_APPLICANT in user_roles and request.user_id == user.id:
        if current_status == REQUEST_STATUS_EXECUTED:
            available_statuses.append(REQUEST_STATUS_APPROVED)
        elif current_status == REQUEST_STATUS_COMPLETED:
            available_statuses.append(REQUEST_STATUS_APPROVED)

    return available_statuses

def get_comment_prompt(status: str, language: str = "ru") -> str:
    """Получение промпта для комментария в зависимости от статуса"""
    prompts = {
        REQUEST_STATUS_PURCHASE: get_text("request_status_mgmt.handlers.prompt_purchase", language=language),
        REQUEST_STATUS_CLARIFICATION: get_text("request_status_mgmt.handlers.prompt_clarification", language=language),
        REQUEST_STATUS_EXECUTED: get_text("request_status_mgmt.handlers.prompt_executed", language=language),
    }

    return prompts.get(status, get_text("request_status_mgmt.handlers.prompt_default", language=language))
