"""Единственная точка вызова Telegram Bot API из API-процесса (A9-P2-9).

До A9-P2-9 в API жили шесть самописных клиентов на сыром httpx (OTP-вход,
уведомления о регистрации и жителям, прокси документов, запрос номера, getMe
для инвайт-ссылки): у каждого свой таймаут, новое TLS на каждое сообщение,
403 «бот заблокирован» не доходил до ``users.bot_blocked_at``, а
``registration/notify`` не смотрел на статус ответа вовсе.

Здесь:

* **один переиспользуемый** ``httpx.AsyncClient`` на event loop с общей
  таймаут-политикой (``DEFAULT_TIMEOUT``; прокси документов передаёт свой);
  закрывается в shutdown (``api/lifecycle.py``);
* **единый результат** :class:`TelegramResult` со статусом
  ``ok`` / ``blocked`` / ``no_chat`` / ``error`` — функции модуля не поднимают
  сетевые исключения (кроме :func:`download_file`, у которого свой контракт);
* **один ретрай только на connect-сбой** (соединение не установлено —
  сообщение гарантированно не ушло, дубль невозможен); read-таймаут после
  отправки не ретраится;
* **403 → ``users.bot_blocked_at``** в отдельной короткой сессии (не держит
  транзакцию запроса) — тот же штамп, что пишет бот из ``my_chat_member``
  (``handlers/bot_membership.py``);
* **токен не попадает в лог**: URL с токеном собирается только здесь, текст
  исключений httpx не логируется (канон ``describe_http_error``), наружу
  исключения переподнимаются ``from None``.

Почему не общий aiogram-бот ``api_bot`` (``lifecycle.py``): он собран с
``parse_mode=HTML`` по умолчанию, а часть мест шлёт простой текст (адреса и
ФИО с ``<``/``&`` сломались бы), и у aiogram нет потокового скачивания с
лимитом, которое нужно прокси документов. Один httpx-клиент даёт те же
выгоды (общий пул соединений и таймаут) при байт-в-байт прежнем wire.

AST-гейт ``tests/api/test_telegram_send_gate.py`` держит инвариант: литералы
``api.telegram.org`` / ``/bot{…}`` в ``uk_management_bot/api/**`` есть только
в этом модуле.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from uk_management_bot.config.settings import settings
from uk_management_bot.utils.http_errors import describe_http_error

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org"

#: Общая таймаут-политика вызовов Bot API (все шесть мест исторически — 10 с).
DEFAULT_TIMEOUT = 10.0

STATUS_OK = "ok"
STATUS_BLOCKED = "blocked"    # 403: пользователь заблокировал бота / деактивирован
STATUS_NO_CHAT = "no_chat"    # 400 «chat not found»: человек не открывал чат с ботом
STATUS_ERROR = "error"        # сеть и прочие отказы Telegram

#: Тест-хук: подмена транспорта httpx (``httpx.MockTransport``). В проде None.
_transport: Optional[httpx.AsyncBaseTransport] = None

_client: Optional[httpx.AsyncClient] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None


@dataclass(frozen=True)
class TelegramResult:
    """Итог одного вызова Bot API."""

    status: str
    http_status: Optional[int] = None
    description: str = ""
    result: Any = None
    #: ``parameters.retry_after`` ответа 429 (секунды) — для троттлинга рассылок.
    retry_after: Optional[float] = None

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    def describe(self) -> str:
        """Безопасное для лога описание (без URL и токена)."""
        if self.http_status is None:
            return self.description or self.status
        return f"HTTP {self.http_status} ({self.description})"


class TelegramUnavailable(Exception):
    """Telegram не отдал файл (сеть/не-2xx). Текст — без URL и токена."""


class TelegramFileTooLarge(Exception):
    """Файл больше переданного лимита — скачивание прервано."""


def classify(status_code: int, description: str) -> str:
    """HTTP-ответ Telegram → статус (чистая функция)."""
    if 200 <= status_code < 300:
        return STATUS_OK
    if status_code == 403:
        # "Forbidden: bot was blocked by the user" и родня — писать нельзя,
        # пока человек сам не разблокирует бота.
        return STATUS_BLOCKED
    if status_code == 400 and "chat not found" in description.lower():
        return STATUS_NO_CHAT
    return STATUS_ERROR


def _get_client() -> httpx.AsyncClient:
    """Общий клиент на текущий event loop (пул соединений не переживает смену loop'а)."""
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client.is_closed or _client_loop is not loop:
        _client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, transport=_transport)
        _client_loop = loop
    return _client


async def aclose() -> None:
    """Закрыть общий клиент (shutdown API-процесса, фикстуры тестов)."""
    global _client, _client_loop
    client, _client, _client_loop = _client, None, None
    if client is not None and not client.is_closed:
        try:
            await client.aclose()
        except Exception as e:  # noqa: BLE001 — shutdown не должен падать
            logger.warning("Telegram-клиент API закрылся с ошибкой: %s", describe_http_error(e))


