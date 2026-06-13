import asyncio
import json as _json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from uk_management_bot.api.auth.service import verify_access_token
from uk_management_bot.services.redis_pubsub import (
    subscribe_to_requests, subscribe_to_shifts, subscribe_to_buildings,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# SEC-03: the ?token= query param leaks the JWT into access logs, proxy
# history and browser history. The web SPA authenticates via the httpOnly
# uk_access cookie (sent automatically on the WS upgrade). Token-based clients
# without a cookie should send the token as the FIRST WS message instead. The
# query param stays supported with a deprecation warning until the deadline
# below, then will be removed.
_WS_QUERY_TOKEN_DEPRECATED_UNTIL = "2026-09-01"
_WS_AUTH_MESSAGE_TIMEOUT = 10  # seconds to wait for the first-message token


def _extract_roles(payload: dict) -> list:
    roles = payload.get("roles", [])
    if isinstance(roles, str):
        try:
            roles = _json.loads(roles)
        except Exception:
            roles = [r.strip() for r in roles.split(',') if r.strip()]
    return roles


def _extract_token_from_message(raw: str) -> Optional[str]:
    """First-message auth payload: accept `{"token": "..."}`,
    `{"type":"auth","token":"..."}`, or a bare token string."""
    if not raw:
        return None
    try:
        obj = _json.loads(raw)
    except Exception:
        stripped = raw.strip()
        return stripped or None
    if isinstance(obj, dict):
        tok = obj.get("token")
        if isinstance(tok, str) and tok.strip():
            return tok.strip()
    return None


async def _safe_close(websocket: WebSocket) -> None:
    try:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    except RuntimeError:
        pass  # socket already closed by the peer


async def authenticate_ws_manager(
    websocket: WebSocket, query_token: Optional[str]
) -> Optional[dict]:
    """Authenticate a manager WebSocket.

    On success accepts the connection and returns the JWT payload; on failure
    closes the socket and returns None. Token source precedence:
      1. ``uk_access`` cookie (web SPA — preferred, validated before accept);
      2. ``access_token`` cookie (legacy transitional alias);
      3. ``?token=`` query param (DEPRECATED — SEC-03, logs a warning);
      4. first WS message (secure path for cookieless/token clients).
    """
    token = websocket.cookies.get("uk_access") or websocket.cookies.get("access_token")
    via_query = False
    if not token and query_token:
        token, via_query = query_token, True

    accepted = False
    if token is None:
        # First-message auth: must accept before we can receive the token.
        await websocket.accept()
        accepted = True
        try:
            raw = await asyncio.wait_for(
                websocket.receive_text(), timeout=_WS_AUTH_MESSAGE_TIMEOUT
            )
        except (asyncio.TimeoutError, WebSocketDisconnect, RuntimeError):
            await _safe_close(websocket)
            return None
        token = _extract_token_from_message(raw)
    elif via_query:
        logger.warning(
            "SEC-03: WebSocket auth via ?token= query is DEPRECATED "
            "(token leaks into access/proxy logs) and will be removed after %s. "
            "Send the token as the first WS message instead.",
            _WS_QUERY_TOKEN_DEPRECATED_UNTIL,
        )

    payload = verify_access_token(token) if token else None
    if not payload or "manager" not in _extract_roles(payload):
        if accepted:
            await _safe_close(websocket)
        else:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    if not accepted:
        await websocket.accept()
    return payload


@router.websocket("/kanban")
async def kanban_ws(websocket: WebSocket, token: str = Query(default=None)):
    if await authenticate_ws_manager(websocket, token) is None:
        return

    pubsub = None
    redis_client = None
    try:
        pubsub, redis_client = await subscribe_to_requests()
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
            except Exception:
                logger.warning("Failed to unsubscribe from pubsub", exc_info=True)
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                logger.warning("Failed to close redis client", exc_info=True)


@router.websocket("/shifts")
async def shifts_ws(websocket: WebSocket, token: str = Query(default=None)):
    if await authenticate_ws_manager(websocket, token) is None:
        return

    pubsub = None
    redis_client = None
    try:
        pubsub, redis_client = await subscribe_to_shifts()
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Shifts WebSocket error")
    finally:
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
            except Exception:
                logger.warning("Failed to unsubscribe from shifts pubsub", exc_info=True)
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                logger.warning("Failed to close redis client", exc_info=True)


@router.websocket("/buildings")
async def buildings_ws(websocket: WebSocket, token: str = Query(default=None)):
    if await authenticate_ws_manager(websocket, token) is None:
        return

    pubsub = None
    redis_client = None
    try:
        pubsub, redis_client = await subscribe_to_buildings()
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Buildings WebSocket error")
    finally:
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
            except Exception:
                logger.warning("Failed to unsubscribe from buildings pubsub", exc_info=True)
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                logger.warning("Failed to close redis client", exc_info=True)
