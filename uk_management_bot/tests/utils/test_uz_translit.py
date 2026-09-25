"""Фаза 3 простого режима: локаль uz_cyrl = транслитерация uz.json.

Таблица слов фиксирует правила ``utils/uz_translit``; гейт по всему uz.json
ловит пробелы в правилах (латиница вне защищённых фрагментов) и порчу
плейсхолдеров; overrides-файл проверяется на ключи и плейсхолдеры uz.
"""
import json
import re
import string
from pathlib import Path

import pytest

from uk_management_bot.utils.helpers import _locale_cache, get_text, load_locale
from uk_management_bot.utils.uz_translit import (
    deep_merge,
    strip_protected,
    to_cyrillic,
    transliterate_tree,
)

LOCALES = Path(__file__).resolve().parents[2] / "config" / "locales"

WORDS = [
    ("Tayyor", "Тайёр"),
    ("Muammo", "Муаммо"),
    ("Yuborish", "Юбориш"),
    ("Qayta", "Қайта"),
    ("Boshlash", "Бошлаш"),
    ("Tugatish", "Тугатиш"),
    ("Material yo‘q", "Материал йўқ"),
    ("Kiritishmadi", "Киритишмади"),
    ("Aloqa yo‘q", "Алоқа йўқ"),
    ("Meniki", "Меники"),
    ("Olish", "Олиш"),
    ("ta’mir", "таъмир"),
    ("e’lon", "эълон"),
    ("yangi", "янги"),
    ("bo‘lim", "бўлим"),
    ("ko‘cha", "кўча"),
    ("g‘isht", "ғишт"),
    # варианты апострофа o‘/g‘
    ("bo'lim", "бўлим"),
    ("boʻlim", "бўлим"),
    ("bo’lim", "бўлим"),
    ("bo`lim", "бўлим"),
    ("tog‘", "тоғ"),
    ("O'zbekiston", "Ўзбекистон"),
    ("Yo'q", "Йўқ"),
    ("G'isht", "Ғишт"),
    # диграфы и регистр
    ("Shahar", "Шаҳар"),
    ("SHAHAR", "ШАҲАР"),
    ("choy", "чой"),
    ("Chiqish", "Чиқиш"),
    ("tong", "тонг"),
    ("smena", "смена"),
    # y + гласная
    ("yozish", "ёзиш"),
    ("Yopish", "Ёпиш"),
    ("yuk", "юк"),
    ("ariza yaratish", "ариза яратиш"),
    ("yetarli", "етарли"),
    ("reyestr", "реестр"),
    ("obyekt", "объект"),
    ("kutish", "кутиш"),
    # e: начало слова / после гласной → э, иначе е
    ("Endi", "Энди"),
    ("eslatma", "эслатма"),
    ("poeziya", "поэзия"),
    ("menejer", "менежер"),
    ("emas", "эмас"),
    # q/h/x/j
    ("qabul", "қабул"),
    ("hovli", "ҳовли"),
    ("xodim", "ходим"),
    ("joy", "жой"),
    ("xona", "хона"),
    # тутуқ белгиси
    ("ma'lumot", "маълумот"),
    ("Ma'lumot", "Маълумот"),
    ("a'zo", "аъзо"),
    ("maʼlumot", "маълумот"),
    ("is'hoq", "исҳоқ"),
    # ts: -tsiya → ция, прочие — т+с
    ("Operatsiya", "Операция"),
    ("muvaffaqiyatsiz", "муваффақиятсиз"),
    ("Ventilyatsiya", "Вентиляция"),
    # цифры, знаки, уже кириллица
    ("09:00 dan", "09:00 дан"),
    ("Ариза", "Ариза"),
    ("Ish tugadi!", "Иш тугади!"),
]


@pytest.mark.parametrize("latin, cyrillic", WORDS)
def test_word_table(latin, cyrillic):
    assert to_cyrillic(latin) == cyrillic


def test_word_table_is_large_enough():
    assert len(WORDS) >= 40


def test_quote_after_consonant_stays_quote():
    assert to_cyrillic("'Yakunlash'ni bosing") == "'Якунлаш'ни босинг"
    assert to_cyrillic("Holat 'Bajarildi' ga") == "Ҳолат 'Бажарилди' га"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("#{request_number} arizasi", "#{request_number} аризаси"),
        ("Salom, {name}!", "Салом, {name}!"),
        ("{count:.1f} soat", "{count:.1f} соат"),
        ("<b>Manzil:</b> {address}", "<b>Манзил:</b> {address}"),
        ('<a href="https://t.me/bot?start=x">Ochish</a>', '<a href="https://t.me/bot?start=x">Очиш</a>'),
        ("Tom &amp; Jamshid &#39;", "Том &amp; Жамшид &#39;"),
        ("Sayt: https://profk.uz/uk/twa yoki www.example.com", "Сайт: https://profk.uz/uk/twa ёки www.example.com"),
        ("@support_bot ga yozing", "@support_bot га ёзинг"),
        ("#ariza #zayavka tegi", "#ariza #zayavka теги"),
        ("/start buyrug'i", "/start буйруғи"),
        ("TWA orqali ID va SMS, QR, PDF, API", "TWA орқали ID ва SMS, QR, PDF, API"),
        ("✅ Tayyor 🔧", "✅ Тайёр 🔧"),
        ("Kod: `invite_v1:abc`", "Код: `invite_v1:abc`"),
        ("auto_create=true bilan", "auto_create=true билан"),
        ("HH:MM formatida", "HH:MM форматида"),
    ],
)
def test_protected_fragments_are_untouched(text, expected):
    assert to_cyrillic(text) == expected


