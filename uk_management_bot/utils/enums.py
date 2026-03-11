"""Enums for type-safe status and role handling."""
from enum import IntEnum


class RequestStatus(IntEnum):
    """Request status enum with mapping to DB string values."""
    NEW = 1
    IN_PROGRESS = 2
    PURCHASE = 3
    CLARIFICATION = 4
    EXECUTED = 5
    COMPLETED = 6
    APPROVED = 7
    CANCELLED = 8

    @property
    def db_value(self) -> str:
        """Russian string stored in DB."""
        return _STATUS_TO_DB[self]

    @property
    def locale_key(self) -> str:
        """Locale key for display."""
        return _STATUS_TO_LOCALE[self]

    @classmethod
    def from_db(cls, value: str) -> "RequestStatus":
        """Resolve DB string to enum. Raises ValueError if unknown."""
        return _DB_TO_STATUS[value]

    @classmethod
    def from_db_safe(cls, value: str, default: "RequestStatus | None" = None) -> "RequestStatus | None":
        """Resolve DB string to enum, returning default if unknown."""
        return _DB_TO_STATUS.get(value, default)


_STATUS_TO_DB = {
    RequestStatus.NEW: "Новая",
    RequestStatus.IN_PROGRESS: "В работе",
    RequestStatus.PURCHASE: "Закуп",
    RequestStatus.CLARIFICATION: "Уточнение",
    RequestStatus.EXECUTED: "Выполнена",
    RequestStatus.COMPLETED: "Исполнено",
    RequestStatus.APPROVED: "Принято",
    RequestStatus.CANCELLED: "Отменена",
}

_DB_TO_STATUS = {v: k for k, v in _STATUS_TO_DB.items()}

_STATUS_TO_LOCALE = {
    RequestStatus.NEW: "statuses.new",
    RequestStatus.IN_PROGRESS: "statuses.in_progress",
    RequestStatus.PURCHASE: "statuses.purchase",
    RequestStatus.CLARIFICATION: "statuses.clarification",
    RequestStatus.EXECUTED: "statuses.executed",
    RequestStatus.COMPLETED: "statuses.completed",
    RequestStatus.APPROVED: "statuses.approved",
    RequestStatus.CANCELLED: "statuses.cancelled",
}


class ShiftStatus(IntEnum):
    ACTIVE = 1
    COMPLETED = 2
    CANCELLED = 3
    PLANNED = 4
    PAUSED = 5

    @property
    def db_value(self) -> str:
        return _SHIFT_STATUS_TO_DB[self]

    @classmethod
    def from_db(cls, value: str) -> "ShiftStatus":
        return _SHIFT_DB_TO_STATUS[value]


_SHIFT_STATUS_TO_DB = {
    ShiftStatus.ACTIVE: "active",
    ShiftStatus.COMPLETED: "completed",
    ShiftStatus.CANCELLED: "cancelled",
    ShiftStatus.PLANNED: "planned",
    ShiftStatus.PAUSED: "paused",
}

_SHIFT_DB_TO_STATUS = {v: k for k, v in _SHIFT_STATUS_TO_DB.items()}


class UserRole(IntEnum):
    APPLICANT = 1
    EXECUTOR = 2
    MANAGER = 3

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
}

_ROLE_DB_TO_ENUM = {v: k for k, v in _ROLE_TO_DB.items()}
