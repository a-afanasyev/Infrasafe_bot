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
