"""Блок ``ai`` конфига автоменеджера: дефолты, вложенный merge, валидация.

``validate_config`` мёржит верхний уровень shallow — вложенный ``ai`` обязан
мёржиться поверх своих дефолтов отдельно, иначе частичный PUT затирает их.
"""
import pytest

from uk_management_bot.services.auto_manager.config import DEFAULT_CONFIG, validate_config


def test_ai_defaults():
    ai = DEFAULT_CONFIG["ai"]
    assert ai["min_confidence"] == 0.7 and ai["clarify_enabled"] and ai["dedup_enabled"]
    assert ai["triage_instructions"] == "" and ai["news_instructions"] == ""
    assert ai["extra_emergency_keywords"] == [] and ai["templates"] == {}
    assert validate_config({})["ai"] == DEFAULT_CONFIG["ai"]


def test_ai_partial_dict_merges_over_defaults():
    cfg = validate_config({"ai": {"min_confidence": 0.9}})
    assert cfg["ai"] == {**DEFAULT_CONFIG["ai"], "min_confidence": 0.9}


def test_ai_instructions_and_extra_keywords_normalized():
    cfg = validate_config({"ai": {
        "triage_instructions": "  Шум — не аварийно.  ", "news_instructions": " 7-й корпус ",
        "extra_emergency_keywords": [" Шлагбаум ", "шлагбаум", "", "газ"],
    }})
    assert cfg["ai"]["triage_instructions"] == "Шум — не аварийно."
    assert cfg["ai"]["news_instructions"] == "7-й корпус"
    # strip+lower, дедуп, базовые слова (газ) не дублируются в дополнительных
    assert cfg["ai"]["extra_emergency_keywords"] == ["шлагбаум"]


@pytest.mark.parametrize("bad", [
    {"triage_instructions": "x" * 2001},
    {"news_instructions": 5},
    {"extra_emergency_keywords": "газ"},
    {"extra_emergency_keywords": ["x" * 51]},
    {"extra_emergency_keywords": ["а"]},   # код-ревью M1: подстрока «а» есть в любом тексте → всё critical
    {"extra_emergency_keywords": ["ab"]},
    {"extra_emergency_keywords": [f"word{i}" for i in range(101)]},
    {"templates": []},
    {"templates": {"nope": {"ru": "x"}}},
    {"templates": {"sla.executor_overdue": {"ru": "{unknown} поле"}}},
    {"templates": {"sla.executor_overdue": {"ru": "{request_number:>10}"}}},
    {"templates": {"sla.executor_overdue": {"ru": "{request_number!r}"}}},
    {"templates": {"sla.executor_overdue": {"ru": "<div>{request_number}</div>"}}},
    {"templates": {"sla.executor_overdue": {"ru": "<b>{request_number}"}}},
    {"templates": {"sla.executor_overdue": {"ru": "x" * 1001}}},
    {"templates": {"sla.executor_overdue": {"de": "x"}}},
])
def test_ai_rejects_bad_new_values(bad):
    with pytest.raises(ValueError):
        validate_config({"ai": bad})


def test_ai_templates_keep_only_non_empty_overrides():
    cfg = validate_config({"ai": {"templates": {
        "sla.executor_overdue": {"ru": "⏰ <b>№{request_number}</b> просрочена", "uz": ""},
        "public.assigned": {"ru": "", "uz": ""},
    }}})
    assert cfg["ai"]["templates"] == {"sla.executor_overdue": {"ru": "⏰ <b>№{request_number}</b> просрочена"}}


def test_ai_none_means_defaults():
    assert validate_config({"ai": None})["ai"] == DEFAULT_CONFIG["ai"]


@pytest.mark.parametrize(
    "bad",
    [
        {"min_confidence": 1.5},
        {"min_confidence": -0.1},
        {"min_confidence": "high"},
        {"min_confidence": True},
        {"clarify_enabled": "yes"},
        {"dedup_enabled": 1},
        {"unknown": 1},
        "not-a-dict",
    ],
)
def test_ai_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        validate_config({"ai": bad})


def test_ai_validate_does_not_mutate_defaults():
    validate_config({"ai": {"min_confidence": 0.5}})
    assert DEFAULT_CONFIG["ai"]["min_confidence"] == 0.7
