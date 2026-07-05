"""Обработчики заявок жителя/исполнителя (AUD3-06: разбит god-файл на под-домены).

Публичный API сохранён (main.py + inspector_requests.py + base.py + тесты):
router, save_request, show_my_requests, _get_user_language, query-хелперы, regex.
Порядок импорта под-модулей = порядок регистрации хендлеров.
"""
from ._router import router
from . import create, create_callbacks, listing, myrequests, executor, materials  # noqa: F401
from .shared import (
    _get_user_language,
    _CANCEL_REQUEST_NUMBER_RE,
    _VIEW_REQUEST_NUMBER_RE,
)
from .create import save_request
from .listing import _get_executor_requests_query, _get_group_pool_query
from .myrequests import show_my_requests

__all__ = [
    "router", "save_request", "show_my_requests", "_get_user_language",
    "_get_executor_requests_query", "_get_group_pool_query",
    "_CANCEL_REQUEST_NUMBER_RE", "_VIEW_REQUEST_NUMBER_RE",
]
