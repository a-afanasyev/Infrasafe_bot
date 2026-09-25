"""Узбекская латиница → узбекская кириллица (локаль бота ``uz_cyrl``).

Локаль ``uz_cyrl`` не поддерживается вручную: ``utils/helpers.load_locale``
строит её из ``uz.json`` этой транслитерацией (новые ключи в uz.json сразу
появляются и в кириллице). Правки для слов, где правило ошибается, — в
``config/locales/uz_cyrl.overrides.json``.

Правила (официальная орфография 1995 г. в обратную сторону):
- o‘ / g‘ (апостроф ‘ ʻ ' ’ `) → ў / ғ; sh → ш, ch → ч, ng → нг;
- yo / yu / ya → ё / ю / я; ye → е в начале слова и после гласной, иначе ъе
  (obyekt → объект); одиночная y → й;
- e → э в начале слова и после гласной, иначе е;
- q → қ, h → ҳ, x → х, j → ж; ts перед «iy»/«io» → ц (operatsiya → операция,
  но muvaffaqiyatsiz → муваффақиятсиз); прочие ts — т+с;
- тутуқ белгиси (' ’ ʼ) после гласной перед буквой → ъ (ta’mir → таъмир);
  s'h → сҳ; апостроф после согласной — это кавычка, остаётся как есть.
- регистр: Sh / SH → Ш, прочее — по регистру первой буквы.

Не трогаются: плейсхолдеры ``{...}``, HTML-теги и сущности, URL, ``@username``,
``#теги``, ``/команды``, аббревиатуры из ``ABBREVIATIONS``, эмодзи и уже
кириллический текст.
"""
import re
from typing import Any, Dict

# Латинские аббревиатуры/бренды, которые в кириллице остаются латиницей.
ABBREVIATIONS = (
    "TWA", "ID", "SMS", "QR", "PDF", "API", "URL", "AI", "OK", "GPS", "TV",
    "JPG", "PNG", "DOCX", "DOC", "MB", "KB", "HH:MM",
)

_PROTECTED_RE = re.compile(
    "|".join(
        (
            r"\{[^{}]*\}",  # плейсхолдеры str.format
            r"<[^<>]+>",  # HTML-теги вместе с атрибутами
            r"&(?:[A-Za-z]+|#\d+|#x[0-9A-Fa-f]+);",  # HTML-сущности
            r"(?:https?://|www\.)[^\s<>\"']+",  # URL
            r"(?<![\w/])t\.me/[^\s<>\"']+",
            r"(?<!\w)@\w+",  # @username
            r"(?<!\w)#\w+",  # #теги
            r"(?<![\w/])/[A-Za-z_]+",  # /команды
            r"(?<![A-Za-z])`[^`\n]+`",  # `код` (не o`/g` — перед ` нет буквы)
            r"\b[A-Za-z]+(?:_[A-Za-z0-9]+)+(?:=[A-Za-z0-9]+)?\b",  # snake_case-идентификаторы
            r"\b(?:" + "|".join(ABBREVIATIONS) + r")\b",
        )
    )
)

_SINGLE = {
    "a": "а", "b": "б", "c": "ц", "d": "д", "f": "ф", "g": "г", "h": "ҳ",
    "i": "и", "j": "ж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о",
    "p": "п", "q": "қ", "r": "р", "s": "с", "t": "т", "u": "у", "v": "в",
    "w": "в", "x": "х", "y": "й", "z": "з",
}
_Y_VOWELS = {"o": "ё", "u": "ю", "a": "я"}
_VOWELS = set("aeiouаеёиоуэюяў")
# Апостроф-модификатор в o‘/g‘; ‘ и ʻ однозначны, остальные — только перед буквой.
_MODIFIERS_STRICT = {"‘", "ʻ"}
_MODIFIERS_LOOSE = {"'", "’", "`"}
# Тутуқ белгиси (разделительный знак).
_TUTUQ = {"'", "’", "ʼ"}


def _case(src: str, cyr: str) -> str:
    return cyr.upper() if src.isupper() else cyr


def _is_letter(ch: str) -> bool:
    return ch.isalpha()


def _is_modifier(s: str, i: int) -> bool:
    """s[i] — апостроф o‘/g‘?"""
    if i >= len(s):
        return False
    if s[i] in _MODIFIERS_STRICT:
        return True
    return s[i] in _MODIFIERS_LOOSE and i + 1 < len(s) and _is_letter(s[i + 1])


def _word_start_or_after_vowel(s: str, i: int) -> bool:
    if i == 0:
        return True
    prev = s[i - 1]
    return not _is_letter(prev) or prev.lower() in _VOWELS


def _step(s: str, i: int) -> tuple:
    """Одна единица транслитерации: (кириллица, сколько символов съедено)."""
    ch = s[i]
    low = ch.lower()
    nxt = s[i + 1].lower() if i + 1 < len(s) else ""

    if low in ("o", "g") and _is_modifier(s, i + 1):
        return _case(ch, "ў" if low == "o" else "ғ"), 2
    if low == "s" and nxt == "h":
        return _case(ch, "ш"), 2
    if low == "c" and nxt == "h":
        return _case(ch, "ч"), 2
    if low == "t" and nxt == "s" and s[i + 2:i + 4].lower() in ("iy", "io"):
        return _case(ch, "ц"), 2
    if low == "y" and nxt in _Y_VOWELS and not (nxt == "o" and _is_modifier(s, i + 2)):
        return _case(ch, _Y_VOWELS[nxt]), 2
    if low == "y" and nxt == "e":
        if _word_start_or_after_vowel(s, i):
            return _case(ch, "е"), 2
        return "ъ" + _case(ch, "е"), 2
    if low == "e":
        return _case(ch, "э" if _word_start_or_after_vowel(s, i) else "е"), 1
    if ch in _TUTUQ and i > 0 and _is_letter(s[i - 1]) and nxt and _is_letter(s[i + 1]):
        prev = s[i - 1].lower()
        if prev == "s" and nxt == "h":
            return "", 1  # is'hoq → исҳоқ: разделяет с и ҳ
        if prev in _VOWELS or ch == "ʼ":
            return "ъ", 1
        return ch, 1  # после согласной — кавычка ('Yakunlash'ni)
    if low in _SINGLE:
        return _case(ch, _SINGLE[low]), 1
    return ch, 1


def _translit_plain(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        piece, used = _step(s, i)
        out.append(piece)
        i += used
    return "".join(out)


def to_cyrillic(text: str) -> str:
    """Транслитерировать строку, не трогая защищённые фрагменты."""
    parts = []
    pos = 0
    for match in _PROTECTED_RE.finditer(text):
        parts.append(_translit_plain(text[pos:match.start()]))
        parts.append(match.group(0))
        pos = match.end()
    parts.append(_translit_plain(text[pos:]))
    return "".join(parts)


def strip_protected(text: str) -> str:
    """Текст без защищённых фрагментов (для гейта «латиница не осталась»)."""
    return _PROTECTED_RE.sub(" ", text)


def transliterate_tree(data: Any) -> Any:
    """Новая структура: все строковые значения в кириллице, ключи как есть."""
    if isinstance(data, dict):
        return {key: transliterate_tree(value) for key, value in data.items()}
    if isinstance(data, list):
        return [transliterate_tree(value) for value in data]
    if isinstance(data, str):
        return to_cyrillic(data)
    return data


def deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Новый словарь: ``base`` с наложенными поверх ``overrides`` (рекурсивно)."""
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
