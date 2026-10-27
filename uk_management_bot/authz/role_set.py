"""Инвариант набора ролей пользователя — один для всех путей записи ролей.

Веб (PUT ролей сотрудника) и бот (редакторы ролей) проверяют итоговый набор
здесь, чтобы правило не расходилось между адаптерами.
"""
from __future__ import annotations

from typing import Iterable, Optional

from uk_management_bot.authz.catalog import ENGINEER, EXECUTOR

#: Роли, которые выдаёт и снимает бот-редактор ролей (AuthService.assign_role /
#: remove_role, кнопки keyboards/user_management). Остальные — веб-админка.
BOT_ASSIGNABLE_ROLES: tuple[str, ...] = ("applicant", "executor", "manager", "inspector",
                                         "resource_meter_entry")


def role_set_error(roles: Iterable[str]) -> Optional[str]:
    """Причина, по которой набор ролей недопустим, или None."""
    current = set(roles)
    if ENGINEER in current and EXECUTOR not in current:
        # Инженер работает в меню и TWA исполнителя: без executor у него нет
        # ни режима, ни права выполнять заявки.
        return "Роль «Инженер» выдаётся только вместе с ролью «Исполнитель»"
    return None
