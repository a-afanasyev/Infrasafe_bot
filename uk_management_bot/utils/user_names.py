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
контракта), либо пустые подписи в интерфейсе. Поэтому публичных хелпера ровно
два: `full_name` (может вернуть None — это часть контракта карточек API) и
`display_name` (всегда непустая строка — для подписей).

Фолбэк был разный в пяти местах (`@username` / `username` / `User {id}` /
`ID{telegram_id}` / `#{id}`) — REFACTOR-133. Выбран один: `@username`, иначе
`ID{telegram_id}`. Внутренний serial (`#id`) как последняя ступень оставлен на
случай пользователя без telegram_id, но в норме не показывается: поддержке
telegram_id полезнее — по нему человека можно найти, по serial'у нет.
"""

from __future__ import annotations

from typing import Optional

#: Многоточие при обрезке; вычитается из лимита, а не добавляется сверх него.
_ELLIPSIS = "..."


def full_name(user) -> Optional[str]:
    """«Имя Фамилия» без лишних пробелов, либо None если имени нет вовсе."""
    if user is None:
        return None
    name = f"{getattr(user, 'first_name', None) or ''} {getattr(user, 'last_name', None) or ''}".strip()
    return name or None


def display_name(user, *, max_len: Optional[int] = None) -> Optional[str]:
    """Непустая подпись пользователя; None только если самого пользователя нет.

    `max_len` — предел ДЛИНЫ РЕЗУЛЬТАТА (многоточие входит в лимит, а не
    добавляется поверх него): подпись кнопки, вылезшая за отведённое место,
    ломает вёрстку ровно так же, как слишком длинное имя.
    """
    if user is None:
        return None

    name = full_name(user)
    if not name:
        username = getattr(user, "username", None)
        telegram_id = getattr(user, "telegram_id", None)
        if username:
            name = f"@{username}"
        elif telegram_id:
            name = f"ID{telegram_id}"
        else:
            name = f"#{getattr(user, 'id', '?')}"

    if max_len is not None and len(name) > max_len:
        name = name[: max(0, max_len - len(_ELLIPSIS))] + _ELLIPSIS
    return name