def test_transliterate_tree_keeps_keys_and_returns_new_object():
    tree = {"buttons": {"done": "Tayyor", "n": 3, "list": ["yangi"]}}
    result = transliterate_tree(tree)
    assert result == {"buttons": {"done": "Тайёр", "n": 3, "list": ["янги"]}}
    assert tree["buttons"]["done"] == "Tayyor"  # исходник не мутирован


def test_deep_merge_does_not_mutate():
    base = {"a": {"x": "1", "y": "2"}, "b": "3"}
    merged = deep_merge(base, {"a": {"y": "Y"}})
    assert merged == {"a": {"x": "1", "y": "Y"}, "b": "3"}
    assert base["a"]["y"] == "2"


# --- интеграция с get_text -----------------------------------------------


def test_get_text_real_key_is_cyrillic_with_placeholders():
    _locale_cache.pop("uz_cyrl", None)
    text = get_text("notifications.workflow.assigned", language="uz_cyrl", request_number="260926-001", address="Ko'cha 1")
    assert "260926-001" in text and "Ko'cha 1" in text
    assert re.search("[а-яўқғҳ]", text)
    assert not re.search("[A-Za-z]", text.replace("Ko'cha", ""))


def test_uz_cyrl_derived_from_patched_uz(monkeypatch):
    monkeypatch.setitem(_locale_cache, "uz", {"k": {"a": "Tayyor, {name}"}, "n": "{count} ta", "n_plural": "{count} tadan"})
    monkeypatch.setitem(_locale_cache, "ru", {"k": {"a": "Готово", "ru_only": "Только Telegram"}, "n": "x"})
    monkeypatch.delitem(_locale_cache, "uz_cyrl", raising=False)
    try:
        assert get_text("k.a", language="uz_cyrl", name="Ali") == "Тайёр, Ali"
        # ключа нет в uz → русский как есть, без транслитерации латиницы
        assert get_text("k.ru_only", language="uz_cyrl") == "Только Telegram"
        # узбекские правила множественного числа: 5 → _plural
        assert get_text("n", language="uz_cyrl", count=5) == "5 тадан"
        assert get_text("n", language="uz_cyrl", count=1) == "1 та"
    finally:
        _locale_cache.pop("uz_cyrl", None)


def test_overrides_are_applied():
    _locale_cache.pop("uz_cyrl", None)
    overrides = json.loads((LOCALES / "uz_cyrl.overrides.json").read_text(encoding="utf-8"))
    key = "requests.files_uploaded_to_media_service"
    assert get_text(key, language="uz_cyrl", count=2) == overrides["requests"]["files_uploaded_to_media_service"].format(count=2)


# --- гейты по всему uz.json ------------------------------------------------


def _flatten(tree, prefix=""):
    for key, value in tree.items():
        if isinstance(value, dict):
            yield from _flatten(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}", value


def _fields(text):
    return {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}


UZ = dict(_flatten(json.loads((LOCALES / "uz.json").read_text(encoding="utf-8"))))
OVERRIDES = dict(_flatten(json.loads((LOCALES / "uz_cyrl.overrides.json").read_text(encoding="utf-8"))))


def test_whole_uz_json_leaves_no_latin_outside_protected_fragments():
    leftovers = {}
    for key, text in UZ.items():
        if not isinstance(text, str):
            continue
        latin = re.findall(r"[A-Za-z]+", strip_protected(to_cyrillic(text)))
        if latin:
            leftovers[key] = latin
    assert not leftovers, f"правила транслитерации не покрывают: {list(leftovers.items())[:20]}"


def test_whole_uz_json_placeholders_survive():
    broken = [
        key for key, text in UZ.items()
        if isinstance(text, str) and _fields(text) != _fields(to_cyrillic(text))
    ]
    assert not broken, f"транслитерация испортила плейсхолдеры: {broken[:20]}"


def test_overrides_only_existing_keys_with_same_placeholders():
    unknown = sorted(set(OVERRIDES) - set(UZ))
    assert not unknown, f"правки для ключей, которых нет в uz.json: {unknown}"
    mismatched = [k for k, v in OVERRIDES.items() if _fields(v) != _fields(UZ[k])]
    assert not mismatched, f"плейсхолдеры правок не совпадают с uz: {mismatched}"


def test_uz_cyrl_locale_has_same_keys_as_uz():
    _locale_cache.pop("uz_cyrl", None)
    assert set(dict(_flatten(load_locale("uz_cyrl")))) == set(UZ)
