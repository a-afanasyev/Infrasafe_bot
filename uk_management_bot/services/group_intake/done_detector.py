"""Детектор «готово»-отчёта исполнителя в рабочей группе (Фаза 4).

Исполнители пишут в группу «сделал #ариза» вместо закрытия заявки. Такое
сообщение — НЕ новая заявка: LLM не зовём, в группе молчим, автору-исполнителю
основной бот пишет в личку (``handlers/group_intake_done``).

Признак — ОБА условия: тег заявки (#заявка/#ariza/… целым словом, тот же
матчер, что у тег-режима) и слово «готово» целым словом. Слова сверяются
после транслита (``translit.py``): кириллица и латиница одним списком —
«тайёр» → «tayyor», «бажарилди» → «bajarildi». Отрицание рядом («не готово»,
«tayyor emas») и вопрос сразу после слова («готово?», «tayyor ?») — не
отчёт; однокоренные «готовлю»/«tayyormi» — тоже (только формы из списка). Чистая функция без I/O; роль автора проверяет
вызывающий.
"""
from __future__ import annotations

import re
from typing import Optional

from uk_management_bot.services.group_intake.translit import translit

# Формы слова ЦЕЛИКОМ (после транслита): «готовлю»/«tayyormi» — не отчёт.
# готово/готов(а, ы) → gotov…; сделал(а, и)/сделан(о) → sdela…;
# tayyor/тайёр; bajarildi/бажарилди, bajardim/бажардим.
_DONE_FORMS = (
    "gotovo", "gotov", "gotova", "gotovy",
    "sdelal", "sdelala", "sdelali", "sdelano", "sdelan",
    "tayyor", "bajarildi", "bajardim",
)
_DONE_RE = re.compile(
    r"(?<![\w'])(?P<neg>ne\s+)?(?:" + "|".join(_DONE_FORMS) + r")(?![\w'])"
    r"(?P<question>\s*\?)?(?P<emas>\s+emas)?",
    flags=re.UNICODE,
)


def has_done_word(text: Optional[str]) -> bool:
    """Есть ли в тексте «готово» без отрицания и без вопроса сразу после
    слова («готово?» — вопрос, не отчёт); регистр и алфавит не важны."""
    for match in _DONE_RE.finditer(translit(text or "")):
        if not (match.group("neg") or match.group("question") or match.group("emas")):
            return True
    return False


def is_done_report(text: Optional[str], *, has_tag: bool) -> bool:
    """«Готово»-отчёт: тег заявки + слово «готово». ``has_tag`` решает
    вызывающий (матчер тега живёт в handlers/group_intake)."""
    return has_tag and has_done_word(text)
