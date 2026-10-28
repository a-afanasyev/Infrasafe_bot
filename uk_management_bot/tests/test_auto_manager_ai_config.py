"""Блок ``ai`` конфига автоменеджера: дефолты, вложенный merge, валидация.

``validate_config`` мёржит верхний уровень shallow — вложенный ``ai`` обязан
мёржиться поверх своих дефолтов отдельно, иначе частичный PUT затирает их.
"""
import pytest

from uk_management_bot.services.auto_manager.config import DEFAULT_CONFIG, validate_config


def test_ai_defaults():
    assert DEFAULT_CONFIG["ai"] == {
        "min_confidence": 0.7,
        "clarify_enabled": True,
        "dedup_enabled": True,
    }
    assert validate_config({})["ai"] == DEFAULT_CONFIG["ai"]


def test_ai_partial_dict_merges_over_defaults():
    cfg = validate_config({"ai": {"min_confidence": 0.9}})
    assert cfg["ai"] == {"min_confidence": 0.9, "clarify_enabled": True, "dedup_enabled": True}


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
