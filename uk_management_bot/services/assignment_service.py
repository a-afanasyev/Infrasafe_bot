"""
Сервис для управления назначениями заявок
Обеспечивает функциональность назначения заявок группам и конкретным исполнителям
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.utils.constants import (
    ASSIGNMENT_TYPE_GROUP,
    ASSIGNMENT_TYPE_INDIVIDUAL,
    ASSIGNMENT_STATUS_ACTIVE,
    ASSIGNMENT_STATUS_CANCELLED,
    ASSIGNMENT_STATUS_COMPLETED,
    AUDIT_ACTION_REQUEST_ASSIGNED,
    REQUEST_STATUS_IN_PROGRESS
)
from uk_management_bot.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# Интеграция с новыми сервисами ЭТАПА 3
try:
    from uk_management_bot.services.smart_dispatcher import SmartDispatcher
    from uk_management_bot.services.assignment_optimizer import AssignmentOptimizer
    from uk_management_bot.services.geo_optimizer import GeoOptimizer
    ADVANCED_ASSIGNMENT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Расширенные сервисы назначения недоступны: {e}")
    ADVANCED_ASSIGNMENT_AVAILABLE = False

class AssignmentService:
    """Сервис для управления назначениями заявок"""
    
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)
    
    def assign_to_group(self, request_number: str, specialization: str, assigned_by: int) -> RequestAssignment:
        """
        Назначение заявки группе исполнителей по специализации
        
        Args:
            request_number: Номер заявки
            specialization: Специализация группы
            assigned_by: ID пользователя, который назначает
            
        Returns:
            RequestAssignment: Созданное назначение
            
        Raises:
            ValueError: При неверных данных
        """
        try:
            # Проверяем существование заявки
            request = self._get_request_by_number(request_number)
            if not request:
                raise ValueError(f"Заявка с номером {request_number} не найдена")
            
            # Отменяем предыдущие активные назначения
            self._cancel_active_assignments(request_number)
            
            # Создаем новое групповое назначение
            assignment = RequestAssignment(
                request_number=request_number,
                assignment_type=ASSIGNMENT_TYPE_GROUP,
                group_specialization=specialization,
                status=ASSIGNMENT_STATUS_ACTIVE,
                created_by=assigned_by
            )
            
            self.db.add(assignment)
            
            # Обновляем заявку
            request.assignment_type = ASSIGNMENT_TYPE_GROUP
            request.assigned_group = specialization
            request.assigned_at = datetime.now()
            request.assigned_by = assigned_by
            
            self.db.commit()
            self.db.refresh(assignment)
            
            # Создаем запись в аудите
            self._create_audit_log(request_number, assigned_by, f"Назначена группе: {specialization}")
            
            # Отправляем уведомления
            self._notify_group_assignment(request, assignment)
            
            logger.info(f"Заявка {request_number} назначена группе {specialization} пользователем {assigned_by}")
            return assignment
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка назначения заявки группе: {e}")
            raise
    
    def assign_to_executor(self, request_number: str, executor_id: int, assigned_by: int) -> RequestAssignment:
        """
        Назначение заявки конкретному исполнителю
        
        Args:
            request_number: Номер заявки
            executor_id: ID исполнителя
            assigned_by: ID пользователя, который назначает
            
        Returns:
            RequestAssignment: Созданное назначение
            
        Raises:
            ValueError: При неверных данных
        """
        try:
            # Проверяем существование заявки
            request = self._get_request_by_number(request_number)
            if not request:
                raise ValueError(f"Заявка с номером {request_number} не найдена")
            
            # Проверяем существование исполнителя
            executor = self.db.query(User).filter(User.id == executor_id).first()
            if not executor:
                raise ValueError(f"Исполнитель с ID {executor_id} не найден")
            
            # Отменяем предыдущие активные назначения
            self._cancel_active_assignments(request_number)
            
            # Создаем новое индивидуальное назначение
            assignment = RequestAssignment(
                request_number=request_number,
                assignment_type=ASSIGNMENT_TYPE_INDIVIDUAL,
                executor_id=executor_id,
                status=ASSIGNMENT_STATUS_ACTIVE,
                created_by=assigned_by
            )
            
            self.db.add(assignment)
            
            # Обновляем заявку
            request.assignment_type = ASSIGNMENT_TYPE_INDIVIDUAL
            request.executor_id = executor_id
            request.assigned_at = datetime.now()
            request.assigned_by = assigned_by
            
            self.db.commit()
            self.db.refresh(assignment)
            
            # Создаем запись в аудите
            executor_name = f"{executor.first_name or ''} {executor.last_name or ''}".strip()
            self._create_audit_log(request_number, assigned_by, f"Назначена исполнителю: {executor_name}")
            
            # Отправляем уведомления
            self._notify_executor_assignment(request, assignment)
            
            logger.info(f"Заявка {request_number} назначена исполнителю {executor_id} пользователем {assigned_by}")
            return assignment
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка назначения заявки исполнителю: {e}")
            raise
    
    def get_executor_assignments(self, executor_id: int, status: str = ASSIGNMENT_STATUS_ACTIVE) -> List[RequestAssignment]:
        """
        Получение назначений исполнителя
        
        Args:
            executor_id: ID исполнителя
            status: Статус назначений (по умолчанию активные)
            
        Returns:
            List[RequestAssignment]: Список назначений
        """
        query = self.db.query(RequestAssignment).filter(
            and_(
                RequestAssignment.executor_id == executor_id,
                RequestAssignment.status == status
            )
        ).order_by(desc(RequestAssignment.created_at))
        
        return query.all()
    
    def get_request_assignments(self, request_number: str) -> List[RequestAssignment]:
        """
        Получение всех назначений заявки
        
        Args:
            request_number: Номер заявки
            
        Returns:
            List[RequestAssignment]: Список назначений
        """
        return self.db.query(RequestAssignment).filter(
            RequestAssignment.request_number == request_number
        ).order_by(desc(RequestAssignment.created_at)).all()
    
    def cancel_assignment(self, assignment_id: int, cancelled_by: int) -> bool:
        """
        Отмена назначения
        
        Args:
            assignment_id: ID назначения
            cancelled_by: ID пользователя, который отменяет
            
        Returns:
            bool: True если отмена успешна
        """
        try:
            assignment = self.db.query(RequestAssignment).filter(
                RequestAssignment.id == assignment_id
            ).first()
            
            if not assignment:
                raise ValueError(f"Назначение с ID {assignment_id} не найдено")
            
            assignment.status = ASSIGNMENT_STATUS_CANCELLED
            
            # Обновляем заявку
            request = self._get_request_by_number(assignment.request_number)
            if request:
                request.assignment_type = None
                request.assigned_group = None
                request.executor_id = None
                request.assigned_at = None
                request.assigned_by = None
            
            self.db.commit()
            
            # Создаем запись в аудите
            self._create_audit_log(assignment.request_number, cancelled_by, "Назначение отменено")
            
            logger.info(f"Назначение {assignment_id} отменено пользователем {cancelled_by}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка отмены назначения: {e}")
            raise
    
    def get_available_executors(self, specialization: str) -> List[User]:
        """
        Получение доступных исполнителей по специализации
        
        Args:
            specialization: Специализация
            
        Returns:
            List[User]: Список доступных исполнителей
        """
        # Получаем пользователей с ролью исполнителя и нужной специализацией
        users = self.db.query(User).filter(
            and_(
                User.roles.contains('["executor"]'),  # JSON содержит роль executor
                User.specialization.contains(specialization),  # JSON содержит специализацию
                User.status == "approved"  # Пользователь одобрен
            )
        ).all()
        
        return users
    
    def get_active_assignment(self, request_number: str) -> Optional[RequestAssignment]:
        """
        Получение активного назначения заявки
        
        Args:
            request_number: Номер заявки
            
        Returns:
            Optional[RequestAssignment]: Активное назначение или None
        """
        return self.db.query(RequestAssignment).filter(
            and_(
                RequestAssignment.request_number == request_number,
                RequestAssignment.status == ASSIGNMENT_STATUS_ACTIVE
            )
        ).first()
    
    def _cancel_active_assignments(self, request_number: str):
        """Отмена всех активных назначений заявки"""
        active_assignments = self.db.query(RequestAssignment).filter(
            and_(
                RequestAssignment.request_number == request_number,
                RequestAssignment.status == ASSIGNMENT_STATUS_ACTIVE
            )
        ).all()
        
        for assignment in active_assignments:
            assignment.status = ASSIGNMENT_STATUS_CANCELLED
    
    def _create_audit_log(self, request_number: str, user_id: int, action_description: str):
        """Создание записи в аудите"""
        try:
            audit_log = AuditLog(
                user_id=user_id,
                action=AUDIT_ACTION_REQUEST_ASSIGNED,
                details=f"Заявка {request_number}: {action_description}",
                timestamp=datetime.now()
            )
            self.db.add(audit_log)
        except Exception as e:
            logger.warning(f"Не удалось создать запись в аудите: {e}")
    
    def _notify_group_assignment(self, request: Request, assignment: RequestAssignment):
        """Уведомление о назначении группе"""
        try:
            # Получаем всех исполнителей с нужной специализацией
            executors = self.get_available_executors(assignment.group_specialization)
            
            for executor in executors:
                self.notification_service.send_notification(
                    user_id=executor.id,
                    notification_type="request_assigned",
                    title="Новая заявка назначена группе",
                    message=f"Заявка #{request.request_number} назначена группе {assignment.group_specialization}",
                    data={"request_number": request.request_number, "assignment_id": assignment.id}
                )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомления о назначении группе: {e}")
    
    def _notify_executor_assignment(self, request: Request, assignment: RequestAssignment):
        """Уведомление о назначении исполнителю"""
        try:
            self.notification_service.send_notification(
                user_id=assignment.executor_id,
                notification_type="request_assigned",
                title="Заявка назначена вам",
                message=f"Заявка #{request.request_number} назначена вам для выполнения",
                data={"request_number": request.request_number, "assignment_id": assignment.id}
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление исполнителю: {e}")
    
    # Методы интеграции с ЭТАПОМ 3
    
    def smart_assign_request(self, request_number: str, assigned_by: int) -> Optional[RequestAssignment]:
        """
        Умное назначение заявки с использованием ИИ
        
        Args:
            request_number: Номер заявки
            assigned_by: ID пользователя, который назначает
            
        Returns:
            Optional[RequestAssignment]: Созданное назначение или None
        """
        if not ADVANCED_ASSIGNMENT_AVAILABLE:
            logger.warning("Умное назначение недоступно, используем базовый метод")
            return None
        
        try:
            request = self._get_request_by_number(request_number)
            if not request:
                raise ValueError(f"Заявка с номером {request_number} не найдена")
            
            # Используем SmartDispatcher для поиска лучшего исполнителя
            dispatcher = SmartDispatcher(self.db)
            assignment_result = dispatcher.auto_assign_request(request_number)
            
            if assignment_result and assignment_result.success:
                logger.info(f"Заявка {request_number} успешно назначена через SmartDispatcher")
                return self.get_active_assignment(request_number)
            else:
                logger.warning(f"SmartDispatcher не смог назначить заявку {request_number}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка умного назначения заявки {request_number}: {e}")
            return None
    
    def optimize_assignments(self, algorithm: str = "hybrid") -> Dict[str, Any]:
        """
        Оптимизация существующих назначений
        
        Args:
            algorithm: Алгоритм оптимизации (greedy, genetic, simulated_annealing, hybrid)
            
        Returns:
            Dict[str, Any]: Результат оптимизации
        """
        if not ADVANCED_ASSIGNMENT_AVAILABLE:
            logger.warning("Оптимизация назначений недоступна")
            return {"error": "Сервис оптимизации недоступен"}
        
        try:
            optimizer = AssignmentOptimizer(self.db)
            result = optimizer.optimize_assignments(algorithm)
            
            logger.info(f"Оптимизация назначений завершена: {result.improvement_score:.2f} улучшение")
            
            return {
                "success": True,
                "algorithm": result.algorithm_used,
                "initial_assignments": result.initial_assignments,
                "optimized_assignments": result.optimized_assignments,
                "improvement_score": result.improvement_score,
                "processing_time": result.processing_time,
                "changes_made": len(result.changes_made)
            }
            
        except Exception as e:
            logger.error(f"Ошибка оптимизации назначений: {e}")
            return {"error": str(e)}
    
    def optimize_routes_for_date(self, date: datetime, executor_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """
        Оптимизация маршрутов исполнителей на дату
        
        Args:
            date: Дата для оптимизации
            executor_ids: Список ID исполнителей (если None - все)
            
        Returns:
            List[Dict[str, Any]]: Результаты оптимизации маршрутов
        """
        if not ADVANCED_ASSIGNMENT_AVAILABLE:
            logger.warning("Геооптимизация недоступна")
            return []
        
        try:
            geo_optimizer = GeoOptimizer(self.db)
            results = geo_optimizer.optimize_daily_routes(date, executor_ids)
            
            route_summaries = []
            for result in results:
                route_summaries.append({
                    "executor_id": result.executor_id,
                    "total_distance_km": result.total_distance_km,
                    "estimated_travel_time": result.estimated_travel_time,
                    "fuel_savings_percent": result.fuel_savings_percent,
                    "time_savings_minutes": result.time_savings_minutes,
                    "route_efficiency_score": result.route_efficiency_score,
                    "number_of_points": len(result.optimized_points),
                    "improvements": result.improvements
                })
            
            logger.info(f"Оптимизировано {len(results)} маршрутов на {date.date()}")
            return route_summaries
            
        except Exception as e:
            logger.error(f"Ошибка оптимизации маршрутов: {e}")
            return []
    
    def auto_assign_urgent_requests(self) -> Dict[str, Any]:
        """
        Автоматическое назначение срочных заявок
        
        Returns:
            Dict[str, Any]: Результат обработки срочных заявок
        """
        if not ADVANCED_ASSIGNMENT_AVAILABLE:
            logger.warning("Автоназначение срочных заявок недоступно")
            return {"error": "Сервис автоназначения недоступен"}
        
        try:
            dispatcher = SmartDispatcher(self.db)
            result = dispatcher.handle_urgent_requests()
            
            return {
                "success": True,
                "processed_requests": result.get("processed_requests", 0),
                "assigned_requests": result.get("assigned_requests", 0),
                "failed_assignments": result.get("failed_assignments", 0),
                "processing_time": result.get("processing_time", 0),
                "details": result.get("details", [])
            }
            
        except Exception as e:
            logger.error(f"Ошибка автоназначения срочных заявок: {e}")
            return {"error": str(e)}
    
    def get_assignment_recommendations(self, request_number: str) -> List[Dict[str, Any]]:
        """
        Получение рекомендаций по назначению заявки
        
        Args:
            request_number: Номер заявки
            
        Returns:
            List[Dict[str, Any]]: Список рекомендаций
        """
        if not ADVANCED_ASSIGNMENT_AVAILABLE:
            logger.warning("Рекомендации по назначению недоступны")
            return []
        
        try:
            request = self._get_request_by_number(request_number)
            if not request:
                return []
            
            dispatcher = SmartDispatcher(self.db)
            
            # Получаем активные смены
            from uk_management_bot.database.models.shift import Shift
            shifts = self.db.query(Shift).filter(Shift.status.in_(['active', 'planned'])).all()
            
            recommendations = []
            for shift in shifts[:5]:  # Топ-5 рекомендаций
                score = dispatcher.calculate_assignment_score(request, shift)
                
                recommendations.append({
                    "shift_id": shift.id,
                    "executor_id": shift.user_id,
                    "executor_name": shift.user.full_name if shift.user else "Неизвестно",
                    "total_score": score.total_score,
                    "specialization_score": score.specialization_score,
                    "geography_score": score.geography_score,
                    "workload_score": score.workload_score,
                    "rating_score": score.rating_score,
                    "urgency_score": score.urgency_score,
                    "recommendation_reason": f"Общий балл: {score.total_score:.2f}"
                })
            
            # Сортируем по убыванию общего балла
            recommendations.sort(key=lambda x: x["total_score"], reverse=True)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Ошибка получения рекомендаций для заявки {request_number}: {e}")
            return []

    def _get_request_by_number(self, request_number: str) -> Optional[Request]:
        """Возвращает заявку по её номеру."""
        if not request_number:
            return None
        return self.db.query(Request).filter(Request.request_number == request_number).first()
