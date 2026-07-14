import uuid

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ApiError, forbidden
from app.core.security import read_session_token
from app.db import get_db
from app.models import User

# Capabilities that differ between operator and reviewer (ТЗ §4)
OPERATOR_ROLES = ("resource_admin", "resource_operator")
REVIEWER_ROLES = ("resource_admin", "resource_reviewer")
STAFF_ROLES = ("resource_admin", "resource_operator", "resource_reviewer")
ALL_ROLES = ("resource_admin", "resource_operator", "resource_reviewer", "resource_viewer")

# resource_meter_entry — узкая роль полевого контролёра: ТОЛЬКО ввод показаний в открытый
# период (одна страница). Намеренно НЕ входит в ALL_ROLES/OPERATOR_ROLES, чтобы не получить
# доступ к остальным данным/операциям — гейтится точечно только на нужных эндпоинтах.
METER_ENTRY_ROLE = "resource_meter_entry"
READING_ENTRY_ROLES = OPERATOR_ROLES + (METER_ENTRY_ROLE,)
WORKSHEET_READ_ROLES = ALL_ROLES + (METER_ENTRY_ROLE,)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise ApiError(401, "unauthorized", "Требуется вход")
    user_id = read_session_token(token)
    if not user_id:
        raise ApiError(401, "unauthorized", "Сессия недействительна или истекла")
    user = db.get(User, uuid.UUID(user_id))
    if not user or not user.is_active:
        raise ApiError(401, "unauthorized", "Пользователь не найден или отключён")
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise forbidden()
        return user

    return checker


def correlation_id(request: Request) -> str | None:
    """Correlation id set by the logging middleware; shared audit helper (DEAD-02)."""
    return getattr(request.state, "correlation_id", None)
