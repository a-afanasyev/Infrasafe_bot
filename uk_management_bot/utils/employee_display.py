"""
Локализованное отображение полей сотрудника.

BUG-BOT-023: вместо сырых DB-значений (status='approved',
roles='applicant, executor, manager', specialization='["plumber",...]')
рендерим через get_text с ключами user_statuses.*, roles.*, specializations.*.
"""
from __future__ import annotations

import json
from typing import Iterable, Optional

from uk_management_bot.utils.helpers import get_text


def format_user_status(status: Optional[str], language: str) -> str:
    """`approved` → `✅ Одобрен`."""
    if not status:
        return get_text("employee_mgmt.handlers.not_specified", language=language)
    localized = get_text(f"user_statuses.{status}", language=language)
    # Если ключ не определён — get_text вернёт сам ключ; покажем raw значение
    if localized == f"user_statuses.{status}":
        return status
    return localized


def format_roles(roles_raw: Optional[str | Iterable[str]], language: str) -> str:
    """JSON-список ролей → "Заявитель, Исполнитель, Менеджер"."""
    if not roles_raw:
        return get_text("employee_mgmt.handlers.not_specified", language=language)

    roles: list[str] = []
    if isinstance(roles_raw, str):
        try:
            parsed = json.loads(roles_raw)
            if isinstance(parsed, list):
                roles = [str(r) for r in parsed if r]
            else:
                roles = [str(parsed)]
        except (json.JSONDecodeError, TypeError):
            # Возможно, уже разделённая строка вида "applicant, executor"
            roles = [r.strip() for r in roles_raw.split(",") if r.strip()]
    else:
        roles = [str(r) for r in roles_raw if r]

    if not roles:
        return get_text("employee_mgmt.handlers.not_specified", language=language)

    translated = []
    for role in roles:
        loc = get_text(f"roles.{role}", language=language)
        translated.append(role if loc == f"roles.{role}" else loc)
    return ", ".join(translated)


def format_specializations(
    specialization_raw: Optional[str | Iterable[str]],
    language: str,
) -> str:
    """JSON-список специализаций → "Сантехник, Электрик, ..."."""
    if not specialization_raw:
        return get_text(
            "specializations.no_specializations",
            language=language,
        )

    specs: list[str] = []
    if isinstance(specialization_raw, str):
        try:
            parsed = json.loads(specialization_raw)
            if isinstance(parsed, list):
                specs = [str(s) for s in parsed if s]
            else:
                specs = [str(parsed)]
        except (json.JSONDecodeError, TypeError):
            specs = [s.strip() for s in specialization_raw.split(",") if s.strip()]
    else:
        specs = [str(s) for s in specialization_raw if s]

    if not specs:
        return get_text("specializations.no_specializations", language=language)

    translated = []
    for spec in specs:
        loc = get_text(f"specializations.{spec}", language=language)
        translated.append(spec if loc == f"specializations.{spec}" else loc)
    return ", ".join(translated)
