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


# ───────────── ревью 2026-09-03: служебная категория не протекает из ответа модели ─────────────


@pytest.mark.parametrize("leaked", ["engineering", "Инженерный разбор"])
def test_service_category_leaked_by_model_falls_back_to_other(leaked):
    """Схема сужена до SELECTABLE, но защитная проверка после парсинга обязана
    держать тот же список: `engineering` (очередь InfraSafe) человек в потоке
    группы выбрать не может — и модель отдать не должна."""
    res = _parse_response(_payload(leaked), keyword_category=None)
    assert res.outcome is Outcome.REQUEST
    assert res.category == "other"
    assert res.category_source == "llm"


def test_service_category_leaked_by_model_yields_to_keyword():
    res = _parse_response(_payload("engineering"), keyword_category="plumbing")
    assert res.category == "plumbing"
    assert res.category_source == "keyword"


# ───────────── 2026-09-22: ретрай разового сетевого сбоя (инцидент profk) ─────────────


def _ok_response(payload=None):
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=json.dumps(payload or _payload("other")))],
    )


@pytest.mark.asyncio
async def test_llm_timeout_is_retried_once_and_succeeds(monkeypatch):
    create = AsyncMock(side_effect=[TimeoutError(), _ok_response()])
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(classifier, "_get_client", lambda: client)
    res = await classify_message("нет света в подъезде дома 12")
    assert res.outcome is Outcome.REQUEST
    assert create.await_count == 2


@pytest.mark.asyncio
async def test_llm_connection_error_is_retried_once(monkeypatch):
    create = AsyncMock(side_effect=[ConnectionResetError(), _ok_response()])
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(classifier, "_get_client", lambda: client)
    res = await classify_message("нет света в подъезде дома 12")
    assert res.outcome is Outcome.REQUEST
    assert create.await_count == 2


@pytest.mark.asyncio
async def test_llm_two_transient_failures_yield_processing_error(monkeypatch):
    create = AsyncMock(side_effect=[TimeoutError(), TimeoutError()])
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(classifier, "_get_client", lambda: client)
    res = await classify_message("нет света в подъезде дома 12")
    assert res.outcome is Outcome.PROCESSING_ERROR
    assert create.await_count == 2


@pytest.mark.asyncio
async def test_llm_non_transient_error_is_not_retried(monkeypatch):
    """4xx/логическая ошибка — повтор бессмыслен (и стоит денег)."""
    create = AsyncMock(side_effect=ValueError("bad request"))
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(classifier, "_get_client", lambda: client)
    res = await classify_message("нет света в подъезде дома 12")
    assert res.outcome is Outcome.PROCESSING_ERROR
    assert create.await_count == 1


# ───────────── A9-P3-7: backoff между попытками, 429 + retry-after, лимитер ─────────────


class _RateLimited(Exception):
    """Утиный двойник anthropic.RateLimitError: status_code + response.headers."""

    def __init__(self, headers=None):
        super().__init__("rate limited")
        self.status_code = 429
        self.response = SimpleNamespace(headers=headers or {})


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    """Паузы между попытками — без реального ожидания, с записью задержек."""
    recorded = []

    async def _fake_sleep(delay):
        recorded.append(delay)

    monkeypatch.setattr(classifier, "_sleep", _fake_sleep, raising=False)
    return recorded


def _client_with(create):
    return SimpleNamespace(messages=SimpleNamespace(create=create))


@pytest.mark.asyncio
async def test_retry_waits_jittered_backoff(monkeypatch, sleeps):
    create = AsyncMock(side_effect=[TimeoutError(), _ok_response()])
    monkeypatch.setattr(classifier, "_get_client", lambda: _client_with(create))
    res = await classify_message("нет света в подъезде дома 12")
    assert res.outcome is Outcome.REQUEST
    assert len(sleeps) == 1
    base = classifier._BACKOFF_BASE
    assert base * 0.5 <= sleeps[0] <= base * 1.5


@pytest.mark.asyncio
async def test_429_honours_retry_after(monkeypatch, sleeps):
    create = AsyncMock(side_effect=[_RateLimited({"retry-after": "2"}), _ok_response()])
    monkeypatch.setattr(classifier, "_get_client", lambda: _client_with(create))
    res = await classify_message("нет света в подъезде дома 12")
    assert res.outcome is Outcome.REQUEST
    assert sleeps == [2.0]
    assert create.await_count == 2


@pytest.mark.asyncio
async def test_429_retry_after_beyond_budget_is_not_retried(monkeypatch, sleeps):
    monkeypatch.setattr(settings, "GROUP_INTAKE_LLM_TIMEOUT", 8.0)
    create = AsyncMock(side_effect=[_RateLimited({"retry-after": "30"}), _ok_response()])
    monkeypatch.setattr(classifier, "_get_client", lambda: _client_with(create))
    res = await classify_message("нет света в подъезде дома 12")
    assert res.outcome is Outcome.PROCESSING_ERROR
    assert create.await_count == 1
    assert sleeps == []


@pytest.mark.asyncio
async def test_retry_consults_limiter_gate(monkeypatch, sleeps):
    """Повтор — второй платный вызов: он обязан пройти тот же лимитер группы."""
    create = AsyncMock(side_effect=[TimeoutError(), _ok_response()])
    monkeypatch.setattr(classifier, "_get_client", lambda: _client_with(create))
    gate = AsyncMock(return_value=False)
    res = await classify_message("нет света в подъезде дома 12", retry_allowed=gate)
    assert res.outcome is Outcome.PROCESSING_ERROR
    gate.assert_awaited_once()
    assert create.await_count == 1


