"""A9-P3-16: гейт «набор плейсхолдеров ru == uz» для локалей бота.

``utils.helpers.get_text`` подставляет параметры через ``str.format(**kwargs)``,
а на ``KeyError/ValueError/IndexError`` молча откатывается к ``replace`` —
битая строка не роняет бота, а уходит пользователю с сырыми ``{...}``.
Поэтому гейт по файлам, а не по рантайму:

* каждая строка ru/uz — валидная format-строка (``string.Formatter().parse``
  понимает экранирование ``{{``/``}}`` так же, как ``str.format``);
* у ключа, общего для ru и uz, одинаковый набор имён полей — иначе в одном
  из языков ``format`` упадёт на ``KeyError`` или не подставит значение;
* позиционных полей (``{}``/``{0}``) нет: ``get_text`` передаёт только kwargs,
  позиционное поле всегда уходит пользователю сырым;
* наборы ключей ru и uz совпадают (чистка — только синхронно в обоих файлах).
"""
from __future__ import annotations

import json
import string
from pathlib import Path

LOCALES = Path(__file__).resolve().parents[1] / "config" / "locales"


def _flatten(tree: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            out.update(_flatten(value, f"{prefix}{key}."))
        else:
            out[f"{prefix}{key}"] = value
    return out


def _load(lang: str) -> dict[str, str]:
    return _flatten(json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8")))


def _fields(text: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(text) if field is not None}


def _fields_or_invalid(text: str) -> set[str] | str:
    """Невалидная строка — отдельный тест; здесь маркер, чтобы не падать с ValueError."""
    try:
        return _fields(text)
    except ValueError as exc:
        return f"<invalid: {exc}>"


RU = _load("ru")
UZ = _load("uz")


def test_ru_and_uz_have_same_keys():
    only_ru = sorted(set(RU) - set(UZ))
    only_uz = sorted(set(UZ) - set(RU))
    assert not only_ru and not only_uz, f"только в ru: {only_ru[:20]}; только в uz: {only_uz[:20]}"


def test_every_string_is_valid_format_string():
    broken = []
    for lang, texts in (("ru", RU), ("uz", UZ)):
        for key, text in texts.items():
            if not isinstance(text, str):
                broken.append(f"{lang}:{key}: не строка ({type(text).__name__})")
                continue
            try:
                _fields(text)
            except ValueError as exc:
                broken.append(f"{lang}:{key}: {exc} — {text[:80]!r}")
    assert not broken, "битые format-строки:\n" + "\n".join(broken)


def test_no_positional_placeholders():
    positional = [
        f"{lang}:{key}: {text[:80]!r}"
        for lang, texts in (("ru", RU), ("uz", UZ))
        for key, text in texts.items()
        if isinstance(fields := _fields_or_invalid(text), set)
        and any(f == "" or f.split(".", 1)[0].split("[", 1)[0].isdigit() for f in fields)
    ]
    assert not positional, "позиционные поля (get_text передаёт только kwargs):\n" + "\n".join(positional)


def test_placeholder_sets_match_between_ru_and_uz():
    mismatched = []
    for key in sorted(set(RU) & set(UZ)):
        ru_fields, uz_fields = _fields_or_invalid(RU[key]), _fields_or_invalid(UZ[key])
        if ru_fields != uz_fields:
            mismatched.append(f"{key}: ru={ru_fields} uz={uz_fields}")
    assert not mismatched, "плейсхолдеры ru != uz:\n" + "\n".join(mismatched)
