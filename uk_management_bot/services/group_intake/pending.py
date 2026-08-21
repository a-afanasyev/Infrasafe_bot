"""Redis-состояние Group Intake: pending-кандидаты, dedup, rate-limit, cooldown.

Отдельный клиент на settings.REDIS_URL (НЕ клиент rate-limiter'а — тот None
при выключенном флаге). Все хелперы fail-closed: сбой Redis → «нельзя»
(тишина в группе), а не исключение в хендлере. Закреплённое сообщение группы
компенсирует fail-silent («нет номера — нет заявки»).

Ключи:
  gint:cand:{chat_id}:{prompt_message_id} — кандидат (SETEX 1h, versioned JSON)
  gint:seen:{chat_id}:{message_id}        — dedup исходных сообщений (24h)
  gint:llm:{chat_id}                      — LLM-лимит на группу (окно 60s)
  gint:invite:{telegram_id}               — cooldown приглашений (1h)
"""
import json
import logging
from typing import Any, Optional

from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)

PAYLOAD_VERSION = 1
CANDIDATE_TTL = 3600
SEEN_TTL = 86400
INVITE_COOLDOWN_TTL = 3600
_LLM_WINDOW = 60
_SOCKET_TIMEOUT = 3

_client: Optional[Any] = None


def _get_client():
    global _client
    if _client is None:
        import redis.asyncio as redis_asyncio

        _client = redis_asyncio.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=_SOCKET_TIMEOUT,
            socket_timeout=_SOCKET_TIMEOUT,
        )
    return _client


async def startup_ping() -> bool:
    """PING на старте бота (best-effort, короткие socket-таймауты).

    False = Redis недоступен: фича молча деградирует (хелперы fail-closed),
    бот продолжает обслуживать остальное.
    """
    try:
        await _get_client().ping()
        return True
    except Exception as e:
        logger.error("group_intake: Redis недоступен на старте: %s", type(e).__name__)
        return False


async def aclose() -> None:
    global _client
    if _client is None:
        return
    try:
        await _client.aclose()
    except Exception:
        pass
    _client = None


def _cand_key(chat_id: int, prompt_message_id: int) -> str:
    return f"gint:cand:{chat_id}:{prompt_message_id}"


async def store_candidate(chat_id: int, prompt_message_id: int, payload: dict) -> bool:
    """Сохранить кандидата под message_id ОТПРАВЛЕННОГО промпта. False = сбой."""
    try:
        body = json.dumps({"v": PAYLOAD_VERSION, **payload}, ensure_ascii=False)
        await _get_client().setex(_cand_key(chat_id, prompt_message_id), CANDIDATE_TTL, body)
        return True
    except Exception as e:
        logger.warning("group_intake: store_candidate failed: %s", type(e).__name__)
        return False


def _parse_candidate(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("v") != PAYLOAD_VERSION:
        return None
    return payload


async def get_candidate(chat_id: int, prompt_message_id: int) -> Optional[dict]:
    """GET без снятия — для проверки авторства нажатия."""
    try:
        raw = await _get_client().get(_cand_key(chat_id, prompt_message_id))
    except Exception as e:
        logger.warning("group_intake: get_candidate failed: %s", type(e).__name__)
        return None
    return _parse_candidate(raw)


async def pop_candidate(chat_id: int, prompt_message_id: int) -> Optional[dict]:
    """GETDEL — идемпотентность «Да»: второй pop возвращает None."""
    try:
        raw = await _get_client().getdel(_cand_key(chat_id, prompt_message_id))
    except Exception as e:
        logger.warning("group_intake: pop_candidate failed: %s", type(e).__name__)
        return None
    return _parse_candidate(raw)


async def mark_seen(chat_id: int, message_id: int) -> bool:
    """True = сообщение свежее (обрабатываем). Дубль или сбой Redis → False."""
    try:
        return bool(
            await _get_client().set(
                f"gint:seen:{chat_id}:{message_id}", "1", nx=True, ex=SEEN_TTL
            )
        )
    except Exception as e:
        logger.warning("group_intake: mark_seen failed: %s", type(e).__name__)
        return False


async def llm_allowed(chat_id: int) -> bool:
    """Лимит LLM-вызовов на группу в минуту (INCR + EXPIRE на первом)."""
    key = f"gint:llm:{chat_id}"
    try:
        client = _get_client()
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, _LLM_WINDOW)
        return count <= settings.GROUP_INTAKE_LLM_PER_MINUTE
    except Exception as e:
        logger.warning("group_intake: llm_allowed failed: %s", type(e).__name__)
        return False


async def invite_allowed(telegram_id: int) -> bool:
    """Cooldown приглашений «в личный бот»: 1 раз в час на пользователя."""
    try:
        return bool(
            await _get_client().set(
                f"gint:invite:{telegram_id}", "1", nx=True, ex=INVITE_COOLDOWN_TTL
            )
        )
    except Exception as e:
        logger.warning("group_intake: invite_allowed failed: %s", type(e).__name__)
        return False
