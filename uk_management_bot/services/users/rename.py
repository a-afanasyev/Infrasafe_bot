"""Исправление ФИО пользователя менеджером — единственный писатель.

Зачем один модуль на два стека: точек входа четыре (карточка жителя и карточка
сотрудника — в дашборде и в боте), а поле одно и то же. Разъехавшиеся писатели
здесь уже были: регистрация клала в `last_name` пустую строку, бот — `None`,
валидации не было ни у кого. Поэтому решение о том, ЧТО записать и ЧТО занести
в аудит, принимается ровно здесь.

Транзакцией модуль не управляет: `apply_rename` кладёт мутацию и `AuditLog` в
переданную сессию, а коммитит вызывающий — у API она `AsyncSession` (`await
db.commit()`), у бота обычная `Session` внутри `run_db`. Всё, что модуль
делает с сессией, — синхронный `db.add`, легальный в обеих.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.utils.person_name import split_full_name, validate_full_name
from uk_management_bot.utils.user_names import full_name as render_full_name

#: Аккаунты, чьё ФИО менеджер не правит. Тот же список, что у
#: `api/shifts/router/_helpers._ensure_not_privileged`, закрывающего смену
#: статуса: раздел «Сотрудники» не даёт менеджеру трогать равных и старших.
#: Свою опечатку привилегированный аккаунт правит сам — в профиле бота
#: (`handlers/profile_editing.py`), где действует над собой.
PRIVILEGED_ROLES = frozenset({"manager", "admin"})

#: Литерал действия в `audit_logs.action` — в одном ряду с `user_approved` /
#: `user_blocked` / `role_assigned` (`services/auth_service.py`).
AUDIT_ACTION = "user_renamed"


class RenameForbidden(Exception):
    """Целевой аккаунт привилегированный — переименование запрещено."""


@dataclass(frozen=True)
class RenamePlan:
    """Что именно запишется. Считается ДО касания сессии."""

    old_full_name: Optional[str]
    new_full_name: str
    first_name: str
    last_name: Optional[str]

    @property
    def changed(self) -> bool:
        return self.old_full_name != self.new_full_name


def ensure_renamable(target) -> None:
    """`RenameForbidden`, если у цели есть привилегированная роль."""
    roles = set(parse_roles_safe(getattr(target, "roles", None)))
    privileged = roles & PRIVILEGED_ROLES
    if privileged:
        raise RenameForbidden(
            "Нельзя менять ФИО аккаунта с ролями "
            f"{', '.join(sorted(privileged))} — он правит свой профиль сам"
        )


def plan_rename(target, raw_full_name) -> RenamePlan:
    """Валидировать ввод и разложить его по колонкам.

    Бросает `InvalidFullName` (пустое / без букв / длиннее лимита) — вызывающий
    переводит `code` в локализованный текст.
    """
    new_full_name = validate_full_name(raw_full_name)
    first_name, last_name = split_full_name(new_full_name)
    return RenamePlan(
        old_full_name=render_full_name(target),
        new_full_name=new_full_name,
        first_name=first_name,
        last_name=last_name,
    )


def apply_rename(db, target, plan: RenamePlan, *, actor_id: Optional[int]) -> bool:
    """Записать ФИО и аудит в текущую сессию. Коммит — за вызывающим.

    Возвращает, была ли запись. ФИО не изменилось → ни мутации, ни строки
    аудита: журнал модерации должен отвечать «кто и когда ПОМЕНЯЛ», а не «кто
    открывал форму».
    """
    if not plan.changed:
        return False

    target.first_name = plan.first_name
    target.last_name = plan.last_name
    db.add(AuditLog(
        action=AUDIT_ACTION,
        user_id=actor_id,
        telegram_user_id=getattr(target, "telegram_id", None),
        details=json.dumps({
            "target_user_id": getattr(target, "id", None),
            "old_full_name": plan.old_full_name,
            "new_full_name": plan.new_full_name,
        }, ensure_ascii=False),
    ))
    return True
