"""WebSocket-каналы дашборда менеджера и протокол отказов (П4).

Ключевая асимметрия, из-за которой клиент нельзя писать «по close-кодам»:
**до `accept()` close-кода не существует.** ASGI-сообщение `websocket.close` в
состоянии CONNECTING означает «апгрейд не состоялся», и ASGI-сервер обязан
ответить обычным HTTP; uvicorn отвечает **403**. Код, переданный в
`websocket.close(...)`, на провод в этом случае не попадает вообще.

    ┌───────────────────────────────┬──────────────────┬────────────────────────┐
    │ Ситуация                      │ На проводе       │ Что видит браузер      │
    ├───────────────────────────────┼──────────────────┼────────────────────────┤
    │ cookie/query-токен есть, но   │ HTTP 403,        │ onerror + onclose 1006,│
    │ невалиден / без exp / роль не │ апгрейда нет     │ onopen НЕ вызывался    │
    │ manager / БД отказала /       │                  │                        │
    │ чужой Origin (PENT-F05)       │                  │                        │
    ├───────────────────────────────┼──────────────────┼────────────────────────┤
    │ first-message auth не прошёл  │ close-кадр 1008  │ onclose 1008           │
    │ (нет токена за 10 с, мусор,   │                  │                        │
    │ роль не manager)              │                  │                        │
    ├───────────────────────────────┼──────────────────┼────────────────────────┤
    │ истёк exp во время стрима     │ close-кадр 4001  │ onclose 4001           │
    ├───────────────────────────────┼──────────────────┼────────────────────────┤
    │ доступ отозван во время       │ close-кадр 4003  │ onclose 4003           │
    │ стрима (блок / снятие роли)   │                  │                        │
    └───────────────────────────────┴──────────────────┴────────────────────────┘

Следствия, которые уже стоили ошибок:

* SPA ходит по cookie, поэтому 1008 для неё **недостижим**: любой отказ
  аутентификации приходит как 403 → 1006. Ветка `event.code === 1008` во фронте
  жива только ради cookieless-клиентов (first-message путь). Признак
  pre-upgrade отказа, доступный браузеру, — «закрылось, ни разу не открывшись»
  (`onclose` без предшествующего `onopen`), см. `frontend/src/hooks/useWebSocket.ts`.
* Различать на этом уровне 401 (токен просрочен, refresh поможет) и 403
  (доступа нет, refresh бесполезен) СМЫСЛА НЕТ: браузерный `WebSocket` API не
  отдаёт HTTP-статус проваленного хендшейка. Поэтому клиент восстанавливается
  по факту «не открылось», а не по статусу, и осознанно ограничивает себя одной
  попыткой refresh в окно.
* Тесты на объекте-дублёре (`FakeWS.closed_code`) и на
  `starlette.testclient.TestClient` для pre-upgrade пути показывают 1008 — оба
  короткозамыкают ASGI и HTTP-хендшейк не делают. Контракт провода проверяется
  только через живой ASGI-сервер: `tests/api/test_ws_wire_protocol.py`.
"""
import asyncio
import json as _json
import logging
import time
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from uk_management_bot.api.auth.service import verify_access_token
from uk_management_bot.config.settings import settings
from uk_management_bot.services.redis_pubsub import (
    subscribe_to_requests, subscribe_to_shifts, subscribe_to_buildings,
    subscribe_to_apartments,
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

# F-04: app close code (RFC 6455 range 4000-4999) "JWT expired" — the client
# refreshes the session and reconnects. Mirrored in access_control ws_security
# (which deliberately does not import from api routers).
WS_TOKEN_EXPIRED = 4001

# F-04 (остаток): доступ отозван УЖЕ во время сессии — пользователь заблокирован
# или лишён роли manager. Отдельный код, а не 4001: реконнект тут не поможет,
# и клиент не должен трактовать это как «обнови сессию и вернись».
WS_ACCESS_REVOKED = 4003

# Как часто перепроверять личность в БД во время стрима. Компромисс: окно, в
# которое заблокированный пользователь ещё получает события, против нагрузки
# (один короткий SELECT на соединение в минуту).
_WS_IDENTITY_RECHECK_INTERVAL = 60.0


async def _ws_identity_ok(user_id: int) -> bool:
    """Существует ли пользователь СЕЙЧАС, не заблокирован и всё ещё manager.

    Источник правды — БД, а не `roles` из JWT: токен это слепок на момент
    выдачи, и до его истечения снятие роли/блокировка иначе не замечались.
    Предикат намеренно повторяет HTTP-путь (`api/dependencies.get_current_user`
    + `require_roles("manager")`): одна дверь не должна быть мягче другой.

    Сессия открывается и ЗАКРЫВАЕТСЯ внутри вызова. Это не стилистика: держать
    сессию открытой на всё время WS-стрима — ровно тот класс бага, что уже
    стоил прод-инцидента в media-service (сессия жила через сетевой I/O → пул
    выеден → 504). Соединение живёт часами, пул — нет.
    """
    from uk_management_bot.api.dependencies import _parse_user_roles
    from uk_management_bot.database.session import AsyncSessionLocal
    from uk_management_bot.database.models.user import User

    if AsyncSessionLocal is None:
        raise RuntimeError("async session factory unavailable")

    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None or user.status == "blocked":
            return False
        return "manager" in _parse_user_roles(user)


def _payload_user_id(payload: dict) -> Optional[int]:
    """`sub` как int или None. Без него личность в БД не найти."""
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        return None


def _token_exp(payload: dict) -> Optional[float]:
    """Numeric ``exp`` claim or None.

    F-04: verify_access_token accepts a correctly signed JWT WITHOUT exp — such
    a token cannot bound the stream lifetime, so it is rejected at auth instead
    of raising KeyError mid-stream.
    """
    exp = payload.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        return None
    return float(exp)


# `_extract_roles` удалён вместе с последним его вызовом: роли WS больше не
# читает из JWT (F-04). Оставлять парсер «на всякий случай» вредно — он бы
# выглядел рабочим путём авторизации, которым уже не является.


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


def _origin_allowed(websocket: WebSocket) -> bool:
    """PENT-F05: Origin-гейт ДО `accept()`.

    Браузер НЕ применяет CORS к WebSocket: страница злоумышленника может
    открыть сокет к нашему домену, и браузер приложит куки жертвы. Куки здесь
    `SameSite=Strict`, что этот вектор уже закрывает, — Origin-гейт стоит
    вторым рубежом и страхует от тихой регрессии настройки куки (переключение
    на `lax`/`none` ради какого-нибудь кросс-поддоменного сценария не должно
    молча открывать WS всему интернету).

    Правило:
      * заголовка нет → пускаем. Его не шлют не-браузерные клиенты (бот, CLI,
        тесты), а у не-браузерного атакующего нет и куки жертвы — подделка
        Origin ему ничего не даёт;
      * есть → должен совпасть с origin'ом самого запроса (SPA живёт на том же
        домене, что и API: edge отдаёт `Host: profk.uz`) либо входить в
        `CORS_ORIGINS` (кросс-origin исключения вроде web.telegram.org).

    Именно «свой origin», а не только `CORS_ORIGINS`: список CORS перечисляет
    ИСКЛЮЧЕНИЯ, и `profk.uz` в нём нет — SPA ходит same-origin. Гейт только на
    нём отрезал бы живой дашборд profk.
    """
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    if origin in settings.CORS_ORIGINS:
        return True
    host = websocket.headers.get("host")
    return bool(host) and urlsplit(origin).netloc == host


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
    if not _origin_allowed(websocket):
        logger.warning(
            "WS отклонён по Origin %r (host %r)",
            websocket.headers.get("origin"), websocket.headers.get("host"),
        )
        await _safe_close(websocket)
        return None

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
    user_id = _payload_user_id(payload) if payload else None

    authorized = False
    if payload and user_id is not None and _token_exp(payload) is not None:
        # Роль решает БД, не токен (F-04). Любой сбой проверки — отказ:
        # fail-open здесь означал бы «пускаем всех, пока БД лежит».
        try:
            authorized = await _ws_identity_ok(user_id)
        except Exception:
            logger.warning(
                "WS identity check failed for user %s — closing (fail-closed)",
                user_id, exc_info=True,
            )
            authorized = False

    if not authorized:
        if accepted:
            await _safe_close(websocket)
        else:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    if not accepted:
        await websocket.accept()
    return payload


async def _pump_pubsub(websocket: WebSocket, pubsub) -> None:
    async for message in pubsub.listen():
        if message["type"] == "message":
            await websocket.send_text(message["data"])


async def _watch_client(websocket: WebSocket) -> None:
    """Дождаться ухода клиента (AUD5-APIFE-2).

    Раньше `receive()` не читался вообще, поэтому закрытие сокета клиентом
    никто не замечал: корутина висела на `pubsub.listen()`, а подписка Redis
    жила дальше — по одной осиротевшей подписке на каждый ушедший дашборд.
    Входящие сообщения после аутентификации не осмысленны, поэтому просто
    сливаем их: важен сам факт разрыва.
    """
    while True:
        await websocket.receive_text()


async def _watch_identity(user_id: Optional[int]) -> None:
    """Периодически сверяться с БД; вернуться, когда доступ отозван (F-04).

    Handshake-проверки мало: соединение живёт до истечения токена, то есть
    блокировка менеджера иначе вступала бы в силу через часы.
    """
    while True:
        await asyncio.sleep(_WS_IDENTITY_RECHECK_INTERVAL)
        if user_id is None:
            return
        try:
            if not await _ws_identity_ok(user_id):
                return
        except Exception:
            # Недоступность БД — не повод рвать живую сессию: handshake уже
            # состоялся, а верхнюю границу всё равно держит exp. Здесь
            # fail-open осознан и ограничен по времени, в отличие от handshake.
            logger.warning("WS identity re-check failed for user %s (keeping stream)",
                           user_id, exc_info=True)


async def _relay(websocket: WebSocket, payload: dict, pubsub) -> None:
    """Гнать события клиенту, пока держится ВСЁ сразу: exp, доступ и сам клиент.

    Четыре условия конкурируют; побеждает наступившее первым:
      * истёк `exp` → close 4001 (клиент обновит сессию и вернётся);
      * доступ отозван → close 4003 (возвращаться незачем);
      * клиент ушёл → тихий выход, `finally` вызывающего снимет подписку;
      * поток pubsub закончился → тихий выход.
    """
    exp = _token_exp(payload) or 0.0  # auth guarantees numeric exp; 0.0 fails closed
    user_id = _payload_user_id(payload)

    pump = asyncio.create_task(_pump_pubsub(websocket, pubsub))
    client = asyncio.create_task(_watch_client(websocket))
    identity = asyncio.create_task(_watch_identity(user_id))
    tasks = {pump, client, identity}

    try:
        done, pending = await asyncio.wait(
            tasks, timeout=max(0.0, exp - time.time()),
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for t in tasks:
            t.cancel()
        # Дожидаемся отмены — иначе задачи переживут хендлер и продолжат
        # писать в закрытый сокет.
        await asyncio.gather(*tasks, return_exceptions=True)

    close_code = None
    if not done:
        close_code = WS_TOKEN_EXPIRED          # сработал таймаут exp
    elif identity in done and not identity.cancelled():
        close_code = WS_ACCESS_REVOKED
    # client/pump в done — клиент уже ушёл или поток иссяк: закрывать нечего.

    if close_code is not None:
        try:
            await websocket.close(code=close_code)
        except RuntimeError:
            pass  # peer already gone


# Имя сохранено: на него ссылаются существующие тесты PR-15 (F-04, close 4001).
_relay_until_exp = _relay


async def _serve_ws(websocket: WebSocket, token: Optional[str], subscribe, label: str) -> None:
    """Общее тело всех трёх WS-эндпоинтов.

    Раньше это были три почти посимвольные копии (AUD5-APIFE-2), различавшиеся
    только функцией подписки и словом в тексте лога — из-за чего правка вроде
    чтения `receive()` требовала трёх одинаковых изменений и разъезжалась бы,
    как уже разъехались карты статусов на фронте.
    """
    payload = await authenticate_ws_manager(websocket, token)
    if payload is None:
        return

    pubsub = None
    redis_client = None
    try:
        pubsub, redis_client = await subscribe()
        await _relay(websocket, payload, pubsub)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("%s WebSocket error", label)
    finally:
        # Снятие подписки и закрытие клиента — обязательно и по отдельности:
        # сбой первого не должен оставить соединение Redis висеть.
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
            except Exception:
                logger.warning("Failed to unsubscribe from %s pubsub", label, exc_info=True)
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                logger.warning("Failed to close redis client (%s)", label, exc_info=True)


@router.websocket("/kanban")
async def kanban_ws(websocket: WebSocket, token: str = Query(default=None)):
    await _serve_ws(websocket, token, subscribe_to_requests, "kanban")


@router.websocket("/shifts")
async def shifts_ws(websocket: WebSocket, token: str = Query(default=None)):
    await _serve_ws(websocket, token, subscribe_to_shifts, "shifts")


@router.websocket("/buildings")
async def buildings_ws(websocket: WebSocket, token: str = Query(default=None)):
    await _serve_ws(websocket, token, subscribe_to_buildings, "buildings")


@router.websocket("/apartments")
async def apartments_ws(websocket: WebSocket, token: str = Query(default=None)):
    """Канал `apartments:updates` — события привязок жителей к квартирам.

    Канал публиковался и раньше (`apartment_request.*`), но подписчика со
    стороны дашборда не было. Раздел «Жители» ускоряется этим каналом, НЕ
    полагаясь на него: статусы аккаунта и верификации событий не имеют вовсе,
    поэтому polling там остаётся основным механизмом, а WS — ускорителем.
    """
    await _serve_ws(websocket, token, subscribe_to_apartments, "apartments")
