"""Классификатор Group Intake: глоссарий категорий в промпте и keyword-подсказка.

Без сети: клиент Anthropic подменяется фейком с AsyncMock `messages.create`.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from uk_management_bot.config.settings import settings
from uk_management_bot.keyboards.requests import SELECTABLE_CATEGORY_KEYS
from uk_management_bot.services.group_intake import classifier
from uk_management_bot.services.group_intake.classifier import (
    Outcome,
    _parse_response,
    _schema,
    _system_prompt,
    classify_message,
)


def _payload(category="other", **overrides):
    base = {
        "is_request": True,
        "category": category,
        "urgency": "high",
        "confidence": 0.99,
        "location_scope": "building",
        "address_hint": None,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _low_threshold(monkeypatch):
    monkeypatch.setattr(settings, "GROUP_INTAKE_MIN_CONFIDENCE", 0.5)


# ───────────── _parse_response: keyword переопределяет только «other» ─────────────


def test_keyword_overrides_llm_other():
    res = _parse_response(_payload("other"), keyword_category="electricity")
    assert res.outcome is Outcome.REQUEST
    assert res.category == "electricity"
    assert res.category_source == "keyword"


def test_keyword_does_not_override_llm_verdict():
    res = _parse_response(_payload("heating"), keyword_category="plumbing")
    assert res.category == "heating"
    assert res.category_source == "llm"


def test_no_keyword_keeps_other():
    res = _parse_response(_payload("other"), keyword_category=None)
    assert res.category == "other"
    assert res.category_source == "llm"


def test_not_request_ignores_keyword():
    res = _parse_response(_payload("other", is_request=False), keyword_category="electricity")
    assert res.outcome is Outcome.NOT_REQUEST
    assert res.category is None


# ───────────── промпт и схема строятся из канона ─────────────


def test_system_prompt_lists_every_selectable_category_with_labels():
    prompt = _system_prompt()
    for key in SELECTABLE_CATEGORY_KEYS:
        assert f"- {key} (" in prompt, key
    # RU и UZ лейбл рядом с ключом, пример из прод-текстов и правило про полив
    assert "electricity (Электрика / Elektrik)" in prompt
    assert "17 v da svet qachon keladi" in prompt
    assert "полив" in prompt.lower() and "landscaping" in prompt
    assert "other" in prompt


def test_schema_enum_is_selectable_not_full_canon():
    assert _schema()["properties"]["category"]["enum"] == list(SELECTABLE_CATEGORY_KEYS)
    assert "engineering" not in _schema()["properties"]["category"]["enum"]


# ───────────── classify_message: подсказка в user-сообщении ─────────────


def _fake_client(payload: dict):
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
    )
    create = AsyncMock(return_value=response)
    return SimpleNamespace(messages=SimpleNamespace(create=create)), create


@pytest.mark.asyncio
async def test_hint_appended_to_user_message_when_keyword_hits(monkeypatch):
    client, create = _fake_client(_payload("other"))
    monkeypatch.setattr(classifier, "_get_client", lambda: client)
    res = await classify_message("20v 48kv elektrik kerak")
    kwargs = create.await_args.kwargs
    assert "electricity (Электрика / Elektrik)" in kwargs["system"]
    user_content = kwargs["messages"][0]["content"]
    assert user_content.startswith("20v 48kv elektrik kerak")
    assert "предположительно electricity" in user_content
    # LLM сказал other → keyword переопределил
    assert res.category == "electricity"
    assert res.category_source == "keyword"


@pytest.mark.asyncio
async def test_no_hint_without_keyword(monkeypatch):
    client, create = _fake_client(_payload("other"))
    monkeypatch.setattr(classifier, "_get_client", lambda: client)
    res = await classify_message("26v 2-podyezd")
    user_content = create.await_args.kwargs["messages"][0]["content"]
    assert user_content == "26v 2-podyezd"
    assert res.category == "other"
    assert res.category_source == "llm"
