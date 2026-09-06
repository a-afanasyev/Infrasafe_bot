"""Бот лифтёра — меню «🛗 Лифты» (модуль «Лифты», Ф5, T10).

Исполнитель со специализацией ``elevator`` (алиас ``maintenance``): навигация
двор → дом → лифт, карточка, смена статуса с причиной, создание заявки на
ремонт, отметка ТО/освидетельствования выполненным. Роутер — с RoleGate
(``_router``), DB-фаза — sync-юниты под ``run_db`` (``_units``), callback —
``elvm:*`` (``_keyboards``). Порядок импорта = порядок регистрации хендлеров:
``_common`` первым (перехват reply-кнопок отмены на текстовых шагах), затем
модули сценариев; подсказка «не по кнопке» регистрируется последней явно.
"""
from aiogram.filters import StateFilter

from uk_management_bot.states.elevators import ALL_STATES

from ._router import router
from . import _common, menu, card, status, repair, maintenance  # noqa: F401 — регистрация по порядку

# ПОСЛЕДНИМ: текстовые хендлеры шагов уже зарегистрированы модулями выше.
router.message.register(_common.handle_non_text, StateFilter(*ALL_STATES))

__all__ = ["router"]