def _parse(response: httpx.Response) -> TelegramResult:
    try:
        body = response.json()
    except Exception:  # noqa: BLE001 — не-JSON тело (прокси, HTML-страница 5xx)
        body = {}
    if not isinstance(body, dict):
        body = {}
    description = str(body.get("description") or "")
    status = classify(response.status_code, description)
    if status == STATUS_OK and body.get("ok") is False:
        status = STATUS_ERROR
    parameters = body.get("parameters")
    retry_after = parameters.get("retry_after") if isinstance(parameters, dict) else None
    if not isinstance(retry_after, (int, float)) or isinstance(retry_after, bool):
        retry_after = None
    return TelegramResult(status, response.status_code, description, body.get("result"),
                          retry_after=retry_after)


async def call(
    method: str, payload: Optional[dict] = None, *, timeout: Optional[float] = None,
) -> TelegramResult:
    """POST ``/bot<TOKEN>/<method>`` с JSON-телом. Никогда не поднимает сетевые исключения."""
    token = settings.BOT_TOKEN
    if not token:
        logger.error("Telegram %s: BOT_TOKEN не задан", method)
        return TelegramResult(STATUS_ERROR, description="BOT_TOKEN не задан")
    url = f"{_API_BASE}/bot{token}/{method}"
    request_timeout = DEFAULT_TIMEOUT if timeout is None else timeout
    for attempt in (1, 2):
        try:
            response = await _get_client().post(
                url, json=payload or {}, timeout=request_timeout)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            logger.warning("Telegram %s: connect-сбой (попытка %s): %s",
                           method, attempt, describe_http_error(e))
            if attempt == 2:
                return TelegramResult(STATUS_ERROR, description=describe_http_error(e))
            continue
        except Exception as e:  # noqa: BLE001 — сеть; наружу только класс, без URL
            logger.error("Telegram %s: вызов не удался: %s", method, describe_http_error(e))
            return TelegramResult(STATUS_ERROR, description=describe_http_error(e))
        return _parse(response)
    return TelegramResult(STATUS_ERROR)  # pragma: no cover — цикл всегда возвращает


async def mark_bot_blocked(telegram_id: int) -> None:
    """Проставить ``users.bot_blocked_at`` по 403 — отдельной короткой сессией.

    Не трогает транзакцию запроса-вызывающего; уже стоящий штамп не
    перезаписывается. Сбой записи — лог, не исключение: доставка — best-effort.
    """
    from sqlalchemy import update

    from uk_management_bot.database import session as db_session
    from uk_management_bot.database.models.user import User

    factory = db_session.AsyncSessionLocal
    if factory is None:
        logger.debug("bot_blocked_at для %s не записан: нет async-сессии БД", telegram_id)
        return
    try:
        async with factory() as db:
            await db.execute(
                update(User)
                .where(User.telegram_id == telegram_id, User.bot_blocked_at.is_(None))
                .values(bot_blocked_at=datetime.now(timezone.utc))
            )
            await db.commit()
    except Exception:  # noqa: BLE001 — best-effort; в тексте ошибки БД токена нет
        logger.exception("Не удалось записать bot_blocked_at для %s", telegram_id)


async def send_message(
    chat_id: int,
    text: str,
    *,
    parse_mode: Optional[str] = None,
    reply_markup: Optional[dict] = None,
    mark_blocked: bool = True,
) -> TelegramResult:
    """``sendMessage``. ``parse_mode=None`` — простой текст (поле не отправляется).

    Отказ Telegram логируется здесь (статус + description — они без токена);
    ``blocked`` при ``mark_blocked`` пишет ``users.bot_blocked_at``.
    """
    payload: dict = {"chat_id": chat_id, "text": text}
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    result = await call("sendMessage", payload)
    if not result.ok:
        logger.warning("Telegram не доставил сообщение %s: %s (%s)",
                       chat_id, result.status, result.describe())
    if result.status == STATUS_BLOCKED and mark_blocked:
        await mark_bot_blocked(chat_id)
    return result


async def get_me() -> TelegramResult:
    return await call("getMe")


async def get_file(file_id: str, *, timeout: Optional[float] = None) -> TelegramResult:
    return await call("getFile", {"file_id": file_id}, timeout=timeout)


async def download_file(
    file_path: str, *, max_bytes: int, timeout: Optional[float] = None,
) -> bytes:
    """Скачать файл по ``file_path`` из :func:`get_file` целиком в память.

    Лимит проверяется по мере чтения (до отдачи заголовков клиенту).
    Raises: :class:`TelegramFileTooLarge`; :class:`TelegramUnavailable` —
    сеть/не-2xx (текст без URL, исходное исключение не цепляется).
    """
    token = settings.BOT_TOKEN
    if not token:
        raise TelegramUnavailable("BOT_TOKEN не задан")
    url = f"{_API_BASE}/file/bot{token}/{file_path}"
    chunks: list[bytes] = []
    size = 0
    try:
        async with _get_client().stream(
            "GET", url, timeout=DEFAULT_TIMEOUT if timeout is None else timeout,
        ) as response:
            if not 200 <= response.status_code < 300:
                raise TelegramUnavailable(f"HTTP {response.status_code}")
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise TelegramFileTooLarge(f"больше {max_bytes} байт")
                chunks.append(chunk)
    except (TelegramUnavailable, TelegramFileTooLarge):
        raise
    except Exception as e:  # noqa: BLE001 — сеть; текст httpx несёт URL с токеном
        raise TelegramUnavailable(describe_http_error(e)) from None
    return b"".join(chunks)
