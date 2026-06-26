"""Operator/Admin API резолюции и ручного открытия (§13.2, §6.3).

Endpoints (USER-API, существующая JWT/cookie-аутентификация, НЕ device-auth):

* ``POST /api/v1/access/events/{event_id}/resolve`` — резолюция manual_review
  (manual_open | deny), идемпотентна по event/decision (§9.5);
* ``POST /api/v1/access/barriers/{barrier_id}/manual-open`` — самостоятельное
  ручное открытие, 409 при активном pending_review (§13.2).

RBAC (§6.3, §3.2): доступ только ролям ``security_operator``, ``manager``,
``system_admin``. executor/inspector/applicant → 403. Без auth → 401. Пустая
причина → 422 (pydantic). Логи PD-safe (§11): только идентификаторы, без ПД.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from access_control.services.lifecycle import (
    BarrierUnavailableError,
    DecisionIdMismatch,
    InvalidResolveAction,
    ManualOpenResult,
    NoPendingReviewError,
    PendingReviewConflict,
    ResolveResult,
    UnknownBarrierError,
    manual_open_barrier,
    resolve_event,
)
from uk_management_bot.api.dependencies import require_approved_roles
from uk_management_bot.database.session import get_db

router = APIRouter(prefix="/api/v1/access", tags=["access-operator"])

logger = logging.getLogger(__name__)

# Роли operator/admin API (§6.3, §3.2). executor/inspector/applicant — без доступа.
# M1: оператор должен быть approved (require_approved_roles) — pending-пользователь
# со старым токеном не получает доступ к ручному открытию/резолюции.
OPERATOR_ROLES = ("security_operator", "manager", "system_admin")

# Лимит длины пользовательских строк (L2): защита от чрезмерного ввода в audit.
_REASON_MAX_LEN = 2000
_SOURCE_MAX_LEN = 64

# Known-limitation (принятый риск пилота, M2): endpoint работает через СИНХРОННУЮ
# сессию (get_db из database.session), а require_approved_roles → get_current_user —
# через АСИНХРОННУЮ (две разные сессии в одном запросе). Для пилота приемлемо
# (auth-чтение и доменная запись не делят транзакцию). Унификация sync/async —
# отдельная задача после пилота.


def _client_ip(request: Request) -> str | None:
    """IP источника запроса для audit (§6.3). Для пилота достаточно client.host.

    Known-limitation: за доверенным прокси корректнее читать первый hop из
    ``X-Forwarded-For``; в пилоте прямой client.host достаточен.
    """
    return request.client.host if request.client else None


class ResolveRequest(BaseModel):
    """Тело резолюции (§9.5). Для manual_open обязательны barrier_id, reason, decision_id."""

    action: Literal["manual_open", "deny"]
    barrier_id: int | None = None
    reason: str | None = Field(
        None, max_length=_REASON_MAX_LEN, description="Причина (обязательна, непустая)"
    )
    decision_id: int | None = Field(None, description="Исходный decision_id")

    @model_validator(mode="after")
    def _check_required(self) -> "ResolveRequest":
        reason_ok = bool(self.reason and self.reason.strip())
        if not reason_ok:
            raise ValueError("reason is required and must be non-empty")
        if self.action == "manual_open" and (
            self.barrier_id is None or self.decision_id is None
        ):
            raise ValueError("manual_open requires barrier_id and decision_id")
        return self


class ManualOpenRequest(BaseModel):
    """Тело самостоятельного ручного открытия (§13.2): причина + audit source."""

    reason: str = Field(
        ..., min_length=1, max_length=_REASON_MAX_LEN, description="Причина (обязательна)"
    )
    source: str = Field(
        ...,
        min_length=1,
        max_length=_SOURCE_MAX_LEN,
        description="Audit source (аварийка/тех)",
    )

    @model_validator(mode="after")
    def _non_blank(self) -> "ManualOpenRequest":
        if not self.reason.strip():
            raise ValueError("reason must be non-empty")
        if not self.source.strip():
            raise ValueError("source must be non-empty")
        return self


class ResolveResponse(BaseModel):
    status: str
    decision_id: int
    decision_group_id: str
    command_id: str | None = None
    replayed: bool = False


class ManualOpenResponse(BaseModel):
    manual_opening_id: int
    command_id: str
    barrier_id: int


@router.post("/events/{event_id}/resolve", response_model=ResolveResponse)
def post_resolve(
    body: ResolveRequest,
    request: Request,
    event_id: int = Path(..., description="camera_event_id под review"),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*OPERATOR_ROLES)),
) -> ResolveResponse:
    """Зарезолвить manual_review: manual_open | deny (§9.5). Идемпотентно."""
    try:
        result: ResolveResult = resolve_event(
            db,
            event_id=event_id,
            action=body.action,
            operator_user_id=user.id,
            reason=body.reason,
            barrier_id=body.barrier_id,
            decision_id=body.decision_id,
            source="operator_resolve",
            ip_address=_client_ip(request),
        )
    except NoPendingReviewError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no active pending_review for event",
        )
    except DecisionIdMismatch as exc:
        # M5: переданный decision_id не совпал с текущим pending → 409.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "decision_id_mismatch", "message": str(exc)},
        )
    except BarrierUnavailableError as exc:
        # M3/M4: barrier деактивирован — manual_open невозможен (pending не залип).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "barrier_unavailable", "message": str(exc)},
        )
    except InvalidResolveAction as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return ResolveResponse(
        status=result.status,
        decision_id=result.decision_id,
        decision_group_id=result.decision_group_id,
        command_id=result.command_id,
        replayed=result.replayed,
    )


@router.post(
    "/barriers/{barrier_id}/manual-open", response_model=ManualOpenResponse
)
def post_manual_open(
    body: ManualOpenRequest,
    request: Request,
    barrier_id: int = Path(..., description="access_barriers.id"),
    db: Session = Depends(get_db),
    user=Depends(require_approved_roles(*OPERATOR_ROLES)),
) -> ManualOpenResponse:
    """Самостоятельное ручное открытие (§13.2). 409 при активном pending_review."""
    # TODO(accepted-risk L1, post-pilot): standalone manual-open не идемпотентен по
    # клиентскому ключу — двойной клик/повтор оператора создаёт два manual_opening.
    # Принятый риск пилота (одна точка, оператор у пульта); сузить idempotency-key'ом
    # после пилота.
    try:
        result: ManualOpenResult = manual_open_barrier(
            db,
            barrier_id=barrier_id,
            operator_user_id=user.id,
            reason=body.reason,
            source=body.source,
            ip_address=_client_ip(request),
        )
    except PendingReviewConflict as exc:
        logger.info(
            "manual-open blocked by active pending_review: barrier_id=%s event_id=%s",
            barrier_id,
            exc.event_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "pending_review_active",
                "event_id": exc.event_id,
            },
        )
    except UnknownBarrierError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="barrier not found"
        )
    except InvalidResolveAction as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return ManualOpenResponse(
        manual_opening_id=result.manual_opening_id,
        command_id=result.command_id,
        barrier_id=result.barrier_id,
    )
