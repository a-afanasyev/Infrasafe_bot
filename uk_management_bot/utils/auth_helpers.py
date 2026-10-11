"""
Утилитарные функции для проверки авторизации и прав доступа
"""

import json
import logging
from typing import Optional, List
from uk_management_bot.database.models.user import User
from uk_management_bot.database.roles_type import roles_contain
from uk_management_bot.utils.constants import ROLE_APPLICANT

logger = logging.getLogger(__name__)


def parse_roles_safe(roles_value: Optional[str]) -> List[str]:
    """
    Безопасно парсит роли из строки (поддерживает CSV и JSON форматы)

    Args:
        roles_value: Строка с ролями (CSV или JSON)

    Returns:
        List[str]: Список ролей

    Examples:
        parse_roles_safe("applicant,executor,manager") -> ["applicant", "executor", "manager"]
        parse_roles_safe('["applicant","executor"]') -> ["applicant", "executor"]
        parse_roles_safe(None) -> []
    """
    if not roles_value:
        return []

    # Уже список (напр. значение прокинуто из middleware/DTO, а не из TEXT-колонки):
    # нормализуем к списку строк без повторного парсинга (COD-01).
    if isinstance(roles_value, list):
        return [str(r) for r in roles_value if isinstance(r, str)]

    try:
        # Сначала пробуем как JSON массив
        parsed = json.loads(roles_value)
        if isinstance(parsed, list):
            return [str(r) for r in parsed if isinstance(r, str)]
    except (json.JSONDecodeError, ValueError, TypeError):
        # Если не JSON, парсим как CSV строку
        if isinstance(roles_value, str):
            return [r.strip() for r in roles_value.split(",") if r.strip()]

    return []


def has_admin_access(roles: Optional[List[str]] = None, user: Optional[User] = None) -> bool:
    """
    Проверяет, есть ли у пользователя права доступа к админ панели
    
    Args:
        roles: Список ролей из middleware
        user: Объект пользователя
        
    Returns:
        bool: True если есть права доступа, False иначе
    """
    # Состав ролей — действие admin_panel.use в authz/catalog.py.
    return _action_via_roles_or_user("admin_panel.use", roles, user)

def has_manager_role(roles: Optional[List[str]] = None,
                     user: Optional[User] = None) -> bool:
    """Именно МЕНЕДЖЕР, без admin.

    `has_admin_access` пропускает обе роли, а канон workflow разрешает
    `MANAGER_ASSIGN` только менеджеру (`request_workflow.guards._is_manager`).
    Без отдельной проверки чистый `admin` доходил бы до команды и получал
    NotAuthorized в виде общей ошибки вместо человеческого отказа.

    Fallback на объект пользователя — зеркало `has_admin_access`: смотреть
    только в `roles` из middleware значило бы отказать настоящему менеджеру,
    когда контекст роли не доехал.
    """
    return _action_via_roles_or_user("management.decide", roles, user)


def has_executor_access(roles: Optional[List[str]] = None, user: Optional[User] = None) -> bool:
    """
    Проверяет, есть ли у пользователя права исполнителя
    
    Args:
        roles: Список ролей из middleware
        user: Объект пользователя
        
    Returns:
        bool: True если есть права исполнителя, False иначе
    """
    # Особенность «как есть» (снимок прав 2026-10-10): ответ зависит от способа
    # вызова — через roles пускает executor/manager/admin (execution.view), через
    # user только executor (execution.work). Сведение — решение владельца.
    from uk_management_bot.authz.catalog import get_action

    if roles and get_action("execution.view").allows(roles):
        return True
    # Fallback через user — только roles (A9-P3-11: active_role прав не даёт).
    if user and get_action("execution.work").allows(parse_roles_safe(getattr(user, "roles", None))):
        return True
    return False


def action_allowed_for_roles(action_key: str, roles) -> bool:
    """Даёт ли набор ролей действие из `authz/catalog.py` (статус не проверяется).

    Точка входа для access_control: его граница с ядром (AUD5-ARCH-4) пускает
    только контрактные модули, и этот модуль среди них — пакет `authz`
    напрямую оттуда не импортируется.
    """
    from uk_management_bot.authz.catalog import get_action

    return get_action(action_key).allows(roles)


def _action_via_roles_or_user(action_key: str, roles: Optional[List[str]], user) -> bool:
    """Общая механика ролевых предикатов бота: сначала роли из middleware,
    затем fallback на `user.roles` (канонический парсер COD-01).

    Ленивый импорт каталога: authz опирается на этот модуль (цикл модулей).
    """
    from uk_management_bot.authz.catalog import get_action

    action = get_action(action_key)
    if roles and action.allows(roles):
        return True
    if user and action.allows(parse_roles_safe(getattr(user, "roles", None))):
        return True
    return False

