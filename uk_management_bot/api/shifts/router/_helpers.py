"""AUD5-ARCH-3 волна 8 (block-move из api/shifts/router.py): хелперы роутера.

Тела перенесены байт-в-байт; см. __init__.py пакета.
"""
import logging
import httpx
from typing import Optional

from fastapi import HTTPException

from uk_management_bot.api.dependencies import _parse_user_roles
from uk_management_bot.api.shifts.schemas import ShiftBrief, ShiftDetail
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.http_errors import describe_http_error
from uk_management_bot.utils.user_names import full_name

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers (no direct ORM — pure serializers / non-DB utilities)
# ---------------------------------------------------------------------------

async def _resolve_bot_username() -> Optional[str]:
    """Return the bot @username used to build invite links.

    The bot process (main.py) self-heals BOT_USERNAME via getMe() at startup
    (BUG-BOT-001), but invite links are built by *this* API process, which only
    reads os.getenv("BOT_USERNAME"). If the var is missing from the API
    environment, the link would render as https://t.me/None. Mirror the bot's
    behaviour here: resolve via Telegram getMe() using BOT_TOKEN and cache the
    result back into settings so subsequent requests skip the network.

    Returns None only when resolution is impossible (no token / API failure),
    so the caller can fail loudly instead of emitting a broken link.
    """
    from uk_management_bot.config.settings import settings as app_settings

    if app_settings.BOT_USERNAME:
        return app_settings.BOT_USERNAME

    token = app_settings.BOT_TOKEN
    if not token:
        logger.error("Cannot resolve bot username: BOT_USERNAME and BOT_TOKEN are both unset")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            resp.raise_for_status()
            username = (resp.json().get("result") or {}).get("username")
    except Exception as exc:  # network/auth issues — never crash the request
        logger.error("getMe() failed while resolving bot username for invite link: %s",
                     describe_http_error(exc))
        return None

    if username:
        app_settings.BOT_USERNAME = username  # cache for subsequent requests
        logger.info(f"Resolved bot username via getMe(): {username}")
    return username


# AUD5-APIFE-13: копия, посимвольно совпадавшая с requests/router.
_executor_name = full_name


def _shift_brief(shift: Shift, user: Optional[User] = None) -> ShiftBrief:
    load_pct = (shift.current_request_count / shift.max_requests * 100) if shift.max_requests > 0 else 0.0
    return ShiftBrief(
        id=shift.id,
        user_id=shift.user_id,
        executor_name=_executor_name(user),
        status=shift.status,
        shift_type=shift.shift_type,
        start_time=shift.start_time,
        end_time=shift.end_time,
        max_requests=shift.max_requests,
        current_request_count=shift.current_request_count,
        load_percentage=load_pct,
        specialization_focus=shift.specialization_focus,
    )


def _shift_detail(shift: Shift, user: Optional[User] = None) -> ShiftDetail:
    load_pct = (shift.current_request_count / shift.max_requests * 100) if shift.max_requests > 0 else 0.0
    return ShiftDetail(
        id=shift.id,
        user_id=shift.user_id,
        executor_name=_executor_name(user),
        status=shift.status,
        shift_type=shift.shift_type,
        start_time=shift.start_time,
        end_time=shift.end_time,
        max_requests=shift.max_requests,
        current_request_count=shift.current_request_count,
        load_percentage=load_pct,
        notes=shift.notes,
        specialization_focus=shift.specialization_focus,
        coverage_areas=shift.coverage_areas,
        priority_level=shift.priority_level,
        completed_requests=shift.completed_requests,
        efficiency_score=shift.efficiency_score,
        quality_rating=shift.quality_rating,
        template_id=shift.shift_template_id,
        created_at=shift.created_at,
    )


def _ensure_not_privileged(user: User, *, action: str) -> None:
    """Raise 403 if the target user is a manager/admin (cannot be modified)."""
    target_roles = set(_parse_user_roles(user))
    if "manager" in target_roles or "admin" in target_roles:
        raise HTTPException(status_code=403, detail=action)
