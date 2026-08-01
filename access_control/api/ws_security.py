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

A6-P2-18 (закрыт бывший accepted-risk L3): во время стрима, как и на WS
дашборда UK, работают три конкурирующих вахты — чтение сокета (уход клиента
замечается сразу, подписка не сиротеет), периодическая ре-проверка личности в
БД (блокировка/отзыв роли → close 4003, а не «поток живёт до exp») и потолок
exp токена (close 4001). Handshake по-прежнему проверяет роли из claim.
"""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from access_control.services.event_broadcaster import get_broker
from uk_management_bot.api.auth.service import verify_access_token
from uk_management_bot.api.ws.router import _origin_allowed
from uk_management_bot.utils.auth_helpers import parse_roles_safe

router = APIRouter()

logger = logging.getLogger(__name__)

# Роли WS-панели охраны (§6.3/§3.2). executor/inspector/applicant — без доступа.
WS_ROLES = ("security_operator", "manager", "system_admin")

# WS close code «policy violation» (RFC 6455): отказ авторизации.
WS_POLICY_VIOLATION = 1008

# F-04: app-код (RFC 6455 диапазон 4000-4999) «JWT истёк» — клиент обновляет
# сессию и переподключается. Дублируется в uk_management_bot/api/ws/router.py
# (как и 1008/таймаут — access_control не импортирует из api-роутеров UK).
WS_TOKEN_EXPIRED = 4001

# A6-P2-18: app-код «доступ отозван» (блокировка/снятие роли в БД) — клиенту
# возвращаться незачем. Зеркало WS_ACCESS_REVOKED из uk_management_bot/api/ws/router.py.
WS_ACCESS_REVOKED = 4003

# Как часто перепроверять личность в БД во время стрима — тот же компромисс,
# что у _WS_IDENTITY_RECHECK_INTERVAL WS-дашборда: окно, в которое
# заблокированный оператор ещё видит события, против одного короткого SELECT
# на соединение в минуту.
_WS_IDENTITY_RECHECK_INTERVAL = 60.0

# F-05: сколько ждать первый auth-message cookieless-клиента. Без лимита
# неаутентифицированные idle-соединения копятся до исчерпания worker'а.
_WS_AUTH_MESSAGE_TIMEOUT = 10

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


def _payload_user_id(payload: dict | None) -> int | None:
    """Claim ``sub`` как int или None — без него личность в БД не найти."""
    try:
        return int((payload or {}).get("sub"))
    except (TypeError, ValueError):
        return None


def _ws_identity_ok_sync(user_id: int) -> bool:
    """Пользователь существует СЕЙЧАС, не заблокирован и всё ещё в WS-роли.

    Источник правды — БД, а не claim ``roles``: токен — слепок на момент выдачи,
    и до его истечения снятие роли/блокировка иначе не замечались (бывший
    accepted-risk L3). Парсинг ролей — тем же ``_parse_user_roles``, что и у
    HTTP/WS дверей UK: одна дверь не должна быть мягче другой.

    Сессия короткая, по одной на проверку, sync ``SessionLocal`` — как у
    retention-воркеров этого пакета; вызывать через ``asyncio.to_thread``.
    Импорты внутри вызова: модуль должен оставаться импортируемым без БД.
    """
    from uk_management_bot.api.dependencies import _parse_user_roles
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.session import SessionLocal

    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or user.status == "blocked":
            return False
        return any(role in WS_ROLES for role in _parse_user_roles(user))


def _token_exp(payload: dict | None) -> float | None:
    """Числовой claim ``exp`` или None.

    F-04: verify_access_token принимает корректно подписанный JWT и БЕЗ exp —
    такой токен нечем ограничить по времени, поэтому отвергается как отказ
    авторизации (None), а не падает KeyError'ом в стриме.
    """
    exp = (payload or {}).get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        return None
    return float(exp)


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
    # PENT-F05: чужой Origin отклоняем ДО accept, тем же правилом, что и на
    # WS дашборда (`uk_management_bot.api.ws.router._origin_allowed`) — здесь
    # такая же cookie-аутентификация, и расходиться этим двум гейтам нельзя.
    if not _origin_allowed(websocket):
        logger.warning(
            "WS охраны отклонён по Origin %r (host %r)",
            websocket.headers.get("origin"), websocket.headers.get("host"),
        )
        await _safe_close(websocket, code=WS_POLICY_VIOLATION)
        return

    # §9.6: JWT в query string запрещён — отклоняем ДО accept.
    if _has_query_token(websocket):
        await _safe_close(websocket, code=WS_POLICY_VIOLATION)
        return

    cookie_token = websocket.cookies.get("uk_access") or websocket.cookies.get(
        "access_token"
    )

    if cookie_token:
        # Путь cookie: проверяем роли и exp ДО accept, отказ — close без accept.
        payload = verify_access_token(cookie_token)
        exp = _token_exp(payload)
        if not _authorized_roles(payload) or exp is None:
            await _safe_close(websocket, code=WS_POLICY_VIOLATION)
            return
        await websocket.accept()
    else:
        # Cookieless: принимаем, ждём JWT в первом сообщении, затем проверяем роли.
        await websocket.accept()
        try:
            first = await asyncio.wait_for(
                websocket.receive_json(), timeout=_WS_AUTH_MESSAGE_TIMEOUT
            )
        except (TimeoutError, WebSocketDisconnect, ValueError, KeyError):
            # TimeoutError (=asyncio.TimeoutError в 3.11+) — F-05: молчащий клиент.
            await _safe_close(websocket, code=WS_POLICY_VIOLATION)
            return
        token = first.get("token") if isinstance(first, dict) else None
        payload = verify_access_token(token) if token else None
        exp = _token_exp(payload)
        if not _authorized_roles(payload) or exp is None:
            await _safe_close(websocket, code=WS_POLICY_VIOLATION)
            return

    await _stream_events(websocket, exp, _payload_user_id(payload))


async def _pump_events(websocket: WebSocket, subscription) -> None:
    while True:
        message = await subscription.get()
        await websocket.send_json(message.to_payload())


async def _watch_client(websocket: WebSocket) -> None:
    """Дождаться ухода клиента (зеркало AUD5-APIFE-2 с WS дашборда).

    Раньше сокет после аутентификации не читался вовсе — закрытие клиентом
    никто не замечал, и подписка на брокер жила до exp токена (≤60 мин) по
    одной сироте на каждый ушедший экран охраны. Входящие сообщения после
    auth не осмысленны — просто сливаем их: важен сам факт разрыва.
    """
    while True:
        await websocket.receive_text()


async def _watch_identity(user_id: int | None) -> None:
    """Периодически сверяться с БД; вернуться, когда доступ отозван (A6-P2-18).

    Вернуться = закрыть стрим 4003. Токен без валидного ``sub`` ре-проверить
    нечем — такой стрим тоже завершается на первом же тике (fail-closed).
    Недоступность БД — не повод рвать живую сессию: handshake уже состоялся,
    а верхнюю границу держит exp; здесь fail-open осознан и ограничен по времени.
    """
    while True:
        await asyncio.sleep(_WS_IDENTITY_RECHECK_INTERVAL)
        if user_id is None:
            return
        try:
            if not await asyncio.to_thread(_ws_identity_ok_sync, user_id):
                return
        except Exception:  # noqa: BLE001
            logger.warning(
                "ws security identity re-check failed for user %s (keeping stream)",
                user_id, exc_info=True,
            )


async def _stream_events(websocket: WebSocket, exp: float, user_id: int | None) -> None:
    """Подписаться на брокер и слать клиенту PD-safe события (§11) до отключения.

    Подписка создаётся ДО ready-фрейма: к моменту, когда клиент видит ``ready``,
    он уже подключён к брокеру и не пропустит последующие события.

    Дальше конкурируют четыре условия; побеждает наступившее первым (структура —
    зеркало ``_relay`` WS-дашборда UK):
      * истёк ``exp`` → close 4001 (клиент обновит сессию и вернётся);
      * доступ отозван в БД → close 4003 (возвращаться незачем);
      * клиент ушёл → тихий выход, finally снимет подписку;
      * ошибка стрима → лог, поток не роняет воркер.
    """
    subscription = get_broker().subscribe()
    try:
        await websocket.send_json({"type": "ready"})

        pump = asyncio.create_task(_pump_events(websocket, subscription))
        client = asyncio.create_task(_watch_client(websocket))
        identity = asyncio.create_task(_watch_identity(user_id))
        tasks = {pump, client, identity}
        try:
            done, _pending = await asyncio.wait(
                tasks, timeout=max(0.0, exp - time.time()),
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for t in tasks:
                t.cancel()
            # Осознанное отличие от `_relay` UK-дашборда: НЕ await'им реап
            # отменённых задач. `cancel()` гарантирует, что pump больше ничего
            # не отправит (его текущий await прерывается до следующего send), а
            # лишний await после ухода клиента проигрывает гонку teardown'а
            # ASGI-хоста (TestClient/anyio отменяет хендлер между disconnect и
            # реапом — CancelledError из cleanup маскирует штатное закрытие).

        if not done:
            # F-04: истечение JWT — штатное закрытие, НЕ ошибка.
            await _safe_close(websocket, code=WS_TOKEN_EXPIRED)
        elif identity in done and not identity.cancelled():
            await _safe_close(websocket, code=WS_ACCESS_REVOKED)
        else:
            # client/pump: уход клиента (WebSocketDisconnect) — тихий выход;
            # всё прочее — неожиданная ошибка стрима.
            for t in done:
                exc = t.exception()
                if exc is not None and not isinstance(exc, WebSocketDisconnect):
                    logger.error("ws security stream error", exc_info=exc)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — поток не должен ронять воркер
        logger.exception("ws security stream error")
    finally:
        subscription.close()
        await _safe_close(websocket)
