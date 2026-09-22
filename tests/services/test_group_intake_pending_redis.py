"""AUD7-CODE-03/04: атомарность pending-состояния Group Intake на НАСТОЯЩЕМ Redis.

CODE-03: редактирование кандидата (адрес/категория/фаза лифта) шло GET → SETEX
без сравнения — воскрешало кандидата, которого подтверждение уже сняло GETDEL,
и повторное «Да» создавало вторую заявку. Теперь запись — CAS по ``rev``:
кандидат без ``rev`` пишется только в пустой ключ (NX), с ``rev`` — только
поверх той же ревизии.

CODE-04: INCR + отдельный EXPIRE лимитера LLM — сбой между ними оставлял
счётчик без TTL навсегда. Теперь одна Lua-операция, и ключ без TTL (наследие
прежнего сбоя) получает срок.

Redis: локальный uk-redis / сервис CI; без Redis — skip (как test_auth_otp_atomic).
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
import redis.asyncio as aioredis

from uk_management_bot.config.settings import settings
from uk_management_bot.services.group_intake import pending

pytestmark = pytest.mark.asyncio


async def _redis_available() -> bool:
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
    try:
        await r.ping()
        return True
    except Exception:
        return False
    finally:
        await r.aclose()


@pytest.fixture()
async def redis_client():
    if not await _redis_available():
        pytest.skip("Redis недоступен — тесты атомарности pending требуют настоящий Redis")
    await pending.aclose()
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield r
    finally:
        await r.aclose()
        await pending.aclose()


@pytest.fixture()
def ids():
    # Уникальные chat_id/message_id на тест — ключи не пересекаются между прогонами.
    return -100_000_000 - (uuid.uuid4().int % 10**9), uuid.uuid4().int % 10**9


PAYLOAD = {"kind": "residents", "author_id": 1, "source_message_id": 42, "text": "свет", "lang": "ru"}


async def test_fresh_store_assigns_rev_and_refuses_to_overwrite_live_candidate(redis_client, ids):
    chat_id, msg_id = ids
    assert await pending.store_candidate(chat_id, msg_id, PAYLOAD) is True
    stored = await pending.get_candidate(chat_id, msg_id)
    assert stored is not None and stored.get("rev")

    # Второй «свежий» store (без rev) поверх живого кандидата — отказ, rev прежний.
    assert await pending.store_candidate(chat_id, msg_id, {**PAYLOAD, "text": "другое"}) is False
    again = await pending.get_candidate(chat_id, msg_id)
    assert again["rev"] == stored["rev"] and again["text"] == "свет"


async def test_edit_after_confirm_does_not_resurrect_candidate(redis_client, ids):
    """Сценарий отчёта: сотрудник А открыл категорию (GET), сотрудник Б нажал «Да»
    (GETDEL), А выбрал категорию (SET) — кандидат воскресал, второе «Да» создавало
    вторую заявку."""
    chat_id, msg_id = ids
    await pending.store_candidate(chat_id, msg_id, PAYLOAD)
    seen_by_a = await pending.get_candidate(chat_id, msg_id)

    popped = await pending.pop_candidate(chat_id, msg_id)
    assert popped is not None

    edited = {k: v for k, v in seen_by_a.items() if k != "v"}
    edited["category"] = "plumbing"
    assert await pending.store_candidate(chat_id, msg_id, edited) is False
    assert await pending.get_candidate(chat_id, msg_id) is None
    assert await pending.pop_candidate(chat_id, msg_id) is None


async def test_stale_rev_is_rejected(redis_client, ids):
    chat_id, msg_id = ids
    await pending.store_candidate(chat_id, msg_id, PAYLOAD)
    first = await pending.get_candidate(chat_id, msg_id)

    edit_1 = {**{k: v for k, v in first.items() if k != "v"}, "category": "electricity"}
    edit_2 = {**{k: v for k, v in first.items() if k != "v"}, "category": "plumbing"}
    assert await pending.store_candidate(chat_id, msg_id, edit_1) is True
    assert await pending.store_candidate(chat_id, msg_id, edit_2) is False  # rev устарел

    current = await pending.get_candidate(chat_id, msg_id)
    assert current["category"] == "electricity" and current["rev"] != first["rev"]


async def test_concurrent_edits_with_same_rev_exactly_one_wins(redis_client, ids):
    chat_id, msg_id = ids
    await pending.store_candidate(chat_id, msg_id, PAYLOAD)
    first = await pending.get_candidate(chat_id, msg_id)
    base = {k: v for k, v in first.items() if k != "v"}

    results = await asyncio.gather(*[
        pending.store_candidate(chat_id, msg_id, {**base, "category": f"c{i}"}) for i in range(8)
    ])
    assert sum(results) == 1


async def test_store_after_pop_without_rev_is_a_fresh_candidate(redis_client, ids):
    """Фаза лифта: после «Да» (GETDEL) кандидат ставится заново под тем же ключом —
    это штатный переход, а не воскрешение: payload без rev → ключ пуст → пишем."""
    chat_id, msg_id = ids
    await pending.store_candidate(chat_id, msg_id, PAYLOAD)
    popped = await pending.pop_candidate(chat_id, msg_id)
    fresh = {k: v for k, v in popped.items() if k not in ("v", "rev")}
    assert await pending.store_candidate(chat_id, msg_id, {**fresh, "phase": "building"}, ttl=120) is True
    ttl = await redis_client.ttl(pending._cand_key(chat_id, msg_id))
    assert 0 < ttl <= 120


async def test_llm_counter_key_without_ttl_gets_expiry(redis_client, ids):
    """Наследие сбоя между INCR и EXPIRE: счётчик без TTL блокировал группу навсегда."""
    chat_id, _ = ids
    key = f"gint:llm:{chat_id}"
    await redis_client.set(key, "5")  # без TTL
    assert await redis_client.ttl(key) == -1

    await pending.llm_allowed(chat_id)

    ttl = await redis_client.ttl(key)
    assert 0 < ttl <= pending._LLM_WINDOW
    await redis_client.delete(key)


async def test_llm_counter_first_call_sets_window_and_limit_holds(redis_client, ids, monkeypatch):
    chat_id, _ = ids
    key = f"gint:llm:{chat_id}"
    monkeypatch.setattr(settings, "GROUP_INTAKE_LLM_PER_MINUTE", 3)

    results = await asyncio.gather(*[pending.llm_allowed(chat_id) for _ in range(5)])

    assert sorted(results) == [False, False, True, True, True]
    assert await redis_client.get(key) == "5"
    assert 0 < await redis_client.ttl(key) <= pending._LLM_WINDOW
    await redis_client.delete(key)


async def test_unmark_seen_lets_same_message_through_again(redis_client, ids):
    """A9-P2-6: отказ лимитера снимает dedup — повтор того же id не «дубль»."""
    chat_id, message_id = ids
    assert await pending.mark_seen(chat_id, message_id) is True
    assert await pending.mark_seen(chat_id, message_id) is False
    await pending.unmark_seen(chat_id, message_id)
    assert await pending.mark_seen(chat_id, message_id) is True
    await redis_client.delete(f"gint:seen:{chat_id}:{message_id}")


async def test_busy_notice_cooldown_once_per_window(redis_client, ids):
    chat_id, author_id = ids
    author_key = f"gint:busy:{chat_id}:{author_id}"
    chat_key = f"gint:busy:{chat_id}"
    assert await pending.busy_notice_allowed(chat_id, author_id) is True
    assert await pending.busy_notice_allowed(chat_id, author_id) is False
    assert 0 < await redis_client.ttl(chat_key) <= pending._LLM_WINDOW
    assert 0 < await redis_client.ttl(author_key) <= pending.BUSY_AUTHOR_COOLDOWN_TTL
    await redis_client.delete(author_key, chat_key)


async def test_busy_notice_one_reply_per_chat_for_many_authors(redis_client, ids):
    """Исчерпанный лимитер группы + 5 разных авторов → один ответ в чат, а не
    пять (иначе бот сам флудит в группу, которую лимитер защищает)."""
    chat_id, base = ids
    authors = [base + n for n in range(5)]
    results = await asyncio.gather(
        *[pending.busy_notice_allowed(chat_id, author) for author in authors]
    )
    assert sorted(results) == [False, False, False, False, True]
    await redis_client.delete(
        f"gint:busy:{chat_id}", *[f"gint:busy:{chat_id}:{a}" for a in authors]
    )


async def test_busy_notice_author_cooldown_outlives_chat_window(redis_client, ids):
    """Окно чата истекло — тот же автор всё ещё под своим (более длинным) cooldown."""
    chat_id, author_id = ids
    assert await pending.busy_notice_allowed(chat_id, author_id) is True
    await redis_client.delete(f"gint:busy:{chat_id}")
    assert await pending.busy_notice_allowed(chat_id, author_id) is False
    assert await pending.busy_notice_allowed(chat_id, author_id + 1) is True
    await redis_client.delete(
        f"gint:busy:{chat_id}", f"gint:busy:{chat_id}:{author_id}",
        f"gint:busy:{chat_id}:{author_id + 1}",
    )
