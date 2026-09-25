"""Детектор «готово»-отчёта исполнителя в рабочей группе (Фаза 4).

Исполнители пишут в группу «сделал #ариза» вместо закрытия заявки. Такое
сообщение — НЕ новая заявка: LLM не зовём, в группе молчим, автору-исполнителю
основной бот пишет в личку (``handlers/group_intake_done``).

Признак — ОБА условия: тег заявки (#заявка/#ariza/… целым словом, тот же
матчер, что у тег-режима) и слово «готово» целым словом. Слова сверяются
после транслита (``translit.py``): кириллица и латиница одним списком —
«тайёр» → «tayyor», «бажарилди» → «bajarildi». Отрицание рядом («не готово»,
«tayyor emas») — не отчёт. Чистая функция без I/O; роль автора проверяет
вызывающий.
"""
from __future__ import annotations

import re
from typing import Optional

from uk_management_bot.services.group_intake.translit import translit

# Основы слов после транслита; совпадение — с начала слова.
# готово/готов → gotov; сделал(а/и)/сделано → sdelal/sdelan;
# tayyor/тайёр; bajarildi/бажарилди, bajardim/бажардим.
_DONE_RE = re.compile(
    r"(?<![\w'])(?P<neg>ne\s+)?(?:gotov|sdela[ln]|tayyor|bajarildi|bajardim)[\w']*"
    r"(?P<emas>\s+emas)?(?![\w'])",
    flags=re.UNICODE,
)


def has_done_word(text: Optional[str]) -> bool:
    """Есть ли в тексте «готово» без отрицания (регистр и алфавит не важны)."""
    for match in _DONE_RE.finditer(translit(text or "")):
        if not match.group("neg") and not match.group("emas"):
            return True
    return False


def is_done_report(text: Optional[str], *, has_tag: bool) -> bool:
    """«Готово»-отчёт: тег заявки + слово «готово». ``has_tag`` решает
    вызывающий (матчер тега живёт в handlers/group_intake)."""
    return has_tag and has_done_word(text)
