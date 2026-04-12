import json
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.database.models.user import User
from sqlalchemy import select
from typing import AsyncGenerator, Optional

security = HTTPBearer(auto_error=False)


def _parse_user_roles(user) -> list[str]:
    """Parse user roles from JSON or CSV string, falling back to single role field."""
    if user.roles:
        raw = user.roles.strip()
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(r) for r in parsed]
            except (json.JSONDecodeError, TypeError):
                pass
        return [r.strip() for r in raw.split(",") if r.strip()]
    return [user.role] if user.role else []


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

    # 1. Try httpOnly cookie first
    token = request.cookies.get("access_token")
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

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.status == "blocked":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account blocked")

    return user


def require_roles(*roles: str):
    """Dependency factory: require_roles('manager', 'executor')"""
    async def checker(user: User = Depends(get_current_user)) -> User:
        user_roles = _parse_user_roles(user)
        if not any(r in user_roles for r in roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    return checker
