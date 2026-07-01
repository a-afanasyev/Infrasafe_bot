"""Обработчики админ/менеджер-панели (AUD3-06: разбит god-файл на под-домены).

Публичный API сохранён: ``router`` (main.py) + ``list_archive_requests`` и
``handle_clarify_request`` (импортируются тестами). Порядок импорта под-модулей =
порядок регистрации хендлеров (сохранён из исходного файла).
"""
from ._router import router
from . import views, lists, invites, actions, materials, assignment  # noqa: F401 — регистрация по порядку
from .lists import list_archive_requests
from .actions import handle_clarify_request

__all__ = ["router", "list_archive_requests", "handle_clarify_request"]
