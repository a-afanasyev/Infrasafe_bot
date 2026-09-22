"""Redis-состояние Group Intake: pending-кандидаты, dedup, rate-limit, cooldown.

Отдельный клиент на settings.REDIS_URL (НЕ клиент rate-limiter'а — тот None
при выключенном флаге). Все хелперы fail-closed: сбой Redis → «нельзя»
(тишина в группе), а не исключение в хендлере. Закреплённое сообщение группы
компенсирует fail-silent («нет номера — нет заявки»).

Ключи:
  gint:cand:{chat_id}:{prompt_message_id} — кандидат (SETEX 1h, versioned JSON;
                                            запись — CAS по ``rev``, см. store_candidate)
  gint:seen:{chat_id}:{message_id}        — dedup исходных сообщений (24h)
  gint:llm:{chat_id}                      — LLM-лимит на группу (окно 60s)
  gint:invite:{telegram_id}               — cooldown приглашений (1h)
  gint:busy:{chat_id}                     — cooldown ответа при отказе лимитера на чат (60s)
  gint:busy:{chat_id}:{telegram_id}       — то же на автора (5 min)
"""
import json
import logging
import uuid
from typing import Any, Optional

from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)

PAYLOAD_VERSION = 1
CANDIDATE_TTL = 3600
SEEN_TTL = 86400
INVITE_COOLDOWN_TTL = 3600
BUSY_AUTHOR_COOLDOWN_TTL = 300
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


# AUD7-CODE-03: запись кандидата — одна атомарная операция вместо GET → SETEX.
# ARGV[3] — ожидаемая ревизия: пусто = «свежий» кандидат (только в пустой ключ,
# NX), иначе — только поверх той же ревизии (CAS). Возврат 1/0.
_STORE_CANDIDATE_LUA = """
local cur = redis.call('GET', KEYS[1])
if ARGV[3] == '' then
  if cur then return 0 end
else
  if not cur then return 0 end
  local ok, decoded = pcall(cjson.decode, cur)
  if not ok or type(decoded) ~= 'table' or decoded['rev'] ~= ARGV[3] then return 0 end
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return 1
"""


async def store_candidate(
    chat_id: int, prompt_message_id: int, payload: dict, *, ttl: int = CANDIDATE_TTL
) -> bool:
    """Сохранить кандидата под message_id ОТПРАВЛЕННОГО промпта. False = сбой/отказ.

    ``ttl`` — время жизни в секундах; фаза лифта (Ф4b) хранит кандидата
    короче общего часа, чтобы ответ после таймаута не создал заявку даже при
    потере in-process таймера (рестарт бота).

    AUD7-CODE-03 — compare-and-set по ``rev``: каждая запись получает новый
    ``rev``; payload С ``rev`` (правка адреса/категории/фазы лифта, полученного
    через get_candidate) пишется только поверх ТОЙ ЖЕ ревизии, payload БЕЗ
    ``rev`` (новый промпт; фаза лифта после pop) — только в пустой ключ. Так
    правка не воскрешает кандидата, которого подтверждение уже сняло GETDEL, и
    из двух одновременных правок побеждает одна. False на отказе CAS —
    вызывающий показывает «устарело», как при истёкшем TTL."""
    expected_rev = payload.get("rev") or ""
    stored = {k: v for k, v in payload.items() if k != "rev"}
    try:
        body = json.dumps(
            {"v": PAYLOAD_VERSION, **stored, "rev": uuid.uuid4().hex}, ensure_ascii=False
        )
        result = await _get_client().eval(
            _STORE_CANDIDATE_LUA, 1, _cand_key(chat_id, prompt_message_id), body, ttl, expected_rev
        )
        return result == 1
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


async def unmark_seen(chat_id: int, message_id: int) -> None:
    """Снять dedup-метку: сообщение не обработано (отказ лимитера в тег-режиме),
    его повтор/правка не должны считаться дублем. Best-effort."""
    try:
        await _get_client().delete(f"gint:seen:{chat_id}:{message_id}")
    except Exception as e:
        logger.warning("group_intake: unmark_seen failed: %s", type(e).__name__)


# Оба ключа проверяются и ставятся одной операцией: параллельные авторы не
# должны проскочить между проверкой чата и записью.
_BUSY_NOTICE_LUA = """
if redis.call('EXISTS', KEYS[1]) == 1 or redis.call('EXISTS', KEYS[2]) == 1 then
  return 0
end
redis.call('SET', KEYS[1], '1', 'EX', ARGV[1])
redis.call('SET', KEYS[2], '1', 'EX', ARGV[2])
return 1
"""


async def busy_notice_allowed(chat_id: int, telegram_id: int) -> bool:
    """Cooldown ответа «классификатор недоступен» при отказе лимитера.

    Не больше одного ответа в чат за окно лимитера (исчерпанный лимит группы
    = флуд; ответ каждому автору превратил бы бота в источник того же флуда)
    и не чаще раза в BUSY_AUTHOR_COOLDOWN_TTL одному автору."""
    try:
        result = await _get_client().eval(
            _BUSY_NOTICE_LUA, 2,
            f"gint:busy:{chat_id}", f"gint:busy:{chat_id}:{telegram_id}",
            _LLM_WINDOW, BUSY_AUTHOR_COOLDOWN_TTL,
        )
        return result == 1
    except Exception as e:
        logger.warning("group_intake: busy_notice_allowed failed: %s", type(e).__name__)
        return False


# AUD7-CODE-04: INCR и назначение окна — одной операцией. Раньше EXPIRE шёл
# отдельной командой и только при count == 1: сбой между ними оставлял счётчик
# без TTL навсегда, и группа переставала проходить лимит. Ключ без TTL (наследие
# такого сбоя) здесь тоже получает срок.
_LLM_INCR_LUA = """
local c = redis.call('INCR', KEYS[1])
if redis.call('TTL', KEYS[1]) < 0 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return c
"""


async def llm_allowed(chat_id: int) -> bool:
    """Лимит LLM-вызовов на группу в минуту (атомарный INCR + окно)."""
    key = f"gint:llm:{chat_id}"
    try:
        count = await _get_client().eval(_LLM_INCR_LUA, 1, key, _LLM_WINDOW)
        return int(count) <= settings.GROUP_INTAKE_LLM_PER_MINUTE
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
