"""Безопасное описание сбоя HTTP-вызова для лога.

⚠ **Нельзя логировать сырое исключение httpx рядом с Bot API.** После
`raise_for_status()` httpx кладёт в текст исключения полный URL запроса, а URL
Bot API содержит токен бота целиком:

    Server error '500 …' for url
    'https://api.telegram.org/bot<ТОКЕН>/getFile?file_id=…'

Токен бота — мастер-ключ: чтение всех апдейтов, отправка от имени бота,
скачивание любого файла, который бот видел. Логи (docker + сборщик) не то
место, где он должен оказаться.

`SecurityFilter` в `utils/structured_logger.py` вычищает эту форму как защита
в глубину, но полагаться только на него нельзя: он навешивается лишь при
`DEBUG=False`, и регэксп — не повод логировать секрет.
"""

from __future__ import annotations


def describe_http_error(exc: BaseException) -> str:
    """Класс исключения (+ HTTP-статус, если он есть) — без URL и тела.

    Этого хватает, чтобы отличить таймаут от 429 и от 5xx; «какой именно
    ресурс» вызывающий добавляет сам из своих параметров, а не из URL.
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        return f"{type(exc).__name__} (HTTP {status})"
    return type(exc).__name__
