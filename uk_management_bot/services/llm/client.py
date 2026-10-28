"""Общий LLM-клиент: Anthropic Messages API, structured outputs (json_schema).

Один вызов = «промпт → JSON-словарь или None». Поведение перенесено из
``group_intake/classifier.py`` дословно (инциденты profk 2026-09-22, A9-P3-7):
- best-effort: любая ошибка (таймаут, refusal, max_tokens, битый JSON,
  недоступность API) — ``None``, исключения наружу не выходят;
- разовый транзиентный сбой (таймаут, сеть, 5xx/429) повторяется ОДИН раз:
  после jitter-паузы, на 429 — после ``retry-after``, и только если повтор
  пропустил гейт вызывающего (``retry_allowed``) — повтор тоже платный вызов;
  весь вызов укладывается в общий дедлайн ``attempts × timeout``: пауза и
  вторая попытка берутся из остатка;
- ключ и тексты промптов в логи не пишутся.

Модуль импортирует только ``settings``, ``anthropic`` (лениво) и stdlib:
его тянет и выделенный процесс Group Intake, и API, и бот.
"""
import asyncio
import json
import logging
import math
import random
import time
from typing import Awaitable, Callable, Optional

from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)

# Пауза перед повтором: база × jitter [0.5, 1.5] — разводит одновременные
# повторы, не долбит провайдера в ту же секунду.
_BACKOFF_BASE = 1.0
# Вторая попытка короче четверти обычного таймаута почти наверняка не успеет —
# такой повтор только тратит деньги и лимит.
_MIN_ATTEMPT_SHARE = 0.25
_DEFAULT_ATTEMPTS = 2

# Паузы и часы — отдельными ссылками: тесты подменяют их без реального ожидания.
_sleep = asyncio.sleep
_sleep_sync = time.sleep
_now = time.monotonic

RetryGate = Callable[[], Awaitable[bool]]
SyncRetryGate = Callable[[], bool]

# Ленивая инициализация: модуль импортируется и в окружениях без ключа
# (тесты, выключенные флаги) — клиенты создаются при первом вызове.
_async_client = None
_sync_client = None


def _get_async_client():
    global _async_client
    if _async_client is None:
        from anthropic import AsyncAnthropic

        _async_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=0)
    return _async_client


def _get_sync_client():
    global _sync_client
    if _sync_client is None:
        from anthropic import Anthropic

        _sync_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=0)
    return _sync_client


# ───────────── ретрай ─────────────


def _status_code(exc: BaseException) -> Optional[int]:
    status = getattr(exc, "status_code", None)
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _is_transient(exc: BaseException) -> bool:
    """Сбой, который имеет смысл повторить: таймаут, обрыв соединения, 5xx/429.

    Логическая ошибка запроса (4xx кроме 429, невалидные данные) повтора не
    заслуживает — тот же запрос упадёт так же и стоит денег. HTTP-статус
    читается утиной типизацией (``status_code`` у ``anthropic.APIStatusError``).
    """
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, ConnectionError, OSError)):
        return True
    status = _status_code(exc)
    if status is not None:
        return status == 429 or status >= 500
    try:
        import anthropic
    except ImportError:  # pragma: no cover — в тестах SDK может отсутствовать
        return False
    return isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError))


