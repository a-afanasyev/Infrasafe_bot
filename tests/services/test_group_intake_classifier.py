"""Классификатор Group Intake: фейковый Anthropic-клиент, все ветки исходов.

REQUEST / NOT_REQUEST / PROCESSING_ERROR не смешиваются: «сломалось» — это
не «не заявка» (в группе одинаково тихо, но логи/метрики различают).
"""
import json
from types import SimpleNamespace

import pytest

from uk_management_bot.services.group_intake import classifier
from uk_management_bot.services.group_intake.classifier import (
    Outcome,
    classify_message,
)


class FakeMessages:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return self.response


def _fake_client(monkeypatch, *, response=None, exc=None):
    messages = FakeMessages(response=response, exc=exc)
    monkeypatch.setattr(
        classifier, "_get_client", lambda: SimpleNamespace(messages=messages)
    )
    return messages


def _response(payload: dict, stop_reason: str = "end_turn"):
    block = SimpleNamespace(type="text", text=json.dumps(payload))
    return SimpleNamespace(stop_reason=stop_reason, content=[block])


_GOOD = {
    "is_request": True,
    "category": "plumbing",
    "urgency": "high",
    "confidence": 0.9,
    "location_scope": "building",
    "address_hint": "дом 12",
}


@pytest.mark.asyncio
async def test_happy_path(monkeypatch):
    messages = _fake_client(monkeypatch, response=_response(_GOOD))
    result = await classify_message("течёт стояк в доме 12")
    assert result.outcome is Outcome.REQUEST
    assert result.category == "plumbing"
    assert result.urgency == "high"
    assert result.location_scope == "building"
    assert result.address_hint == "дом 12"
    # structured outputs действительно запрошены
    assert "output_config" in messages.calls[0]
    assert messages.calls[0]["output_config"]["format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_not_request(monkeypatch):
    _fake_client(
        monkeypatch,
        response=_response({**_GOOD, "is_request": False, "confidence": 0.1}),
    )
    result = await classify_message("всем привет, как дела?")
    assert result.outcome is Outcome.NOT_REQUEST


@pytest.mark.asyncio
async def test_low_confidence_is_not_request(monkeypatch):
    _fake_client(monkeypatch, response=_response({**_GOOD, "confidence": 0.3}))
    result = await classify_message("что-то где-то как-то")
    assert result.outcome is Outcome.NOT_REQUEST


@pytest.mark.asyncio
async def test_garbage_category_and_urgency_fall_back(monkeypatch):
    payload = {**_GOOD, "category": "COSMIC_RAYS", "urgency": "МОЛНИЕНОСНО"}
    _fake_client(monkeypatch, response=_response(payload))
    result = await classify_message("сломалось что-то")
    assert result.outcome is Outcome.REQUEST
    assert result.category == "other"
    assert result.urgency == "low"


@pytest.mark.asyncio
async def test_uppercase_enums_normalized(monkeypatch):
    payload = {**_GOOD, "category": "Plumbing", "urgency": "HIGH", "location_scope": "Building"}
    _fake_client(monkeypatch, response=_response(payload))
    result = await classify_message("течёт")
    assert result.outcome is Outcome.REQUEST
    assert result.category == "plumbing"
    assert result.urgency == "high"
    assert result.location_scope == "building"


@pytest.mark.asyncio
async def test_address_hint_truncated_to_100(monkeypatch):
    payload = {**_GOOD, "address_hint": "д" * 500}
    _fake_client(monkeypatch, response=_response(payload))
    result = await classify_message("длинный адрес")
    assert result.address_hint is not None
    assert len(result.address_hint) == 100


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.5, 1.5])
async def test_bad_confidence_is_processing_error(monkeypatch, bad):
    _fake_client(monkeypatch, response=_response({**_GOOD, "confidence": bad}))
    result = await classify_message("x" * 30)
    assert result.outcome is Outcome.PROCESSING_ERROR


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
async def test_bad_stop_reason_is_processing_error(monkeypatch, stop_reason):
    _fake_client(monkeypatch, response=_response(_GOOD, stop_reason=stop_reason))
    result = await classify_message("x" * 30)
    assert result.outcome is Outcome.PROCESSING_ERROR


@pytest.mark.asyncio
async def test_empty_content_is_processing_error(monkeypatch):
    resp = SimpleNamespace(stop_reason="end_turn", content=[])
    _fake_client(monkeypatch, response=resp)
    result = await classify_message("x" * 30)
    assert result.outcome is Outcome.PROCESSING_ERROR


@pytest.mark.asyncio
async def test_invalid_json_is_processing_error(monkeypatch):
    block = SimpleNamespace(type="text", text="{broken json")
    resp = SimpleNamespace(stop_reason="end_turn", content=[block])
    _fake_client(monkeypatch, response=resp)
    result = await classify_message("x" * 30)
    assert result.outcome is Outcome.PROCESSING_ERROR


@pytest.mark.asyncio
async def test_exception_is_processing_error(monkeypatch):
    _fake_client(monkeypatch, exc=RuntimeError("network down"))
    result = await classify_message("x" * 30)
    assert result.outcome is Outcome.PROCESSING_ERROR


@pytest.mark.asyncio
async def test_timeout_is_processing_error(monkeypatch):
    import asyncio

    async def slow_create(**kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr(classifier.settings, "GROUP_INTAKE_LLM_TIMEOUT", 0.05)
    monkeypatch.setattr(
        classifier,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=slow_create)),
    )
    result = await classify_message("x" * 30)
    assert result.outcome is Outcome.PROCESSING_ERROR


@pytest.mark.asyncio
async def test_text_truncated_to_2000_before_llm(monkeypatch):
    messages = _fake_client(monkeypatch, response=_response(_GOOD))
    await classify_message("x" * 5000)
    sent = messages.calls[0]["messages"][0]["content"]
    assert len(sent) == 2000
