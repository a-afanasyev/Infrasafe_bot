"""Проверка прав: «можно ли этому человеку это действие».

Одна функция `can` на все каналы (API, бот, workflow). Роли берутся
каноническим резолвером `get_user_roles` (пустые роли = applicant,
`active_role` прав не добавляет — A9-P3-11), состав ролей действия — из
каталога. Статус проверяется только у действий `approved_only`.
"""
from __future__ import annotations

from typing import Any, Iterable, Union

from uk_management_bot.authz.catalog import get_action

#: Субъект проверки: пользователь (объект с полями roles/status) или уже
#: известный набор ролей (например, из middleware бота).
Subject = Union[Any, Iterable[str]]


def roles_of(subject: Subject) -> list[str]:
    """Роли субъекта: у пользователя — через канонический резолвер."""
    if hasattr(subject, "roles") and hasattr(subject, "status"):
        # Ленивый импорт: auth_helpers сам опирается на каталог (цикл модулей).
        from uk_management_bot.utils.auth_helpers import get_user_roles

        return get_user_roles(subject)
    if isinstance(subject, str):
        # Строка — частая ошибка: "manager" иначе стал бы набором букв.
        raise TypeError("Передайте пользователя или набор ролей, а не строку")
    return [str(role) for role in subject]


def has_action_roles(subject: Subject, action_key: str) -> bool:
    """Даёт ли набор ролей действие — без проверки статуса аккаунта."""
    return get_action(action_key).allows(roles_of(subject))


#: Действия админки ролей: суперадмин проходит их независимо от своих ролей.
SUPERADMIN_PREFIX = "rbac."


def is_listed_superadmin(subject: Subject) -> bool:
    """telegram_id прописан в ADMIN_USER_IDS — независимо от статуса аккаунта.

    Для защиты такого аккаунта от чужих действий (блокировка, удаление):
    заблокированный суперадмин прав не имеет, но и снять блокировку с него
    менеджер не должен мочь, как и поставить её.
    """
    telegram_id = getattr(subject, "telegram_id", None)
    if telegram_id is None:
        return False
    from uk_management_bot.config.settings import settings

    return int(telegram_id) in set(settings.ADMIN_USER_IDS or ())


def is_superadmin(subject: Subject) -> bool:
    """Суперадмин — пользователь, чей telegram_id прописан в ADMIN_USER_IDS.

    Назначается только через env/Doppler и рестарт: в админке его не снять и
    не выдать. Заблокированный или удалённый аккаунт суперадмином не считается.
    """
    if getattr(subject, "status", None) in ("blocked", "deleted") or getattr(subject, "deleted_at", None):
        return False
    return is_listed_superadmin(subject)


def can(subject: Subject, action_key: str) -> bool:
    """Разрешено ли действие субъекту.

    Для `approved_only`-действия пользователь обязан быть одобрен. Если
    субъект — голый набор ролей, статус неизвестен: такая проверка для
    `approved_only` невозможна и запрещена (передайте пользователя).
    Действия админки ролей (`rbac.*`) суперадмину разрешены всегда.
    """
    action = get_action(action_key)
    is_user = hasattr(subject, "roles") and hasattr(subject, "status")
    if action.approved_only and not is_user:
        raise TypeError(
            f"Действие {action_key} требует одобренный аккаунт — передайте пользователя, а не роли"
        )
    if is_user and action_key.startswith(SUPERADMIN_PREFIX) and is_superadmin(subject):
        return True
    if not action.allows(roles_of(subject)):
        return False
    if action.approved_only and getattr(subject, "status", None) != "approved":
        return False
    return True
