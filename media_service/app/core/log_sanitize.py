"""Санитизация токена бота в логах и исключениях media-service (E1, аудит 2026-08-18).

⚠ Нельзя логировать сырое исключение httpx рядом с Bot API: после
`raise_for_status()` httpx кладёт в текст исключения ПОЛНЫЙ URL запроса, а URL
Bot API содержит токен бота целиком. Токен — мастер-ключ бота.

Локальный близнец `uk_management_bot/utils/http_errors.py` — импортировать
оригинал media не может: в образ (`media_service/Dockerfile`) копируются только
`app/`, `client/`, `migrations/`. Контракт двух копий пиннится тестом
(`tests/services/test_media_sniff_contract.py` — образец приёма).
"""
from __future__ import annotations

import logging
import re
import traceback

# Та же форма, что в REDACT_WHOLE_PATTERNS структурного логгера бота.
_BOT_TOKEN_RE = re.compile(r"/bot\d+:[A-Za-z0-9_-]{20,}")


def describe_http_error(exc: BaseException) -> str:
    """Класс исключения (+ HTTP-статус, если он есть) — без URL и тела.

    Этого хватает, чтобы отличить таймаут от 429 и от 5xx; «какой именно
    ресурс» вызывающий добавляет сам из своих параметров, а не из URL.
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        return f"{type(exc).__name__} (HTTP {status})"
    return type(exc).__name__


def redact_token(text: str) -> str:
    return _BOT_TOKEN_RE.sub("/bot[REDACTED]", text)


class TelegramDownloadError(Exception):
    """Санитизированная замена исходного httpx-исключения (E1).

    Поднимается `from None`: исходное исключение несёт URL с токеном и не
    должно попасть ни в traceback (`formatException` печатает его сырьём),
    ни в debug-ответ глобального хендлера (`str(exc)` при DEBUG=true).
    """


class TokenSanitizingFilter(logging.Filter):
    """Второй рубеж на root-логгере: маскирует токен в message И в traceback.

    Стандартный Formatter кладёт `formatException(record.exc_info)` в вывод
    сырьём — фильтр поэтому ФОРМАТИРУЕТ traceback сам, санитизирует и отдаёт
    как `exc_text` (Formatter использует готовый exc_text вместо exc_info).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "/bot" in message:
            record.msg = redact_token(message)
            record.args = ()
        if record.exc_info and record.exc_info[0] is not None:
            formatted = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = redact_token(formatted)
            record.exc_info = None
        elif record.exc_text and "/bot" in record.exc_text:
            record.exc_text = redact_token(record.exc_text)
        return True


def install_root_filter() -> None:
    """Идемпотентно навешивает фильтр на root-хендлеры (зовётся из main.py)."""
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, TokenSanitizingFilter) for f in handler.filters):
            handler.addFilter(TokenSanitizingFilter())
