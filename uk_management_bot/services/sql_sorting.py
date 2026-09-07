"""Сортировка списочных запросов по выбору пользователя.

Слой чистый: только SQLAlchemy, без fastapi и aiogram, — модуль импортируют и
доменные пакеты (у «Лифтов» на это есть импорт-гейт).

Имя колонки НИКОГДА не подставляется в SQL: вызывающий передаёт готовый
белый список «идентификатор → выражения ORDER BY», а сам идентификатор
проверяет ``Literal`` в сигнатуре роутера, то есть FastAPI отвечает 422 на
чужое значение ещё до обращения к базе.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Select

# Идентификатор колонки → выражения ORDER BY в порядке ВОЗРАСТАНИЯ.
# Несколько выражений — составной ключ (например адрес дома, затем подъезд).
SortFields = Mapping[str, Sequence[Any]]


def apply_sort(
    stmt: Select,
    *,
    fields: SortFields,
    sort: str | None,
    order: str | None,
    default: Sequence[Any],
    tiebreak: Any,
) -> Select:
    """``ORDER BY`` по выбранной колонке, иначе — порядок раздела по умолчанию.

    ``tiebreak`` добавляется ВСЕГДА и в том виде, в каком его передали:
    направление выбора пользователя на него не влияет. Без него строки с
    одинаковым значением идут в произвольном порядке, и постраничная выдача
    начинает терять и дублировать записи между страницами — тот же довод, что
    в ``api/requests/service.py`` для номера заявки.

    Пустые значения уходят в конец в ОБЕ стороны (``NULLS LAST``): строка без
    данных не должна всплывать наверх при развороте, где её принимают за
    максимум. Это же правило действует в браузере (``utils/tableSort.ts``),
    поэтому клиентская и серверная сортировка не расходятся.
    """
    columns = fields.get(sort) if sort else None
    if not columns:
        return stmt.order_by(*default, tiebreak)
    descending = order == "desc"
    return stmt.order_by(
        *((c.desc() if descending else c.asc()).nullslast() for c in columns),
        tiebreak,
    )
