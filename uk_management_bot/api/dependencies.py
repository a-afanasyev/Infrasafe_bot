from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.database.models.user import User
from uk_management_bot.api.users.queries import get_user_by_id
from uk_management_bot.utils.auth_helpers import get_user_roles
from typing import AsyncGenerator, Optional

security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Async database not available (SQLite dev mode — use PostgreSQL)",
        )
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    from uk_management_bot.api.auth.service import verify_access_token

    # 1. Try httpOnly cookie first (Web SPA, plan §4.2 / §7.2 — uk_access).
    #    Legacy "access_token" is a transitional fallback for already-logged-in
    #    sessions issued before this PR; remove after one release window.
    token = request.cookies.get("uk_access") or request.cookies.get("access_token")
    # 2. Fallback to Authorization header (for TWA / backward compat)
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = await get_user_by_id(db, uid)

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    # Удалённый аккаунт: soft-delete сохраняет роли (нужны для истории заявок),
    # поэтому уже выданный токен продолжал бы открывать дашборд до истечения.
    if getattr(user, "deleted_at", None) is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deleted")
    if user.status == "blocked":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account blocked")

    return user


def require_roles(*roles: str):
    """Dependency factory: require_roles('manager', 'executor')"""
    async def checker(user: User = Depends(get_current_user)) -> User:
        # A9-P3-11: канонический резолвер бота — пустые roles = applicant,
        # active_role ролей не добавляет (прежний фолбэк на неё эскалировал).
        user_roles = get_user_roles(user)
        if not any(r in user_roles for r in roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    return checker


def require_approved_roles(*roles: str):
    """Like ``require_roles`` but ALSO requires ``user.status == 'approved'``.

    План «Обходчик» (R3/P0): ``get_current_user`` блокирует только ``blocked``,
    поэтому pending-пользователь со старым токеном иначе прошёл бы на создание
    заявки/адресные GET. Эта зависимость вешается ТОЛЬКО на целевые пути
    (create + адресные GET). Не внутри ``require_roles`` — иначе затронула бы
    ~68 эндпоинтов, где pending-доступ легитимен (онбординг).
    """
    async def checker(user: User = Depends(get_current_user)) -> User:
        user_roles = get_user_roles(user)
        if not any(r in user_roles for r in roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        if user.status != "approved":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account not approved")
        return user
    return checker
