"""
SmartDispatcher - Интеллектуальная система автоматического назначения заявок на смены
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session
import statistics
import json

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_assignment import ShiftAssignment
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.constants import REQUEST_STATUSES, SHIFT_STATUSES, SPECIALIZATIONS
import logging

logger = logging.getLogger(__name__)


@dataclass
class AssignmentScore:
    """Структура для оценки качества назначения"""
    shift_id: int
    request_id: int
    total_score: float
    specialization_match: float
    workload_balance: float
    geographic_proximity: float
    executor_rating: float
    urgency_priority: float
    factors: Dict[str, Any]
    recommended: bool


@dataclass
class DispatchResult:
    """Результат работы диспетчера"""
    assigned_count: int
    failed_count: int
    assignments: List[AssignmentScore]
    errors: List[str]
    processing_time: float
    optimization_summary: Dict[str, Any]


class SmartDispatcher:
    """Умный диспетчер для автоматического назначения заявок"""
    
    def __init__(self, db: Session):
        self.db = db
        
        # Веса критериев назначения (должны в сумме давать 1.0)
        self.weights = {
            'specialization_match': 0.35,    # Соответствие специализации
            'geographic_proximity': 0.25,    # Географическая близость
            'workload_balance': 0.20,        # Балансировка нагрузки
            'executor_rating': 0.15,         # Рейтинг исполнителя
            'urgency_priority': 0.05         # Срочность заявки
        }
        
        # Пороговые значения
        self.min_assignment_score = 0.6     # Минимальная оценка для назначения
        self.max_requests_per_executor = 8  # Максимум заявок на исполнителя
        self.urgent_priority_boost = 0.2    # Бонус за срочные заявки
    
    # ========== ОСНОВНЫЕ МЕТОДЫ НАЗНАЧЕНИЯ ==========
    
    def auto_assign_requests(
        self, 
        request_ids: Optional[List[int]] = None,
        max_assignments: Optional[int] = None
    ) -> DispatchResult:
        """
        Автоматически назначает заявки на оптимальные смены
        
        Args:
            request_ids: Список ID заявок (если None, берутся все неназначенные)
            max_assignments: Максимальное количество назначений за один раз
        
        Returns:
            Результат назначения
        """
        start_time = datetime.now()
        
        try:
            # Получаем заявки для назначения
            requests = self._get_requests_for_assignment(request_ids)
            if not requests:
                return DispatchResult(0, 0, [], ["Нет заявок для назначения"], 0.0, {})
            
            if max_assignments:
                requests = requests[:max_assignments]
            
            # Получаем активные смены
            active_shifts = self._get_active_shifts()
            if not active_shifts:
                return DispatchResult(0, len(requests), [], ["Нет активных смен"], 0.0, {})
            
            # Выполняем назначения
            results = []
            assigned_count = 0
            failed_count = 0
            errors = []
            
            # Сортируем заявки по приоритету (срочные сначала)
            sorted_requests = self._prioritize_requests(requests)
            
            for request in sorted_requests:
                try:
                    assignment_score = self._find_best_assignment(request, active_shifts)
                    
                    if assignment_score and assignment_score.recommended:
                        success = self._execute_assignment(assignment_score)
                        if success:
                            results.append(assignment_score)
                            assigned_count += 1
                            
                            # Обновляем информацию о смене
                            self._update_shift_workload(assignment_score.shift_id, 1)
                        else:
                            failed_count += 1
                            errors.append(f"Ошибка назначения заявки {request.request_number}")
                    else:
                        failed_count += 1
                        errors.append(f"Не найдена подходящая смена для заявки {request.request_number}")
                        
                except Exception as e:
                    failed_count += 1
                    error_msg = f"Ошибка обработки заявки {request.request_number}: {e}"
                    errors.append(error_msg)
                    logger.error(error_msg)
            
            # Вычисляем время обработки
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Создаем сводку оптимизации
            optimization_summary = self._create_optimization_summary(results, active_shifts)
            
            logger.info(f"Диспетчер завершил работу: {assigned_count} назначений, "
                       f"{failed_count} ошибок за {processing_time:.2f}с")
            
            return DispatchResult(
                assigned_count=assigned_count,
                failed_count=failed_count,
                assignments=results,
                errors=errors,
                processing_time=processing_time,
                optimization_summary=optimization_summary
            )
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Критическая ошибка в диспетчере: {e}")
            return DispatchResult(0, 0, [], [str(e)], processing_time, {})
    
    def handle_urgent_requests(self) -> DispatchResult:
        """
        Обрабатывает срочные заявки с высоким приоритетом
        
        Returns:
            Результат обработки срочных заявок
        """
        try:
            urgent_requests = self.db.query(Request).filter(
                and_(
                    Request.status.in_(['Новая', 'Принята']),
                    Request.urgency.in_(['Срочная', 'Критическая']),
                    Request.executor_id.is_(None)  # Не назначена
                )
            ).order_by(Request.created_at.asc()).all()
            
            if not urgent_requests:
                return DispatchResult(0, 0, [], [], 0.0, {"urgent_mode": True})
            
            # Временно увеличиваем вес срочности
            original_urgency_weight = self.weights['urgency_priority']
            self.weights['urgency_priority'] = 0.3
            
            try:
                result = self.auto_assign_requests([req.id for req in urgent_requests])
                result.optimization_summary['urgent_mode'] = True
                return result
            finally:
                # Восстанавливаем исходный вес
                self.weights['urgency_priority'] = original_urgency_weight
                
        except Exception as e:
            logger.error(f"Ошибка обработки срочных заявок: {e}")
            return DispatchResult(0, 0, [], [str(e)], 0.0, {"urgent_mode": True})
    
    def balance_workload(self) -> Dict[str, Any]:
        """
        Балансирует нагрузку между активными сменами
        
        Returns:
            Результаты балансировки
        """
        try:
            # Получаем активные смены с их нагрузкой
            active_shifts = self._get_active_shifts()
            if len(active_shifts) < 2:
                return {"message": "Недостаточно смен для балансировки", "changes": 0}
            
            # Анализируем дисбаланс нагрузки
            workloads = {shift.id: shift.current_request_count for shift in active_shifts}
            avg_workload = statistics.mean(workloads.values())
            
            overloaded_shifts = [
                shift_id for shift_id, workload in workloads.items() 
                if workload > avg_workload * 1.3
            ]
            
            underloaded_shifts = [
                shift_id for shift_id, workload in workloads.items()
                if workload < avg_workload * 0.7
            ]
            
            if not (overloaded_shifts and underloaded_shifts):
                return {"message": "Нагрузка сбалансирована", "changes": 0}
            
            # Выполняем перераспределение
            changes_made = 0
            
            for overloaded_id in overloaded_shifts:
                excess_requests = self._get_redistributable_requests(overloaded_id)
                
                for request_assignment in excess_requests[:2]:  # Перераспределяем не более 2 за раз
                    best_shift = self._find_best_shift_for_redistribution(
                        request_assignment, underloaded_shifts
                    )
                    
                    if best_shift:
                        success = self._redistribute_assignment(request_assignment, best_shift)
                        if success:
                            changes_made += 1
                            workloads[overloaded_id] -= 1
                            workloads[best_shift] += 1
            
            return {
                "message": f"Балансировка завершена",
                "changes": changes_made,
                "workload_distribution": workloads
            }
            
        except Exception as e:
            logger.error(f"Ошибка балансировки нагрузки: {e}")
            return {"error": str(e), "changes": 0}
    
    def calculate_assignment_score(
        self, 
        request: Request, 
        shift: Shift
    ) -> AssignmentScore:
        """
        Вычисляет оценку качества назначения заявки на смену
        
        Args:
            request: Заявка
            shift: Смена
        
        Returns:
            Оценка назначения
        """
        try:
            factors = {}
            
            # 1. Соответствие специализации (35%)
            spec_score = self._calculate_specialization_match(request, shift)
            factors['specialization'] = spec_score
            
            # 2. Географическая близость (25%)
            geo_score = self._calculate_geographic_proximity(request, shift)
            factors['geography'] = geo_score
            
            # 3. Балансировка нагрузки (20%)
            workload_score = self._calculate_workload_balance_score(shift)
            factors['workload'] = workload_score
            
            # 4. Рейтинг исполнителя (15%)
            executor_score = self._calculate_executor_rating_score(shift)
            factors['executor'] = executor_score
            
            # 5. Приоритет срочности (5%)
            urgency_score = self._calculate_urgency_priority_score(request)
            factors['urgency'] = urgency_score
            
            # Вычисляем итоговую оценку
            total_score = (
                spec_score * self.weights['specialization_match'] +
                geo_score * self.weights['geographic_proximity'] +
                workload_score * self.weights['workload_balance'] +
                executor_score * self.weights['executor_rating'] +
                urgency_score * self.weights['urgency_priority']
            )
            
            # Проверяем, рекомендуется ли назначение
            recommended = (
                total_score >= self.min_assignment_score and
                shift.current_request_count < self.max_requests_per_executor and
                not shift.is_full
            )
            
            return AssignmentScore(
                shift_id=shift.id,
                request_id=request.request_number,
                total_score=total_score,
                specialization_match=spec_score,
                workload_balance=workload_score,
                geographic_proximity=geo_score,
                executor_rating=executor_score,
                urgency_priority=urgency_score,
                factors=factors,
                recommended=recommended
            )
            
        except Exception as e:
            logger.error(f"Ошибка вычисления оценки назначения: {e}")
            return AssignmentScore(
                shift_id=shift.id,
                request_id=request.request_number,
                total_score=0.0,
                specialization_match=0.0,
                workload_balance=0.0,
                geographic_proximity=0.0,
                executor_rating=0.0,
                urgency_priority=0.0,
                factors={},
                recommended=False
            )
    
    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========
    
    def _get_requests_for_assignment(self, request_ids: Optional[List[int]] = None) -> List[Request]:
        """Получает заявки для назначения"""
        try:
            query = self.db.query(Request).filter(
                and_(
                    Request.status.in_(['Новая', 'Принята']),
                    Request.executor_id.is_(None)  # Не назначена исполнителю
                )
            )
            
            if request_ids:
                query = query.filter(Request.id.in_(request_ids))
            
            return query.order_by(Request.created_at.asc()).all()
            
        except Exception as e:
            logger.error(f"Ошибка получения заявок: {e}")
            return []
    
    def _get_active_shifts(self) -> List[Shift]:
        """Получает активные смены для назначения"""
        try:
            now = datetime.now()
            
            return self.db.query(Shift).filter(
                and_(
                    Shift.status.in_(['active', 'planned']),
                    Shift.user_id.isnot(None),  # Есть назначенный исполнитель
                    or_(
                        Shift.end_time.is_(None),  # Смена не завершена
                        Shift.end_time > now       # Или завершается в будущем
                    )
                )
            ).order_by(Shift.current_request_count.asc()).all()
            
        except Exception as e:
            logger.error(f"Ошибка получения активных смен: {e}")
            return []
    
    def _prioritize_requests(self, requests: List[Request]) -> List[Request]:
        """Приоритизирует заявки для обработки"""
        urgency_priority = {
            'Критическая': 4,
            'Срочная': 3,
            'Средняя': 2,
            'Обычная': 1
        }
        
        return sorted(requests, key=lambda r: (
            -urgency_priority.get(r.urgency, 1),  # Срочность (убывание)
            r.created_at                          # Время создания (возрастание)
        ))
    
    def _find_best_assignment(
        self, 
        request: Request, 
        shifts: List[Shift]
    ) -> Optional[AssignmentScore]:
        """Находит лучшее назначение для заявки"""
        try:
            best_score = None
            best_assignment = None
            
            for shift in shifts:
                # Пропускаем переполненные смены
                if shift.is_full or shift.current_request_count >= self.max_requests_per_executor:
                    continue
                
                score = self.calculate_assignment_score(request, shift)
                
                if score.recommended and (not best_score or score.total_score > best_score):
                    best_score = score.total_score
                    best_assignment = score
            
            return best_assignment
            
        except Exception as e:
            logger.error(f"Ошибка поиска лучшего назначения: {e}")
            return None
    
    def _execute_assignment(self, assignment: AssignmentScore) -> bool:
        """Выполняет назначение заявки на смену"""
        try:
            # Создаем запись назначения
            shift_assignment = ShiftAssignment(
                shift_id=assignment.shift_id,
                request_id=assignment.request_id,
                assignment_priority=1,
                estimated_duration=60,  # По умолчанию 60 минут
                ai_score=assignment.total_score,
                assignment_reason=f"Автоназначение (оценка: {assignment.total_score:.2f})",
                factors_json=json.dumps(assignment.factors)
            )
            
            self.db.add(shift_assignment)
            
            # Обновляем заявку
            request = self.db.query(Request).filter(Request.id == assignment.request_id).first()
            if request:
                shift = self.db.query(Shift).filter(Shift.id == assignment.shift_id).first()
                if shift:
                    request.executor_id = shift.user_id
                    request.assigned_at = datetime.now()
                    request.assignment_type = 'individual'
            
            self.db.commit()
            
            logger.info(f"Назначена заявка {assignment.request_id} на смену {assignment.shift_id} "
                       f"с оценкой {assignment.total_score:.2f}")
            
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка выполнения назначения: {e}")
            return False
    
    def _update_shift_workload(self, shift_id: int, delta: int) -> None:
        """Обновляет нагрузку смены"""
        try:
            shift = self.db.query(Shift).filter(Shift.id == shift_id).first()
            if shift:
                shift.current_request_count = max(0, shift.current_request_count + delta)
                self.db.commit()
        except Exception as e:
            logger.error(f"Ошибка обновления нагрузки смены {shift_id}: {e}")
    
    def _calculate_specialization_match(self, request: Request, shift: Shift) -> float:
        """Вычисляет соответствие специализации"""
        try:
            if not shift.specialization_focus:
                return 0.7  # Универсальная смена
            
            # Определяем специализацию заявки по категории
            request_spec = self._extract_specialization_from_request(request)
            if not request_spec:
                return 0.5
            
            # Проверяем точное совпадение
            if request_spec in shift.specialization_focus:
                return 1.0
            
            # Проверяем универсальную специализацию
            if 'universal' in shift.specialization_focus:
                return 0.8
            
            # Частичное совпадение (смежные специализации)
            related_scores = {
                'electric': {'maintenance': 0.6},
                'plumbing': {'maintenance': 0.6},
                'hvac': {'maintenance': 0.7},
                'maintenance': {'electric': 0.5, 'plumbing': 0.5, 'hvac': 0.6}
            }
            
            if request_spec in related_scores:
                for spec in shift.specialization_focus:
                    if spec in related_scores[request_spec]:
                        return related_scores[request_spec][spec]
            
            return 0.2  # Минимальное совпадение
            
        except Exception as e:
            logger.error(f"Ошибка вычисления соответствия специализации: {e}")
            return 0.5
    
    def _calculate_geographic_proximity(self, request: Request, shift: Shift) -> float:
        """Вычисляет географическую близость (упрощенная версия)"""
        try:
            if not shift.coverage_areas:
                return 0.8  # Покрывает все зоны
            
            # Простая модель на основе адреса заявки
            request_address = (request.address or '').lower()
            
            # Проверяем прямые совпадения
            for area in shift.coverage_areas:
                if area.lower() in request_address or 'all' in shift.coverage_areas:
                    return 1.0
            
            # Проверяем частичные совпадения
            keywords_match = {
                'двор': ['yard', 'parking', 'outdoor'],
                'подъезд': ['building', 'entrance'],
                'квартира': ['apartment', 'residential'],
                'техническ': ['technical', 'utility']
            }
            
            for keyword, areas in keywords_match.items():
                if keyword in request_address:
                    for area in shift.coverage_areas:
                        if any(a in area.lower() for a in areas):
                            return 0.7
            
            return 0.3  # Низкая близость
            
        except Exception as e:
            logger.error(f"Ошибка вычисления географической близости: {e}")
            return 0.5
    
    def _calculate_workload_balance_score(self, shift: Shift) -> float:
        """Вычисляет оценку балансировки нагрузки"""
        try:
            if shift.max_requests <= 0:
                return 0.0
            
            load_percentage = shift.load_percentage
            
            # Оптимальная загруженность: 50-70%
            if 50 <= load_percentage <= 70:
                return 1.0
            elif 30 <= load_percentage < 50:
                return 0.8
            elif 70 < load_percentage <= 85:
                return 0.6
            elif load_percentage < 30:
                return 0.9  # Предпочитаем загрузить свободные смены
            else:
                return 0.2  # Перегруженная смена
                
        except Exception as e:
            logger.error(f"Ошибка вычисления балансировки нагрузки: {e}")
            return 0.5
    
    def _calculate_executor_rating_score(self, shift: Shift) -> float:
        """Вычисляет оценку рейтинга исполнителя"""
        try:
            if not shift.quality_rating:
                return 0.7  # Средняя оценка для новых исполнителей
            
            # Нормализуем рейтинг от 1-5 к 0-1
            normalized_rating = (shift.quality_rating - 1) / 4
            return max(0.0, min(1.0, normalized_rating))
            
        except Exception as e:
            logger.error(f"Ошибка вычисления рейтинга исполнителя: {e}")
            return 0.5
    
    def _calculate_urgency_priority_score(self, request: Request) -> float:
        """Вычисляет приоритет по срочности"""
        urgency_scores = {
            'Критическая': 1.0,
            'Срочная': 0.8,
            'Средняя': 0.5,
            'Обычная': 0.3
        }
        
        return urgency_scores.get(request.urgency, 0.3)
    
    def _extract_specialization_from_request(self, request: Request) -> Optional[str]:
        """Извлекает специализацию из заявки"""
        try:
            category = (request.category or '').lower()
            
            specialization_keywords = {
                'electric': ['электр', 'свет', 'розетк', 'провод', 'выключат', 'электричеств'],
                'plumbing': ['сантех', 'вода', 'труб', 'кран', 'унитаз', 'ванн', 'душ'],
                'hvac': ['отопл', 'кондиц', 'вент', 'батар', 'радиат', 'климат'],
                'security': ['охран', 'безопас', 'домофон', 'камер', 'сигнал'],
                'cleaning': ['убор', 'мусор', 'чист'],
                'maintenance': ['ремонт', 'обслуж', 'техническ', 'поломк']
            }
            
            for spec, keywords in specialization_keywords.items():
                if any(keyword in category for keyword in keywords):
                    return spec
            
            return 'maintenance'  # По умолчанию
            
        except Exception as e:
            logger.error(f"Ошибка извлечения специализации: {e}")
            return 'maintenance'
    
    def _create_optimization_summary(
        self, 
        assignments: List[AssignmentScore], 
        shifts: List[Shift]
    ) -> Dict[str, Any]:
        """Создает сводку оптимизации"""
        try:
            if not assignments:
                return {"message": "Нет назначений для анализа"}
            
            scores = [a.total_score for a in assignments]
            
            return {
                "total_assignments": len(assignments),
                "average_score": round(statistics.mean(scores), 3),
                "min_score": round(min(scores), 3),
                "max_score": round(max(scores), 3),
                "score_distribution": {
                    "excellent": len([s for s in scores if s >= 0.9]),
                    "good": len([s for s in scores if 0.7 <= s < 0.9]),
                    "acceptable": len([s for s in scores if 0.6 <= s < 0.7]),
                    "poor": len([s for s in scores if s < 0.6])
                },
                "shifts_utilized": len(set(a.shift_id for a in assignments)),
                "total_active_shifts": len(shifts)
            }
            
        except Exception as e:
            logger.error(f"Ошибка создания сводки оптимизации: {e}")
            return {"error": str(e)}
    
    def _get_redistributable_requests(self, shift_id: int) -> List[ShiftAssignment]:
        """Получает заявки, которые можно перераспределить"""
        try:
            return self.db.query(ShiftAssignment).filter(
                and_(
                    ShiftAssignment.shift_id == shift_id,
                    ShiftAssignment.status == 'active'
                )
            ).order_by(ShiftAssignment.ai_score.asc()).limit(3).all()
            
        except Exception as e:
            logger.error(f"Ошибка получения перераспределяемых заявок: {e}")
            return []
    
    def _find_best_shift_for_redistribution(
        self, 
        assignment: ShiftAssignment, 
        available_shifts: List[int]
    ) -> Optional[int]:
        """Находит лучшую смену для перераспределения"""
        try:
            shifts = self.db.query(Shift).filter(Shift.id.in_(available_shifts)).all()
            
            best_shift_id = None
            min_workload = float('inf')
            
            for shift in shifts:
                if shift.current_request_count < min_workload and not shift.is_full:
                    min_workload = shift.current_request_count
                    best_shift_id = shift.id
            
            return best_shift_id
            
        except Exception as e:
            logger.error(f"Ошибка поиска смены для перераспределения: {e}")
            return None
    
    def _redistribute_assignment(self, assignment: ShiftAssignment, new_shift_id: int) -> bool:
        """Перераспределяет назначение на другую смену"""
        try:
            old_shift_id = assignment.shift_id
            
            # Обновляем назначение
            assignment.shift_id = new_shift_id
            assignment.assignment_reason += f" (перераспределено с смены {old_shift_id})"
            
            # Обновляем заявку
            request = self.db.query(Request).filter(Request.id == assignment.request_id).first()
            if request:
                new_shift = self.db.query(Shift).filter(Shift.id == new_shift_id).first()
                if new_shift:
                    request.executor_id = new_shift.user_id
            
            # Обновляем счетчики нагрузки
            self._update_shift_workload(old_shift_id, -1)
            self._update_shift_workload(new_shift_id, 1)
            
            self.db.commit()
            
            logger.info(f"Перераспределена заявка {assignment.request_id} "
                       f"со смены {old_shift_id} на {new_shift_id}")
            
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка перераспределения: {e}")
            return False