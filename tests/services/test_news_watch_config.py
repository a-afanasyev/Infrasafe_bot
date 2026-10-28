"""Конфиг мониторинга отключений (services/news_watch/config.py)."""
import pytest

from uk_management_bot.services.news_watch.config import DEFAULT_CONFIG, validate_config


def test_defaults_are_safe():
    cfg = validate_config({})
    assert cfg == DEFAULT_CONFIG
    assert cfg["auto_publish"] is False
    assert cfg["sources"] == []
    assert 0 < cfg["min_confidence"] <= 1
    assert cfg["keywords"], "дефолтные ключевые слова ru/uz обязаны быть"
    assert cfg["broadcast"] == {"dm": True, "residents_groups": True}


def test_sources_normalized():
    cfg = validate_config({"sources": [{"chat": "@ToshkentElektr", "title": "Электросети"},
                                       {"chat": " https://t.me/suv_taminoti "}]})
    assert cfg["sources"] == [
        {"chat": "@toshkentelektr", "title": "Электросети"},
        {"chat": "@suv_taminoti", "title": ""},
    ]


def test_keywords_lowercased_and_deduped():
    cfg = validate_config({"keywords": ["Отключ", "ОТКЛЮЧ", " elektr "]})
    assert cfg["keywords"] == ["отключ", "elektr"]


@pytest.mark.parametrize(
    "bad",
    [
        {"sources": "x"},
        {"sources": [{"title": "без chat"}]},
        {"sources": [{"chat": ""}]},
        {"sources": [{"chat": "@a", "extra": 1}]},
        {"keywords": "x"},
        {"keywords": [1]},
        {"min_confidence": 1.5},
        {"min_confidence": "0.5"},
        {"auto_publish": "yes"},
        {"complex_context": 5},
        {"broadcast": {"sms": True}},
        {"broadcast": {"dm": "no"}},
        {"unknown": 1},
    ],
)
def test_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        validate_config(bad)


def test_complex_context_trimmed_and_limited():
    cfg = validate_config({"complex_context": "  ЖК Тест, ул. Тестовая  "})
    assert cfg["complex_context"] == "ЖК Тест, ул. Тестовая"
    with pytest.raises(ValueError):
        validate_config({"complex_context": "x" * 5000})


def test_validate_does_not_mutate_defaults():
    validate_config({"keywords": ["zzz"], "sources": [{"chat": "@xxxxx"}]})
    assert "zzz" not in DEFAULT_CONFIG["keywords"] and DEFAULT_CONFIG["sources"] == []