def get_user_roles(user: User) -> List[str]:
    """ЕДИНСТВЕННЫЙ канонический резолвер ролей (A9-P3-11): бот, API-двери
    (``api.dependencies.require_roles``) и access_control.

    Роли берутся ТОЛЬКО из ``user.roles`` (JSON/CSV/list через
    ``parse_roles_safe``). Пусто, нечитаемо или ошибка → ``["applicant"]`` —
    минимальная непривилегированная роль. ``active_role`` ролей НЕ добавляет:
    прежний API-фолбэк на ``active_role`` при пустых ``roles`` пускал в
    менеджерские эндпоинты пользователя без единой роли.
    """
    try:
        roles_list = parse_roles_safe(user.roles)
    except Exception as exc:
        logger.warning(f"Ошибка получения ролей пользователя {getattr(user, 'telegram_id', None)}: {exc}")
        return [ROLE_APPLICANT]
    if not roles_list:
        # Инварианта «roles непусты» в БД нет (колонка nullable) — сигналим о
        # такой строке, трактуем как applicant.
        logger.warning(
            "Пустые/нечитаемые roles у пользователя %s — трактуем как applicant",
            getattr(user, "telegram_id", None),
        )
        return [ROLE_APPLICANT]
    return roles_list


def get_active_role(user: User) -> str:
    """Активная роль: ``active_role``, только если она ЕСТЬ среди канонических
    ролей (``get_user_roles``); иначе первая из них (A9-P3-11 — устаревший или
    чужой ``active_role`` не повышает права)."""
    try:
        roles_list = get_user_roles(user)
        active = user.active_role
        if active and active in roles_list:
            return active
        return roles_list[0]
    except Exception as exc:
        logger.warning(f"Ошибка получения активной роли пользователя {getattr(user, 'telegram_id', None)}: {exc}")

    return ROLE_APPLICANT

def check_user_role_sync(user_id: int, required_role: str, db) -> bool:
    """Sync-ядро check_user_role (AUD3-07): тело 1:1, вызывается и из
    async-обёртки (неконвертированные хендлеры), и из run_db-юнитов
    конвертированных (сессия воркер-потока)."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        user_roles = get_user_roles(user)
        return required_role in user_roles
        
    except Exception as e:
        logger.error(f"Ошибка проверки роли пользователя {user_id}: {e}")
        return False


async def check_user_role(user_id: int, required_role: str, db) -> bool:
    """
    Проверяет, имеет ли пользователь указанную роль
    
    Args:
        user_id: ID пользователя
        required_role: Требуемая роль
        db: Сессия базы данных
        
    Returns:
        bool: True если пользователь имеет требуемую роль, False иначе
    """
    return check_user_role_sync(user_id, required_role, db)


def legacy_role_filter(*roles: str):
    """SQLAlchemy-выражение «у пользователя есть хотя бы одна из ролей».

    DB-060/AUD3-01 (PR-31): legacy-колонка ``User.role`` удалена. Фильтр теперь
    идёт по JSON-массиву ``User.roles`` через ``roles_contain`` (DB-049: на
    PostgreSQL — ``roles @> '["role"]'`` под GIN, на sqlite — ``LIKE '%"role"%'``),
    точное совпадение элемента массива. Это РАСШИРЯЕТ
    прежнее ``role == x`` (одна основная роль) до «роль среди всех ролей» —
    устаревшая колонка расходилась с реальным набором ролей (см. AUD3-01).

    Args:
        *roles: одна или несколько ролей; результат — ИЛИ по вхождению любой.
    """
    return roles_contain(User.roles, *roles)


def sync_legacy_role(user: User, primary_role: str) -> None:
    """No-op после дропа legacy-колонки ``User.role`` (DB-060, PR-31).

    Колонка удалена; источник истины — ``user.roles`` (JSON) + ``user.active_role``,
    которые вызывающий код поддерживает сам. Сигнатура сохранена, чтобы не трогать
    точки вызова — функция намеренно ничего не делает.
    """
    return None


def legacy_primary_role(user) -> Optional[str]:
    """Скалярная «основная роль» пользователя без дефолта «applicant» (PR-31).

    Заменяет чтение удалённой колонки ``User.role``: возвращает ``active_role``,
    если она входит в ``roles`` (A9-P3-11), иначе первую роль из ``roles``,
    иначе ``None``. В отличие от ``get_active_role``/``get_user_roles`` НЕ
    подставляет дефолт «applicant» — нужна там, где при отсутствии роли важен
    пустой результат (fallback-ветки).
    """
    roles_list = parse_roles_safe(getattr(user, "roles", None))
    active = getattr(user, "active_role", None)
    if active and active in roles_list:
        return active
    return roles_list[0] if roles_list else None
