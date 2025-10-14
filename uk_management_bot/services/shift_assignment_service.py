"""
Сервис автоматического назначения исполнителей на смены
Обеспечивает интеллектуальное распределение исполнителей с учетом специализаций, нагрузки и предпочтений
"""

from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import and_, or_, func, desc
from sqlalchemy.orm import Session
from dataclasses import dataclass
from enum import Enum

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.services.assignment_service import AssignmentService
from uk_management_bot.services.smart_dispatcher import SmartDispatcher
from uk_management_bot.services.notification_service import NotificationService
from uk_management_bot.utils.constants import ROLE_EXECUTOR
import logging

logger = logging.getLogger(__name__)


class AssignmentPriority(Enum):
    """Приоритеты назначения исполнителей"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ExecutorScore:
    """Оценка исполнителя для назначения на смену"""
    executor_id: int
    executor_name: str
    total_score: float
    specialization_match: float
    workload_score: float
    rating_score: float
    availability_score: float
    preference_score: float
    geographic_score: float
    conflict_penalties: float
    reasons: List[str]


@dataclass
class AssignmentConflict:
    """Конфликт назначения"""
    type: str
    executor_id: int
    shift_id: int
    description: str
    severity: str  # low, medium, high, critical
    can_resolve: bool
    resolution_suggestion: Optional[str] = None


class ShiftAssignmentService:
    """
    Сервис для автоматического назначения исполнителей на смены
    Использует ИИ-алгоритмы для оптимального распределения нагрузки
    """

    def __init__(self, db: Session):
        self.db = db
        self.assignment_service = AssignmentService(db)
        self.smart_dispatcher = SmartDispatcher(db)
        self.notification_service = NotificationService(db)

        # Веса для расчета оценки назначения
        self.weights = {
            'specialization': 0.35,  # Соответствие специализации
            'workload': 0.25,        # Текущая загруженность
            'rating': 0.15,          # Рейтинг исполнителя
            'availability': 0.10,    # Доступность
            'preference': 0.10,      # Предпочтения исполнителя
            'geographic': 0.05       # Географическая близость
        }

    # ========== ОСНОВНЫЕ МЕТОДЫ АВТОНАЗНАЧЕНИЯ ==========

    def auto_assign_executors_to_shifts(
        self,
        shifts: List[Shift],
        force_reassign: bool = False
    ) -> Dict[str, Any]:
        """
        Автоматически назначает исполнителей на список смен

        Args:
            shifts: Список смен для назначения
            force_reassign: Переназначить даже если исполнитель уже назначен

        Returns:
            Dict с результатами назначения
        """
        try:
            logger.info(f"Начало автоназначения для {len(shifts)} смен")

            results = {
                'total_shifts': len(shifts),
                'successful_assignments': 0,
                'failed_assignments': 0,
                'conflicts_found': 0,
                'assignments': [],
                'conflicts': [],
                'warnings': []
            }

            # Фильтруем смены для назначения
            shifts_to_assign = []
            for shift in shifts:
                if not shift.user_id or force_reassign:
                    shifts_to_assign.append(shift)
                else:
                    results['warnings'].append(f"Смена {shift.id} уже имеет назначенного исполнителя")

            if not shifts_to_assign:
                logger.info("Нет смен для назначения")
                return results

            # Получаем всех доступных исполнителей
            available_executors = self._get_available_executors()

            if not available_executors:
                logger.error("Нет доступных исполнителей")
                results['warnings'].append("Нет доступных исполнителей")
                return results

            # Назначаем исполнителей по одному, учитывая предыдущие назначения
            for shift in shifts_to_assign:
                assignment_result = self._assign_single_shift(shift, available_executors)

                if assignment_result['success']:
                    results['successful_assignments'] += 1
                    results['assignments'].append(assignment_result)

                    # Обновляем информацию о назначенном исполнителе
                    executor_id = assignment_result['executor_id']
                    self._update_executor_workload_cache(executor_id)

                else:
                    results['failed_assignments'] += 1
                    if assignment_result.get('conflicts'):
                        results['conflicts'].extend(assignment_result['conflicts'])
                        results['conflicts_found'] += len(assignment_result['conflicts'])

            # Создаем записи аудита
            self._create_assignment_audit(results)

            # Отправляем уведомления о назначениях
            if results['successful_assignments'] > 0:
                self._notify_successful_assignments(results['assignments'])

            logger.info(f"Автоназначение завершено: {results['successful_assignments']}/{results['total_shifts']} успешно")

            return results

        except Exception as e:
            logger.error(f"Ошибка автоназначения исполнителей: {e}")
            return {
                'total_shifts': len(shifts),
                'successful_assignments': 0,
                'failed_assignments': len(shifts),
                'error': str(e)
            }

    def _assign_single_shift(
        self,
        shift: Shift,
        available_executors: List[User]
    ) -> Dict[str, Any]:
        """Назначает исполнителя на одну смену"""
        try:
            # Получаем оценки всех исполнителей для этой смены
            executor_scores = self._evaluate_executors_for_shift(shift, available_executors)

            if not executor_scores:
                return {
                    'success': False,
                    'shift_id': shift.id,
                    'error': 'Нет подходящих исполнителей'
                }

            # Сортируем по убыванию оценки
            executor_scores.sort(key=lambda x: x.total_score, reverse=True)

            # Пробуем назначить лучшего исполнителя
            best_executor = executor_scores[0]

            # Проверяем конфликты
            conflicts = self._check_assignment_conflicts(shift, best_executor.executor_id)

            if conflicts and any(c.severity in ['high', 'critical'] for c in conflicts):
                return {
                    'success': False,
                    'shift_id': shift.id,
                    'conflicts': [self._conflict_to_dict(c) for c in conflicts],
                    'attempted_executor': best_executor.executor_id
                }

            # Выполняем назначение
            shift.user_id = best_executor.executor_id
            shift.assigned_at = datetime.now()
            shift.assigned_by_user_id = None  # Системное назначение

            # Создаем запись аудита
            audit = AuditLog(
                user_id=best_executor.executor_id,
                action="SHIFT_AUTO_ASSIGNED",
                details={
                    "shift_id": shift.id,
                    "executor_id": best_executor.executor_id,
                    "assignment_score": best_executor.total_score,
                    "reasons": best_executor.reasons,
                    "conflicts": len(conflicts) if conflicts else 0
                }
            )
            self.db.add(audit)
            self.db.commit()

            return {
                'success': True,
                'shift_id': shift.id,
                'executor_id': best_executor.executor_id,
                'executor_name': best_executor.executor_name,
                'assignment_score': best_executor.total_score,
                'reasons': best_executor.reasons,
                'minor_conflicts': len([c for c in conflicts if c.severity in ['low', 'medium']]) if conflicts else 0
            }

        except Exception as e:
            logger.error(f"Ошибка назначения исполнителя на смену {shift.id}: {e}")
            return {
                'success': False,
                'shift_id': shift.id,
                'error': str(e)
            }

    def _evaluate_executors_for_shift(
        self,
        shift: Shift,
        executors: List[User]
    ) -> List[ExecutorScore]:
        """Оценивает исполнителей для назначения на смену"""
        scores = []

        for executor in executors:
            try:
                score = self._calculate_executor_score(shift, executor)
                if score.total_score > 0:  # Только подходящих исполнителей
                    scores.append(score)
            except Exception as e:
                logger.error(f"Ошибка оценки исполнителя {executor.id}: {e}")

        return scores

    def _calculate_executor_score(self, shift: Shift, executor: User) -> ExecutorScore:
        """Рассчитывает оценку исполнителя для назначения на смену"""

        # 1. Соответствие специализации
        specialization_score = self._calculate_specialization_match(shift, executor)

        # 2. Оценка загруженности
        workload_score = self._calculate_workload_score(shift, executor)

        # 3. Рейтинг исполнителя
        rating_score = self._calculate_rating_score(executor)

        # 4. Доступность
        availability_score = self._calculate_availability_score(shift, executor)

        # 5. Предпочтения исполнителя
        preference_score = self._calculate_preference_score(shift, executor)

        # 6. Географическая близость
        geographic_score = self._calculate_geographic_score(shift, executor)

        # 7. Штрафы за конфликты
        conflict_penalties = self._calculate_conflict_penalties(shift, executor)

        # Общая оценка
        total_score = (
            specialization_score * self.weights['specialization'] +
            workload_score * self.weights['workload'] +
            rating_score * self.weights['rating'] +
            availability_score * self.weights['availability'] +
            preference_score * self.weights['preference'] +
            geographic_score * self.weights['geographic'] -
            conflict_penalties
        )

        # Собираем причины оценки
        reasons = []
        if specialization_score > 0.8:
            reasons.append("Отличное соответствие специализации")
        if workload_score > 0.7:
            reasons.append("Низкая текущая нагрузка")
        if rating_score > 0.8:
            reasons.append("Высокий рейтинг исполнителя")
        if availability_score == 1.0:
            reasons.append("Полная доступность")
        if conflict_penalties > 0:
            reasons.append("Есть незначительные конфликты")

        return ExecutorScore(
            executor_id=executor.id,
            executor_name=f"{executor.first_name} {executor.last_name}",
            total_score=max(0, total_score),  # Не может быть отрицательной
            specialization_match=specialization_score,
            workload_score=workload_score,
            rating_score=rating_score,
            availability_score=availability_score,
            preference_score=preference_score,
            geographic_score=geographic_score,
            conflict_penalties=conflict_penalties,
            reasons=reasons
        )

    # ========== МЕТОДЫ РАСЧЕТА ОЦЕНОК ==========

    def _calculate_specialization_match(self, shift: Shift, executor: User) -> float:
        """Рассчитывает соответствие специализации исполнителя требованиям смены"""
        if not shift.specialization_focus or not executor.specialization:
            return 0.0

        # Преобразуем специализации в множества для сравнения
        required_specs = set(shift.specialization_focus)
        executor_specs = set(executor.specialization)

        # Рассчитываем пересечение
        intersection = required_specs.intersection(executor_specs)
        union = required_specs.union(executor_specs)

        if not union:
            return 0.0

        # Jaccard coefficient для схожести множеств
        similarity = len(intersection) / len(union)

        # Бонус за полное покрытие требований
        if required_specs.issubset(executor_specs):
            similarity += 0.2

        return min(1.0, similarity)

    def _calculate_workload_score(self, shift: Shift, executor: User) -> float:
        """Рассчитывает оценку на основе текущей загруженности исполнителя"""
        try:
            # Получаем активные смены исполнителя за неделю
            week_start = shift.planned_start_time.date() - timedelta(days=7)
            week_end = shift.planned_start_time.date() + timedelta(days=7)

            executor_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.user_id == executor.id,
                    func.date(Shift.planned_start_time) >= week_start,
                    func.date(Shift.planned_start_time) <= week_end,
                    Shift.status.in_(['planned', 'active'])
                )
            ).count()

            # Получаем активные заявки исполнителя
            active_requests = self.db.query(Request).filter(
                and_(
                    Request.executor_id == executor.id,
                    Request.status.in_(['В работе', 'Принята', 'Закуп'])
                )
            ).count()

            # Рассчитываем балл загруженности (чем меньше нагрузка, тем выше балл)
            max_shifts_per_week = 7  # Максимум смен в неделю
            max_active_requests = 10  # Максимум активных заявок

            shift_load_score = max(0, (max_shifts_per_week - executor_shifts) / max_shifts_per_week)
            request_load_score = max(0, (max_active_requests - active_requests) / max_active_requests)

            return (shift_load_score + request_load_score) / 2

        except Exception as e:
            logger.error(f"Ошибка расчета загруженности для исполнителя {executor.id}: {e}")
            return 0.5  # Средняя оценка при ошибке

    def _calculate_rating_score(self, executor: User) -> float:
        """Рассчитывает оценку на основе рейтинга исполнителя"""
        if not hasattr(executor, 'rating') or executor.rating is None:
            return 0.5  # Средняя оценка для исполнителей без рейтинга

        # Нормализуем рейтинг от 0 до 1 (предполагаем рейтинг от 1 до 5)
        return min(1.0, max(0.0, (executor.rating - 1) / 4))

    def _calculate_availability_score(self, shift: Shift, executor: User) -> float:
        """Рассчитывает доступность исполнителя на время смены"""
        try:
            # Проверяем пересечения с другими сменами
            overlapping_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.user_id == executor.id,
                    Shift.id != shift.id,
                    Shift.status.in_(['planned', 'active']),
                    or_(
                        and_(
                            Shift.planned_start_time <= shift.planned_start_time,
                            Shift.planned_end_time > shift.planned_start_time
                        ),
                        and_(
                            Shift.planned_start_time < shift.planned_end_time,
                            Shift.planned_end_time >= shift.planned_end_time
                        )
                    )
                )
            ).count()

            if overlapping_shifts > 0:
                return 0.0  # Полное пересечение

            # Проверяем минимальный отдых между сменами
            adjacent_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.user_id == executor.id,
                    Shift.id != shift.id,
                    Shift.status.in_(['planned', 'active', 'completed']),
                    or_(
                        # Смена заканчивается незадолго до начала новой
                        and_(
                            Shift.planned_end_time <= shift.planned_start_time,
                            Shift.planned_end_time > shift.planned_start_time - timedelta(hours=8)
                        ),
                        # Смена начинается вскоре после окончания новой
                        and_(
                            Shift.planned_start_time >= shift.planned_end_time,
                            Shift.planned_start_time < shift.planned_end_time + timedelta(hours=8)
                        )
                    )
                )
            ).first()

            if adjacent_shifts:
                return 0.7  # Сниженная доступность из-за недостаточного отдыха

            return 1.0  # Полная доступность

        except Exception as e:
            logger.error(f"Ошибка расчета доступности для исполнителя {executor.id}: {e}")
            return 0.5

    def _calculate_preference_score(self, shift: Shift, executor: User) -> float:
        """Рассчитывает соответствие предпочтениям исполнителя"""
        # Базовая реализация - можно расширить в будущем
        # Пока возвращаем нейтральную оценку
        return 0.5

    def _calculate_geographic_score(self, shift: Shift, executor: User) -> float:
        """Рассчитывает географическую близость исполнителя к зоне смены"""
        # Базовая реализация - можно интегрировать с GeoOptimizer
        return 0.5

    def _calculate_conflict_penalties(self, shift: Shift, executor: User) -> float:
        """Рассчитывает штрафы за конфликты назначения"""
        penalties = 0.0

        # Штраф за превышение максимальных смен в неделю
        week_shifts = self.db.query(Shift).filter(
            and_(
                Shift.user_id == executor.id,
                func.date(Shift.planned_start_time) >= shift.planned_start_time.date() - timedelta(days=3),
                func.date(Shift.planned_start_time) <= shift.planned_start_time.date() + timedelta(days=3),
                Shift.status.in_(['planned', 'active'])
            )
        ).count()

        if week_shifts >= 5:  # Много смен за неделю
            penalties += 0.3

        return penalties

    # ========== МЕТОДЫ БАЛАНСИРОВКИ НАГРУЗКИ ==========

    def balance_executor_workload(self, target_date: date = None) -> Dict[str, Any]:
        """
        Балансирует нагрузку между исполнителями на указанную дату

        Args:
            target_date: Дата для балансировки (по умолчанию завтра)

        Returns:
            Dict с результатами балансировки
        """
        try:
            if not target_date:
                target_date = date.today() + timedelta(days=1)

            logger.info(f"Начало балансировки нагрузки на {target_date}")

            # Получаем все смены на указанную дату
            shifts = self.db.query(Shift).filter(
                and_(
                    func.date(Shift.planned_start_time) == target_date,
                    Shift.status == 'planned'
                )
            ).all()

            if not shifts:
                return {'message': f'Нет смен для балансировки на {target_date}'}

            # Анализируем текущее распределение
            distribution = self._analyze_workload_distribution(shifts)

            # Если нагрузка уже сбалансирована, ничего не делаем
            if distribution['is_balanced']:
                return {
                    'message': 'Нагрузка уже сбалансирована',
                    'distribution': distribution
                }

            # Выполняем перераспределение
            rebalance_result = self._rebalance_shifts(shifts, distribution)

            return {
                'target_date': target_date,
                'initial_distribution': distribution,
                'rebalancing_performed': True,
                'rebalance_result': rebalance_result
            }

        except Exception as e:
            logger.error(f"Ошибка балансировки нагрузки: {e}")
            return {'error': str(e)}

    def _analyze_workload_distribution(self, shifts: List[Shift]) -> Dict[str, Any]:
        """Анализирует распределение нагрузки между исполнителями"""

        # Подсчитываем смены по исполнителям
        executor_loads = {}
        unassigned_shifts = 0

        for shift in shifts:
            if shift.user_id:
                executor_loads[shift.user_id] = executor_loads.get(shift.user_id, 0) + 1
            else:
                unassigned_shifts += 1

        if not executor_loads:
            return {
                'total_shifts': len(shifts),
                'unassigned_shifts': unassigned_shifts,
                'is_balanced': False,
                'message': 'Все смены неназначены'
            }

        # Статистика распределения
        loads = list(executor_loads.values())
        avg_load = sum(loads) / len(loads)
        max_load = max(loads)
        min_load = min(loads)
        load_variance = sum((load - avg_load) ** 2 for load in loads) / len(loads)

        # Считаем распределение сбалансированным, если разброс небольшой
        is_balanced = (max_load - min_load) <= 1 and load_variance < 1.0

        return {
            'total_shifts': len(shifts),
            'assigned_shifts': len(shifts) - unassigned_shifts,
            'unassigned_shifts': unassigned_shifts,
            'unique_executors': len(executor_loads),
            'executor_loads': executor_loads,
            'avg_load': avg_load,
            'max_load': max_load,
            'min_load': min_load,
            'load_variance': load_variance,
            'is_balanced': is_balanced
        }

    def _rebalance_shifts(self, shifts: List[Shift], distribution: Dict[str, Any]) -> Dict[str, Any]:
        """Выполняет перераспределение смен для балансировки нагрузки"""

        # Находим перегруженных и недогруженных исполнителей
        executor_loads = distribution['executor_loads']
        avg_load = distribution['avg_load']

        overloaded = []
        underloaded = []

        for executor_id, load in executor_loads.items():
            if load > avg_load + 1:
                overloaded.append((executor_id, load))
            elif load < avg_load - 1:
                underloaded.append((executor_id, load))

        if not overloaded or not underloaded:
            return {'message': 'Нет возможности для перераспределения'}

        # Пытаемся перераспределить смены
        redistributions = []

        for overloaded_executor, overload in overloaded:
            # Находим смены этого исполнителя, которые можно перенести
            executor_shifts = [s for s in shifts if s.user_id == overloaded_executor]

            for shift in executor_shifts:
                if len(underloaded) == 0:
                    break

                # Пытаемся найти подходящего недогруженного исполнителя
                for i, (underloaded_executor, underload) in enumerate(underloaded):
                    executor = self.db.query(User).filter(User.id == underloaded_executor).first()

                    if executor and self._can_assign_shift(shift, executor):
                        # Выполняем перенос
                        old_executor_id = shift.user_id
                        shift.user_id = underloaded_executor
                        shift.assigned_at = datetime.now()

                        redistributions.append({
                            'shift_id': shift.id,
                            'from_executor': old_executor_id,
                            'to_executor': underloaded_executor
                        })

                        # Обновляем счетчики
                        underloaded[i] = (underloaded_executor, underload + 1)
                        if underload + 1 >= avg_load:
                            underloaded.pop(i)

                        break

                # Прекращаем, если достигли среднего уровня
                current_load = len([s for s in shifts if s.user_id == overloaded_executor])
                if current_load <= avg_load + 1:
                    break

        if redistributions:
            self.db.commit()

        return {
            'redistributions_performed': len(redistributions),
            'redistributions': redistributions
        }

    def _can_assign_shift(self, shift: Shift, executor: User) -> bool:
        """Проверяет, можно ли назначить смену исполнителю"""
        # Базовая проверка - можно расширить
        return (
            executor.role == ROLE_EXECUTOR and
            executor.status == 'approved' and
            self._calculate_availability_score(shift, executor) > 0.5
        )

    # ========== МЕТОДЫ УПРАВЛЕНИЯ КОНФЛИКТАМИ ==========

    def _check_assignment_conflicts(
        self,
        shift: Shift,
        executor_id: int
    ) -> List[AssignmentConflict]:
        """Проверяет конфликты при назначении исполнителя на смену"""
        conflicts = []

        executor = self.db.query(User).filter(User.id == executor_id).first()
        if not executor:
            conflicts.append(AssignmentConflict(
                type="executor_not_found",
                executor_id=executor_id,
                shift_id=shift.id,
                description="Исполнитель не найден",
                severity="critical",
                can_resolve=False
            ))
            return conflicts

        # Проверка роли
        if executor.role != ROLE_EXECUTOR:
            conflicts.append(AssignmentConflict(
                type="invalid_role",
                executor_id=executor_id,
                shift_id=shift.id,
                description=f"Неверная роль: {executor.role}, требуется: {ROLE_EXECUTOR}",
                severity="high",
                can_resolve=False
            ))

        # Проверка статуса
        if executor.status != 'approved':
            conflicts.append(AssignmentConflict(
                type="invalid_status",
                executor_id=executor_id,
                shift_id=shift.id,
                description=f"Неверный статус: {executor.status}, требуется: approved",
                severity="high",
                can_resolve=True,
                resolution_suggestion="Подтвердить статус исполнителя"
            ))

        # Проверка пересечений смен
        if self._calculate_availability_score(shift, executor) == 0.0:
            conflicts.append(AssignmentConflict(
                type="time_conflict",
                executor_id=executor_id,
                shift_id=shift.id,
                description="Пересечение с другой сменой",
                severity="critical",
                can_resolve=True,
                resolution_suggestion="Изменить время смены или найти другого исполнителя"
            ))

        return conflicts

    def resolve_assignment_conflicts(
        self,
        shift_id: int,
        conflict_resolution: str = "auto"
    ) -> Dict[str, Any]:
        """
        Разрешает конфликты назначения для смены

        Args:
            shift_id: ID смены с конфликтами
            conflict_resolution: Стратегия разрешения ("auto", "manual")

        Returns:
            Dict с результатами разрешения конфликтов
        """
        try:
            shift = self.db.query(Shift).filter(Shift.id == shift_id).first()
            if not shift:
                return {'error': 'Смена не найдена'}

            if not shift.user_id:
                return {'error': 'У смены нет назначенного исполнителя'}

            # Проверяем конфликты
            conflicts = self._check_assignment_conflicts(shift, shift.user_id)

            if not conflicts:
                return {'message': 'Конфликтов не найдено'}

            resolved_conflicts = []
            unresolved_conflicts = []

            for conflict in conflicts:
                if conflict.can_resolve and conflict_resolution == "auto":
                    resolution_result = self._auto_resolve_conflict(conflict)
                    if resolution_result['resolved']:
                        resolved_conflicts.append(conflict)
                    else:
                        unresolved_conflicts.append(conflict)
                else:
                    unresolved_conflicts.append(conflict)

            return {
                'shift_id': shift_id,
                'total_conflicts': len(conflicts),
                'resolved_conflicts': len(resolved_conflicts),
                'unresolved_conflicts': len(unresolved_conflicts),
                'conflicts_details': [self._conflict_to_dict(c) for c in unresolved_conflicts]
            }

        except Exception as e:
            logger.error(f"Ошибка разрешения конфликтов для смены {shift_id}: {e}")
            return {'error': str(e)}

    def _auto_resolve_conflict(self, conflict: AssignmentConflict) -> Dict[str, Any]:
        """Автоматически разрешает конфликт"""
        try:
            if conflict.type == "invalid_status":
                # Здесь можно добавить автоматическое обновление статуса
                # Пока просто логируем
                logger.info(f"Необходимо обновить статус исполнителя {conflict.executor_id}")
                return {'resolved': False, 'reason': 'Требует ручного вмешательства'}

            elif conflict.type == "time_conflict":
                # Пытаемся найти альтернативного исполнителя
                shift = self.db.query(Shift).filter(Shift.id == conflict.shift_id).first()
                if shift:
                    available_executors = self._get_available_executors()
                    alternative_result = self._assign_single_shift(shift, available_executors)

                    if alternative_result['success']:
                        return {'resolved': True, 'method': 'alternative_executor'}

                return {'resolved': False, 'reason': 'Не найден альтернативный исполнитель'}

            return {'resolved': False, 'reason': 'Неизвестный тип конфликта'}

        except Exception as e:
            logger.error(f"Ошибка автоматического разрешения конфликта: {e}")
            return {'resolved': False, 'reason': str(e)}

    def _conflict_to_dict(self, conflict: AssignmentConflict) -> Dict[str, Any]:
        """Преобразует конфликт в словарь"""
        return {
            'type': conflict.type,
            'executor_id': conflict.executor_id,
            'shift_id': conflict.shift_id,
            'description': conflict.description,
            'severity': conflict.severity,
            'can_resolve': conflict.can_resolve,
            'resolution_suggestion': conflict.resolution_suggestion
        }

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

    def _get_available_executors(self) -> List[User]:
        """Получает список доступных исполнителей"""
        return self.db.query(User).filter(
            and_(
                User.role == ROLE_EXECUTOR,
                User.status == 'approved'
            )
        ).all()

    def _update_executor_workload_cache(self, executor_id: int):
        """Обновляет кеш загруженности исполнителя"""
        # Здесь можно добавить кеширование в Redis для производительности
        pass

    def _create_assignment_audit(self, results: Dict[str, Any]):
        """Создает записи аудита для результатов назначения"""
        try:
            audit = AuditLog(
                user_id=None,  # Системная операция
                action="BATCH_ASSIGNMENT_COMPLETED",
                details={
                    "total_shifts": results['total_shifts'],
                    "successful_assignments": results['successful_assignments'],
                    "failed_assignments": results['failed_assignments'],
                    "conflicts_found": results['conflicts_found']
                }
            )
            self.db.add(audit)
            self.db.commit()
        except Exception as e:
            logger.error(f"Ошибка создания аудита назначений: {e}")

    def _notify_successful_assignments(self, assignments: List[Dict[str, Any]]):
        """Отправляет уведомления о успешных назначениях"""
        try:
            for assignment in assignments:
                executor_id = assignment['executor_id']
                shift_id = assignment['shift_id']

                self.notification_service.notify_user(
                    executor_id,
                    "Новое назначение на смену",
                    f"Вы назначены на смену {shift_id}. Проверьте детали в разделе 'Мои смены'."
                )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомлений о назначениях: {e}")

    # ========== МЕТОДЫ ДЛЯ ИНТЕГРАЦИИ ==========

    def get_best_executor_for_shift(self, shift: Shift) -> Optional[ExecutorScore]:
        """
        Возвращает лучшего исполнителя для назначения на смену

        Args:
            shift: Смена для назначения

        Returns:
            ExecutorScore лучшего исполнителя или None
        """
        try:
            available_executors = self._get_available_executors()
            if not available_executors:
                return None

            executor_scores = self._evaluate_executors_for_shift(shift, available_executors)
            if not executor_scores:
                return None

            # Возвращаем лучшего
            return max(executor_scores, key=lambda x: x.total_score)

        except Exception as e:
            logger.error(f"Ошибка получения лучшего исполнителя для смены {shift.id}: {e}")
            return None

    def reassign_on_absence(self, executor_id: int, reason: str = "absence") -> Dict[str, Any]:
        """
        Переназначает смены при отсутствии исполнителя

        Args:
            executor_id: ID отсутствующего исполнителя
            reason: Причина переназначения

        Returns:
            Dict с результатами переназначения
        """
        try:
            # Находим активные и запланированные смены исполнителя
            executor_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.user_id == executor_id,
                    Shift.status.in_(['planned', 'active']),
                    Shift.planned_start_time >= datetime.now()
                )
            ).all()

            if not executor_shifts:
                return {'message': 'У исполнителя нет активных смен для переназначения'}

            # Переназначаем каждую смену
            results = {
                'total_shifts': len(executor_shifts),
                'reassigned': 0,
                'failed': 0,
                'details': []
            }

            for shift in executor_shifts:
                # Убираем текущего исполнителя
                shift.user_id = None

                # Пытаемся найти замену
                available_executors = self._get_available_executors()
                assignment_result = self._assign_single_shift(shift, available_executors)

                if assignment_result['success']:
                    results['reassigned'] += 1
                    results['details'].append({
                        'shift_id': shift.id,
                        'new_executor': assignment_result['executor_id'],
                        'status': 'reassigned'
                    })
                else:
                    results['failed'] += 1
                    results['details'].append({
                        'shift_id': shift.id,
                        'status': 'failed',
                        'reason': assignment_result.get('error', 'Unknown error')
                    })

            # Создаем запись аудита
            audit = AuditLog(
                user_id=executor_id,
                action="EXECUTOR_ABSENCE_REASSIGNMENT",
                details={
                    "reason": reason,
                    "total_shifts": results['total_shifts'],
                    "reassigned": results['reassigned'],
                    "failed": results['failed']
                }
            )
            self.db.add(audit)
            self.db.commit()

            return results

        except Exception as e:
            logger.error(f"Ошибка переназначения смен для исполнителя {executor_id}: {e}")
            return {'error': str(e)}

    def handle_executor_preferences(self, executor_id: int) -> Dict[str, Any]:
        """
        Обрабатывает предпочтения исполнителя при назначении смен

        Args:
            executor_id: ID исполнителя

        Returns:
            Dict с информацией о предпочтениях
        """
        # Базовая реализация - можно расширить в будущем
        return {
            'executor_id': executor_id,
            'preferences_applied': False,
            'message': 'Система предпочтений планируется к реализации'
        }

    # ========== ИНТЕГРАЦИЯ С СИСТЕМОЙ ЗАЯВОК ==========

    def auto_assign_requests_to_shift_executors(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Автоматически назначает заявки исполнителям на основе их смен

        Args:
            target_date: Целевая дата (по умолчанию - сегодня)

        Returns:
            Dict с результатами назначения заявок
        """
        try:
            if target_date is None:
                target_date = date.today()

            logger.info(f"Автоназначение заявок исполнителям на {target_date}")

            # Получаем активные смены на дату
            active_shifts = self.db.query(Shift).filter(
                func.date(Shift.start_time) == target_date,
                Shift.status.in_(['planned', 'active']),
                Shift.user_id.isnot(None)
            ).all()

            # Получаем неназначенные заявки
            unassigned_requests = self.db.query(Request).filter(
                Request.status == 'new',
                func.date(Request.created_at) == target_date
            ).all()

            if not active_shifts or not unassigned_requests:
                return {
                    'status': 'no_work',
                    'message': f'Нет активных смен или неназначенных заявок на {target_date}',
                    'shifts': len(active_shifts),
                    'requests': len(unassigned_requests)
                }

            results = {
                'status': 'success',
                'target_date': str(target_date),
                'total_requests': len(unassigned_requests),
                'assigned_requests': 0,
                'failed_assignments': 0,
                'assignment_details': []
            }

            # Создаем AssignmentService для работы с заявками
            assignment_service = AssignmentService(self.db)

            # Пытаемся назначить каждую заявку
            for request in unassigned_requests:
                try:
                    # Находим подходящую смену для заявки
                    best_shift = self._find_best_shift_for_request(request, active_shifts)

                    if best_shift:
                        # Назначаем заявку исполнителю смены
                        assignment_result = assignment_service.smart_assign_request(
                            request_number=request.request_number,
                            assigned_by=1  # Система автоназначения
                        )

                        if assignment_result:
                            results['assigned_requests'] += 1
                            results['assignment_details'].append({
                                'request_number': request.request_number,
                                'executor_id': best_shift.user_id,
                                'shift_id': best_shift.id,
                                'specialization': request.specialization,
                                'status': 'assigned'
                            })
                        else:
                            results['failed_assignments'] += 1
                            results['assignment_details'].append({
                                'request_number': request.request_number,
                                'status': 'failed',
                                'reason': 'Assignment service failed'
                            })
                    else:
                        results['failed_assignments'] += 1
                        results['assignment_details'].append({
                            'request_number': request.request_number,
                            'status': 'failed',
                            'reason': 'No suitable shift found'
                        })

                except Exception as e:
                    logger.error(f"Ошибка назначения заявки {request.request_number}: {e}")
                    results['failed_assignments'] += 1
                    results['assignment_details'].append({
                        'request_number': request.request_number,
                        'status': 'failed',
                        'reason': str(e)
                    })

            logger.info(f"Автоназначение заявок завершено: {results['assigned_requests']} назначено")
            return results

        except Exception as e:
            logger.error(f"Ошибка автоназначения заявок: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'target_date': str(target_date) if target_date else None
            }

    def _find_best_shift_for_request(self, request: Request, shifts: List[Shift]) -> Optional[Shift]:
        """
        Находит наилучшую смену для заявки

        Args:
            request: Заявка для назначения
            shifts: Список доступных смен

        Returns:
            Optional[Shift]: Лучшая смена или None
        """
        best_shift = None
        best_score = 0

        for shift in shifts:
            score = self._calculate_shift_request_match_score(shift, request)
            if score > best_score:
                best_score = score
                best_shift = shift

        return best_shift if best_score > 0.3 else None  # Минимальный порог соответствия

    def _calculate_shift_request_match_score(self, shift: Shift, request: Request) -> float:
        """
        Вычисляет соответствие между сменой и заявкой

        Args:
            shift: Смена
            request: Заявка

        Returns:
            float: Оценка соответствия (0.0 - 1.0)
        """
        score = 0.0

        # Проверяем специализацию (вес 40%)
        if shift.specialization_focus:
            if request.specialization in shift.specialization_focus:
                score += 0.4
            elif any(spec in shift.specialization_focus for spec in [request.specialization]):
                score += 0.2

        # Проверяем географическую близость (вес 30%)
        if shift.geographic_zone and hasattr(request, 'location'):
            # Упрощенная проверка - в реальной системе нужна геолокация
            if request.location and shift.geographic_zone.lower() in request.location.lower():
                score += 0.3

        # Проверяем загруженность смены (вес 20%)
        if shift.current_request_count < shift.max_requests:
            load_ratio = shift.current_request_count / shift.max_requests
            score += 0.2 * (1.0 - load_ratio)  # Меньше нагрузка = выше оценка

        # Проверяем приоритет заявки (вес 10%)
        if hasattr(request, 'priority'):
            if request.priority == 'critical':
                score += 0.1
            elif request.priority == 'high':
                score += 0.05

        return min(score, 1.0)

    def sync_request_assignments_with_shifts(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Синхронизирует назначения заявок с текущими сменами

        Args:
            target_date: Целевая дата (по умолчанию - сегодня)

        Returns:
            Dict с результатами синхронизации
        """
        try:
            if target_date is None:
                target_date = date.today()

            logger.info(f"Синхронизация назначений заявок со сменами на {target_date}")

            # Получаем заявки с назначениями, где исполнитель не работает в этот день
            from uk_management_bot.database.models.request_assignment import RequestAssignment

            mismatched_assignments = self.db.query(RequestAssignment).join(Request).join(User).filter(
                RequestAssignment.status == 'active',
                func.date(Request.created_at) == target_date,
                ~RequestAssignment.assigned_to.in_(
                    self.db.query(Shift.user_id).filter(
                        func.date(Shift.start_time) == target_date,
                        Shift.status.in_(['planned', 'active'])
                    )
                )
            ).all()

            results = {
                'status': 'success',
                'target_date': str(target_date),
                'mismatched_assignments': len(mismatched_assignments),
                'reassigned': 0,
                'failed_reassignments': 0,
                'details': []
            }

            # Переназначаем несоответствующие заявки
            for assignment in mismatched_assignments:
                try:
                    # Отменяем старое назначение
                    assignment.status = 'cancelled'
                    assignment.cancelled_at = datetime.utcnow()

                    # Пытаемся найти новое назначение
                    self.auto_assign_requests_to_shift_executors(target_date)

                    results['reassigned'] += 1
                    results['details'].append({
                        'request_id': assignment.request_number,
                        'old_executor': assignment.assigned_to,
                        'status': 'reassigned'
                    })

                except Exception as e:
                    logger.error(f"Ошибка переназначения заявки {assignment.request_number}: {e}")
                    results['failed_reassignments'] += 1
                    results['details'].append({
                        'request_id': assignment.request_number,
                        'error': str(e)
                    })

            self.db.commit()

            logger.info(f"Синхронизация завершена: {results['reassigned']} переназначений")
            return results

        except Exception as e:
            logger.error(f"Ошибка синхронизации назначений: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'target_date': str(target_date) if target_date else None
            }