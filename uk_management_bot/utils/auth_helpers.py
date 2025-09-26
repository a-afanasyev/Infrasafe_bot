"""
Утилитарные функции для проверки авторизации и прав доступа
"""

import json
import logging
from typing import Optional, List
from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)

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
        # Проверяем новое поле roles
        if user.roles:
            try:
                user_roles = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
                if isinstance(user_roles, list) and any(role in ['admin', 'manager'] for role in user_roles):
                    return True
            except Exception as e:
                logger.warning(f"Ошибка парсинга ролей пользователя {user.telegram_id}: {e}")
        
        # Fallback к старому полю role
        if user.role in ['admin', 'manager']:
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
            
        # Проверяем новое поле roles
        if user.roles:
            try:
                user_roles = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
                if isinstance(user_roles, list) and "executor" in user_roles:
                    return True
            except Exception as e:
                logger.warning(f"Ошибка парсинга ролей пользователя {user.telegram_id}: {e}")
        
        # Fallback к старому полю role
        if user.role in ['executor', 'manager', 'admin']:
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
    roles_list = []
    
    try:
        # Проверяем новое поле roles
        if user.roles:
            try:
                parsed = json.loads(user.roles)
                if isinstance(parsed, list) and parsed:
                    roles_list = [str(r) for r in parsed if isinstance(r, str)]
            except Exception as parse_exc:
                logger.warning(f"Ошибка парсинга roles для пользователя {user.telegram_id}: {parse_exc}")
        
        # Fallback к старому полю role
        if not roles_list and user.role:
            roles_list = [user.role]
            
    except Exception as exc:
        logger.warning(f"Ошибка получения ролей пользователя {user.telegram_id}: {exc}")
    
    return roles_list or ["applicant"]

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