@pytest.mark.asyncio
async def test_retry_allowed_by_limiter_proceeds(monkeypatch, sleeps):
    create = AsyncMock(side_effect=[TimeoutError(), _ok_response()])
    monkeypatch.setattr(classifier, "_get_client", lambda: _client_with(create))
    gate = AsyncMock(return_value=True)
    res = await classify_message("нет света в подъезде дома 12", retry_allowed=gate)
    assert res.outcome is Outcome.REQUEST
    assert create.await_count == 2


# ───────────── A9-P3-5: телефоны маскируются перед отправкой в LLM ─────────────


@pytest.mark.parametrize(
    "phone",
    [
        "+998901234567",
        "998901234567",
        "901234567",
        "+998 90 123 45 67",
        "+998 (90) 123-45-67",
        "90-123-45-67",
        "(90) 123 45 67",
        "90 1234567",
    ],
)
def test_mask_phones_formats(phone):
    masked = classifier.mask_phones(f"течёт стояк, звоните {phone} дом 12 кв 45")
    assert masked == "течёт стояк, звоните [PHONE] дом 12 кв 45"


@pytest.mark.parametrize(
    "text",
    [
        "дом 12 кв 45 подъезд 3 этаж 9",
        "20v 48kv elektrik kerak",
        "17 v, 2-podyezd, 5 qavat",
        "с 10:00 до 18:00 нет воды",
        "счётчик 12345",
        "заявка 250923-001 повтор",
        "сумма 123 456 789 руб",
        "с 23.09.2026 нет горячей воды",
        "лицевой счёт 1234567890123",
    ],
)
def test_mask_phones_keeps_addresses_and_short_numbers(text):
    assert classifier.mask_phones(text) == text


def test_mask_phones_does_not_swallow_following_apartment():
    """Жадный шаблон съедал номер квартиры после телефона."""
    assert classifier.mask_phones("звоните 901234567 45 кв") == "звоните [PHONE] 45 кв"
    assert classifier.mask_phones("+998 90 123-45-67 45") == "[PHONE] 45"


@pytest.mark.asyncio
async def test_phone_on_text_limit_boundary_is_masked_whole(monkeypatch):
    """Маскирование ДО усечения: телефон на границе лимита не уходит хвостом."""
    client, create = _fake_client(_payload("plumbing"))
    monkeypatch.setattr(classifier, "_get_client", lambda: client)
    # без словарных маркеров — иначе к content добавится keyword-подсказка
    text = "x" * (classifier._TEXT_LIMIT - 6) + " +998901234567"
    await classify_message(text)
    content = create.await_args.kwargs["messages"][0]["content"]
    assert "9989" not in content
    assert len(content) == classifier._TEXT_LIMIT


# ───────────── A9-P3-7: общий дедлайн вызова (попытка + пауза + попытка) ─────────────


class _FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.mark.asyncio
async def test_retry_skipped_when_pause_exhausts_total_budget(monkeypatch):
    """Попытка 8 с + retry-after 7.5 с: по отдельности укладывались в бюджет
    одного вызова, вместе с повтором вышло бы ~23.5 с. Общий дедлайн —
    2 × таймаут: на повтор остаётся 0.5 с — меньше минимальной попытки."""
    monkeypatch.setattr(settings, "GROUP_INTAKE_LLM_TIMEOUT", 8.0)
    clock = _FakeClock()
    monkeypatch.setattr(classifier, "_now", clock, raising=False)
    slept = []

    async def _fake_sleep(delay):
        slept.append(delay)
        clock.now += delay

    monkeypatch.setattr(classifier, "_sleep", _fake_sleep)

    async def _slow_429(**_kwargs):
        clock.now += 8.0
        raise _RateLimited({"retry-after": "7.5"})

    create = AsyncMock(side_effect=_slow_429)
    monkeypatch.setattr(classifier, "_get_client", lambda: _client_with(create))
    res = await classify_message("нет света в подъезде дома 12")
    assert res.outcome is Outcome.PROCESSING_ERROR
    assert create.await_count == 1
    assert slept == []


@pytest.mark.asyncio
async def test_whole_call_fits_total_budget_in_real_time(monkeypatch):
    """Реальное время: зависающий провайдер — две попытки и пауза укладываются
    в 2 × таймаут, вторая попытка режется остатком дедлайна."""
    import asyncio
    import time

    monkeypatch.setattr(settings, "GROUP_INTAKE_LLM_TIMEOUT", 0.2)
    monkeypatch.setattr(classifier, "_BACKOFF_BASE", 0.1)
    monkeypatch.setattr(classifier, "_sleep", asyncio.sleep)

    async def _hang(**_kwargs):
        await asyncio.sleep(60)

    create = AsyncMock(side_effect=_hang)
    monkeypatch.setattr(classifier, "_get_client", lambda: _client_with(create))
    started = time.monotonic()
    res = await classify_message("нет света в подъезде дома 12")
    elapsed = time.monotonic() - started
    assert res.outcome is Outcome.PROCESSING_ERROR
    assert create.await_count == 2
    assert elapsed < 2 * 0.2 + 0.1


@pytest.mark.asyncio
async def test_classifier_sends_masked_text(monkeypatch):
    client, create = _fake_client(_payload("plumbing"))
    monkeypatch.setattr(classifier, "_get_client", lambda: client)
    await classify_message("Течёт стояк, дом 12 кв 45, звоните +998 90 123-45-67")
    content = create.await_args.kwargs["messages"][0]["content"]
    assert "[PHONE]" in content
    assert "123-45-67" not in content
    assert "дом 12 кв 45" in content
