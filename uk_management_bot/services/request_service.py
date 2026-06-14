from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional, Dict, Any
import logging

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.validators import validate_description
from uk_management_bot.utils.constants import (
    REQUEST_URGENCIES,
    URGENCY_DEFAULT,
    normalize_urgency,
    REQUEST_STATUSES,
    ROLE_APPLICANT,
    ROLE_EXECUTOR,
    ROLE_MANAGER,
)
from uk_management_bot.services.notification_service import notify_status_changed
from uk_management_bot.services.webhook_payloads import (
    emit_request_created_sync,
)
# Google Sheets интеграция убрана из продукта

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
        urgency: str = URGENCY_DEFAULT,
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
            # TASK 17 Этап B: Валидация через внутренние ключи
            from uk_management_bot.keyboards.requests import (
                CATEGORY_INTERNAL_KEYS,
                resolve_category_key
            )
            category_key = resolve_category_key(category)
            if category_key not in CATEGORY_INTERNAL_KEYS:
                raise ValueError(f"Неверная категория: {category}")
            
            # Толерантно (Phase 1 rollout): ключ ИЛИ legacy-рус → ключ
            urgency = normalize_urgency(urgency)
            if urgency is None:
                raise ValueError("Неверная срочность")

            # Базовая валидация адреса (адреса теперь выбираются из справочника)
            if not address or len(address.strip()) < 5:
                raise ValueError("Адрес не может быть пустым")

            if not validate_description(description):
                raise ValueError("Описание слишком короткое или длинное")
            
            # Генерируем уникальный номер заявки
            request_number = Request.generate_request_number(self.db)
            
            # Создание заявки.
            # ВНИМАНИЕ (план «Обходчик»): этот sync-конструктор принимает сырой
            # текст address/apartment и НЕ вызывается ни одним прод-путём создания
            # заявки (проверено грепом 2026-06). Оставлен как legacy/system-helper;
            # пишет address_type='legacy' (структурные FK не заполняются). Новые
            # пути создания обязаны идти через resolve_request_address.
            request = Request(
                request_number=request_number,
                user_id=user_id,
                category=category,
                address=address,
                description=description,
                apartment=apartment,
                urgency=urgency,
                media_files=media_files or [],
                status="Новая",
                address_type="legacy",
            )
            
            self.db.add(request)

            # ARCH-113: emit + INSERT in one transaction — protects against orphan
            # requests (request row durable but outbox row missing on commit failure).
            # `created_at` is None pre-commit and serialises as "" via the builder fallback.
            emit_request_created_sync(self.db, request, source="bot")

            self.db.commit()
            self.db.refresh(request)

            logger.info(f"Создана заявка {request.request_number} пользователем {user_id}")
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

        ОПТИМИЗИРОВАНО (14.10.2025):
        - Eager loading для user, executor, apartment_obj (N+1 исправлен)
        - Пагинация 50 записей по умолчанию

        Args:
            user_id: ID пользователя
            status: Фильтр по статусу (опционально)
            limit: Лимит записей (по умолчанию 50)
            offset: Смещение для пагинации

        Returns:
            List[Request]: Список заявок
        """
        try:
            from sqlalchemy.orm import joinedload
            from uk_management_bot.database.models import Apartment, Building

            query = (
                self.db.query(Request)
                .options(
                    # Загружаем связанные объекты одним запросом (FIX N+1)
                    joinedload(Request.user),  # Создатель заявки
                    joinedload(Request.executor),  # Исполнитель
                    joinedload(Request.apartment_obj)
                    .joinedload(Apartment.building)
                    .joinedload(Building.yard)
                )
                .filter(Request.user_id == user_id)
            )

            if status:
                query = query.filter(Request.status == status)

            requests = query.order_by(desc(Request.created_at)).offset(offset).limit(limit).all()

            logger.info(f"Получено {len(requests)} заявок для пользователя {user_id} (limit={limit}, offset={offset})")
            return requests

        except Exception as e:
            logger.error(f"Ошибка получения заявок пользователя {user_id}: {e}")
            return []
    
    def get_request_by_number(self, request_number: str) -> Optional[Request]:
        """
        Получение заявки по номеру

        ОПТИМИЗИРОВАНО (14.10.2025):
        - Eager loading для user, executor, apartment_obj (N+1 исправлен)

        Args:
            request_number: Номер заявки в формате YYMMDD-NNN

        Returns:
            Optional[Request]: Заявка или None
        """
        try:
            from sqlalchemy.orm import joinedload
            from uk_management_bot.database.models import Apartment, Building

            request = (
                self.db.query(Request)
                .options(
                    # Загружаем связанные объекты одним запросом (FIX N+1)
                    joinedload(Request.user),
                    joinedload(Request.executor),
                    joinedload(Request.apartment_obj)
                    .joinedload(Apartment.building)
                    .joinedload(Building.yard)
                )
                .filter(Request.request_number == request_number)
                .first()
            )
            return request

        except Exception as e:
            logger.error(f"Ошибка получения заявки {request_number}: {e}")
            return None
    
    # Устаревший метод для совместимости - будет удален
    def get_request_by_id(self, request_id: int) -> Optional[Request]:
        """
        УСТАРЕВШИЙ МЕТОД - использовать get_request_by_number
        """
        logger.warning(f"Using deprecated get_request_by_id({request_id})")
        return None
    
    # SSOT-кластер #1, PR2d: update_request_status удалён. Это был actor-less
    # raw-writer статуса (status/executor_id/completed_at), которым пользовался
    # только legacy report-approval (request_reports). Тот переведён на канон
    # (APPLICANT_ACCEPT через rated-accept / APPLICANT_RETURN). Единый writer —
    # update_status_by_actor (шим над run_command, PR2c).

    # === Новая логика: обновление статуса с учетом ролей и допустимых переходов ===
    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        try:
            return self.db.query(User).filter(User.telegram_id == telegram_id).first()
        except Exception as e:
            logger.error(f"Ошибка поиска пользователя по telegram_id {telegram_id}: {e}")
            return None

    def is_transition_allowed(self, current_status: str, target_status: str) -> bool:
        """
        Матрица допустимых переходов статусов.

        Обновлено 08.03.2026:
        - Из "Выполнена" разрешён прямой переход в "Принято" (приёмка заявителем)
        - Из "Исполнено" разрешён переход обратно в "Выполнена" (re-confirm менеджером)

        Workflow:
        Новая -> В работе -> Выполнена -> Принято
                    ↓         ↓    ↑
               Уточнение ↔ Закуп  ↓ (re-confirm)
                              Исполнено (возврат заявителем)
        """
        allowed: Dict[str, List[str]] = {
            # Новая заявка: менеджер сразу переводит в работу или вспомогательные статусы
            "Новая": ["В работе", "Закуп", "Уточнение", "Отменена"],

            # В работе: исполнитель выполняет или запрашивает уточнение/закуп
            "В работе": ["Уточнение", "Закуп", "Выполнена", "Отменена"],

            # Уточнение: можно вернуть в работу или перейти к закупу
            "Уточнение": ["В работе", "Закуп", "Отменена"],

            # Закуп: после закупки возврат в работу или уточнение
            "Закуп": ["В работе", "Уточнение", "Отменена"],

            # Выполнена: исполнитель завершил, менеджер проверяет
            # +Принято (прямая приёмка), сохранить Исполнено (return-flow)
            "Выполнена": ["Принято", "Исполнено", "В работе", "Отменена"],

            # Исполнено: заявитель вернул, менеджер может re-confirm (Выполнена) или другие действия
            "Исполнено": ["Выполнена", "Принято", "В работе", "Отменена"],

            # Принято: финальный статус, заявитель принял работу
            "Принято": [],

            # Отменена: финальный статус
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
        except (ValueError, TypeError):
            # ARCH-04: битый JSON ролей — не глотать молча, видимый warning.
            logger.warning(f"is_role_allowed_for_transition: битый JSON в user.roles (user_id={actor.id}), fallback к user.role")
        
        # Fallback к старому полю role если новая система не настроена
        if not user_roles and actor.role:
            user_roles = [actor.role]
        
        # Заявитель: отмена своей "Новой", приёмка/возврат из "Выполнена" и legacy "Исполнено"
        if active_role == ROLE_APPLICANT:
            is_owner = request.user_id == actor.id
            if is_owner and request.status == "Новая" and target_status == "Отменена":
                return True
            # Приёмка из "Выполнена" (основной путь)
            if is_owner and request.status == "Выполнена" and target_status == "Принято":
                return True
            # Возврат из "Выполнена" в return-flow
            if is_owner and request.status == "Выполнена" and target_status == "Исполнено":
                return True
            # Legacy: приёмка и возврат из "Исполнено"
            if is_owner and request.status == "Исполнено" and target_status == "Принято":
                return True
            if is_owner and request.status == "Исполнено" and target_status == "В работе":
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
        request_number: str,
        new_status: str,
        actor_telegram_id: int,
        notes: Optional[str] = None,
        requested_materials: Optional[str] = None,
        completion_report: Optional[str] = None,
        completion_media: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Обновление статуса заявки актором (бот).

        SSOT-кластер #1, PR2c: тонкий адаптер над `run_command_sync` —
        единым каноническим writer'ом workflow-переходов. Прежняя матрица
        переходов (`is_transition_allowed`) и ролей (`is_role_allowed_for_
        transition`) больше НЕ используются здесь: авторизацию, допустимость
        перехода, смену и repeat-политику решает канон (utils/request_workflow)
        ПОД локом, внутри своей транзакции. Сигнатура и форма ответа
        ({success, message, request}) сохранены для совместимости вызывающих.

        Доп.поля (requested_materials/completion_report/completion_media)
        прокидываются исполнительскими хендлерами (PR2c-2) в payload команды
        вместо прямой записи в ORM.

        Returns dict with keys: success(bool), message(str), request(Optional[Request])
        """
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            LegacyStatusIntent, PrincipalRef,
            NotAuthorized, InvalidTransition, RepeatRejected, RepeatConflict,
            PayloadInvalid, WorkflowError)
        try:
            if new_status not in REQUEST_STATUSES:
                return {"success": False, "message": f"Неверный статус: {new_status}", "request": None}

            actor: Optional[User] = self.get_user_by_telegram_id(actor_telegram_id)
            if not actor:
                return {"success": False, "message": "Пользователь не найден", "request": None}

            # Same-status notes-append: канон не моделирует «дописать примечание
            # без перехода». Сохраняем прежнее поведение прямой записью в notes
            # (notes — не workflow-поле, вне SSOT-владения).
            current = self.get_request_by_number(request_number)
            if current is None:
                return {"success": False, "message": "Заявка не найдена", "request": None}
            if new_status == current.status:
                if notes:
                    existing = (current.notes or "").strip()
                    current.notes = (existing + "\n" if existing else "") + notes
                    self.db.commit()
                    self.db.refresh(current)
                    return {"success": True, "message": "Примечание добавлено", "request": current}
                return {"success": True, "message": "Статус не изменён", "request": current}

            payload = self._build_status_payload(
                new_status, notes=notes, requested_materials=requested_materials,
                completion_report=completion_report, completion_media=completion_media)

            try:
                outcome = run_command_sync(
                    SessionLocal, request_number,
                    PrincipalRef(kind="user", user_id=actor.id, source="telegram"),
                    LegacyStatusIntent(
                        command_id=f"svc:{actor.id}:{request_number}",
                        target_status=new_status, payload=payload),
                )
            except RequestNotFound:
                return {"success": False, "message": "Заявка не найдена", "request": None}
            except NotAuthorized:
                return {"success": False, "message": "Недостаточно прав для изменения статуса", "request": None}
            except (InvalidTransition, RepeatRejected, RepeatConflict):
                return {"success": False, "message": "Недопустимый переход статуса", "request": None}
            except PayloadInvalid as e:
                logger.info(f"PayloadInvalid update_status_by_actor {request_number}: {e}")
                return {"success": False, "message": "Ошибка при обновлении статуса", "request": None}
            except WorkflowError as e:
                logger.info(f"WorkflowError update_status_by_actor {request_number}: {e}")
                return {"success": False, "message": "Ошибка при обновлении статуса", "request": None}

            # run_command работал в своей сессии → перечитываем заявку свежей
            # (identity-map вызывающей сессии устарел).
            self.db.expire_all()
            request = self.get_request_by_number(request_number)

            # Уведомления (best-effort, post-commit; durable audit/outbox уже в tx)
            try:
                notify_status_changed(self.db, request, outcome.old_status, outcome.new_status)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о смене статуса для заявки {request_number}: {e}")
            logger.info(
                f"Пользователь {actor.id} изменил статус заявки {request_number} "
                f"с '{outcome.old_status}' на '{outcome.new_status}' (canon)")
            if outcome.no_op:
                return {"success": True, "message": "Статус не изменён", "request": request}
            return {"success": True, "message": "Статус обновлен", "request": request}
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка update_status_by_actor для заявки {request_number}: {e}")
            return {"success": False, "message": "Ошибка при обновлении статуса", "request": None}

    @staticmethod
    def _build_status_payload(
        new_status: str, *, notes: Optional[str] = None,
        requested_materials: Optional[str] = None,
        completion_report: Optional[str] = None,
        completion_media: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Транспортный маппер: status-вход бота → payload канон-команды.

        Ключ — целевой статус (как в API _build_workflow_payload, PR2b).
        Кладёт только те ключи, которые принимает действие, разрешающее
        переход в этот статус (см. PAYLOAD_SCHEMAS). Для статусов без доп.
        данных (В работе/Новая/Принято) — пустой payload (канон решит сам).
        """
        from uk_management_bot.utils.constants import (
            REQUEST_STATUS_PURCHASE, REQUEST_STATUS_EXECUTED,
            REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_CANCELLED)
        payload: Dict[str, Any] = {}
        if new_status == REQUEST_STATUS_PURCHASE:
            if requested_materials is not None:
                payload["requested_materials"] = requested_materials
        elif new_status == REQUEST_STATUS_EXECUTED:
            if completion_report is not None:
                payload["completion_report"] = completion_report
            if completion_media is not None:
                payload["completion_media"] = completion_media
        elif new_status == REQUEST_STATUS_CLARIFICATION:
            if notes:
                payload["question"] = notes
        elif new_status == REQUEST_STATUS_CANCELLED:
            if notes:
                payload["reason"] = notes
        return payload
    
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

        ОПТИМИЗИРОВАНО (14.10.2025):
        - Eager loading для user, executor, apartment_obj (N+1 исправлен)
        - Пагинация 50 записей по умолчанию

        Args:
            user_id: ID пользователя (опционально)
            category: Категория (опционально)
            status: Статус (опционально)
            address_search: Поиск по адресу (опционально)
            limit: Лимит записей (по умолчанию 50)
            offset: Смещение для пагинации

        Returns:
            List[Request]: Список найденных заявок
        """
        try:
            from sqlalchemy.orm import joinedload
            from uk_management_bot.database.models import Apartment, Building

            query = (
                self.db.query(Request)
                .options(
                    # Загружаем связанные объекты одним запросом (FIX N+1)
                    joinedload(Request.user),
                    joinedload(Request.executor),
                    joinedload(Request.apartment_obj)
                    .joinedload(Apartment.building)
                    .joinedload(Building.yard)
                )
            )

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

            logger.info(f"Найдено {len(requests)} заявок (limit={limit}, offset={offset})")
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
            # TASK 17 Этап B: Используем внутренние ключи и учитываем legacy тексты
            from uk_management_bot.keyboards.requests import (
                CATEGORY_INTERNAL_KEYS,
                CATEGORY_DEFINITIONS
            )
            from sqlalchemy import or_
            
            category_stats = {}
            for internal_key in CATEGORY_INTERNAL_KEYS:
                # Создаём условие для поиска: внутренний ключ ИЛИ legacy тексты
                legacy_texts = CATEGORY_DEFINITIONS[internal_key].get("legacy_texts", [])
                conditions = [Request.category == internal_key]
                for legacy_text in legacy_texts:
                    conditions.append(Request.category == legacy_text)
                
                # Используем OR для поиска по внутреннему ключу или legacy текстам
                count = query.filter(or_(*conditions)).count()
                # Сохраняем статистику под внутренним ключом
                category_stats[internal_key] = count
            
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
    
    def delete_request(self, request_number: str, user_id: int) -> bool:
        """
        Удаление заявки (только создателем или администратором)
        
        Args:
            request_number: Номер заявки
            user_id: ID пользователя, выполняющего удаление
            
        Returns:
            bool: True если удаление успешно
        """
        try:
            request = self.get_request_by_number(request_number)
            if not request:
                return False
            
            # Проверяем права на удаление
            if request.user_id != user_id:
                # Проверяем, является ли пользователь администратором
                user = self.db.query(User).filter(User.id == user_id).first()
                if not user or user.role != "admin":
                    logger.warning(f"Попытка удаления заявки {request_number} без прав пользователем {user_id}")
                    return False
            
            self.db.delete(request)
            self.db.commit()
            
            logger.info(f"Заявка {request_number} удалена пользователем {user_id}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка удаления заявки {request_number}: {e}")
            return False
    
    def add_media_to_request(self, request_number: str, file_ids: List[str]) -> Optional[Request]:
        """
        Добавление медиафайлов к заявке
        
        Args:
            request_number: Номер заявки
            file_ids: Список file_ids медиафайлов
            
        Returns:
            Optional[Request]: Обновленная заявка или None
        """
        try:
            request = self.get_request_by_number(request_number)
            if not request:
                return None
            
            # Добавляем новые файлы к существующим
            current_files = request.media_files or []
            updated_files = current_files + file_ids
            
            request.media_files = updated_files
            self.db.commit()
            self.db.refresh(request)
            
            logger.info(f"Добавлено {len(file_ids)} медиафайлов к заявке {request_number}")
            return request
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка добавления медиафайлов к заявке {request_number}: {e}")
            return None
    
    def _get_user_name(self, user_id: int) -> str:
        """Получение имени пользователя по ID"""
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            return user.name if user else f"User_{user_id}"
        except Exception:
            return f"User_{user_id}"
