"""Страховка основного бота: полная тишина в групповых чатах.

Group Intake живёт в ВЫДЕЛЕННОМ боте (group_intake_main.py) — основному боту
в группах делать нечего, и штатно его туда не добавляют. Но если всё же
добавят, без этого роутера групповые тексты/команды проваливались бы в
приватные хендлеры и их FSM (класс дефектов BUG-155: «кнопочный» текст из
группы дёргает чужой флоу). Роутер подключается ПЕРВЫМ и молча поглощает
любое групповое сообщение; приватные апдейты root-фильтр не проходят.
"""
from aiogram import F, Router
from aiogram.types import Message

router = Router(name="group_silence")
router.message.filter(F.chat.type.in_({"group", "supergroup"}))


@router.message()
async def swallow_group_message(message: Message) -> None:
    """Catch-all: групповое сообщение обработано «ничем» и дальше не идёт."""
    return None
