"""Ссылки на ОСНОВНОЙ бот в текстах группового приёма.

Групповой бот — отдельный процесс (group_intake_main), но регистрация,
адреса и жизнь заявки остаются в личном боте ``settings.BOT_USERNAME``.
"""

from __future__ import annotations

from uk_management_bot.config.settings import settings


def bot_link() -> str:
    return f"https://t.me/{settings.BOT_USERNAME}"


def deeplink() -> str:
    return f"https://t.me/{settings.BOT_USERNAME}?start=group"
