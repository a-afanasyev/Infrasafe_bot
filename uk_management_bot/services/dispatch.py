"""FEAT-группы: авто-dispatch новой заявки на группу-специализацию при создании.

Заявка создаётся в статусе «Новая»; этот хелпер сразу переводит её
Новая→В работе с групповым назначением по `CATEGORY_TO_SPECIALIZATION` через
канонический run_command (`SYSTEM_DISPATCH_ASSIGN`, system-principal
«dispatcher»). После этого любой дежурный исполнитель группы может «взять»
заявку (`EXECUTOR_CLAIM`).

Best-effort: ошибка dispatch (нет seeded system-user, нет маппинга категории,
гонка статуса и т.п.) НЕ валит уже-созданную заявку — она остаётся «Новая»
(менеджер назначит вручную). Вызывается ПОСЛЕ commit создания: бот —
`save_request` (sync), API/TWA/обходчик — `_persist_request` (async).

realtime: бот-путь создания realtime не публикует вовсе (только outbox-webhook,
который run_command тоже эмитит), поэтому sync-хелпер ограничивается dispatch'ем.
API-путь публикует realtime `request.created` (Новая) → async-хелпер обязан
до-опубликовать `request.status_changed`, иначе канбан показал бы stale «Новая».
"""

from __future__ import annotations

import logging
from typing import Optional

from uk_management_bot.constants.categories import CATEGORY_TO_SPECIALIZATION
from uk_management_bot.utils.request_workflow import (
    Action,
    ActionCommand,
    PrincipalRef,
)

logger = logging.getLogger(__name__)


def _dispatch_principal() -> PrincipalRef:
    return PrincipalRef(kind="system", user_id=None,
                        source="dispatcher", system_actor="dispatcher")


def _dispatch_command(request_number: str, specialization: str) -> ActionCommand:
    return ActionCommand(
        command_id=f"dispatch:{request_number}",
        action=Action.SYSTEM_DISPATCH_ASSIGN,
        payload={"group": specialization},
    )


def _specialization_for(category: Optional[str]) -> Optional[str]:
    if not category:
        return None
    return CATEGORY_TO_SPECIALIZATION.get(category)


def auto_dispatch_new_request_sync(request_number: str,
                                   category: Optional[str]) -> None:
    """Бот-путь: Новая→В работе + group-назначение (best-effort)."""
    spec = _specialization_for(category)
    if not spec:
        return
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.services.workflow_runner import run_command_sync
    try:
        run_command_sync(SessionLocal, request_number,
                         _dispatch_principal(),
                         _dispatch_command(request_number, spec))
        logger.info("[DISPATCH] Заявка %s авто-назначена группе '%s'",
                    request_number, spec)
    except Exception as e:  # best-effort — не валим создание заявки
        logger.warning("[DISPATCH] авто-назначение %s ('%s') не выполнено: %s",
                       request_number, spec, e)


async def auto_dispatch_new_request_async(request_number: str,
                                          category: Optional[str]) -> None:
    """API/TWA/обходчик: Новая→В работе + group + realtime status_changed."""
    spec = _specialization_for(category)
    if not spec:
        return
    from uk_management_bot.database.session import AsyncSessionLocal
    from uk_management_bot.services.workflow_runner import run_command_async
    try:
        outcome = await run_command_async(
            AsyncSessionLocal, request_number,
            _dispatch_principal(), _dispatch_command(request_number, spec))
        logger.info("[DISPATCH] Заявка %s авто-назначена группе '%s'",
                    request_number, spec)
    except Exception as e:  # best-effort — не валим создание заявки
        logger.warning("[DISPATCH] авто-назначение %s ('%s') не выполнено: %s",
                       request_number, spec, e)
        return
    await _publish_status_changed(outcome, request_number)


async def _publish_status_changed(outcome, request_number: str) -> None:
    """До-публикация realtime для канбана (Новая уже эмитнута при создании)."""
    from uk_management_bot.services.redis_pubsub import publish_request_event
    from uk_management_bot.utils.request_workflow import normalize_status
    for ev in outcome.post_commit_intents:
        if ev.kind != "realtime":
            continue
        try:
            await publish_request_event("request.status_changed", {
                "number": request_number,
                "old_status": normalize_status(outcome.old_state),
                "new_status": ev.data.get("status"),
            })
        except Exception as e:  # realtime best-effort
            logger.debug("[DISPATCH] realtime publish %s пропущен: %s",
                         request_number, e)
