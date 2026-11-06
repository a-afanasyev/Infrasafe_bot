"""Конфиг мониторинга отключений (services/news_watch/config.py)."""
import pytest

from uk_management_bot.services.news_watch.config import (
    DEFAULT_CONFIG,
    MAX_KEYWORDS,
    MAX_SOURCES,
    validate_config,
)


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


# ───────────── A11-CODE-02: лимиты, ограничивающие поток в LLM и юзербот ─────────────


def test_sources_limit():
    ok = validate_config({"sources": [{"chat": f"@chan{i:04d}"} for i in range(MAX_SOURCES)]})
    assert len(ok["sources"]) == MAX_SOURCES
    with pytest.raises(ValueError, match="sources"):
        validate_config({"sources": [{"chat": f"@chan{i:04d}"} for i in range(MAX_SOURCES + 1)]})


def test_keywords_limit():
    validate_config({"keywords": [f"слово{i}" for i in range(MAX_KEYWORDS)]})
    with pytest.raises(ValueError, match="keywords"):
        validate_config({"keywords": [f"слово{i}" for i in range(MAX_KEYWORDS + 1)]})


@pytest.mark.parametrize("word", ["ва", " г ", "x"])
def test_too_short_keyword_rejected(word):
    """Подстрока из 1–2 букв совпадает почти с любым текстом — каждая новость шла бы в LLM."""
    with pytest.raises(ValueError, match="keywords"):
        validate_config({"keywords": ["вод", word]})


def test_default_keywords_pass_new_rules():
    assert validate_config({})["keywords"] == DEFAULT_CONFIG["keywords"]


# ───────────── A11: предполётная проверка сохранённого конфига ─────────────
# load_config при невалидных данных молча отдаёт дефолт (пустые источники) —
# поэтому перед выкаткой новых правил сохранённый конфиг проверяется ими явно.


@pytest.fixture
def sync_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from uk_management_bot.database.models.news_item import NewsWatchConfig

    engine = create_engine("sqlite://")
    NewsWatchConfig.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def _store(factory, data):
    from uk_management_bot.database.models.news_item import NewsWatchConfig

    with factory() as db:
        db.add(NewsWatchConfig(id=1, data=data))
        db.commit()


def test_check_stored_no_row_is_ok(sync_session):
    from uk_management_bot.services.news_watch.config import check_stored_config_sync

    with sync_session() as db:
        assert check_stored_config_sync(db) is None


def test_check_stored_valid_is_ok(sync_session):
    from uk_management_bot.services.news_watch.config import check_stored_config_sync

    _store(sync_session, {**DEFAULT_CONFIG, "sources": [{"chat": "@infrasafe_news", "title": ""}]})
    with sync_session() as db:
        assert check_stored_config_sync(db) is None


@pytest.mark.parametrize("bad", [
    {"keywords": ["вод", "ва"]},
    {"sources": [{"chat": f"@chan{i:04d}"} for i in range(MAX_SOURCES + 1)]},
])
def test_check_stored_reports_incompatible_config(sync_session, bad):
    from uk_management_bot.services.news_watch.config import check_stored_config_sync

    _store(sync_session, {**DEFAULT_CONFIG, **bad})
    with sync_session() as db:
        problem = check_stored_config_sync(db)
    assert problem and ("keywords" in problem or "sources" in problem)


def test_cli_exit_codes(sync_session):
    from uk_management_bot.services.news_watch.config import main

    assert main(["--check-stored"], session_factory=sync_session) == 0
    _store(sync_session, {**DEFAULT_CONFIG, "keywords": ["ва"]})
    assert main(["--check-stored"], session_factory=sync_session) == 1


def test_limits_only_on_write_stored_config_still_loads(sync_session):
    """Конфиг, сохранённый до лимитов A11, читается как есть — источники не теряются."""
    from uk_management_bot.services.news_watch.config import load_config_sync

    stored = {**DEFAULT_CONFIG, "keywords": ["вод", "ГВ"], "sources": [{"chat": "@infrasafe_news", "title": ""}]}
    _store(sync_session, stored)
    with sync_session() as db:
        cfg = load_config_sync(db)
    assert cfg["sources"] == [{"chat": "@infrasafe_news", "title": ""}]
    assert "гв" in cfg["keywords"]
    with pytest.raises(ValueError, match="keywords"):
        validate_config(stored)  # запись того же — отказ
