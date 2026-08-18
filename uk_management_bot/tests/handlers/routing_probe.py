"""Разрешение роутинга aiogram: какой хендлер РЕАЛЬНО заберёт callback_data.

Класс дефектов «перекрытие фильтров» (BUG-155 п.3) живёт не в теле хендлера, а
в том, доходит ли до него апдейт: решают порядок регистрации роутеров в
`main.py` и широта фильтра — «первый подошедший забирает». Юнит-тест хендлера
такое не видит по построению, потому что зовёт функцию напрямую.

Здесь фильтры проверяются ровно так же, как их проверяет диспетчер, но без
исполнения хендлера и без сети.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from aiogram.types import CallbackQuery, Chat, Message, User as TgUser


def make_callback(data: str, from_id: int = 1) -> CallbackQuery:
    user = TgUser(id=from_id, is_bot=False, first_name="Тест")
    chat = Chat(id=from_id, type="private")
    message = Message(message_id=1, date=datetime.now(timezone.utc), chat=chat, from_user=user)
    return CallbackQuery(id="1", from_user=user, chat_instance="x", data=data, message=message)


async def _resolve(routers, data: str, raw_state=None):
    event = make_callback(data)
    for router in routers:
        for sub in [router, *router.sub_routers]:
            for handler in sub.callback_query.handlers:
                ok, _ = await handler.check(event, raw_state=raw_state)
                if ok:
                    return handler.callback.__name__
    return None


def resolve(routers, data: str, raw_state=None):
    """Имя хендлера-победителя либо None, если апдейт не подхватит никто.

    `routers` передаются в том же порядке, в каком они включены в `main.py` —
    именно он и определяет победителя.
    """
    return asyncio.run(_resolve(routers, data, raw_state))


# ══════════════════════════════════════════════════════════════════════════════
# resolve_ctx — разрешение С root-фильтрами и контекстом middleware
# ══════════════════════════════════════════════════════════════════════════════
#
# resolve() выше НАМЕРЕННО оставлен байт-в-байт: он тестирует перекрытие
# фильтров (BUG-155) и сознательно не знает про гейты. После появления
# RoleGate (root-фильтры роутеров, аудит 2026-08-18) resolve() врёт про
# достижимость: он зовёт handler.check() в обход check_root_filters и не
# передаёт kwargs (roles/user) — жителя от менеджера не отличает.
#
# resolve_ctx воспроизводит Router._propagate_event (aiogram
# dispatcher/router.py): root-фильтры роутера проверяются ДО хендлеров и ДО
# sub_routers; отказ = роутер пропускается ЦЕЛИКОМ (UNHANDLED, апдейт идёт к
# следующему top-level роутеру). Контекст (roles/user/…) передаётся и в
# root-фильтры, и в фильтры хендлеров — как data глобальных update-middleware.


def make_message(text: str, from_id: int = 1) -> Message:
    user = TgUser(id=from_id, is_bot=False, first_name="Тест")
    chat = Chat(id=from_id, type="private")
    return Message(
        message_id=1, date=datetime.now(timezone.utc), chat=chat,
        from_user=user, text=text,
    )


async def _resolve_ctx(routers, event, observer_name: str, raw_state=None, **data):
    data = {"raw_state": raw_state, **data}
    # Реальный диспетчер кладёт bot в data; фильтр Command требует его в check().
    if "bot" not in data:
        from unittest.mock import MagicMock
        data["bot"] = MagicMock(name="bot_stub")
    for router in routers:
        for sub in [router, *router.sub_routers]:
            observer = getattr(sub, observer_name)
            ok, extra = await observer.check_root_filters(event, **data)
            if not ok:
                continue  # root-фильтр отказал → весь (под)роутер мимо
            sub_data = {**data, **(extra or {})}
            for handler in observer.handlers:
                ok, _ = await handler.check(event, **sub_data)
                if ok:
                    return handler.callback.__module__, handler.callback.__name__
    return None


def resolve_ctx(routers, event, observer_name: str = "callback_query",
                raw_state=None, **data):
    """(module, name) хендлера-победителя либо None — С учётом root-фильтров.

    `event` — CallbackQuery (make_callback) или Message (make_message);
    `observer_name` — "callback_query" | "message"; `data` — контекст
    middleware (roles=..., user=..., ...). Победитель сверяется ПАРОЙ
    (module, name): имена хендлеров в проекте дублируются (cancel_action ×2).
    """
    return asyncio.run(_resolve_ctx(routers, event, observer_name, raw_state, **data))
