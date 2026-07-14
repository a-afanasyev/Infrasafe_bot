import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import write_audit
from app.core.deps import get_current_user
from app.core.errors import ApiError, bad_request
from app.core.ratelimit import AUTH_LIMIT, limiter
from app.core.security import create_session_token, generate_ticket_token, hash_ticket_token
from app.db import get_db
from app.models import LaunchTicket, Tenant, User
from app.models.base import utcnow
from app.models.catalog import RESOURCE_ROLES

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        create_session_token(str(user.id)),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="none" if settings.cookie_secure else "lax",
        path="/",
    )


def _get_default_tenant(db: Session) -> Tenant:
    tenant = db.execute(select(Tenant).order_by(Tenant.created_at)).scalars().first()
    if not tenant:
        raise ApiError(500, "no_tenant", "Tenant не инициализирован")
    return tenant


class TicketCreateIn(BaseModel):
    external_user_id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=200)
    role: str


class TicketCreateOut(BaseModel):
    ticket: str
    expires_in: int


@router.post("/tickets", response_model=dict)
@limiter.limit(AUTH_LIMIT)
def create_ticket(
    request: Request,
    payload: TicketCreateIn,
    db: Session = Depends(get_db),
    x_service_token: str = Header(default=""),
):
    """Internal endpoint: UK backend mints a one-shot launch ticket (service-to-service)."""
    settings = get_settings()
    if not secrets.compare_digest(x_service_token, settings.service_token):  # SEC-08: constant-time
        raise ApiError(401, "unauthorized", "Неверный сервисный токен")
    if payload.role not in RESOURCE_ROLES:
        raise bad_request(f"Роль должна быть одной из {RESOURCE_ROLES}")

    tenant = _get_default_tenant(db)
    token = generate_ticket_token()
    db.add(
        LaunchTicket(
            tenant_id=tenant.id,
            token_hash=hash_ticket_token(token),
            external_user_id=payload.external_user_id,
            display_name=payload.display_name,
            role=payload.role,
            expires_at=utcnow() + timedelta(seconds=settings.ticket_ttl_seconds),
        )
    )
    db.commit()
    return {"data": TicketCreateOut(ticket=token, expires_in=settings.ticket_ttl_seconds).model_dump(mode="json")}


class ExchangeIn(BaseModel):
    ticket: str = Field(min_length=10)


@router.post("/session/exchange", response_model=dict)
@limiter.limit(AUTH_LIMIT)
def exchange_ticket(
    request: Request, payload: ExchangeIn, response: Response, db: Session = Depends(get_db)
):
    """Exchange a one-shot launch ticket for an httpOnly session (ТЗ §7.1)."""
    ticket = db.execute(
        select(LaunchTicket).where(LaunchTicket.token_hash == hash_ticket_token(payload.ticket))
    ).scalar_one_or_none()
    if not ticket:
        raise ApiError(401, "invalid_ticket", "Ticket не найден")
    expires_at = ticket.expires_at
    if expires_at.tzinfo is None:  # sqlite drops tz info
        from datetime import timezone

        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < utcnow():
        raise ApiError(401, "ticket_expired", "Ticket истёк")

    # SEC-06: atomically claim the ticket. Concurrent exchanges race on this single
    # UPDATE; only the one that flips used_at IS NULL → now() wins (rowcount == 1).
    claimed = db.execute(
        update(LaunchTicket)
        .where(LaunchTicket.id == ticket.id, LaunchTicket.used_at.is_(None))
        .values(used_at=utcnow())
    )
    if claimed.rowcount == 0:
        raise ApiError(401, "ticket_used", "Ticket уже использован")

    user = db.execute(
        select(User).where(User.tenant_id == ticket.tenant_id, User.external_id == ticket.external_user_id)
    ).scalar_one_or_none()
    if user is None:
        user = User(
            tenant_id=ticket.tenant_id,
            external_id=ticket.external_user_id,
            display_name=ticket.display_name,
            role=ticket.role,
        )
        db.add(user)
        db.flush()
    else:
        user.display_name = ticket.display_name
        user.role = ticket.role
        user.is_active = True

    write_audit(
        db,
        user=user,
        entity_type="session",
        entity_id=user.id,
        action="ticket_exchange",
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    db.commit()
    _set_session_cookie(response, user)
    return {"data": {"user_id": str(user.id), "display_name": user.display_name, "role": user.role}}


class DevLoginIn(BaseModel):
    external_user_id: str = "dev-admin"
    display_name: str = "Dev Admin"
    role: str = "resource_admin"


@router.post("/dev-login", response_model=dict)
@limiter.limit(AUTH_LIMIT)
def dev_login(request: Request, payload: DevLoginIn, response: Response, db: Session = Depends(get_db)):
    """Development-only login; disabled in production via RESOURCE_DEV_AUTH_ENABLED=false."""
    settings = get_settings()
    if not settings.dev_auth_enabled:
        raise ApiError(404, "not_found", "Endpoint недоступен")
    if payload.role not in RESOURCE_ROLES:
        raise bad_request(f"Роль должна быть одной из {RESOURCE_ROLES}")
    tenant = _get_default_tenant(db)
    user = db.execute(
        select(User).where(User.tenant_id == tenant.id, User.external_id == payload.external_user_id)
    ).scalar_one_or_none()
    if user is None:
        user = User(
            tenant_id=tenant.id,
            external_id=payload.external_user_id,
            display_name=payload.display_name,
            role=payload.role,
        )
        db.add(user)
    else:
        user.role = payload.role
        user.is_active = True
    db.commit()
    _set_session_cookie(response, user)
    return {"data": {"user_id": str(user.id), "display_name": user.display_name, "role": user.role}}


@router.get("/me", response_model=dict)
def me(user: User = Depends(get_current_user)):
    return {"data": {"user_id": str(user.id), "display_name": user.display_name, "role": user.role}}


@router.post("/logout", response_model=dict)
def logout(response: Response):
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return {"data": {"ok": True}}