def _retry_after(exc: BaseException) -> Optional[float]:
    """Секунды из ``retry-after-ms``/``retry-after`` ответа 429 (HTTP-дата — нет)."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None:
        return None
    for name, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        raw = headers.get(name)
        if raw is None:
            continue
        try:
            value = float(raw) * scale
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value >= 0:
            return value
    return None


def _retry_delay(exc: BaseException) -> float:
    """Пауза перед повтором: ``retry-after`` на 429, иначе jitter-backoff."""
    if _status_code(exc) == 429:
        server_delay = _retry_after(exc)
        if server_delay is not None:
            return server_delay
    return _BACKOFF_BASE * random.uniform(0.5, 1.5)


def _plan_retry(
    exc: BaseException, attempt: int, attempts: int, deadline: float, timeout: float, tag: str
) -> Optional[float]:
    """Пауза перед повтором или None, если повтора не будет (без учёта гейта)."""
    if attempt >= attempts or not _is_transient(exc):
        return None
    delay = _retry_delay(exc)
    if deadline - _now() - delay < timeout * _MIN_ATTEMPT_SHARE:
        # Пауза (jitter или retry-after провайдера) съедает остаток общего
        # дедлайна — вызывающий получит None раньше, чем бессмысленный повтор.
        logger.warning("%s.llm_retry_skipped: delay=%.1fs over budget", tag, delay)
        return None
    return delay


def _log_retry(exc: BaseException, attempt: int, delay: float, tag: str) -> None:
    logger.warning(
        "%s.llm_retry: attempt=%s failed: %s status=%s delay=%.2fs",
        tag, attempt, type(exc).__name__, _status_code(exc), delay,
    )


# ───────────── запрос и разбор ответа ─────────────


def _request_kwargs(
    *, system: str, user: str, schema: dict, model: str, max_tokens: int,
    effort: Optional[str], timeout: float,
) -> dict:
    output_config: dict = {"format": {"type": "json_schema", "schema": schema}}
    if effort:
        output_config = {**output_config, "effort": effort}
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": output_config,
        "timeout": timeout,
    }


def _payload(response, tag: str) -> Optional[dict]:
    """JSON-словарь из ответа модели; любая неполнота — None."""
    stop_reason = getattr(response, "stop_reason", None)
    if stop_reason in ("refusal", "max_tokens"):
        logger.warning("%s.processing_error: stop_reason=%s", tag, stop_reason)
        return None
    blocks = getattr(response, "content", None) or []
    text_block = next((b for b in blocks if getattr(b, "type", "") == "text"), None)
    if text_block is None or not getattr(text_block, "text", ""):
        logger.warning("%s.processing_error: empty content", tag)
        return None
    try:
        payload = json.loads(text_block.text)
    except (json.JSONDecodeError, TypeError):
        logger.warning("%s.processing_error: invalid json", tag)
        return None
    if not isinstance(payload, dict):
        logger.warning("%s.processing_error: json is not an object", tag)
        return None
    return payload


# ───────────── публичные вызовы ─────────────


async def llm_json_async(
    *,
    system: str,
    user: str,
    schema: dict,
    model: str,
    timeout: float,
    max_tokens: int,
    effort: Optional[str] = None,
    attempts: int = _DEFAULT_ATTEMPTS,
    retry_allowed: Optional[RetryGate] = None,
    tag: str = "llm",
) -> Optional[dict]:
    """Один structured-output вызов из async-слоя. Никогда не бросает.

    ``effort`` — ``output_config.effort`` (``low``…``max``); None — не
    передаётся (поведение Group Intake). ``retry_allowed`` — гейт повтора
    (лимитер вызывающего): повтор — второй платный вызов.
    """
    deadline = _now() + timeout * attempts
    for attempt in range(1, attempts + 1):
        attempt_budget = min(timeout, deadline - _now())
        try:
            async with asyncio.timeout(attempt_budget):
                response = await _get_async_client().messages.create(
                    **_request_kwargs(
                        system=system, user=user, schema=schema, model=model,
                        max_tokens=max_tokens, effort=effort, timeout=attempt_budget,
                    )
                )
            return _payload(response, tag)
        except Exception as e:  # таймаут, сеть, 4xx/5xx, что угодно — best-effort
            delay = _plan_retry(e, attempt, attempts, deadline, timeout, tag)
            if delay is None:
                logger.warning("%s.processing_error: llm call failed: %s", tag, type(e).__name__)
                return None
            if retry_allowed is not None and not await retry_allowed():
                logger.warning("%s.llm_retry_skipped: rate_limited", tag)
                return None
            _log_retry(e, attempt, delay, tag)
            await _sleep(delay)
    return None  # pragma: no cover — цикл всегда завершается return выше


def llm_json_sync(
    *,
    system: str,
    user: str,
    schema: dict,
    model: str,
    timeout: float,
    max_tokens: int,
    effort: Optional[str] = None,
    attempts: int = _DEFAULT_ATTEMPTS,
    retry_allowed: Optional[SyncRetryGate] = None,
    tag: str = "llm",
) -> Optional[dict]:
    """То же из синхронного кода (путь ``auto_dispatch_new_request_sync``).

    Таймаут попытки — HTTP-таймаут SDK (``timeout=`` в запросе); дедлайн и
    ретрай — как в async-варианте.
    """
    deadline = _now() + timeout * attempts
    for attempt in range(1, attempts + 1):
        attempt_budget = min(timeout, deadline - _now())
        try:
            response = _get_sync_client().messages.create(
                **_request_kwargs(
                    system=system, user=user, schema=schema, model=model,
                    max_tokens=max_tokens, effort=effort, timeout=attempt_budget,
                )
            )
            return _payload(response, tag)
        except Exception as e:
            delay = _plan_retry(e, attempt, attempts, deadline, timeout, tag)
            if delay is None:
                logger.warning("%s.processing_error: llm call failed: %s", tag, type(e).__name__)
                return None
            if retry_allowed is not None and not retry_allowed():
                logger.warning("%s.llm_retry_skipped: rate_limited", tag)
                return None
            _log_retry(e, attempt, delay, tag)
            _sleep_sync(delay)
    return None  # pragma: no cover
