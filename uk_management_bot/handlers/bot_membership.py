"""Статус «пользователь заблокировал бота» — realtime-источник.

Telegram шлёт боту ``my_chat_member`` при блокировке (status → kicked) и
разблокировке (kicked → member) в приватном чате. Пишем штамп в
``users.bot_blocked_at`` — его показывает бейдж «Бот заблокирован» в карточках
жителей/сотрудников дашборда. Второй источник того же поля — вердикт доставки
запроса номера (``api/users/phone_request.py``): он покрывает блокировки,
случившиеся до этого хендлера.

Middleware-цепочка бота этот тип апдейта не обогащает (нет user/roles в data)
— хендлер работает от сырого события и сам резолвит пользователя по
telegram_id; неизвестный боту человек просто игнорируется.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMemberUpdated

from uk_management_bot.database.session import run_db

logger = logging.getLogger(__name__)

router = Router()
router.my_chat_member.filter(F.chat.type == "private")

def _set_bot_blocked(db, telegram_id: int, blocked: bool) -> bool:
    """Проставить/снять штамп. -> запись найдена и изменена."""
    from uk_management_bot.database.models.user import User

    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user is None:
        return False
    if blocked and user.bot_blocked_at is None:
        user.bot_blocked_at = datetime.now(timezone.utc)
    elif not blocked and user.bot_blocked_at is not None:
        user.bot_blocked_at = None
    else:
        return False  # состояние уже такое — без пустого коммита
    db.commit()
    return True


@router.my_chat_member()
async def on_private_membership_change(event: ChatMemberUpdated, *, _db=None):
    """kicked → штамп блокировки; member → снять; прочее игнорируем.

    Документированный цикл блокировки приватного чата — member ↔ kicked.
    Прочие статусы (left и т.п.) осознанно НЕ трогают штамп (ревью): их
    семантика для приватного чата не подтверждена, а ложное движение бейджа
    хуже пропуска — пропуск добьёт второй источник (вердикт доставки)."""
    status = event.new_chat_member.status
    if status == ChatMemberStatus.KICKED:
        blocked = True
    elif status == ChatMemberStatus.MEMBER:
        blocked = False
    else:
        return
    changed = await run_db(
        lambda s: _set_bot_blocked(s, event.from_user.id, blocked), db=_db)
    if changed:
        logger.info("Пользователь %s %s бота", event.from_user.id,
                    "заблокировал" if blocked else "разблокировал")
