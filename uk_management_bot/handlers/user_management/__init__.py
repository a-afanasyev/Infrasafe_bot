"""Обработчики управления пользователями (AUD3-06: разбит god-файл на под-домены).

Публичный API сохранён: ``router`` (для main.py) и ``open_user_management``
(лениво импортируется handlers/admin.py). Порядок импорта под-модулей = порядок
регистрации хендлеров в роутере (сохранён из исходного файла).
"""
from ._router import router
from . import panels, listing, actions, fsm, roles_specs  # noqa: F401 — регистрация хендлеров по порядку
from .entry import open_user_management

__all__ = ["router", "open_user_management"]
