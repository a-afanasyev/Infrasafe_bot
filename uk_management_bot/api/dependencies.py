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
    #    A10-API-08: транзитный фолбэк на cookie `access_token` снят — на общем
    #    домене чужая cookie с таким именем затеняла Bearer TWA-клиента.
    token = request.cookies.get("uk_access")
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


def require_action(action_key: str):
    """Dependency factory: пропустить, если пользователю разрешено действие.

    `Depends(require_action("staff.manage"))`. Кто может — в
    `uk_management_bot/authz/catalog.py`. Порядок проверок и тексты отказов
    совпадают с прежними `require_roles` / `require_approved_roles`: сначала
    роли (403 Insufficient permissions), затем — для `approved_only` — статус
    (403 Account not approved). Неизвестное действие — ошибка при импорте
    модуля роутера, а не тихий отказ в рантайме.
    """
    from uk_management_bot.authz.catalog import get_action
    from uk_management_bot.authz.policy import is_superadmin

    action = get_action(action_key)

    async def checker(user: User = Depends(get_current_user)) -> User:
        if action.superadmin_bypass and is_superadmin(user):
            return user
        if not action.allows(get_user_roles(user)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        if action.approved_only and user.status != "approved":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account not approved")
        return user

    checker.__qualname__ = f"require_action[{action_key}]"
    return checker


def require_roles(*roles: str):
    """Dependency factory: require_roles('manager', 'executor')

    Устаревший путь: новые маршруты используют `require_action`; ратчет
    tests/services/test_rbac_baseline.py не даёт добавлять гейты по ролям.
    """
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
