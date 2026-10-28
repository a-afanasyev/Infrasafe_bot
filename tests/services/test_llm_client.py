"""Общий LLM-клиент (`services/llm/client.py`): цикл «вызов → ретрай → JSON».

Поведение перенесено из Group Intake дословно: одна попытка + один повтор
на транзиентном сбое, jitter/retry-after, общий дедлайн, гейт ``retry_allowed``.
Без сети: клиент Anthropic подменяется фейком.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from uk_management_bot.services.llm import client as llm


_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def _response(payload, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
    )


class _RateLimited(Exception):
    def __init__(self, headers=None):
        super().__init__("rate limited")
        self.status_code = 429
        self.response = SimpleNamespace(headers=headers or {})


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    recorded = []

    async def _fake_sleep(delay):
        recorded.append(delay)

    def _fake_sleep_sync(delay):
        recorded.append(delay)

    monkeypatch.setattr(llm, "_sleep", _fake_sleep)
    monkeypatch.setattr(llm, "_sleep_sync", _fake_sleep_sync)
    return recorded


def _async_client(monkeypatch, create):
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(llm, "_get_async_client", lambda: client)
    return client


def _sync_client(monkeypatch, create):
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(llm, "_get_sync_client", lambda: client)
    return client


def _call_async(**overrides):
    kwargs = dict(
        system="sys", user="hello", schema=_SCHEMA, model="m", timeout=8.0,
        max_tokens=50, tag="t",
    )
    kwargs.update(overrides)
    return llm.llm_json_async(**kwargs)


def _call_sync(**overrides):
    kwargs = dict(
        system="sys", user="hello", schema=_SCHEMA, model="m", timeout=8.0,
        max_tokens=50, tag="t",
    )
    kwargs.update(overrides)
    return llm.llm_json_sync(**kwargs)


# ───────────── happy path и форма запроса ─────────────


@pytest.mark.asyncio
async def test_async_happy_path_returns_payload_and_requests_json_schema(monkeypatch):
    create = AsyncMock(return_value=_response({"ok": True}))
    _async_client(monkeypatch, create)
    assert await _call_async() == {"ok": True}
    kwargs = create.await_args.kwargs
    assert kwargs["model"] == "m"
    assert kwargs["system"] == "sys"
    assert kwargs["messages"] == [{"role": "user", "content": "hello"}]
    assert kwargs["output_config"] == {"format": {"type": "json_schema", "schema": _SCHEMA}}


@pytest.mark.asyncio
async def test_effort_is_passed_only_when_given(monkeypatch):
    create = AsyncMock(return_value=_response({"ok": True}))
    _async_client(monkeypatch, create)
    await _call_async(effort="low")
    assert create.await_args.kwargs["output_config"]["effort"] == "low"


def test_sync_happy_path(monkeypatch):
    create = MagicMock(return_value=_response({"ok": True}))
    _sync_client(monkeypatch, create)
    assert _call_sync() == {"ok": True}
    assert create.call_args.kwargs["output_config"]["format"]["schema"] == _SCHEMA


# ───────────── отказы → None, без исключений ─────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
async def test_bad_stop_reason_is_none(monkeypatch, stop_reason):
    _async_client(monkeypatch, AsyncMock(return_value=_response({"ok": True}, stop_reason)))
    assert await _call_async() is None


@pytest.mark.asyncio
async def test_empty_content_is_none(monkeypatch):
    _async_client(monkeypatch, AsyncMock(return_value=SimpleNamespace(stop_reason="end_turn", content=[])))
    assert await _call_async() is None


@pytest.mark.asyncio
async def test_invalid_json_is_none(monkeypatch):
    resp = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="{broken")])
    _async_client(monkeypatch, AsyncMock(return_value=resp))
    assert await _call_async() is None


@pytest.mark.asyncio
async def test_non_dict_json_is_none(monkeypatch):
    resp = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="[1,2]")])
    _async_client(monkeypatch, AsyncMock(return_value=resp))
    assert await _call_async() is None


@pytest.mark.asyncio
async def test_timeout_is_none(monkeypatch):
    import asyncio

    async def slow(**kwargs):
        await asyncio.sleep(60)

    _async_client(monkeypatch, slow)
    assert await _call_async(timeout=0.05) is None


# ───────────── ретрай: транзиентный сбой повторяется один раз ─────────────


@pytest.mark.asyncio
async def test_transient_failure_retried_once_with_jitter(monkeypatch, sleeps):
    create = AsyncMock(side_effect=[TimeoutError(), _response({"ok": True})])
    _async_client(monkeypatch, create)
    assert await _call_async() == {"ok": True}
    assert create.await_count == 2
    assert len(sleeps) == 1
    assert llm._BACKOFF_BASE * 0.5 <= sleeps[0] <= llm._BACKOFF_BASE * 1.5


@pytest.mark.asyncio
async def test_two_transient_failures_yield_none(monkeypatch):
    create = AsyncMock(side_effect=[TimeoutError(), ConnectionResetError()])
    _async_client(monkeypatch, create)
    assert await _call_async() is None
    assert create.await_count == 2


@pytest.mark.asyncio
async def test_non_transient_error_not_retried(monkeypatch):
    create = AsyncMock(side_effect=ValueError("bad request"))
    _async_client(monkeypatch, create)
    assert await _call_async() is None
    assert create.await_count == 1


@pytest.mark.asyncio
async def test_429_honours_retry_after(monkeypatch, sleeps):
    create = AsyncMock(side_effect=[_RateLimited({"retry-after": "2"}), _response({"ok": True})])
    _async_client(monkeypatch, create)
    assert await _call_async() == {"ok": True}
    assert sleeps == [2.0]


@pytest.mark.asyncio
async def test_retry_after_beyond_budget_not_retried(monkeypatch, sleeps):
    create = AsyncMock(side_effect=[_RateLimited({"retry-after": "30"}), _response({"ok": True})])
    _async_client(monkeypatch, create)
    assert await _call_async(timeout=8.0) is None
    assert create.await_count == 1
    assert sleeps == []


@pytest.mark.asyncio
async def test_retry_consults_gate(monkeypatch, sleeps):
    create = AsyncMock(side_effect=[TimeoutError(), _response({"ok": True})])
    _async_client(monkeypatch, create)
    gate = AsyncMock(return_value=False)
    assert await _call_async(retry_allowed=gate) is None
    assert create.await_count == 1
    assert gate.await_count == 1
    assert sleeps == []


def test_sync_transient_failure_retried_once(monkeypatch, sleeps):
    create = MagicMock(side_effect=[TimeoutError(), _response({"ok": True})])
    _sync_client(monkeypatch, create)
    assert _call_sync() == {"ok": True}
    assert create.call_count == 2
    assert len(sleeps) == 1


def test_sync_non_transient_not_retried(monkeypatch):
    create = MagicMock(side_effect=ValueError("nope"))
    _sync_client(monkeypatch, create)
    assert _call_sync() is None
    assert create.call_count == 1
