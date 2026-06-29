"""WebSocket-панель охраны: live-трансляция событий доступа (§9.6, §15.13).

Endpoint ``/ws/v1/access/security`` принимает (§9.6):

* защищённую httpOnly cookie существующей web-сессии (``uk_access``); ИЛИ
* JWT в ПЕРВОМ WS-сообщении для cookieless-клиента (``{"token": "<jwt>"}``).

JWT в query string ЗАПРЕЩЁН (§9.6): если токен пришёл в query — соединение
отклоняется до accept. Роли проверяются из claim ``roles`` (=roles[], §3.2),
НЕ из ``active_role``: допускаются ``security_operator``, ``manager``,
``system_admin`` (§6.3). Иначе — close с policy-violation кодом 1008.

Декодирование JWT переиспользует ``verify_access_token`` из ``uk_management_bot``
(тот же секрет/алгоритм, что и web-сессия) — отдельной крипты тут нет.

После успешной аутентификации клиент подписывается на брокер и получает
PD-safe события доступа в реальном времени (§11: без полного номера/фото).

Known-limitation (пилот): аутентификация доверяет ролям из подписанного
непросроченного JWT без живой ре-проверки блокировки/отзыва роли в БД (read-only
поток для одной пилотной точки). Полная ре-проверка — после пилота.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from access_control.services.event_broadcaster import get_broker
from uk_management_bot.api.auth.service import verify_access_token
from uk_management_bot.utils.auth_helpers import parse_roles_safe

router = APIRouter()

logger = logging.getLogger(__name__)

# Роли WS-панели охраны (§6.3/§3.2). executor/inspector/applicant — без доступа.
WS_ROLES = ("security_operator", "manager", "system_admin")

# WS close code «policy violation» (RFC 6455): отказ авторизации.
WS_POLICY_VIOLATION = 1008

# Имена query-параметров, в которых JWT запрещён (§9.6).
_FORBIDDEN_QUERY_TOKEN_KEYS = ("token", "access_token", "jwt")


def _authorized_roles(payload: dict | None) -> bool:
    """Есть ли у токена хотя бы одна WS-роль (из claim ``roles``, §3.2).

    Claim ``roles`` в JWT — уже JSON-массив (jose декодирует в ``list``); на случай
    legacy CSV/JSON-строки делегируем парсинг в ``parse_roles_safe``.
    """
    if not payload:
        return False
    raw = payload.get("roles")
    if isinstance(raw, list):
        roles = [str(r) for r in raw]
    else:
        roles = parse_roles_safe(raw)
    return any(role in WS_ROLES for role in roles)


def _has_query_token(websocket: WebSocket) -> bool:
    """JWT в query string (§9.6: запрещён)."""
    return any(key in websocket.query_params for key in _FORBIDDEN_QUERY_TOKEN_KEYS)


async def _safe_close(websocket: WebSocket, code: int = 1000) -> None:
    """Закрыть WS, не падая на уже разорванном соединении.

    Если клиент отвалился до/во время handshake, повторный ``close`` бросает
    ``RuntimeError`` («Unexpected ASGI message 'websocket.close'») — глушим его,
    как и в ``_stream_events`` finally, чтобы не сорить трейсбеками в лог.
    """
    if websocket.client_state == WebSocketState.DISCONNECTED:
        return
    try:
        await websocket.close(code=code)
    except RuntimeError:
        pass


@router.websocket("/ws/v1/access/security")
async def ws_security(websocket: WebSocket) -> None:
    """WS-панель охраны: аутентификация (§9.6) + live-поток событий (§15.13)."""
    # §9.6: JWT в query string запрещён — отклоняем ДО accept.
    if _has_query_token(websocket):
        await _safe_close(websocket, code=WS_POLICY_VIOLATION)
        return

    cookie_token = websocket.cookies.get("uk_access") or websocket.cookies.get(
        "access_token"
    )

    if cookie_token:
        # Путь cookie: проверяем роли ДО accept, отказ — close без accept.
        if not _authorized_roles(verify_access_token(cookie_token)):
            await _safe_close(websocket, code=WS_POLICY_VIOLATION)
            return
        await websocket.accept()
    # TODO(accepted-risk L3, post-pilot): роли проверяются один раз при коннекте; при
    # отзыве роли в течение долгоживущей WS-сессии поток не разрывается. Принятый риск
    # пилота; после пилота — периодическая ре-проверка роли (короткий TTL/heartbeat).
    else:
        # Cookieless: принимаем, ждём JWT в первом сообщении, затем проверяем роли.
        await websocket.accept()
        try:
            first = await websocket.receive_json()
        except (WebSocketDisconnect, ValueError, KeyError):
            await _safe_close(websocket, code=WS_POLICY_VIOLATION)
            return
        token = first.get("token") if isinstance(first, dict) else None
        if not token or not _authorized_roles(verify_access_token(token)):
            await _safe_close(websocket, code=WS_POLICY_VIOLATION)
            return

    await _stream_events(websocket)


async def _stream_events(websocket: WebSocket) -> None:
    """Подписаться на брокер и слать клиенту PD-safe события (§11) до отключения.

    Подписка создаётся ДО ready-фрейма: к моменту, когда клиент видит ``ready``,
    он уже подключён к брокеру и не пропустит последующие события.
    """
    subscription = get_broker().subscribe()
    try:
        await websocket.send_json({"type": "ready"})
        while True:
            message = await subscription.get()
            await websocket.send_json(message.to_payload())
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — поток не должен ронять воркер
        logger.exception("ws security stream error")
    finally:
        subscription.close()
        await _safe_close(websocket)
