"""Схема паспорта дома: поля, группы строк, привязка к форме №3824.

Схема строится от формы (эталон `form_3824.json`), а не от каталога исходной
страницы — расхождения разобраны в `docs/PASSPORT_FORM_MAPPING.md`.

* у поля свой внутренний ключ; номер и строки формы хранятся отдельно
  (`form_no`, `form_rows`), у поля вне формы их нет;
* официальное название не хранится в схеме, а берётся из эталона дословно
  (`official_uz`) — так оно не может разойтись с формой;
* интерфейсное узбекское название — латиницей: по умолчанию транслитерация
  официального, у полей вне формы задаётся явно;
* вариант выбора печатается в вариант формы (`Option.form`), в «другое»
  (`other=True`) либо остаётся вне формы (`form=None`).

Изменение состава, типов или вариантов требует повышения `SCHEMA_VERSION`
(тест держит отпечаток): подписанные редакции хранят свою копию схемы.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Optional, Union

SCHEMA_VERSION = 1

#: Объекты, общие на несколько домов: значение хранится в одном «основном»
#: доме, остальные ссылаются на него (решение владельца 2026-11-20).
SHARE_UNITS = ("plot", "greenery", "playgrounds")

_ETALON_PATH = Path(__file__).with_name("form_3824.json")


@dataclass(frozen=True)
class Option:
    key: str
    ru: str
    uz: str
    form: Optional[str] = None  # дословный вариант формы; None — вне формы
    other: bool = False  # печатается в «другое» формы с расшифровкой


@dataclass(frozen=True)
class Field:
    key: str
    type: str  # int | decimal | choice | text
    ru: str
    uz: str
    unit: Optional[str] = None
    form_no: Optional[str] = None
    form_rows: Optional[tuple[int, ...]] = None  # None при form_no — весь пункт
    label: Optional[str] = None  # sub: «пункт: строка»; own: название в самой строке
    options: tuple[Option, ...] = ()
    computed: bool = False
    show_if: Optional[tuple[str, tuple[str, ...]]] = None
    share: Optional[str] = None


@dataclass(frozen=True)
class Group:
    """Строки: в интерфейсе их сколько угодно, при печати они сворачиваются."""

    key: str
    ru: str
    uz: str
    fields: tuple[Field, ...]
    form: tuple[tuple[str, Optional[tuple[int, ...]]], ...] = ()
    show_if: Optional[tuple[str, tuple[str, ...]]] = None
    share: Optional[str] = None


Item = Union[Field, Group]


@dataclass(frozen=True)
class Section:
    key: str
    no: Optional[int]  # номер раздела формы; None — дополнение УК
    ru: str
    uz: str
    items: tuple[Item, ...]


# ── эталон формы ────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def etalon() -> dict:
    return json.loads(_ETALON_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _etalon_rows() -> dict[tuple[str, int], dict]:
    return {(r["no"], r["row"]): r for r in etalon()["rows"] if r["kind"] in ("item", "row")}


def etalon_items() -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for no, row in _etalon_rows():
        out.setdefault(no, []).append(row)
    return out


def etalon_text() -> str:
    parts: list[str] = []
    for row in etalon()["rows"]:
        parts.append(row.get("title", ""))
        parts.extend(row.get("cells", []))
    return "\n".join(parts)


def official_uz(field: Field) -> Optional[str]:
    """Название строки формы дословно, кириллицей; у поля вне формы — None."""
    if field.form_no is None:
        return None
    rows = _etalon_rows()
    title = rows[(field.form_no, 1)]["title"]
    if field.label is None or not field.form_rows:
        return title
    cell = rows[(field.form_no, field.form_rows[0])]["cells"][0]
    return cell if field.label == "own" else f"{title}: {cell}"  # html-raw: текст эталона формы, не ввод и не Telegram


# ── узбекская кириллица → латиница (для интерфейса) ─────────────────────────

_VOWELS = "аеёиоуэюяўАЕЁИОУЭЮЯЎ"
_PLAIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ё": "yo", "ж": "j", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s",
    "т": "t", "у": "u", "ф": "f", "х": "x", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ь": "",
    "ы": "i", "э": "e", "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}


def uz_latin(text: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(text):
        low = ch.lower()
        prev = text[i - 1] if i else " "
        after_vowel = prev in _VOWELS or prev in "ъьЪЬ"
        if low == "е":
            lat = "ye" if (not prev.isalpha() or after_vowel) else "e"
        elif low == "ц":
            lat = "ts" if after_vowel else "s"
        elif low in _PLAIN:
            lat = _PLAIN[low]
        else:
            out.append(ch)
            continue
        out.append(lat.capitalize() if ch != low else lat)
    return "".join(out)


# ── сборка ──────────────────────────────────────────────────────────────────

def opt(key: str, ru: str, form: Optional[str] = None, *, uz: Optional[str] = None,
        other: bool = False) -> Option:
    if uz is None:
        if form is None:
            raise ValueError(f"вариант {key}: вне формы нужно явное название uz")
        uz = uz_latin(form[1:-1] if form.startswith("(") and form.endswith(")") else form)
    return Option(key=key, ru=ru, uz=uz, form=form, other=other)


def field(key: str, type_: str, ru: str, *, unit: Optional[str] = None, form: Optional[str] = None,
          rows: Optional[tuple[int, ...]] = None, label: Optional[str] = None, uz: Optional[str] = None,
          options: tuple[Option, ...] = (), computed: bool = False,
          show_if: Optional[tuple[str, tuple[str, ...]]] = None, share: Optional[str] = None) -> Field:
    draft = Field(key=key, type=type_, ru=ru, uz=uz or "", unit=unit, form_no=form, form_rows=rows,
                  label=label, options=options, computed=computed, show_if=show_if, share=share)
    if uz is None:
        official = official_uz(draft)
        if official is None:
            raise ValueError(f"поле {key}: вне формы нужно явное название uz")
        uz = uz_latin(official)
    return Field(**{**draft.__dict__, "uz": uz})


@lru_cache(maxsize=1)
def sections() -> tuple[Section, ...]:
    from .schema_extra import PLAYGROUNDS
    from .schema_form import FORM_SECTIONS

    return (*FORM_SECTIONS, PLAYGROUNDS)


def iter_fields() -> Iterator[Field]:
    """Одиночные поля (строки групп сюда не входят)."""
    for section in sections():
        for item in section.items:
            if isinstance(item, Field):
                yield item


def iter_groups() -> Iterator[Group]:
    for section in sections():
        for item in section.items:
            if isinstance(item, Group):
                yield item


def claims() -> Iterator[tuple[str, tuple[int, ...]]]:
    """Какие строки формы заполняет схема: (пункт, строки)."""
    all_rows = etalon_items()
    for item in (*iter_fields(), *iter_groups()):
        pairs = item.form if isinstance(item, Group) else (
            ((item.form_no, item.form_rows),) if item.form_no else ())
        for no, rows in pairs:
            yield no, tuple(rows if rows is not None else all_rows.get(no, ()))


# ── представление для API и для подписанной редакции ───────────────────────

def _field_out(item: Field) -> dict:
    out = {"kind": "field", "key": item.key, "type": item.type, "ru": item.ru, "uz": item.uz,
           "unit": item.unit, "form_no": item.form_no,
           "form_rows": list(item.form_rows) if item.form_rows else None,
           "official_uz": official_uz(item), "computed": item.computed, "share": item.share,
           "show_if": [item.show_if[0], list(item.show_if[1])] if item.show_if else None}
    if item.options:
        out["options"] = [{"key": o.key, "ru": o.ru, "uz": o.uz, "form": o.form, "other": o.other}
                          for o in item.options]
    return out


def _item_out(item: Item) -> dict:
    if isinstance(item, Field):
        return _field_out(item)
    return {"kind": "group", "key": item.key, "ru": item.ru, "uz": item.uz, "share": item.share,
            "form": [[no, list(rows) if rows else None] for no, rows in item.form],
            "show_if": [item.show_if[0], list(item.show_if[1])] if item.show_if else None,
            "fields": [_field_out(f) for f in item.fields]}


@lru_cache(maxsize=1)
def public_schema() -> dict:
    return {"version": SCHEMA_VERSION,
            "sections": [{"key": s.key, "no": s.no, "ru": s.ru, "uz": s.uz,
                          "items": [_item_out(i) for i in s.items]} for s in sections()]}
