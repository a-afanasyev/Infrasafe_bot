from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from database.models.request import Request
from database.models.user import User
from database.models.audit import AuditLog
from utils.validators import validate_address, validate_description
from utils.constants import (
    REQUEST_CATEGORIES,
    REQUEST_URGENCIES,
    REQUEST_STATUSES,
    ROLE_APPLICANT,
    ROLE_EXECUTOR,
    ROLE_MANAGER,
    AUDIT_ACTION_REQUEST_STATUS_CHANGED,
)
from services.shift_service import ShiftService
from services.notification_service import notify_status_changed, async_notify_request_status_changed

logger = logging.getLogger(__name__)

class RequestService:
    """Сервис для работы с заявками"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_request(
        self,
        user_id: int,
        category: str,
        address: str,
        description: str,
        apartment: Optional[str] = None,
        urgency: str = "Обычная",
        media_files: Optional[List[str]] = None
    ) -> Request:
        """
        Создание новой заявки
        
        Args:
            user_id: ID пользователя
            category: Категория заявки
            address: Адрес
            description: Описание проблемы
            apartment: Номер квартиры (опционально)
            urgency: Срочность
            media_files: Список file_ids медиафайлов
            
        Returns:
            Request: Созданная заявка
            
        Raises:
            ValueError: При неверных данных
        """
        try:
            # Валидация входных данных
            if category not in REQUEST_CATEGORIES:
                raise ValueError(f"Неверная категория: {category}")
            
            if urgency not in REQUEST_URGENCIES:
                raise ValueError(f"Неверная срочность: {urgency}")
            
            if not validate_address(address):
                raise ValueError("Неверный формат адреса")
            
            if not validate_description(description):
                raise ValueError("Описание слишком короткое или длинное")
            
            # Создание заявки
            request = Request(
                user_id=user_id,
                category=category,
                address=address,
                description=description,
                apartment=apartment,
                urgency=urgency,
                media_files=media_files or [],
                status="Новая"
            )
            
            self.db.add(request)
            self.db.commit()
            self.db.refresh(request)
            
            logger.info(f"Создана заявка ID {request.id} пользователем {user_id}")
            return request
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка создания заявки: {e}")
            raise
    
    def get_user_requests(
        self,
        user_id: int,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Request]:
        """
        Получение заявок пользователя с фильтрацией
        
        Args:
            user_id: ID пользователя
            status: Фильтр по статусу (опционально)
            limit: Лимит записей
            offset: Смещение
            
        Returns:
            List[Request]: Список заявок
        """
        try:
            query = self.db.query(Request).filter(Request.user_id == user_id)
            
            if status:
                query = query.filter(Request.status == status)
            
            requests = query.order_by(desc(Request.created_at)).offset(offset).limit(limit).all()
            
            logger.info(f"Получено {len(requests)} заявок для пользователя {user_id}")
            return requests
            
        except Exception as e:
            logger.error(f"Ошибка получения заявок пользователя {user_id}: {e}")
            return []
    
    def get_request_by_id(self, request_id: int) -> Optional[Request]:
        """
        Получение заявки по ID
        
        Args:
            request_id: ID заявки
            
        Returns:
            Optional[Request]: Заявка или None
        """
        try:
            request = self.db.query(Request).filter(Request.id == request_id).first()
            return request
            
        except Exception as e:
            logger.error(f"Ошибка получения заявки {request_id}: {e}")
            return None
    
    def update_request_status(
        self,
        request_id: int,
        new_status: str,
        executor_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Optional[Request]:
        """
        Обновление статуса заявки
        
        Args:
            request_id: ID заявки
            new_status: Новый статус
            executor_id: ID исполнителя (опционально)
            notes: Примечания (опционально)
            
        Returns:
            Optional[Request]: Обновленная заявка или None
        """
        try:
            if new_status not in REQUEST_STATUSES:
                raise ValueError(f"Неверный статус: {new_status}")
            
            request = self.get_request_by_id(request_id)
            if not request:
                return None
            
            old_status = request.status
            # Разрешаем no-op обновление (тот же статус) для добавления примечаний
            if new_status == old_status:
                if notes:
                    request.notes = (request.notes or "").strip()
                    request.notes = (request.notes + "\n" if request.notes else "") + notes
                self.db.commit()
                self.db.refresh(request)
                logger.info(f"Обновлены примечания заявки {request_id} при неизменном статусе '{old_status}'")
                return request
            request.status = new_status
            
            if executor_id:
                request.executor_id = executor_id
            
            if notes:
                existing_notes = (request.notes or "").strip()
                request.notes = (existing_notes + "\n" if existing_notes else "") + notes
            
            # Если заявка завершена, устанавливаем время завершения
            if new_status == "Завершена":
                request.completed_at = datetime.now()
            
            self.db.commit()
            self.db.refresh(request)
            
            logger.info(f"Статус заявки {request_id} изменен с '{old_status}' на '{new_status}'")
            return request
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка обновления статуса заявки {request_id}: {e}")
            return None

    # === Новая логика: обновление статуса с учетом ролей и допустимых переходов ===
    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        try:
            return self.db.query(User).filter(User.telegram_id == telegram_id).first()
        except Exception as e:
            logger.error(f"Ошибка поиска пользователя по telegram_id {telegram_id}: {e}")
            return None

    def is_transition_allowed(self, current_status: str, target_status: str) -> bool:
        """Матрица допустимых переходов статусов."""
        allowed: Dict[str, List[str]] = {
            # Менеджер может сразу перевести Новая -> В работе / Закуп / Уточнение
            "Новая": ["В работе", "Закуп", "Уточнение", "Принята", "Отменена"],
            "Принята": ["В работе", "Отменена"],
            "В работе": ["Уточнение", "Закуп", "Выполнена", "Отменена"],
            # Разрешаем взаимные переходы между рабочими подстатусами
            "Уточнение": ["В работе", "Закуп", "Отменена"],
            "Закуп": ["В работе", "Уточнение", "Отменена"],
            "Выполнена": ["Подтверждена"],
            "Подтверждена": [],
            "Отменена": [],
        }
        return target_status in allowed.get(current_status, [])

    def is_role_allowed_for_transition(
        self,
        actor: User,
        request: Request,
        target_status: str
    ) -> bool:
        # Определяем активную роль пользователя (новая система ролей)
        active_role = actor.active_role if actor.active_role else actor.role
        
        # Получаем список всех ролей пользователя
        user_roles = []
        try:
            if actor.roles:
                import json
                parsed_roles = json.loads(actor.roles)
                if isinstance(parsed_roles, list):
                    user_roles = parsed_roles
        except Exception:
            pass
        
        # Fallback к старому полю role если новая система не настроена
        if not user_roles and actor.role:
            user_roles = [actor.role]
        
        # Заявитель: только отмена своей "Новой" и подтверждение выполненной
        if active_role == ROLE_APPLICANT:
            is_owner = request.user_id == actor.id
            if is_owner and request.status == "Новая" and target_status == "Отменена":
                return True
            if is_owner and request.status == "Выполнена" and target_status == "Подтверждена":
                return True
            return False
        
        # Исполнитель: может брать в работу и менять рабочие статусы
        if active_role == ROLE_EXECUTOR:
            return target_status in ["В работе", "Уточнение", "Закуп", "Выполнена"]
        
        # Менеджер и Админ: широкие права
        if active_role in [ROLE_MANAGER, "admin"]:
            return True
            
        return False

    def update_status_by_actor(
        self,
        request_id: int,
        new_status: str,
        actor_telegram_id: int,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Безопасное обновление статуса с проверкой ролей и допустимых переходов.

        Returns dict with keys: success(bool), message(str), request(Optional[Request])
        """
        try:
            # Валидация статуса
            if new_status not in REQUEST_STATUSES:
                return {"success": False, "message": f"Неверный статус: {new_status}", "request": None}

            # Получаем заявку и актера
            request: Optional[Request] = self.db.query(Request).filter(Request.id == request_id).first()
            if not request:
                return {"success": False, "message": "Заявка не найдена", "request": None}

            actor: Optional[User] = self.get_user_by_telegram_id(actor_telegram_id)
            if not actor:
                return {"success": False, "message": "Пользователь не найден", "request": None}

            # Запрет для владельца брать свою заявку в работу и завершать
            if request.user_id == actor.id and new_status in ["В работе", "Выполнена", "Принята"]:
                return {"success": False, "message": "Нельзя управлять собственной заявкой", "request": None}

            # Если статус не меняется, но есть примечание — просто дополняем notes без проверки матрицы
            if new_status == request.status:
                if notes:
                    existing = (request.notes or "").strip()
                    request.notes = (existing + "\n" if existing else "") + notes
                    self.db.commit()
                    self.db.refresh(request)
                    return {"success": True, "message": "Примечание добавлено", "request": request}
                else:
                    return {"success": True, "message": "Статус не изменён", "request": request}

            # Проверяем допустимость перехода
            if not self.is_transition_allowed(request.status, new_status):
                return {"success": False, "message": "Недопустимый переход статуса", "request": None}

            # Проверяем права роли
            if not self.is_role_allowed_for_transition(actor, request, new_status):
                return {"success": False, "message": "Недостаточно прав для изменения статуса", "request": None}

            # Проверяем активную смену для исполнителя
            active_role = actor.active_role if actor.active_role else actor.role
            if active_role == ROLE_EXECUTOR:
                shift_service = ShiftService(self.db)
                if not shift_service.is_user_in_active_shift(actor.telegram_id):
                    return {"success": False, "message": "Вы не в смене. Смена необходима для выполнения этого действия", "request": None}

            old_status = request.status
            request.status = new_status

            # Назначаем исполнителя при переходе в работу, если еще не назначен
            if new_status == "В работе" and not request.executor_id:
                request.executor_id = actor.id

            if notes:
                request.notes = notes

            if new_status == "Выполнена":
                request.completed_at = datetime.now()

            self.db.commit()
            self.db.refresh(request)

            # Аудит
            try:
                audit = AuditLog(
                    user_id=actor.id,
                    action=AUDIT_ACTION_REQUEST_STATUS_CHANGED,
                    details={
                        "request_id": request.id,
                        "old_status": old_status,
                        "new_status": new_status,
                        "notes": notes,
                        "actor_role": actor.role,
                    },
                )
                self.db.add(audit)
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.error(f"Ошибка записи аудита смены статуса для заявки {request_id}: {e}")

            # Уведомления (best-effort)
            try:
                # sync лог
                notify_status_changed(self.db, request, old_status, new_status)
                # попытка async (если в контексте есть bot, вызывать из хэндлеров можно напрямую)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о смене статуса для заявки {request_id}: {e}")
            logger.info(
                f"Пользователь {actor.id} ({actor.role}) изменил статус заявки {request_id} "
                f"с '{old_status}' на '{new_status}'"
            )
            return {"success": True, "message": "Статус обновлен", "request": request}
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка update_status_by_actor для заявки {request_id}: {e}")
            return {"success": False, "message": "Ошибка при обновлении статуса", "request": None}
    
    def search_requests(
        self,
        user_id: Optional[int] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        address_search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Request]:
        """
        Поиск заявок по различным критериям
        
        Args:
            user_id: ID пользователя (опционально)
            category: Категория (опционально)
            status: Статус (опционально)
            address_search: Поиск по адресу (опционально)
            limit: Лимит записей
            offset: Смещение
            
        Returns:
            List[Request]: Список найденных заявок
        """
        try:
            query = self.db.query(Request)
            
            # Применяем фильтры
            if user_id:
                query = query.filter(Request.user_id == user_id)
            
            if category:
                query = query.filter(Request.category == category)
            
            if status:
                query = query.filter(Request.status == status)
            
            if address_search:
                query = query.filter(Request.address.ilike(f"%{address_search}%"))
            
            requests = query.order_by(desc(Request.created_at)).offset(offset).limit(limit).all()
            
            logger.info(f"Найдено {len(requests)} заявок по критериям поиска")
            return requests
            
        except Exception as e:
            logger.error(f"Ошибка поиска заявок: {e}")
            return []
    
    def get_request_statistics(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Получение статистики по заявкам
        
        Args:
            user_id: ID пользователя (опционально)
            
        Returns:
            Dict[str, Any]: Статистика
        """
        try:
            query = self.db.query(Request)
            
            if user_id:
                query = query.filter(Request.user_id == user_id)
            
            total_requests = query.count()
            
            # Статистика по статусам
            status_stats = {}
            for status in REQUEST_STATUSES:
                count = query.filter(Request.status == status).count()
                status_stats[status] = count
            
            # Статистика по категориям
            category_stats = {}
            for category in REQUEST_CATEGORIES:
                count = query.filter(Request.category == category).count()
                category_stats[category] = count
            
            # Статистика по срочности
            urgency_stats = {}
            for urgency in REQUEST_URGENCIES:
                count = query.filter(Request.urgency == urgency).count()
                urgency_stats[urgency] = count
            
            return {
                "total_requests": total_requests,
                "status_statistics": status_stats,
                "category_statistics": category_stats,
                "urgency_statistics": urgency_stats
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {
                "total_requests": 0,
                "status_statistics": {},
                "category_statistics": {},
                "urgency_statistics": {}
            }
    
    def delete_request(self, request_id: int, user_id: int) -> bool:
        """
        Удаление заявки (только создателем или администратором)
        
        Args:
            request_id: ID заявки
            user_id: ID пользователя, выполняющего удаление
            
        Returns:
            bool: True если удаление успешно
        """
        try:
            request = self.get_request_by_id(request_id)
            if not request:
                return False
            
            # Проверяем права на удаление
            if request.user_id != user_id:
                # Проверяем, является ли пользователь администратором
                user = self.db.query(User).filter(User.id == user_id).first()
                if not user or user.role != "admin":
                    logger.warning(f"Попытка удаления заявки {request_id} без прав пользователем {user_id}")
                    return False
            
            self.db.delete(request)
            self.db.commit()
            
            logger.info(f"Заявка {request_id} удалена пользователем {user_id}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка удаления заявки {request_id}: {e}")
            return False
    
    def add_media_to_request(self, request_id: int, file_ids: List[str]) -> Optional[Request]:
        """
        Добавление медиафайлов к заявке
        
        Args:
            request_id: ID заявки
            file_ids: Список file_ids медиафайлов
            
        Returns:
            Optional[Request]: Обновленная заявка или None
        """
        try:
            request = self.get_request_by_id(request_id)
            if not request:
                return None
            
            # Добавляем новые файлы к существующим
            current_files = request.media_files or []
            updated_files = current_files + file_ids
            
            request.media_files = updated_files
            self.db.commit()
            self.db.refresh(request)
            
            logger.info(f"Добавлено {len(file_ids)} медиафайлов к заявке {request_id}")
            return request
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка добавления медиафайлов к заявке {request_id}: {e}")
            return None
