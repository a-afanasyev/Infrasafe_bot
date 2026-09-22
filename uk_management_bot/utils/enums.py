"""Enum ролей для type-safe работы с `user.roles`.

Статусы заявок/смен здесь больше не дублируются (A9-P2-28): канон —
`utils/constants.py` (`REQUEST_STATUS_*`, `SHIFT_STATUS_*`).
"""
from enum import IntEnum


class UserRole(IntEnum):
    APPLICANT = 1
    EXECUTOR = 2
    MANAGER = 3
    INSPECTOR = 4
    # Роли модуля контроля доступа (access_control, ТЗ §3.2)
    SYSTEM_ADMIN = 5
    SECURITY_OPERATOR = 6

    @property
    def db_value(self) -> str:
        return _ROLE_TO_DB[self]

    @classmethod
    def from_db(cls, value: str) -> "UserRole":
        return _ROLE_DB_TO_ENUM[value]


_ROLE_TO_DB = {
    UserRole.APPLICANT: "applicant",
    UserRole.EXECUTOR: "executor",
    UserRole.MANAGER: "manager",
    UserRole.INSPECTOR: "inspector",
    UserRole.SYSTEM_ADMIN: "system_admin",
    UserRole.SECURITY_OPERATOR: "security_operator",
}

_ROLE_DB_TO_ENUM = {v: k for k, v in _ROLE_TO_DB.items()}
