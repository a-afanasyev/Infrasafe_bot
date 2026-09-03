"""Keyword-проход классификатора Group Intake (детерминированный, до LLM).

Эталон — восемь реальных текстов из групп profk за август–сентябрь 2026,
которые LLM без глоссария отправил в «Другое» (8 из 27 заявок из групп).
Шесть из них очевидны человеку — словарь ОБЯЗАН их узнавать; два
неоднозначны («19v oldi», «26v 2-podyezd») — словарь НЕ обязан угадывать,
и любое срабатывание на них — ложное.
"""

import pytest

from uk_management_bot.keyboards.requests import SELECTABLE_CATEGORY_KEYS
from uk_management_bot.services.group_intake.category_keywords import (
    MIN_STEM_LEN,
    CATEGORY_GLOSSARY,
    CATEGORY_KEYWORDS,
    guess_category,
    keyword_scores,
    normalize_text,
)
from uk_management_bot.services.group_intake.translit import translit

PROD_CASES = [
    ("25v poliv yoqilsin", "landscaping"),
    ("17 v da svet qachon keladi", "electricity"),
    ("20v 48kv elektrik kerak", "electricity"),
    ("16v 106kv elektrik kerak", "electricity"),
    ("Проверить весь подвал 23 дома. Есть вода?", "plumbing"),
    ("16в подволида сувини тортиш керак", "plumbing"),
]
AMBIGUOUS = ["19v oldi", "26v 2-podyezd"]


@pytest.mark.parametrize("text,expected", PROD_CASES)
def test_prod_texts_are_recognised(text, expected):
    assert guess_category(text) == expected


@pytest.mark.parametrize("text", AMBIGUOUS)
def test_ambiguous_prod_texts_stay_unknown(text):
    assert guess_category(text) is None


@pytest.mark.parametrize("text", [
    "sug'orish kerak",     # ASCII-апостроф
    "sugʻorish kerak",     # U+02BB (узбекская латиница)
    "sug’orish kerak",     # U+2019
    "sug`orish kerak",     # backtick
])
def test_uzbek_apostrophe_variants_match(text):
    assert guess_category(text) == "landscaping"


def test_uzbek_cyrillic_goes_through_translit():
    # ў/қ/ғ/ҳ — не в русском алфавите; без них «оқмаяпти» не стал бы «oqmayapti»
    assert translit("сув оқмаяпти") == "suv oqmayapti"
    assert translit("ўтлар") == "o'tlar"
    assert guess_category("сув оқмаяпти") == "plumbing"


def test_stem_anchors_to_word_start():
    # «рассвет» содержит «свет», но не начинается с него — не электрика
    assert guess_category("рассвет над двором") is None


def test_hyphen_and_apostrophe_are_removed_uniformly():
    assert normalize_text("вай-фай не работает") == "вайфай не работает"
    assert normalize_text("jo'mrak") == "jomrak"
    assert guess_category("вай-фай не работает") == "internet"


def test_longest_stem_wins():
    scores = keyword_scores("отопление и вода")
    assert scores["heating"] > scores["plumbing"]
    assert guess_category("отопление и вода") == "heating"


def test_tie_breaks_by_dictionary_order():
    # «лифт» и «свет» — по 4 символа; electricity в словаре раньше elevator
    assert keyword_scores("лифт стоит, свет мигает")["electricity"] == \
        keyword_scores("лифт стоит, свет мигает")["elevator"]
    assert guess_category("лифт стоит, свет мигает") == "electricity"


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_text_is_unknown(text):
    assert guess_category(text) is None
    assert keyword_scores(text) == {}


# ───────────── ратчеты: словарь и глоссарий синхронны с каноном ─────────────


def test_keywords_cover_every_selectable_category_except_other():
    assert set(CATEGORY_KEYWORDS) == set(SELECTABLE_CATEGORY_KEYS) - {"other"}


def test_keyword_order_is_priority_and_starts_with_electricity_plumbing():
    keys = list(CATEGORY_KEYWORDS)
    assert keys[:2] == ["electricity", "plumbing"]


def test_glossary_covers_every_selectable_category():
    assert set(CATEGORY_GLOSSARY) == set(SELECTABLE_CATEGORY_KEYS)
    for key, (description, examples) in CATEGORY_GLOSSARY.items():
        assert description.strip(), key
        assert len(examples) >= 2, key


@pytest.mark.parametrize("key,stems", list(CATEGORY_KEYWORDS.items()))
def test_stems_are_normalised_and_long_enough(key, stems):
    for stem in stems:
        assert stem == normalize_text(stem), (key, stem)
        assert len(stem) >= MIN_STEM_LEN, (key, stem)


# ───────────── ревью 2026-09-03: MIN_STEM_LEN — реальный инвариант, не декларация ─────────────


def test_stems_shorter_than_min_len_never_match(monkeypatch):
    """Короткий стем = лавина ложных хитов по `startswith`; словарь и
    матчер держат один порог `MIN_STEM_LEN`, а не число в двух местах."""
    from uk_management_bot.services.group_intake import category_keywords as kw

    monkeypatch.setitem(kw.CATEGORY_KEYWORDS, "elevator", ("li",))
    assert kw.MIN_STEM_LEN >= 3
    assert kw.guess_category("li ishlamayapti") is None
    assert kw.keyword_scores("li ishlamayapti") == {}
