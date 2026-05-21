"""
RoleFilter — aiogram filter that matches handlers only when the user's
``active_role`` is in the allowed set.

Why this exists
---------------
Several reply-keyboard buttons share the same text across role-specific
menus (e.g. ``📦 Архив`` appears in BOTH the executor main menu and the
admin/manager panel). Aiogram registers handlers in router-include order,
so the first matching ``F.text == "..."`` handler always wins regardless
of the user's current role. That causes role-mismatch routing — see
BUG-BOT-019.

Adding ``RoleFilter`` to ambiguous handlers lets each one match only when
``active_role`` matches the role family the handler belongs to. The
``active_role`` is injected into handler kwargs by ``role_mode_middleware``
(see :mod:`uk_management_bot.middlewares.auth`).

Usage
-----
.. code-block:: python

    from uk_management_bot.filters import RoleFilter

    @router.message(F.text.in_(ARCHIVE_TEXTS), RoleFilter(["executor"]))
    async def executor_archive(...):
        ...

    @router.message(F.text.in_(ADMIN_ARCHIVE_TEXTS),
                    RoleFilter(["manager", "admin"]))
    async def admin_archive(...):
        ...
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)


class RoleFilter(BaseFilter):
    """Match only when ``active_role`` is in the allowed set.

    Args:
        allowed_roles: Iterable of role names that should match. Stored
            as an immutable tuple to keep the filter hashable/safe.
        default: Role to assume when ``active_role`` is missing from
            handler kwargs (fail-safe). Defaults to ``"applicant"`` to
            mirror ``role_mode_middleware``'s fallback.
    """

    def __init__(
        self,
        allowed_roles: Iterable[str],
        default: str = "applicant",
    ) -> None:
        self.allowed_roles: tuple[str, ...] = tuple(allowed_roles)
        self.default: str = default

    async def __call__(  # type: ignore[override]
        self,
        event: TelegramObject,
        active_role: Optional[str] = None,
        **kwargs: object,
    ) -> bool:
        """Return True iff ``active_role`` is in ``allowed_roles``.

        ``active_role`` is supplied by aiogram's DI from middleware data
        (see ``role_mode_middleware``). When absent, we treat the user as
        the configured default — this is the same fail-safe applied by
        the middleware itself.
        """
        effective = active_role or self.default
        matched = effective in self.allowed_roles
        if not matched:
            logger.debug(
                "RoleFilter reject: active_role=%r, allowed=%r",
                effective,
                self.allowed_roles,
            )
        return matched
