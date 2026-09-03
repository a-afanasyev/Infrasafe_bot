"""Keyword-проход категории заявки (детерминированный, до LLM) + глоссарий.

Зачем: за 60 дней на profk 8 из 27 заявок из групп ушли в «Другое», все —
вердикт LLM без глоссария на коротких текстах вроде «20v elektrik kerak»
или «25v poliv yoqilsin». Словарь ловит такие тексты сам, а глоссарий даёт
модели описание категорий с примерами (ru / uz-кириллица / uz-латиница).

Правила:
- нормализация одна и для текста, и для стемов: casefold, ё→е, апострофы
  (' ʻ ’ ‘ `) и дефисы удаляются — иначе `\\w+` режет «sug'orish» по
  апострофу и стем не совпадает;
- узбекская кириллица — через транслит ТЕКСТА (`translit`), стемы держим в
  двух алфавитах: ru-кириллица и uz-латиница;
- стем совпадает по началу слова (`token.startswith(stem)`) — «рассвет»
  не электрика; минимальная длина 3;
- счёт категории = длина самого длинного сработавшего стема, тай-брейк —
  порядок словаря (electricity и plumbing первыми: самые частые);
- порога нет: либо хит, либо None. `other`/`engineering` в словаре нет.
"""

import re
from typing import Optional

from uk_management_bot.services.group_intake.translit import translit

_APOSTROPHES_AND_HYPHENS = re.compile(r"['ʻ’‘`\-]")
_TOKEN = re.compile(r"\w+")
MIN_STEM_LEN = 3

# Порядок = приоритет при равном счёте. Стемы уже нормализованы
# (ратчет в тестах держит инвариант `stem == normalize_text(stem)`).
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "electricity": (
        "свет", "света", "электр", "розетк", "провод", "щиток", "лампочк",
        "искр", "коротит",
        "svet", "chiroq", "elektr", "rozetka", "lampochka",
    ),
    "plumbing": (
        "вода", "воды", "воду", "теч", "протеч", "капает", "кран", "труб",
        "стояк", "канализ", "засор", "унитаз", "затоп", "потоп",
        "suv", "oqyapti", "oqmoqda", "quvur", "kanalizatsiya", "jomrak",
        "hojatxona", "unitaz",
    ),
    "heating": (
        "отоплен", "батаре", "радиатор", "холодн",
        "isitish", "batare", "radiator", "sovuq",
    ),
    "elevator": ("лифт", "lift"),
    "landscaping": (
        "полив", "газон", "клумб", "дерев", "кустарн", "трав", "озелен",
        "poliv", "gazon", "daraxt", "gulzor", "maysa", "sugor",
    ),
    "cleaning": (
        "мусор", "убор", "грязн",
        "axlat", "chiqindi", "tozal", "supur",
    ),
    "security": (
        "охран", "камер", "шлагбаум", "домофон",
        "qorovul", "kamera", "shlagbaum", "domofon",
    ),
    "internet": (
        "интернет", "wifi", "вайфай", "антенн",
        "internet", "televizor",
    ),
    "ventilation": (
        "вентиляц", "вытяжк",
        "ventilyats", "shamollat",
    ),
    "repair": (
        "плитк", "двер", "окн", "стекл", "крыш", "кровл", "фасад", "трещин",
        "eshik", "deraza", "plitka", "devor", "yoriq",
    ),
}

# Глоссарий для системного промпта: описание + примеры (ru / uz-кириллица /
# uz-латиница, включая реальные прод-тексты, которые LLM отправлял в other).
CATEGORY_GLOSSARY: dict[str, tuple[str, tuple[str, ...]]] = {
    "electricity": (
        "свет, розетки, щиток, проводка, отключение электричества",
        ("в подъезде нет света", "17 v da svet qachon keladi", "20v 48kv elektrik kerak"),
    ),
    "plumbing": (
        "вода, трубы, краны, стояки, канализация, протечки и затопления",
        ("течёт кран в ванной", "Проверить весь подвал 23 дома. Есть вода?",
         "16в подволида сувини тортиш керак"),
    ),
    "heating": (
        "отопление, батареи, радиаторы, холодно в квартире",
        ("батареи холодные", "isitish ishlamayapti"),
    ),
    "ventilation": (
        "вентиляция, вытяжка, запах из вентшахты",
        ("не работает вытяжка", "ventilyatsiya ishlamayapti"),
    ),
    "elevator": (
        "лифт: не едет, застрял, шумит",
        ("лифт не работает", "lift ishlamayapti"),
    ),
    "cleaning": (
        "уборка подъезда и двора, вывоз мусора, грязь",
        ("не убирают подъезд", "axlat olib ketilmadi"),
    ),
    "landscaping": (
        "благоустройство двора: полив, газон, клумбы, деревья, кустарники, озеленение",
        ("25v poliv yoqilsin", "нужно полить газон", "daraxtlarni kesish kerak"),
    ),
    "security": (
        "охрана, камеры, шлагбаум, домофон, посторонние",
        ("не работает шлагбаум", "domofon ishlamayapti"),
    ),
    "internet": (
        "интернет, Wi-Fi, ТВ, антенна",
        ("нет интернета в доме", "internet yo'q"),
    ),
    "repair": (
        "мелкий ремонт общего имущества: плитка, двери, окна, стекла, крыша, фасад, трещины",
        ("отвалилась плитка на фасаде", "eshik buzilgan"),
    ),
    "other": (
        "только если ни одна категория выше не подходит",
        ("нужна консультация по оплате", "19v oldi"),
    ),
}


def normalize_text(text: Optional[str]) -> str:
    """casefold + ё→е + удаление апострофов и дефисов (для текста И стемов)."""
    if not text:
        return ""
    lowered = text.casefold().replace("ё", "е")
    return _APOSTROPHES_AND_HYPHENS.sub("", lowered)


def _tokens(text: Optional[str]) -> set[str]:
    if not text or not text.strip():
        return set()
    variants = (normalize_text(text), normalize_text(translit(text)))
    return {tok for variant in variants for tok in _TOKEN.findall(variant)}


def keyword_scores(text: Optional[str]) -> dict[str, int]:
    """Категория → длина самого длинного сработавшего стема (только хиты)."""
    tokens = _tokens(text)
    if not tokens:
        return {}
    scores: dict[str, int] = {}
    for category, stems in CATEGORY_KEYWORDS.items():
        best = 0
        for stem in stems:
            # Порог — здесь, а не только в ратчете: короткий стем по
            # `startswith` = лавина ложных хитов.
            if len(stem) < MIN_STEM_LEN:
                continue
            if len(stem) > best and any(tok.startswith(stem) for tok in tokens):
                best = len(stem)
        if best:
            scores[category] = best
    return scores


def guess_category(text: Optional[str]) -> Optional[str]:
    """Лучшая категория по ключевым словам или None. Тай-брейк — порядок словаря."""
    scores = keyword_scores(text)
    if not scores:
        return None
    best_score = max(scores.values())
    for category in CATEGORY_KEYWORDS:  # порядок словаря = приоритет
        if scores.get(category) == best_score:
            return category
    return None  # недостижимо: ключи scores ⊂ ключи словаря
