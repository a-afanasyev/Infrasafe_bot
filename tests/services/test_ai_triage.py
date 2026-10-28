"""ИИ-триаж новой заявки (services/ai_manager/triage.py) — чистые функции.

Два независимых анализатора: детерминированный `detect_emergency` (работает
всегда, в т.ч. при отказе LLM) и `llm_triage_sync` (structured output через
общий клиент). Итоговая срочность — максимум; LLM может только поднять.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from uk_management_bot.config.settings import settings
from uk_management_bot.services.ai_manager import triage
from uk_management_bot.services.ai_manager.triage import (
    LlmTriage,
    TriageHints,
    detect_emergency,
    final_urgency,
    llm_triage_sync,
    parse_llm_triage,
    triage_sync,
)
from uk_management_bot.services.llm import client as llm


# ───────────── детерминированная аварийность ─────────────


@pytest.mark.parametrize(
    "text",
    [
        "Запах газа в подъезде!",
        "подвал затопило, вода по щиколотку",
        "Lift qolib ketdi, ichida odam bor",
        "GAZ hidi kelyapti",
        "искрит розетка в щитке",
    ],
)
def test_detect_emergency_hits(text):
    assert detect_emergency(text) == "critical"


@pytest.mark.parametrize("text", ["течёт кран на кухне", "chiroq o'chdi", "", None])
def test_detect_emergency_misses(text):
    assert detect_emergency(text) is None


def test_final_urgency_is_max_and_never_lowers():
    assert final_urgency("high", TriageHints(emergency=None, llm=None)) == "high"
    assert final_urgency("low", TriageHints(emergency="critical", llm=None)) == "critical"
    low_llm = LlmTriage(category=None, urgency="low", needs_clarification=False,
                        clarification_question={}, duplicate_of=None, confidence=0.9, reasoning="")
    assert final_urgency("high", TriageHints(emergency=None, llm=low_llm)) == "high"
    assert final_urgency("garbage", TriageHints(emergency=None, llm=None)) == "low"


# ───────────── разбор ответа модели ─────────────


def _payload(**over):
    base = {
        "category": "electricity",
        "urgency": "high",
        "needs_clarification": False,
        "clarification_question_ru": "",
        "clarification_question_uz": "",
        "duplicate_of": None,
        "confidence": 0.92,
        "reasoning": "нет света в подъезде",
    }
    base.update(over)
    return base


def test_parse_happy_path():
    res = parse_llm_triage(_payload(), min_confidence=0.7, candidates=())
    assert isinstance(res, LlmTriage)
    assert res.category == "electricity"
    assert res.urgency == "high"
    assert res.needs_clarification is False
    assert res.duplicate_of is None
    assert res.confidence == 0.92


def test_parse_below_threshold_keeps_only_clarification():
    """Низкая уверенность = расплывчатый текст: категория/срочность/дубль в топку, вопрос — остаётся."""
    res = parse_llm_triage(_payload(confidence=0.5, needs_clarification=True,
                                    clarification_question_ru="Что именно не работает?",
                                    clarification_question_uz="Aynan nima ishlamayapti?",
                                    duplicate_of="261028-001"),
                           min_confidence=0.7, candidates=("261028-001",))
    assert res is not None
    assert res.category is None and res.urgency is None and res.duplicate_of is None
    assert res.needs_clarification and res.clarification_question["ru"] == "Что именно не работает?"
    assert res.confidence == 0.5
    quiet = parse_llm_triage(_payload(confidence=0.5), min_confidence=0.7, candidates=())
    assert quiet is not None and not quiet.needs_clarification and quiet.category is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, 1.5, "0.9"])
def test_parse_bad_confidence_is_none(bad):
    assert parse_llm_triage(_payload(confidence=bad), min_confidence=0.7, candidates=()) is None


def test_parse_unknown_category_means_no_change():
    res = parse_llm_triage(_payload(category="COSMIC"), min_confidence=0.7, candidates=())
    assert res is not None and res.category is None


def test_parse_service_category_does_not_leak():
    res = parse_llm_triage(_payload(category="engineering"), min_confidence=0.7, candidates=())
    assert res is not None and res.category is None


def test_parse_bad_urgency_means_no_change():
    res = parse_llm_triage(_payload(urgency="МОЛНИЕНОСНО"), min_confidence=0.7, candidates=())
    assert res is not None and res.urgency is None


def test_parse_clarification_requires_question():
    res = parse_llm_triage(_payload(needs_clarification=True), min_confidence=0.7, candidates=())
    assert res is not None and res.needs_clarification is False
    res = parse_llm_triage(
        _payload(needs_clarification=True, clarification_question_ru="Где именно?",
                 clarification_question_uz="Qayerda aynan?"),
        min_confidence=0.7, candidates=(),
    )
    assert res is not None and res.needs_clarification is True
    assert res.clarification_question == {"ru": "Где именно?", "uz": "Qayerda aynan?"}


def test_parse_duplicate_only_from_candidates():
    res = parse_llm_triage(_payload(duplicate_of="261028-001"), min_confidence=0.7, candidates=())
    assert res is not None and res.duplicate_of is None
    res = parse_llm_triage(_payload(duplicate_of="261028-001"), min_confidence=0.7,
                           candidates=("261028-001",))
    assert res is not None and res.duplicate_of == "261028-001"


def test_parse_reasoning_truncated_and_missing_keys_is_none():
    res = parse_llm_triage(_payload(reasoning="x" * 1000), min_confidence=0.7, candidates=())
    assert res is not None and len(res.reasoning) == 200
    assert parse_llm_triage({"category": "electricity"}, min_confidence=0.7, candidates=()) is None


# ───────────── вызов через общий клиент ─────────────


def _response(payload):
    return SimpleNamespace(stop_reason="end_turn",
                           content=[SimpleNamespace(type="text", text=json.dumps(payload))])


def _sync_client(monkeypatch, create):
    monkeypatch.setattr(llm, "_get_sync_client",
                        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))


def test_llm_triage_uses_settings_model_effort_and_context(monkeypatch):
    create = MagicMock(return_value=_response(_payload()))
    _sync_client(monkeypatch, create)
    monkeypatch.setattr(settings, "AI_MANAGER_MODEL", "claude-haiku-5-5")
    monkeypatch.setattr(settings, "AI_MANAGER_EFFORT", "low")
    res = llm_triage_sync(
        "нет света в подъезде, звоните +998901234567", category="plumbing", lang="uz",
        open_same_address=(("261028-001", "electricity", "свет моргает"),), min_confidence=0.7,
    )
    assert res is not None and res.category == "electricity"
    kw = create.call_args.kwargs
    assert kw["model"] == "claude-haiku-5-5"
    assert kw["output_config"]["effort"] == "low"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    user = kw["messages"][0]["content"]
    assert "[PHONE]" in user and "9989" not in user
    assert "plumbing" in user and "uz" in user
    assert "261028-001" in user
    # промпт стабилен (кэшируется провайдером): глоссарий в system, не в user
    assert "electricity (" in kw["system"]


def test_llm_triage_failure_is_none(monkeypatch):
    _sync_client(monkeypatch, MagicMock(side_effect=ValueError("boom")))
    assert llm_triage_sync("x", category="plumbing", lang="ru",
                           open_same_address=(), min_confidence=0.7) is None


def test_triage_sync_keeps_emergency_when_llm_fails(monkeypatch):
    _sync_client(monkeypatch, MagicMock(side_effect=ValueError("boom")))
    hints = triage_sync("запах газа на кухне", category="plumbing", lang="ru",
                        open_same_address=(), min_confidence=0.7)
    assert hints.emergency == "critical"
    assert hints.llm is None
    assert final_urgency("low", hints) == "critical"


def test_schema_is_flat_for_structured_outputs():
    """Structured outputs: без minimum/maximum/maxLength/enum — диапазоны и
    словари проверяет parse_llm_triage."""
    schema = triage._schema()
    dumped = json.dumps(schema)
    for banned in ("minimum", "maximum", "maxLength", "enum"):
        assert banned not in dumped
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


# ───────────── правила со страницы «Правила ИИ» ─────────────


def test_detect_emergency_base_keywords_plus_extra():
    assert detect_emergency("сломался шлагбаум", extra=("шлагбаум",)) == "critical"
    assert detect_emergency("утечка газа", extra=("шлагбаум",)) == "critical"   # базовые неотключаемы
    assert detect_emergency("шум у соседей", extra=("шлагбаум",)) is None


def test_triage_instructions_land_in_system_prompt(monkeypatch):
    create = MagicMock(return_value=_response(_payload()))
    _sync_client(monkeypatch, create)
    triage.llm_payload_sync("нет света", category=None, lang="ru", open_same_address=(),
                            instructions="Шум — не аварийно.")
    system = create.call_args.kwargs["system"]
    assert "Правила управляющей компании" in system and "Шум — не аварийно." in system
    assert system.index("Глоссарий категорий") < system.index("Правила управляющей компании")
    triage.llm_payload_sync("нет света", category=None, lang="ru", open_same_address=())
    assert "Правила управляющей компании" not in create.call_args.kwargs["system"]
