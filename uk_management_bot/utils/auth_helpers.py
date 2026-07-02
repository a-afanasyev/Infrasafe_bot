"""
Утилитарные функции для проверки авторизации и прав доступа
"""

import json
import logging
from typing import Optional, List
from sqlalchemy import or_
from uk_management_bot.database.models.user import User

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
    # Проверяем через roles параметр
    if roles and any(role in ['admin', 'manager'] for role in roles):
        return True
    
    # Fallback проверка через user объект
    if user:
        # Проверяем новое поле roles (COD-01: канонический парсер, JSON+CSV)
        user_roles = parse_roles_safe(getattr(user, "roles", None))
        if any(role in ['admin', 'manager'] for role in user_roles):
            return True

    return False

def has_executor_access(roles: Optional[List[str]] = None, user: Optional[User] = None) -> bool:
    """
    Проверяет, есть ли у пользователя права исполнителя
    
    Args:
        roles: Список ролей из middleware
        user: Объект пользователя
        
    Returns:
        bool: True если есть права исполнителя, False иначе
    """
    # Проверяем через roles параметр
    if roles and any(role in ['executor', 'manager', 'admin'] for role in roles):
        return True
    
    # Fallback проверка через user объект
    if user:
        # Проверяем активную роль
        if user.active_role == "executor":
            return True

        # Проверяем новое поле roles (COD-01: канонический парсер, JSON+CSV)
        if "executor" in parse_roles_safe(getattr(user, "roles", None)):
            return True

    return False

def get_user_roles(user: User) -> List[str]:
    """
    Получает список ролей пользователя с fallback логикой

    Args:
        user: Объект пользователя

    Returns:
        List[str]: Список ролей пользователя
    """
    try:
        # Используем безопасную функцию парсинга ролей
        roles_list = parse_roles_safe(user.roles)

        return roles_list or ["applicant"]

    except Exception as exc:
        logger.warning(f"Ошибка получения ролей пользователя {user.telegram_id}: {exc}")
        return ["applicant"]

def get_active_role(user: User) -> str:
    """
    Получает активную роль пользователя с fallback логикой
    
    Args:
        user: Объект пользователя
        
    Returns:
        str: Активная роль пользователя
    """
    try:
        # Проверяем активную роль
        if user.active_role:
            return user.active_role
        
        # Fallback к списку ролей
        roles_list = get_user_roles(user)
        if roles_list:
            return roles_list[0]
            
    except Exception as exc:
        logger.warning(f"Ошибка получения активной роли пользователя {user.telegram_id}: {exc}")
    
    return "applicant"

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
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        user_roles = get_user_roles(user)
        return required_role in user_roles
        
    except Exception as e:
        logger.error(f"Ошибка проверки роли пользователя {user_id}: {e}")
        return False


def legacy_role_filter(*roles: str):
    """SQLAlchemy-выражение «у пользователя есть хотя бы одна из ролей».

    DB-060/AUD3-01 (PR-31): legacy-колонка ``User.role`` удалена. Фильтр теперь
    идёт по JSON-массиву ``User.roles`` (хранится как TEXT, напр.
    ``'["applicant", "executor"]'``) через ``LIKE '%"role"%'`` — кросс-диалектно
    (sqlite-тесты + postgres-прод), матчит закавыченный токен роли. Это РАСШИРЯЕТ
    прежнее ``role == x`` (одна основная роль) до «роль среди всех ролей» —
    устаревшая колонка расходилась с реальным набором ролей (см. AUD3-01).

    Args:
        *roles: одна или несколько ролей; результат — ИЛИ по вхождению любой.
    """
    clauses = [User.roles.like(f'%"{role}"%') for role in roles]
    if len(clauses) == 1:
        return clauses[0]
    return or_(*clauses)


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
    иначе первую роль из ``roles``, иначе ``None``. В отличие от
    ``get_active_role``/``get_user_roles`` НЕ подставляет дефолт «applicant» —
    нужна там, где при отсутствии роли важен пустой результат (fallback-ветки).
    """
    if getattr(user, "active_role", None):
        return user.active_role
    roles_list = parse_roles_safe(getattr(user, "roles", None))
    return roles_list[0] if roles_list else None
