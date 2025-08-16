"""
Сервис управления пользователями для менеджеров

Предоставляет функции для:
- Получения списков пользователей с фильтрацией
- Статистики пользователей
- Поиска и пагинации
- Форматирования информации о пользователях
"""

import json
import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from database.models.user import User
from utils.helpers import get_text

logger = logging.getLogger(__name__)


class UserManagementService:
    """Сервис управления пользователями для менеджеров"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ═══ СТАТИСТИКА ПОЛЬЗОВАТЕЛЕЙ ═══
    
    def get_user_stats(self) -> Dict[str, int]:
        """
        Получить статистику пользователей
        
        Returns:
            Dict с количествами пользователей по категориям
        """
        try:
            stats = {
                'pending': self.db.query(User).filter(User.status == 'pending').count(),
                'approved': self.db.query(User).filter(User.status == 'approved').count(),
                'blocked': self.db.query(User).filter(User.status == 'blocked').count(),
                'total': self.db.query(User).count()
            }
            
            # Подсчет сотрудников (executor или manager)
            staff_count = self.db.query(User).filter(
                or_(
                    User.roles.contains('executor'),
                    User.roles.contains('manager')
                )
            ).count()
            
            stats['staff'] = staff_count
            
            logger.info(f"Статистика пользователей получена: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики пользователей: {e}")
            return {
                'pending': 0,
                'approved': 0, 
                'blocked': 0,
                'staff': 0,
                'total': 0
            }
    
    # ═══ СПИСКИ ПОЛЬЗОВАТЕЛЕЙ С ПАГИНАЦИЕЙ ═══
    
    def get_users_by_status(self, status: str, page: int = 1, limit: int = 10) -> Dict:
        """
        Получить пользователей по статусу с пагинацией
        
        Args:
            status: Статус пользователя (pending, approved, blocked)
            page: Номер страницы (начиная с 1)
            limit: Количество пользователей на странице
            
        Returns:
            Dict с пользователями и информацией о пагинации
        """
        try:
            offset = (page - 1) * limit
            
            # Базовый запрос
            query = self.db.query(User).filter(User.status == status)
            
            # Сортировка: новые пользователи сначала
            query = query.order_by(User.created_at.desc())
            
            # Подсчет общего количества
            total = query.count()
            
            # Получение пользователей для текущей страницы
            users = query.offset(offset).limit(limit).all()
            
            # Расчет информации о пагинации
            total_pages = (total + limit - 1) // limit if total > 0 else 1
            has_next = page * limit < total
            has_prev = page > 1
            
            result = {
                'users': users,
                'total': total,
                'page': page,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_prev': has_prev,
                'status': status
            }
            
            logger.info(f"Получены пользователи со статусом {status}: страница {page}, найдено {len(users)}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка получения пользователей по статусу {status}: {e}")
            return {
                'users': [],
                'total': 0,
                'page': page,
                'total_pages': 1,
                'has_next': False,
                'has_prev': False,
                'status': status
            }
    
    def get_staff_users(self, page: int = 1, limit: int = 10) -> Dict:
        """
        Получить сотрудников (executor и manager) с пагинацией
        
        Args:
            page: Номер страницы
            limit: Количество пользователей на странице
            
        Returns:
            Dict с сотрудниками и информацией о пагинации
        """
        try:
            offset = (page - 1) * limit
            
            # Запрос сотрудников (executor или manager)
            query = self.db.query(User).filter(
                or_(
                    User.roles.contains('executor'),
                    User.roles.contains('manager')
                )
            )
            
            # Сортировка по активности (approved сначала)
            query = query.order_by(User.status.desc(), User.created_at.desc())
            
            total = query.count()
            users = query.offset(offset).limit(limit).all()
            
            total_pages = (total + limit - 1) // limit if total > 0 else 1
            has_next = page * limit < total
            has_prev = page > 1
            
            result = {
                'users': users,
                'total': total,
                'page': page,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_prev': has_prev,
                'type': 'staff'
            }
            
            logger.info(f"Получены сотрудники: страница {page}, найдено {len(users)}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка получения сотрудников: {e}")
            return {
                'users': [],
                'total': 0,
                'page': page,
                'total_pages': 1,
                'has_next': False,
                'has_prev': False,
                'type': 'staff'
            }
    
    # ═══ ПОИСК И ФИЛЬТРАЦИЯ ═══
    
    def search_users(self, query: str = None, filters: Dict = None, page: int = 1, limit: int = 10) -> Dict:
        """
        Поиск пользователей с фильтрами
        
        Args:
            query: Поисковый запрос (имя, username)
            filters: Фильтры (status, role, specialization)
            page: Номер страницы
            limit: Количество результатов на странице
            
        Returns:
            Dict с результатами поиска и пагинацией
        """
        try:
            offset = (page - 1) * limit
            
            # Базовый запрос
            db_query = self.db.query(User)
            
            # Поиск по тексту (имя, фамилия, username)
            if query and query.strip():
                search_term = f"%{query.strip()}%"
                db_query = db_query.filter(
                    or_(
                        User.first_name.ilike(search_term),
                        User.last_name.ilike(search_term),
                        User.username.ilike(search_term)
                    )
                )
            
            # Применение фильтров
            if filters:
                if filters.get('status'):
                    db_query = db_query.filter(User.status == filters['status'])
                
                if filters.get('role'):
                    db_query = db_query.filter(User.roles.contains(filters['role']))
                
                if filters.get('specialization'):
                    db_query = db_query.filter(User.specialization.contains(filters['specialization']))
            
            # Сортировка результатов
            db_query = db_query.order_by(User.status.desc(), User.created_at.desc())
            
            total = db_query.count()
            users = db_query.offset(offset).limit(limit).all()
            
            total_pages = (total + limit - 1) // limit if total > 0 else 1
            has_next = page * limit < total
            has_prev = page > 1
            
            result = {
                'users': users,
                'total': total,
                'page': page,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_prev': has_prev,
                'query': query,
                'filters': filters or {}
            }
            
            logger.info(f"Поиск пользователей: query='{query}', filters={filters}, найдено {len(users)}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка поиска пользователей: {e}")
            return {
                'users': [],
                'total': 0,
                'page': page,
                'total_pages': 1,
                'has_next': False,
                'has_prev': False,
                'query': query,
                'filters': filters or {}
            }
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Получить пользователя по ID
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Объект User или None
        """
        try:
            return self.db.query(User).filter(User.id == user_id).first()
        except Exception as e:
            logger.error(f"Ошибка получения пользователя по ID {user_id}: {e}")
            return None
    
    # ═══ ФОРМАТИРОВАНИЕ ИНФОРМАЦИИ ═══
    
    def format_user_info(self, user: User, language: str = 'ru', detailed: bool = True) -> str:
        """
        Форматировать информацию о пользователе для отображения
        
        Args:
            user: Объект пользователя
            language: Язык интерфейса
            detailed: Подробная информация или краткая
            
        Returns:
            Отформатированная строка с информацией о пользователе
        """
        try:
            # Базовая информация
            name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            if not name:
                name = user.username or f"ID{user.telegram_id}"
            
            # Статус с эмодзи
            status_emoji = {
                "pending": "📝",
                "approved": "✅", 
                "blocked": "🚫"
            }.get(user.status, "❓")
            
            status_text = get_text(f"user_status.{user.status}", language=language)
            
            # Роли
            roles_text = self._format_user_roles(user, language)
            
            if detailed:
                # Подробная информация
                info_parts = [
                    f"👤 {name}",
                    f"📱 @{user.username or get_text('common.none', language=language)}",
                    f"{status_emoji} {status_text}",
                    f"👥 {roles_text}",
                ]
                
                # Специализации для исполнителей
                spec_text = self._format_user_specializations(user, language)
                if spec_text:
                    info_parts.append(f"🛠️ {spec_text}")
                
                # Контактная информация
                if user.phone:
                    info_parts.append(f"📞 {user.phone}")
                
                info_parts.append(f"🆔 {user.telegram_id}")
                
                return "\n".join(info_parts)
            else:
                # Краткая информация
                return f"{status_emoji} {name} ({roles_text})"
                
        except Exception as e:
            logger.error(f"Ошибка форматирования информации о пользователе {user.id}: {e}")
            return f"Пользователь {user.id} (ошибка отображения)"
    
    def _format_user_roles(self, user: User, language: str = 'ru') -> str:
        """Форматировать роли пользователя"""
        try:
            if not user.roles:
                return get_text("roles.none", language=language)
            
            roles = json.loads(user.roles)
            if not isinstance(roles, list):
                return get_text("roles.none", language=language)
            
            role_names = []
            for role in roles:
                role_text = get_text(f"roles.{role}", language=language)
                role_names.append(role_text)
                
                # Отметить активную роль
                if role == user.active_role:
                    role_names[-1] = f"*{role_names[-1]}*"
            
            return ", ".join(role_names)
            
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Ошибка парсинга ролей пользователя {user.id}: {e}")
            return get_text("roles.none", language=language)
    
    def _format_user_specializations(self, user: User, language: str = 'ru') -> str:
        """Форматировать специализации пользователя"""
        try:
            if not user.specialization:
                return ""
            
            # Проверяем, есть ли роль executor
            if user.roles:
                roles = json.loads(user.roles)
                if 'executor' not in roles:
                    return ""
            
            specializations = [s.strip() for s in user.specialization.split(',') if s.strip()]
            if not specializations:
                return ""
            
            spec_names = []
            for spec in specializations:
                spec_text = get_text(f"specializations.{spec}", language=language)
                spec_names.append(spec_text)
            
            return ", ".join(spec_names)
            
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Ошибка парсинга специализаций пользователя {user.id}: {e}")
            return ""
    
    def format_stats_message(self, stats: Dict[str, int], language: str = 'ru') -> str:
        """
        Форматировать сообщение со статистикой пользователей
        
        Args:
            stats: Статистика пользователей
            language: Язык интерфейса
            
        Returns:
            Отформатированное сообщение
        """
        try:
            return get_text("user_management.stats_text", language=language).format(**stats)
        except Exception as e:
            logger.error(f"Ошибка форматирования статистики: {e}")
            return f"Статистика пользователей:\nВсего: {stats.get('total', 0)}"
    
    # ═══ УТИЛИТАРНЫЕ МЕТОДЫ ═══
    
    def is_user_staff(self, user: User) -> bool:
        """Проверить, является ли пользователь сотрудником"""
        try:
            if not user.roles:
                return False
            
            roles = json.loads(user.roles)
            return 'executor' in roles or 'manager' in roles
            
        except (json.JSONDecodeError, Exception):
            return False
    
    def get_user_role_list(self, user: User) -> List[str]:
        """Получить список ролей пользователя"""
        try:
            if not user.roles:
                return []
            
            roles = json.loads(user.roles)
            return roles if isinstance(roles, list) else []
            
        except (json.JSONDecodeError, Exception):
            return []
