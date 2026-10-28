"""Тексты пингов ИИ-менеджера: локаль по умолчанию, переопределение из конфига.

Ключ = суффикс локали после ``ai_manager.`` (``sla.executor_overdue``,
``public.assigned``). Переопределения — из ``auto_manager_config.data.ai
.templates``, действуют в пределах ``with overrides(...)`` (contextvars: тик
SLA работает в потоке, public_status — в своей сессии).

Контракт переопределения: только простые подстановки ``{имя}`` из набора
стандартного шаблона (ни format-spec, ни конверсий, ни позиционных);
подстановка через ``re.sub`` — ``str.format`` не вызывается; HTML — только
теги Telegram, сбалансированные, ``<``/``>`` вне тегов запрещены; итоговый
текст ≤ RENDERED_MAX, иначе — стандартный текст локали (штатный пинг лучше
обрезанного HTML).
"""
from __future__ import annotations

import contextvars
import re
from contextlib import contextmanager
from functools import lru_cache
from html.parser import HTMLParser
from typing import Iterator, Mapping, Optional

from uk_management_bot.utils.helpers import LANGUAGE_FALLBACKS, get_text

TEMPLATE_KEYS: tuple[str, ...] = (
    "sla.executor_overdue", "sla.staff_group", "sla.manager_overdue", "sla.reassign_failed",
    "sla.reassigned_old", "sla.clarification_reminder", "sla.clarification_manager",
    "sla.executed_unconfirmed", "sla.auto_accepted", "sla.critical_unassigned",
    "public.assigned", "public.executed",
)
LANGS = ("ru", "uz")
TEXT_MAX = 1000          # длина шаблона
RENDERED_MAX = 3500      # длина после подстановки (лимит Telegram 4096 с запасом)
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_ANY_BRACE = re.compile(r"\{[^{}]*\}|[{}]")
_TAG = re.compile(r"<[^<>]+>")
_TG_TAGS = frozenset({
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "tg-spoiler", "blockquote",
})
_TG_ATTRS: dict[str, frozenset[str]] = {"a": frozenset({"href"}), "pre": frozenset({"language"})}
_overrides: contextvars.ContextVar[Mapping[str, Mapping[str, str]]] = contextvars.ContextVar(
    "ai_templates", default={},
)


def default_text(key: str, lang: str) -> str:
    return get_text(f"ai_manager.{key}", language=lang)


def placeholders_of(text: str) -> frozenset[str]:
    """Имена простых подстановок; любая другая скобка — ValueError."""
    for m in _ANY_BRACE.finditer(text):
        if not _PLACEHOLDER.fullmatch(m.group(0)):
            raise ValueError(f"недопустимая подстановка {m.group(0)!r}: только {{имя}}")
    return frozenset(_PLACEHOLDER.findall(text))


@lru_cache(maxsize=None)
def placeholders(key: str) -> frozenset[str]:
    return placeholders_of(default_text(key, "ru"))


def defaults() -> dict[str, dict]:
    """Для API/страницы: стандартные тексты и допустимые плейсхолдеры."""
    return {key: {"ru": default_text(key, "ru"), "uz": default_text(key, "uz"),
                  "placeholders": sorted(placeholders(key))} for key in TEMPLATE_KEYS}


class _TgHtml(HTMLParser):
    """Допустимые теги Telegram с допустимыми атрибутами, сбалансированные."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []
        self.error: Optional[str] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        allowed = _TG_ATTRS.get(tag, frozenset())
        if tag not in _TG_TAGS or any(name not in allowed for name, _ in attrs):
            self.error = self.error or f"недопустимый тег <{tag}>"
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack.pop() != tag:
            self.error = self.error or f"непарный тег </{tag}>"

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.error = self.error or f"недопустимый тег <{tag}/>"


def check_telegram_html(text: str) -> None:
    """ValueError, если текст нельзя отправить с parse_mode=HTML."""
    if "<" in _TAG.sub("", text) or ">" in _TAG.sub("", text):
        raise ValueError("символы < и > вне тегов нужно экранировать (&lt; &gt;)")
    parser = _TgHtml()
    parser.feed(text)
    parser.close()
    if parser.error or parser.stack:
        raise ValueError(parser.error or f"незакрытый тег <{parser.stack[-1]}>")


def _validate_one(key: str, lang: str, text: object) -> Optional[str]:
    if lang not in LANGS or not isinstance(text, str):
        raise ValueError(f"ai.templates.{key}: язык {lang!r} / текст должен быть строкой")
    text = text.strip()
    if not text:
        return None
    if len(text) > TEXT_MAX:
        raise ValueError(f"ai.templates.{key}.{lang}: длиннее {TEXT_MAX} символов")
    try:
        extra = sorted(placeholders_of(text) - placeholders(key))
        check_telegram_html(text)
    except ValueError as e:
        raise ValueError(f"ai.templates.{key}.{lang}: {e}") from None
    if extra:
        raise ValueError(f"ai.templates.{key}.{lang}: недопустимые плейсхолдеры {extra}")
    return text


def validate_overrides(raw: object) -> dict[str, dict[str, str]]:
    """Чистая валидация блока ``ai.templates``; пустые строки отбрасываются."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("ai.templates: ожидается dict")
    out: dict[str, dict[str, str]] = {}
    for key, langs in raw.items():
        if key not in TEMPLATE_KEYS:
            raise ValueError(f"ai.templates: неизвестный шаблон {key!r}")
        if not isinstance(langs, dict):
            raise ValueError(f"ai.templates.{key}: ожидается dict {{ru, uz}}")
        kept = {lang: text for lang, raw_text in langs.items()
                if (text := _validate_one(key, lang, raw_text)) is not None}
        if kept:
            out[key] = kept
    return out


@contextmanager
def overrides(templates: Optional[Mapping[str, Mapping[str, str]]]) -> Iterator[None]:
    token = _overrides.set(templates or {})
    try:
        yield
    finally:
        _overrides.reset(token)


def render(key: str, lang: str = "ru", **fmt) -> str:
    """Переопределение из контекста (язык с fallback uz_cyrl→uz) или локаль.
    Нет значения для подстановки / результат длиннее RENDERED_MAX → локаль."""
    text = _overrides.get().get(key, {}).get(LANGUAGE_FALLBACKS.get(lang, lang))
    if text and placeholders_of(text) <= set(fmt):
        rendered = _PLACEHOLDER.sub(lambda m: str(fmt[m.group(1)]), text)
        if len(rendered) <= RENDERED_MAX:
            return rendered
    return get_text(f"ai_manager.{key}", language=lang, **fmt)
