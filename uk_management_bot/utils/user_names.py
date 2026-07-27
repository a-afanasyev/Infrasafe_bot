"""Отображаемое имя пользователя — канон (AUD5-APIFE-13 / AUD5-CODE-8).

Копий было шесть, и они делятся на ДВА разных вопроса, а не на один
продублированный:

* «Имя Фамилия или ничего» — карточки API (`api/requests/router`,
  `api/shifts/router`): отсутствие имени осмысленно, клиент решает сам, что
  показать вместо него. Здесь `full_name`.
* «Что-нибудь непустое для показа» — подписи кнопок и текстов
  (`api/shifts/executor_router`, `api/feedback/router`, `keyboards/*`): пустая
  подпись недопустима, нужен фолбэк.

Слить их в одну функцию нельзя: получилось бы либо `#id` в ответах API (смена
контракта), либо пустые подписи в интерфейсе. Поэтому канон — только
`full_name`, а фолбэк каждая точка дописывает свой, явно и рядом с местом
показа. Фолбэки исторически разные (`@username` / `username` / `User {id}` /
`ID{telegram_id}` / `#{id}`), и унификация видимых строк — отдельное решение,
здесь оно НЕ принимается, чтобы техническая правка не меняла интерфейс.
"""

from __future__ import annotations

from typing import Optional


def full_name(user) -> Optional[str]:
    """«Имя Фамилия» без лишних пробелов, либо None если имени нет вовсе."""
    if user is None:
        return None
    name = f"{getattr(user, 'first_name', None) or ''} {getattr(user, 'last_name', None) or ''}".strip()
    return name or None
