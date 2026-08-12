"""AUD5-ARCH-3 волна 8 (block-move): api/shifts/router.py (974 строки, 30
маршрутов + хелперы-сериализаторы) разнесён на пакет с сохранением dotted-path
(`api.main` импортирует `from uk_management_bot.api.shifts.router import router`).

Тела перенесены байт-в-байт. Порядок импортов под-модулей ниже — СТРОГО порядок
исходника: он задаёт порядок регистрации маршрутов на общем APIRouter, а в
FastAPI выигрывает первый матч — статические пути (/employees/pending,
/schedule, /stats, /transfers, /templates, /from-template) обязаны
регистрироваться ДО catch-all /{shift_id} (shift_crud — последним).
"""
from ._router import router
from ._helpers import (
    _ensure_not_privileged,
    _executor_name,
    _resolve_bot_username,
    _shift_brief,
    _shift_detail,
)
from . import employees
from . import shifts_read
from . import templates
from . import transfers
from . import shift_crud

__all__ = [
    "router",
    "_ensure_not_privileged",
    "_executor_name",
    "_resolve_bot_username",
    "_shift_brief",
    "_shift_detail",
    "employees",
    "shifts_read",
    "templates",
    "transfers",
    "shift_crud",
]
