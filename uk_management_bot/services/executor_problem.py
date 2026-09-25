"""«Проблема» исполнителя: комментарий в заявку по шаблону + уведомление менеджерам.

Решение владельца (план «Простой режим исполнителя»): статус заявки не
меняется, менеджер получает уведомление. Шаблоны — `PROBLEM_TEMPLATES`,
подписи — в локалях бота (`notifications.executor_problem.*`).

Хранение без миграции: `RequestComment` с `comment_type="problem"`, текст —
подпись шаблона (RU, язык хранения системных записей истории) и через перевод
строки — текст исполнителя. Уведомление менеджеру рендерится на ЕГО языке из
кода шаблона, а не из сохранённой строки.

Рассылка менеджерам (сеть, Telegram) — в API-слое
(`api/requests/problem_notify.py`): домен не импортирует HTTP-пакет
(AUD7-ARCH-02); здесь только тексты.
"""
from __future__ import annotations

import html
from typing import Optional

from uk_management_bot.utils.helpers import get_text

PROBLEM_TEMPLATES = ("no_material", "not_let_in", "resident_absent", "need_master")

_KEY_PREFIX = "notifications.executor_problem"
# Хранимый текст комментария — на языке системных записей истории.
_STORAGE_LANGUAGE = "ru"
_MAX_ADDRESS = 200
_MAX_TEXT = 1000


def problem_label(template: str, language: str) -> str:
    return get_text(f"{_KEY_PREFIX}.{template}", language=language)


def problem_comment_text(template: str, text: Optional[str]) -> str:
    """Текст комментария в истории: подпись шаблона [+ перевод строки + текст]."""
    label = problem_label(template, _STORAGE_LANGUAGE)
    details = (text or "").strip()
    return f"{label}\n{details}" if details else label  # html-raw: текст комментария в БД, экранируется в точке вывода


def _clip(value: Optional[str], limit: int) -> str:
    value = value or ""
    return value if len(value) <= limit else value[: limit - 1] + "…"


def render_manager_text(language: str, *, request_number: str, executor: str,
                        address: Optional[str], template: str, text: Optional[str]) -> str:
    """HTML для менеджера. Пользовательское — через html.escape (обрезка ДО escape)."""
    details = (text or "").strip()
    return get_text(
        f"{_KEY_PREFIX}.message",
        language=language,
        request_number=html.escape(request_number),
        executor=html.escape(executor),
        address=html.escape(_clip(address, _MAX_ADDRESS)),
        problem=html.escape(problem_label(template, language)),
        details=(get_text(f"{_KEY_PREFIX}.details", language=language,
                          text=html.escape(_clip(details, _MAX_TEXT)))
                 if details else ""),
    )
