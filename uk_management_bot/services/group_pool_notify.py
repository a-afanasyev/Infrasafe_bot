"""FEAT-группы: «заявку #N взял X» — остальным дежурным группы после взятия.

Один источник для обоих путей взятия (EXECUTOR_CLAIM): бот (`claim_request_`,
sync-сессия хендлера) и API (`POST /requests/{n}/claim`, фоновая задача со
своей короткой сессией). Получатели и текст считаются здесь одинаково:
on-shift approved-исполнители той же специализации, кроме взявшего
(group_specialization сохранён в назначении как история).

Best-effort: не бросает. Ошибки отправки логируются только классом/статусом
(`describe_http_error`) — сырое исключение httpx рядом с Bot API несёт токен
бота в URL.
"""
from __future__ import annotations

import html
import logging
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import get_user_roles
from uk_management_bot.utils.constants import ROLE_EXECUTOR
from uk_management_bot.utils.datetime_utils import utc_now
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.http_errors import describe_http_error
from uk_management_bot.utils.shifts import on_shift_window
from uk_management_bot.utils.specializations import (
    matches_required_specs,
    parse_specialization_values,
    parse_specializations,
)

logger = logging.getLogger(__name__)


def _recipients(group_spec: Optional[str], candidates: Iterable[User],
                claimer_id: int) -> list[User]:
    """Кого уведомить: исполнители группы на смене, кроме взявшего."""
    # Требование разбирается явно: пустое означало бы «уведомить всех».
    required = parse_specialization_values(group_spec, side="need",
                                           allow_universal=True)
    if not required:
        return []
    # BUG-166: общий предикат — иначе универсал не получал бы уведомления о
    # заявках, которые он мог бы взять.
    return [
        ex for ex in candidates
        if ex.id != claimer_id and ex.telegram_id
        and ROLE_EXECUTOR in get_user_roles(ex)
        and matches_required_specs(parse_specializations(ex), required)
    ]


async def _send(request_number: str, claimer_name: str,
                recipients: list[User], bot=None) -> int:
    if not recipients:
        return 0
    from uk_management_bot.services.notification_service import _get_shared_bot

    bot = bot or _get_shared_bot()
    if bot is None:
        return 0
    sent = 0
    for ex in recipients:
        # A9-P2-2: имя из Telegram в HTML-уведомлении; parse_mode явно —
        # fallback-бот API-процесса собран без HTML-дефолта.
        text = get_text("requests.claimed_by_other_notify",
                        language=(ex.language or "ru")).format(
            request_number=request_number, executor=html.escape(claimer_name))
        try:
            await bot.send_message(chat_id=ex.telegram_id, text=text,
                                   parse_mode="HTML")
            sent += 1
        except Exception as e:
            logger.debug("claim-notify исполнителю %s пропущено: %s",
                         ex.id, describe_http_error(e))
    return sent


def _claimer_name(claimer: Optional[User], claimer_id: int) -> str:
    return (claimer.first_name if claimer else None) or str(claimer_id)


async def notify_group_pool_claimed_sync(db: Session, request_number: str,
                                         claimer: User, bot=None) -> int:
    """Бот-путь: чтение через sync-сессию хендлера. Не бросает."""
    from uk_management_bot.services.request_handler_service import (
        RequestHandlerService,
    )
    try:
        service = RequestHandlerService(db)
        assignment = service.get_active_assignment(request_number)
        spec = assignment.group_specialization if assignment else None
        recipients = _recipients(
            spec, service.list_on_shift_notify_candidates(), claimer.id)
        return await _send(request_number, _claimer_name(claimer, claimer.id),
                           recipients, bot)
    except Exception as e:
        logger.warning("claim-notify для %s не выполнен: %s",
                       request_number, describe_http_error(e))
        return 0


async def notify_group_pool_claimed_detached(request_number: str,
                                             claimer_id: int) -> int:
    """API-путь (fastapi BackgroundTasks): своя короткая сессия только на
    чтение, закрыта до первой отправки. Не бросает."""
    from uk_management_bot.database.session import AsyncSessionLocal

    if AsyncSessionLocal is None:
        return 0
    try:
        async with AsyncSessionLocal() as db:
            spec = await db.scalar(
                select(RequestAssignment.group_specialization).where(
                    RequestAssignment.request_number == request_number,
                    RequestAssignment.status == "active"))
            claimer = await db.get(User, claimer_id)
            # WR-05: «approved + на смене» — один запрос, как в sync-пути.
            candidates = (await db.execute(
                select(User).join(Shift, Shift.user_id == User.id)
                .where(User.status == "approved", on_shift_window(utc_now()))
                .distinct())).scalars().all()
        recipients = _recipients(spec, candidates, claimer_id)
        return await _send(request_number, _claimer_name(claimer, claimer_id),
                           recipients)
    except Exception as e:
        logger.warning("claim-notify для %s не выполнен: %s",
                       request_number, describe_http_error(e))
        return 0
