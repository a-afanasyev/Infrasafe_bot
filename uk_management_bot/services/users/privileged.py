"""Привилегированная цель модерации — ОДИН предикат для API и бота (A10-INT-01).

Кого рядовой менеджер не может заблокировать/разблокировать/удалить/лишить
ролей: носителя manager/admin, суперадмина из `ADMIN_USER_IDS` (иначе его
можно было бы выключить из-под собственной админки прав) и любого, чьи роли
дают `staff.manage` — в том числе выданное своей ролью в админке ролей.

До этого гейт жил только в API (`api/shifts/router/_helpers.py`), а бот
(`handlers/user_management`, `handlers/employee_management`) ходил в
`AuthService` напрямую — менеджер из Telegram мог заблокировать или удалить
другого менеджера. Теперь `AuthService` отказывает сам, API-хелпер переводит
тот же предикат в 403.
"""
from __future__ import annotations

from uk_management_bot.authz.policy import has_action_roles, is_listed_superadmin
from uk_management_bot.utils.auth_helpers import get_user_roles

PRIVILEGED_ROLES = frozenset({"manager", "admin"})


def is_privileged_target(user) -> bool:
    """True — цель защищена от модерации рядовым менеджером."""
    roles = set(get_user_roles(user))
    return bool(
        roles & PRIVILEGED_ROLES
        or is_listed_superadmin(user)
        or has_action_roles(sorted(roles), "staff.manage")
    )
