"""Сервис складского учёта материалов (закупки и движение матсредств).

Паттерн workflow_runner: чистое ядро (``allocate_fifo``, валидации) + тонкие
sync/async-обёртки. FIFO-математика одна на оба пути.

Инварианты (см. модели database/models/material.py):

* issues/allocations полностью immutable; receipts immutable кроме
  ``qty_remaining``. Исправления — только сторно (полное, однократное,
  со ссылкой на исходную операцию).
* Отрицательные остатки запрещены: нехватка → ``InsufficientStockError``.
* Конкурентность: партии лочатся ``with_for_update()`` со стабильным
  ``ORDER BY created_at, id`` (нет дедлоков); на sqlite (тесты) FOR UPDATE
  молча опускается — как в остальном репо.
* Commit — у вызывающего (sync-путь бота добавляет RequestComment в той же
  сессии; async-путь коммитит в API-роутере).
"""

# AUD5-ARCH-3 волна 9 (block-move): модуль разнесён на пакет с сохранением
# dotted-path, тела определений байт-в-байт. Раскрой: _core (ошибки/DTO/
# FIFO-ядро/shared-строители apply), sync_ops (sync-слой бота), catalog
# (карточки API), movements (приход/списание/корректировки/сторно), reads
# (остатки/журнал/отчёты), _sa (SQL-хелперы журнала).

# `_escape_like` реэкспортируется (его импортирует api/materials/service.py);
# поиск по названию материала обязан идти через `ci_contains` — см. докстринг
# `utils/sql_search` про локаль `C` на проде.
from uk_management_bot.utils.sql_search import (  # noqa: F401
    ci_contains,
    escape_like as _escape_like,
    is_postgres,
)

from ._core import (
    Allocation,
    BatchView,
    InsufficientStockError,
    MaterialConflictError,
    MaterialNotFoundError,
    MaterialServiceError,
    MaterialValidationError,
    RequestNotFoundError,
    allocate_fifo,
    money,
    parse_price,
    parse_qty,
    validate_unit,
)
from .catalog import create_material, update_material
from .movements import adjust, create_receipt, issue_material
from .reads import (
    get_procurement,
    get_request_materials,
    get_stock,
    list_operations,
)
from .sync_ops import (
    get_material_stock_sync,
    issue_material_sync,
    list_materials_with_stock,
)

__all__ = [
    "Allocation",
    "BatchView",
    "InsufficientStockError",
    "MaterialConflictError",
    "MaterialNotFoundError",
    "MaterialServiceError",
    "MaterialValidationError",
    "RequestNotFoundError",
    "_escape_like",
    "adjust",
    "allocate_fifo",
    "ci_contains",
    "create_material",
    "create_receipt",
    "get_material_stock_sync",
    "get_procurement",
    "get_request_materials",
    "get_stock",
    "is_postgres",
    "issue_material",
    "issue_material_sync",
    "list_materials_with_stock",
    "list_operations",
    "money",
    "parse_price",
    "parse_qty",
    "update_material",
    "validate_unit",
]
