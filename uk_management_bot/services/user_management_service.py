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

from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import get_text

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
            # Статистика жителей (заявителей) по статусам
            # Поддерживаем как новую систему ролей (JSON), так и старую (role поле)
            residents_pending = self.db.query(User).filter(
                and_(
                    User.status == 'pending',
                    or_(
                        User.roles.contains('applicant'),
                        User.roles.contains('resident'),
                        and_(
                            or_(User.roles.is_(None), User.roles == ''),
                            User.role == 'applicant'
                        )
                    )
                )
            ).count()
            
            residents_approved = self.db.query(User).filter(
                and_(
                    User.status == 'approved',
                    or_(
                        User.roles.contains('applicant'),
                        User.roles.contains('resident'),
                        and_(
                            or_(User.roles.is_(None), User.roles == ''),
                            User.role == 'applicant'
                        )
                    )
                )
            ).count()
            
            residents_blocked = self.db.query(User).filter(
                and_(
                    User.status == 'blocked',
                    or_(
                        User.roles.contains('applicant'),
                        User.roles.contains('resident'),
                        and_(
                            or_(User.roles.is_(None), User.roles == ''),
                            User.role == 'applicant'
                        )
                    )
                )
            ).count()
            
            # Подсчет сотрудников (executor или manager)
            staff_count = self.db.query(User).filter(
                or_(
                    User.roles.contains('executor'),
                    User.roles.contains('manager')
                )
            ).count()
            
            # Общее количество пользователей
            total_users = self.db.query(User).count()
            
            stats = {
                'pending': residents_pending,
                'approved': residents_approved,
                'blocked': residents_blocked,
                'staff': staff_count,
                'total': total_users
            }
            
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
    
    # ═══ СТАТИСТИКА СОТРУДНИКОВ ═══
    
    def get_employee_stats(self) -> Dict[str, int]:
        """
        Получить статистику сотрудников

        Returns:
            Dict с количествами сотрудников по категориям
        """
        try:
            # Сотрудники в ожидании (executor или manager со статусом pending)
            # Проверяем оба поля: role (старая система) и roles (новая система)
            pending_employees = self.db.query(User).filter(
                and_(
                    User.status == 'pending',
                    or_(
                        User.roles.like('%"executor"%'),
                        User.roles.like('%"manager"%'),
                        User.role == 'executor',
                        User.role == 'manager'
                    )
                )
            ).count()

            # Активные сотрудники (executor или manager со статусом approved)
            active_employees = self.db.query(User).filter(
                and_(
                    User.status == 'approved',
                    or_(
                        User.roles.like('%"executor"%'),
                        User.roles.like('%"manager"%'),
                        User.role == 'executor',
                        User.role == 'manager'
                    )
                )
            ).count()

            # Заблокированные сотрудники (executor или manager со статусом blocked)
            blocked_employees = self.db.query(User).filter(
                and_(
                    User.status == 'blocked',
                    or_(
                        User.roles.like('%"executor"%'),
                        User.roles.like('%"manager"%'),
                        User.role == 'executor',
                        User.role == 'manager'
                    )
                )
            ).count()

            # Исполнители (executor)
            executors = self.db.query(User).filter(
                or_(
                    User.roles.like('%"executor"%'),
                    User.role == 'executor'
                )
            ).count()

            # Менеджеры (manager)
            managers = self.db.query(User).filter(
                or_(
                    User.roles.like('%"manager"%'),
                    User.role == 'manager'
                )
            ).count()
            
            stats = {
                'pending': pending_employees,
                'active': active_employees,
                'blocked': blocked_employees,
                'executors': executors,
                'managers': managers
            }
            
            logger.info(f"Статистика сотрудников получена: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики сотрудников: {e}")
            return {
                'pending': 0,
                'active': 0,
                'blocked': 0,
                'executors': 0,
                'managers': 0
            }
    
    # ═══ СПИСКИ ПОЛЬЗОВАТЕЛЕЙ С ПАГИНАЦИЕЙ ═══
    
    def get_residents_by_status(self, status: str, page: int = 1, limit: int = 10) -> Dict:
        """
        Получить жителей (заявителей) по статусу с пагинацией
        
        Args:
            status: Статус пользователя (pending, approved, blocked)
            page: Номер страницы (начиная с 1)
            limit: Количество пользователей на странице
            
        Returns:
            Dict с жителями и информацией о пагинации
        """
        try:
            offset = (page - 1) * limit
            
            # Базовый запрос: только жители (applicant или resident)
            # Исключаем пользователей, которые являются только сотрудниками
            # Поддерживаем как новую систему ролей (JSON), так и старую (role поле)
            query = self.db.query(User).filter(
                and_(
                    User.status == status,
                    or_(
                        # Новая система ролей (JSON поле roles)
                        User.roles.contains('applicant'),
                        User.roles.contains('resident'),
                        # Старая система ролей (поле role) - для обратной совместимости
                        and_(
                            or_(User.roles.is_(None), User.roles == ''),
                            User.role == 'applicant'
                        )
                    )
                )
            )
            
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
            
            logger.info(f"Получены жители со статусом {status}: страница {page}, найдено {len(users)}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка получения жителей по статусу {status}: {e}")
            return {
                'users': [],
                'total': 0,
                'page': page,
                'total_pages': 1,
                'has_next': False,
                'has_prev': False,
                'status': status
            }
    
    def get_users_by_status(self, status: str, page: int = 1, limit: int = 10) -> Dict:
        """
        Получить пользователей по статусу с пагинацией (для обратной совместимости)
        
        Args:
            status: Статус пользователя (pending, approved, blocked)
            page: Номер страницы (начиная с 1)
            limit: Количество пользователей на странице
            
        Returns:
            Dict с пользователями и информацией о пагинации
        """
        # Используем новый метод для жителей
        return self.get_residents_by_status(status, page, limit)
    
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
            # Включаем всех сотрудников, независимо от других ролей
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

            # BUG-BOT-024: статус уже содержит emoji в локали (user_status.approved = "✅ Одобрен"),
            # отдельный emoji-префикс вызывает двойной значок (`✅ ✅ Одобрен`).
            # Для краткого формата используем только emoji-карту; для detailed — только локализованный текст.
            status_emoji = {
                "pending": "📝",
                "approved": "✅",
                "blocked": "🚫"
            }.get(user.status, "❓")

            status_text = get_text(f"user_status.{user.status}", language=language)

            # Роли
            roles_text = self._format_user_roles(user, language)

            if detailed:
                # BUG-BOT-024: для username показываем "Username не указан" вместо "@не указано"
                if user.username:
                    username_line = f"📱 @{user.username}"
                else:
                    username_line = (
                        f"📱 {get_text('user_mgmt.handlers.username_not_specified', language=language)}"
                    )
                # Подробная информация
                info_parts = [
                    f"👤 {name}",
                    username_line,
                    status_text,
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
    
    def is_user_employee(self, user: User) -> bool:
        """Проверить, является ли пользователь сотрудником (executor или manager)"""
        try:
            if not user.roles:
                return False
            
            # Проверяем через LIKE для JSON
            return (
                user.roles and (
                    '"executor"' in user.roles or 
                    '"manager"' in user.roles
                )
            )
            
        except Exception:
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
    
    # ═══ МЕТОДЫ ДЛЯ РАБОТЫ С СОТРУДНИКАМИ ═══
    
    def get_employees_list(self, list_type: str, page: int = 1, per_page: int = 20) -> Dict:
        """
        Получить список сотрудников с пагинацией

        ОПТИМИЗИРОВАНО (14.10.2025):
        - Увеличена пагинация с 5 до 20 записей по умолчанию

        Args:
            list_type: Тип списка (pending, active, blocked, executors, managers)
            page: Номер страницы
            per_page: Количество на странице (по умолчанию 20)

        Returns:
            Dict с данными сотрудников и пагинацией
        """
        try:
            # Базовый запрос для сотрудников (executor или manager)
            # Проверяем оба поля: role (старая система) и roles (новая система)
            base_query = self.db.query(User).filter(
                or_(
                    User.roles.like('%"executor"%'),
                    User.roles.like('%"manager"%'),
                    User.role == 'executor',
                    User.role == 'manager'
                )
            )

            # Применяем фильтры в зависимости от типа списка
            if list_type == 'pending':
                query = base_query.filter(User.status == 'pending')
            elif list_type == 'active':
                query = base_query.filter(User.status == 'approved')
            elif list_type == 'blocked':
                query = base_query.filter(User.status == 'blocked')
            elif list_type == 'executors':
                query = base_query.filter(
                    or_(
                        User.roles.like('%"executor"%'),
                        User.role == 'executor'
                    )
                )
            elif list_type == 'managers':
                query = base_query.filter(
                    or_(
                        User.roles.like('%"manager"%'),
                        User.role == 'manager'
                    )
                )
            else:
                query = base_query
            
            # Общее количество
            total_employees = query.count()
            
            # Вычисляем пагинацию
            total_pages = (total_employees + per_page - 1) // per_page
            offset = (page - 1) * per_page
            
            # Получаем сотрудников для текущей страницы
            employees = query.order_by(User.created_at.desc()).offset(offset).limit(per_page).all()
            
            result = {
                'employees': employees,
                'current_page': page,
                'total_pages': total_pages,
                'total_employees': total_employees
            }
            
            logger.info(f"Список сотрудников получен: {list_type}, страница {page}, всего {total_employees}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка получения списка сотрудников: {e}")
            return {
                'employees': [],
                'current_page': 1,
                'total_pages': 1,
                'total_employees': 0
            }
    
    def search_employees(self, query: str, page: int = 1, per_page: int = 5) -> Dict:
        """
        Поиск сотрудников

        Args:
            query: Поисковый запрос
            page: Номер страницы
            per_page: Количество на странице

        Returns:
            Dict с результатами поиска
        """
        try:
            # Базовый запрос для сотрудников
            # Проверяем оба поля: role (старая система) и roles (новая система)
            base_query = self.db.query(User).filter(
                or_(
                    User.roles.like('%"executor"%'),
                    User.roles.like('%"manager"%'),
                    User.role == 'executor',
                    User.role == 'manager'
                )
            )
            
            # Поиск по имени, фамилии, username или телефону
            search_query = base_query.filter(
                or_(
                    User.first_name.ilike(f'%{query}%'),
                    User.last_name.ilike(f'%{query}%'),
                    User.username.ilike(f'%{query}%'),
                    User.phone.ilike(f'%{query}%')
                )
            )
            
            # Общее количество
            total_employees = search_query.count()
            
            # Вычисляем пагинацию
            total_pages = (total_employees + per_page - 1) // per_page
            offset = (page - 1) * per_page
            
            # Получаем результаты для текущей страницы
            employees = search_query.order_by(User.created_at.desc()).offset(offset).limit(per_page).all()
            
            result = {
                'employees': employees,
                'current_page': page,
                'total_pages': total_pages,
                'total_employees': total_employees,
                'search_query': query
            }
            
            logger.info(f"Поиск сотрудников: '{query}', найдено {total_employees}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка поиска сотрудников: {e}")
            return {
                'employees': [],
                'current_page': 1,
                'total_pages': 1,
                'total_employees': 0,
                'search_query': query
            }
