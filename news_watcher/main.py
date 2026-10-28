"""Entrypoint юзербота (Telethon). Только здесь импортируется telethon.

Цикл: раз в ``refresh_seconds`` — список источников из API → подписка на
новые (``JoinChannelRequest``) и отписка от убранных; каждое новое сообщение
в подписанных каналах/группах → ``handle_message`` → inbox API.
Только чтение: юзербот никогда не пишет в чужие чаты.
"""
from __future__ import annotations

import asyncio
import logging

from news_watcher.watcher import ApiClient, Offsets, Settings, diff_sources, handle_message, normalize_handle

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("news_watcher.main")


async def run() -> None:
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest

    settings = Settings.from_env()
    api = ApiClient(settings)
    offsets = Offsets(settings.offsets_path)
    client = TelegramClient(StringSession(settings.session), settings.api_id, settings.api_hash)
    subscribed: set[str] = set()
    entities: dict[str, object] = {}

    async def refresh_sources() -> None:
        nonlocal subscribed
        try:
            wanted = {h for h in (normalize_handle(s) for s in await api.fetch_sources()) if h}
        except Exception as e:
            logger.warning("sources fetch failed: %s", type(e).__name__)
            return
        join, leave = diff_sources(subscribed, wanted)
        for handle in sorted(join):
            try:
                entity = await client.get_entity(handle)
                await client(JoinChannelRequest(entity))
                entities[handle] = entity
                subscribed = subscribed | {handle}
                logger.info("subscribed %s", handle)
            except Exception as e:
                logger.warning("join %s failed: %s", handle, type(e).__name__)
        for handle in sorted(leave):
            try:
                entity = entities.pop(handle, None) or await client.get_entity(handle)
                await client(LeaveChannelRequest(entity))
            except Exception as e:
                logger.warning("leave %s failed: %s", handle, type(e).__name__)
            subscribed = subscribed - {handle}
            logger.info("unsubscribed %s", handle)

    @client.on(events.NewMessage())
    async def on_message(event) -> None:
        chat = await event.get_chat()
        handle = normalize_handle(getattr(chat, "username", None))
        if handle not in subscribed:
            return
        await handle_message(
            api, offsets, chat_id=int(event.chat_id), message_id=int(event.message.id),
            chat_title=getattr(chat, "title", None), text=event.message.message or "",
            posted_at=event.message.date,
        )

    await client.start()
    logger.info("news_watcher started")
    try:
        while True:
            await refresh_sources()
            await asyncio.sleep(settings.refresh_seconds)
    finally:
        await api.aclose()
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(run())
