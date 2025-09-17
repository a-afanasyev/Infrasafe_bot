"""
AssignmentOptimizer - Продвинутый оптимизатор назначений с алгоритмами машинного обучения
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple, Set
from dataclasses import dataclass
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session
import statistics
import math
import random

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_assignment import ShiftAssignment
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.constants import REQUEST_STATUSES, SHIFT_STATUSES
import logging

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Результат оптимизации назначений"""
    initial_assignments: int
    optimized_assignments: int
    improvement_score: float
    processing_time: float
    changes_made: List[Dict[str, Any]]
    metrics_before: Dict[str, float]
    metrics_after: Dict[str, float]
    algorithm_used: str


@dataclass
class ConstraintViolation:
    """Нарушение ограничений"""
    type: str
    severity: str  # 'critical', 'high', 'medium', 'low'
    description: str
    shift_id: Optional[int]
    request_id: Optional[int]
    suggested_fix: str


class AssignmentOptimizer:
    """Продвинутый оптимизатор назначений с множественными алгоритмами"""
    
    def __init__(self, db: Session):
        self.db = db
        
        # Ограничения системы
        self.constraints = {
            'max_requests_per_shift': 10,
            'min_specialization_match': 0.6,
            'max_workload_imbalance': 0.3,
            'max_travel_time_minutes': 45,
            'urgent_response_time_minutes': 30
        }
        
        # Параметры алгоритмов
        self.genetic_params = {
            'population_size': 50,
            'generations': 100,
            'mutation_rate': 0.1,
            'crossover_rate': 0.8,
            'elite_size': 5
        }
        
        self.simulated_annealing_params = {
            'initial_temperature': 100.0,
            'cooling_rate': 0.95,
            'min_temperature': 0.1,
            'max_iterations': 1000
        }
    
    # ========== ОСНОВНЫЕ МЕТОДЫ ОПТИМИЗАЦИИ ==========
    
    def optimize_assignments(
        self, 
        algorithm: str = 'hybrid',
        optimization_scope: str = 'active'
    ) -> OptimizationResult:
        """
        Оптимизирует назначения заявок с использованием выбранного алгоритма
        
        Args:
            algorithm: 'greedy', 'genetic', 'simulated_annealing', 'hybrid'
            optimization_scope: 'active', 'all', 'urgent'
        
        Returns:
            Результат оптимизации
        """
        start_time = datetime.now()
        
        try:
            # Получаем текущие назначения
            assignments = self._get_assignments_for_optimization(optimization_scope)
            if not assignments:
                return self._empty_optimization_result(algorithm)
            
            # Вычисляем начальные метрики
            initial_metrics = self._calculate_assignment_metrics(assignments)
            
            # Выбираем и применяем алгоритм оптимизации
            if algorithm == 'greedy':
                result = self._greedy_optimization(assignments)
            elif algorithm == 'genetic':
                result = self._genetic_algorithm_optimization(assignments)
            elif algorithm == 'simulated_annealing':
                result = self._simulated_annealing_optimization(assignments)
            elif algorithm == 'hybrid':
                result = self._hybrid_optimization(assignments)
            else:
                raise ValueError(f"Неизвестный алгоритм: {algorithm}")
            
            # Вычисляем финальные метрики
            final_assignments = self._get_assignments_for_optimization(optimization_scope)
            final_metrics = self._calculate_assignment_metrics(final_assignments)
            
            # Вычисляем улучшение
            improvement = self._calculate_improvement(initial_metrics, final_metrics)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return OptimizationResult(
                initial_assignments=len(assignments),
                optimized_assignments=len(final_assignments),
                improvement_score=improvement,
                processing_time=processing_time,
                changes_made=result.get('changes', []),
                metrics_before=initial_metrics,
                metrics_after=final_metrics,
                algorithm_used=algorithm
            )
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Ошибка оптимизации назначений: {e}")
            return OptimizationResult(
                initial_assignments=0,
                optimized_assignments=0,
                improvement_score=0.0,
                processing_time=processing_time,
                changes_made=[],
                metrics_before={},
                metrics_after={},
                algorithm_used=algorithm
            )
    
    def resolve_conflicts(self) -> List[ConstraintViolation]:
        """
        Выявляет и разрешает конфликты в назначениях
        
        Returns:
            Список найденных и исправленных нарушений
        """
        try:
            violations = []
            
            # Проверяем перегрузки смен
            overload_violations = self._check_shift_overloads()
            violations.extend(overload_violations)
            
            # Проверяем соответствие специализаций
            spec_violations = self._check_specialization_mismatches()
            violations.extend(spec_violations)
            
            # Проверяем временные конфликты
            time_violations = self._check_time_conflicts()
            violations.extend(time_violations)
            
            # Проверяем срочные заявки
            urgent_violations = self._check_urgent_request_delays()
            violations.extend(urgent_violations)
            
            # Исправляем критические нарушения
            for violation in violations:
                if violation.severity == 'critical':
                    self._fix_violation(violation)
            
            logger.info(f"Найдено {len(violations)} нарушений ограничений")
            return violations
            
        except Exception as e:
            logger.error(f"Ошибка разрешения конфликтов: {e}")
            return []
    
    def redistribute_workload(self, target_balance: float = 0.15) -> Dict[str, Any]:
        """
        Перераспределяет нагрузку для достижения целевого баланса
        
        Args:
            target_balance: Целевой коэффициент дисбаланса (0-1)
        
        Returns:
            Результаты перераспределения
        """
        try:
            # Получаем текущее распределение нагрузки
            workload_distribution = self._get_workload_distribution()
            current_imbalance = self._calculate_workload_imbalance(workload_distribution)
            
            if current_imbalance <= target_balance:
                return {
                    "status": "balanced",
                    "current_imbalance": current_imbalance,
                    "target_balance": target_balance,
                    "changes": 0
                }
            
            # Выполняем перераспределение
            changes = []
            iterations = 0
            max_iterations = 50
            
            while current_imbalance > target_balance and iterations < max_iterations:
                # Находим самую перегруженную и недогруженную смены
                overloaded_shift = max(workload_distribution, key=workload_distribution.get)
                underloaded_shift = min(workload_distribution, key=workload_distribution.get)
                
                # Перемещаем одну заявку
                moved = self._move_request_between_shifts(overloaded_shift, underloaded_shift)
                if moved:
                    workload_distribution[overloaded_shift] -= 1
                    workload_distribution[underloaded_shift] += 1
                    changes.append({
                        "from_shift": overloaded_shift,
                        "to_shift": underloaded_shift,
                        "request_id": moved
                    })
                
                current_imbalance = self._calculate_workload_imbalance(workload_distribution)
                iterations += 1
                
                if not moved:
                    break
            
            return {
                "status": "optimized" if current_imbalance <= target_balance else "improved",
                "initial_imbalance": self._calculate_workload_imbalance(
                    self._get_workload_distribution()
                ),
                "final_imbalance": current_imbalance,
                "target_balance": target_balance,
                "changes": len(changes),
                "iterations": iterations,
                "redistribution_details": changes
            }
            
        except Exception as e:
            logger.error(f"Ошибка перераспределения нагрузки: {e}")
            return {"error": str(e)}
    
    def emergency_rebalance(self, shift_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Экстренное перебалансирование при критических ситуациях
        
        Args:
            shift_id: ID смены для экстренной разгрузки (опционально)
        
        Returns:
            Результаты экстренного перебалансирования
        """
        try:
            start_time = datetime.now()
            
            if shift_id:
                # Разгружаем конкретную смену
                result = self._emergency_unload_shift(shift_id)
            else:
                # Общее экстренное перебалансирование
                result = self._emergency_global_rebalance()
            
            processing_time = (datetime.now() - start_time).total_seconds()
            result['processing_time'] = processing_time
            
            logger.info(f"Экстренное перебалансирование завершено за {processing_time:.2f}с")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка экстренного перебалансирования: {e}")
            return {"error": str(e)}
    
    # ========== АЛГОРИТМЫ ОПТИМИЗАЦИИ ==========
    
    def _greedy_optimization(self, assignments: List[ShiftAssignment]) -> Dict[str, Any]:
        """Жадный алгоритм оптимизации"""
        try:
            changes = []
            
            # Сортируем назначения по качеству (худшие первые)
            sorted_assignments = sorted(assignments, key=lambda a: a.ai_score or 0)
            
            for assignment in sorted_assignments:
                if assignment.ai_score and assignment.ai_score < 0.7:
                    # Ищем лучшую альтернативную смену
                    better_shift = self._find_better_shift_for_assignment(assignment)
                    
                    if better_shift:
                        old_shift_id = assignment.shift_id
                        success = self._move_assignment_to_shift(assignment, better_shift)
                        
                        if success:
                            changes.append({
                                "assignment_id": assignment.id,
                                "from_shift": old_shift_id,
                                "to_shift": better_shift,
                                "improvement": "greedy"
                            })
            
            return {"changes": changes, "algorithm": "greedy"}
            
        except Exception as e:
            logger.error(f"Ошибка жадного алгоритма: {e}")
            return {"changes": [], "algorithm": "greedy"}
    
    def _genetic_algorithm_optimization(self, assignments: List[ShiftAssignment]) -> Dict[str, Any]:
        """Генетический алгоритм оптимизации"""
        try:
            if len(assignments) < 10:
                return self._greedy_optimization(assignments)  # Для малого объема используем жадный
            
            # Создаем начальную популяцию
            population = self._create_initial_population(assignments)
            
            best_solution = None
            best_fitness = float('-inf')
            
            for generation in range(self.genetic_params['generations']):
                # Оценка приспособленности
                fitness_scores = [self._calculate_fitness(solution) for solution in population]
                
                # Находим лучшее решение
                current_best_idx = max(range(len(fitness_scores)), key=lambda i: fitness_scores[i])
                current_best_fitness = fitness_scores[current_best_idx]
                
                if current_best_fitness > best_fitness:
                    best_fitness = current_best_fitness
                    best_solution = population[current_best_idx].copy()
                
                # Селекция
                selected = self._tournament_selection(population, fitness_scores)
                
                # Скрещивание и мутация
                new_population = []
                for i in range(0, len(selected), 2):
                    parent1 = selected[i]
                    parent2 = selected[i + 1] if i + 1 < len(selected) else selected[0]
                    
                    if random.random() < self.genetic_params['crossover_rate']:
                        child1, child2 = self._crossover(parent1, parent2)
                    else:
                        child1, child2 = parent1.copy(), parent2.copy()
                    
                    if random.random() < self.genetic_params['mutation_rate']:
                        child1 = self._mutate(child1)
                    if random.random() < self.genetic_params['mutation_rate']:
                        child2 = self._mutate(child2)
                    
                    new_population.extend([child1, child2])
                
                # Элитизм - сохраняем лучшие решения
                elite_indices = sorted(range(len(fitness_scores)), 
                                     key=lambda i: fitness_scores[i], 
                                     reverse=True)[:self.genetic_params['elite_size']]
                
                for idx in elite_indices:
                    new_population[idx] = population[idx]
                
                population = new_population[:self.genetic_params['population_size']]
            
            # Применяем лучшее решение
            changes = self._apply_genetic_solution(assignments, best_solution) if best_solution else []
            
            return {"changes": changes, "algorithm": "genetic", "best_fitness": best_fitness}
            
        except Exception as e:
            logger.error(f"Ошибка генетического алгоритма: {e}")
            return {"changes": [], "algorithm": "genetic"}
    
    def _simulated_annealing_optimization(self, assignments: List[ShiftAssignment]) -> Dict[str, Any]:
        """Алгоритм имитации отжига"""
        try:
            if not assignments:
                return {"changes": [], "algorithm": "simulated_annealing"}
            
            # Текущее решение
            current_solution = {a.id: a.shift_id for a in assignments}
            current_cost = self._calculate_solution_cost(current_solution)
            
            best_solution = current_solution.copy()
            best_cost = current_cost
            
            temperature = self.simulated_annealing_params['initial_temperature']
            changes = []
            
            for iteration in range(self.simulated_annealing_params['max_iterations']):
                # Генерируем соседнее решение
                neighbor_solution = self._generate_neighbor_solution(current_solution)
                neighbor_cost = self._calculate_solution_cost(neighbor_solution)
                
                # Принимаем или отклоняем решение
                cost_diff = neighbor_cost - current_cost
                
                if cost_diff < 0 or random.random() < math.exp(-cost_diff / temperature):
                    current_solution = neighbor_solution
                    current_cost = neighbor_cost
                    
                    # Обновляем лучшее решение
                    if current_cost < best_cost:
                        best_solution = current_solution.copy()
                        best_cost = current_cost
                        
                        changes.append({
                            "iteration": iteration,
                            "cost_improvement": best_cost - current_cost,
                            "temperature": temperature
                        })
                
                # Охлаждение
                temperature *= self.simulated_annealing_params['cooling_rate']
                
                if temperature < self.simulated_annealing_params['min_temperature']:
                    break
            
            # Применяем лучшее найденное решение
            applied_changes = self._apply_annealing_solution(assignments, best_solution)
            
            return {
                "changes": applied_changes,
                "algorithm": "simulated_annealing",
                "iterations": iteration + 1,
                "best_cost": best_cost,
                "cost_reduction": current_cost - best_cost
            }
            
        except Exception as e:
            logger.error(f"Ошибка алгоритма отжига: {e}")
            return {"changes": [], "algorithm": "simulated_annealing"}
    
    def _hybrid_optimization(self, assignments: List[ShiftAssignment]) -> Dict[str, Any]:
        """Гибридный алгоритм, комбинирующий несколько подходов"""
        try:
            all_changes = []
            
            # Этап 1: Жадная оптимизация для быстрых улучшений
            greedy_result = self._greedy_optimization(assignments)
            all_changes.extend(greedy_result.get('changes', []))
            
            # Этап 2: Применяем генетический алгоритм для глобальной оптимизации
            if len(assignments) > 20:
                # Получаем обновленные назначения после жадной оптимизации
                updated_assignments = self._get_assignments_for_optimization('active')
                genetic_result = self._genetic_algorithm_optimization(updated_assignments)
                all_changes.extend(genetic_result.get('changes', []))
            
            # Этап 3: Финальная балансировка нагрузки
            balance_result = self.redistribute_workload(0.15)
            if 'redistribution_details' in balance_result:
                for change in balance_result['redistribution_details']:
                    all_changes.append({
                        "type": "workload_balance",
                        "from_shift": change['from_shift'],
                        "to_shift": change['to_shift'],
                        "request_id": change['request_id']
                    })
            
            return {
                "changes": all_changes,
                "algorithm": "hybrid",
                "stages": ["greedy", "genetic", "balance"],
                "total_improvements": len(all_changes)
            }
            
        except Exception as e:
            logger.error(f"Ошибка гибридного алгоритма: {e}")
            return {"changes": [], "algorithm": "hybrid"}
    
    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========
    
    def _get_assignments_for_optimization(self, scope: str) -> List[ShiftAssignment]:
        """Получает назначения для оптимизации в зависимости от области"""
        try:
            query = self.db.query(ShiftAssignment).filter(
                ShiftAssignment.status == 'active'
            )
            
            if scope == 'urgent':
                # Только срочные заявки
                query = query.join(Request).filter(
                    Request.urgency.in_(['Срочная', 'Критическая'])
                )
            elif scope == 'active':
                # Только активные смены
                query = query.join(Shift).filter(
                    Shift.status.in_(['active', 'planned'])
                )
            
            return query.all()
            
        except Exception as e:
            logger.error(f"Ошибка получения назначений для оптимизации: {e}")
            return []
    
    def _calculate_assignment_metrics(self, assignments: List[ShiftAssignment]) -> Dict[str, float]:
        """Вычисляет метрики качества назначений"""
        try:
            if not assignments:
                return {}
            
            ai_scores = [a.ai_score for a in assignments if a.ai_score is not None]
            
            # Распределение нагрузки по сменам
            shift_workloads = {}
            for assignment in assignments:
                shift_id = assignment.shift_id
                shift_workloads[shift_id] = shift_workloads.get(shift_id, 0) + 1
            
            workload_values = list(shift_workloads.values())
            
            return {
                "average_ai_score": statistics.mean(ai_scores) if ai_scores else 0.0,
                "min_ai_score": min(ai_scores) if ai_scores else 0.0,
                "max_ai_score": max(ai_scores) if ai_scores else 0.0,
                "workload_imbalance": self._calculate_workload_imbalance(shift_workloads),
                "total_assignments": len(assignments),
                "average_workload": statistics.mean(workload_values) if workload_values else 0.0,
                "workload_std_dev": statistics.stdev(workload_values) if len(workload_values) > 1 else 0.0
            }
            
        except Exception as e:
            logger.error(f"Ошибка вычисления метрик: {e}")
            return {}
    
    def _calculate_improvement(self, before: Dict[str, float], after: Dict[str, float]) -> float:
        """Вычисляет общее улучшение оптимизации"""
        try:
            if not (before and after):
                return 0.0
            
            improvements = []
            
            # Улучшение качества назначений
            if 'average_ai_score' in before and 'average_ai_score' in after:
                score_improvement = after['average_ai_score'] - before['average_ai_score']
                improvements.append(score_improvement * 0.4)  # 40% веса
            
            # Улучшение балансировки нагрузки
            if 'workload_imbalance' in before and 'workload_imbalance' in after:
                balance_improvement = before['workload_imbalance'] - after['workload_imbalance']
                improvements.append(balance_improvement * 0.6)  # 60% веса
            
            return sum(improvements) if improvements else 0.0
            
        except Exception as e:
            logger.error(f"Ошибка вычисления улучшения: {e}")
            return 0.0
    
    def _get_workload_distribution(self) -> Dict[int, int]:
        """Получает текущее распределение нагрузки по сменам"""
        try:
            result = self.db.query(
                Shift.id, 
                func.count(ShiftAssignment.id).label('assignment_count')
            ).outerjoin(ShiftAssignment, 
                and_(
                    ShiftAssignment.shift_id == Shift.id,
                    ShiftAssignment.status == 'active'
                )
            ).filter(
                Shift.status.in_(['active', 'planned'])
            ).group_by(Shift.id).all()
            
            return {shift_id: count for shift_id, count in result}
            
        except Exception as e:
            logger.error(f"Ошибка получения распределения нагрузки: {e}")
            return {}
    
    def _calculate_workload_imbalance(self, workloads: Dict[int, int]) -> float:
        """Вычисляет коэффициент дисбаланса нагрузки"""
        if not workloads or len(workloads) < 2:
            return 0.0
        
        values = list(workloads.values())
        mean_load = statistics.mean(values)
        
        if mean_load == 0:
            return 0.0
        
        variance = statistics.variance(values)
        return math.sqrt(variance) / mean_load
    
    # Проверки нарушений ограничений
    
    def _check_shift_overloads(self) -> List[ConstraintViolation]:
        """Проверяет перегрузки смен"""
        violations = []
        try:
            overloaded_shifts = self.db.query(Shift).filter(
                Shift.current_request_count > self.constraints['max_requests_per_shift']
            ).all()
            
            for shift in overloaded_shifts:
                violations.append(ConstraintViolation(
                    type="shift_overload",
                    severity="high",
                    description=f"Смена {shift.id} перегружена: {shift.current_request_count} заявок",
                    shift_id=shift.id,
                    request_id=None,
                    suggested_fix="Перераспределить часть заявок на другие смены"
                ))
        except Exception as e:
            logger.error(f"Ошибка проверки перегрузок: {e}")
        
        return violations
    
    def _check_specialization_mismatches(self) -> List[ConstraintViolation]:
        """Проверяет несоответствие специализаций"""
        violations = []
        try:
            mismatched_assignments = self.db.query(ShiftAssignment).filter(
                and_(
                    ShiftAssignment.status == 'active',
                    ShiftAssignment.ai_score < self.constraints['min_specialization_match']
                )
            ).all()
            
            for assignment in mismatched_assignments:
                violations.append(ConstraintViolation(
                    type="specialization_mismatch",
                    severity="medium",
                    description=f"Низкое соответствие специализации (оценка: {assignment.ai_score})",
                    shift_id=assignment.shift_id,
                    request_id=assignment.request_id,
                    suggested_fix="Найти исполнителя с подходящей специализацией"
                ))
        except Exception as e:
            logger.error(f"Ошибка проверки специализаций: {e}")
        
        return violations
    
    def _check_time_conflicts(self) -> List[ConstraintViolation]:
        """Проверяет временные конфликты"""
        violations = []
        # Реализация проверки временных конфликтов
        return violations
    
    def _check_urgent_request_delays(self) -> List[ConstraintViolation]:
        """Проверяет задержки срочных заявок"""
        violations = []
        try:
            urgent_cutoff = datetime.now() - timedelta(
                minutes=self.constraints['urgent_response_time_minutes']
            )
            
            delayed_urgent = self.db.query(Request).filter(
                and_(
                    Request.urgency.in_(['Срочная', 'Критическая']),
                    Request.status == 'Новая',
                    Request.created_at < urgent_cutoff
                )
            ).all()
            
            for request in delayed_urgent:
                violations.append(ConstraintViolation(
                    type="urgent_delay",
                    severity="critical",
                    description=f"Срочная заявка #{request.request_number} не назначена более {self.constraints['urgent_response_time_minutes']} мин",
                    shift_id=None,
                    request_id=request.request_number,
                    suggested_fix="Немедленно назначить на доступную смену"
                ))
        except Exception as e:
            logger.error(f"Ошибка проверки срочных заявок: {e}")
        
        return violations
    
    def _fix_violation(self, violation: ConstraintViolation) -> bool:
        """Исправляет нарушение ограничения"""
        try:
            if violation.type == "urgent_delay" and violation.request_id:
                # Принудительно назначаем срочную заявку
                from uk_management_bot.services.smart_dispatcher import SmartDispatcher
                dispatcher = SmartDispatcher(self.db)
                result = dispatcher.handle_urgent_requests()
                return result.assigned_count > 0
            
            # Другие типы исправлений...
            return False
            
        except Exception as e:
            logger.error(f"Ошибка исправления нарушения {violation.type}: {e}")
            return False
    
    # Методы для генетического алгоритма
    
    def _create_initial_population(self, assignments: List[ShiftAssignment]) -> List[Dict[int, int]]:
        """Создает начальную популяцию для генетического алгоритма"""
        population = []
        base_solution = {a.id: a.shift_id for a in assignments}
        
        # Добавляем текущее решение
        population.append(base_solution)
        
        # Генерируем случайные вариации
        for _ in range(self.genetic_params['population_size'] - 1):
            solution = base_solution.copy()
            # Случайно изменяем некоторые назначения
            for _ in range(random.randint(1, min(5, len(assignments)))):
                assignment_id = random.choice(list(solution.keys()))
                available_shifts = self._get_available_shifts_for_assignment(assignment_id)
                if available_shifts:
                    solution[assignment_id] = random.choice(available_shifts)
            population.append(solution)
        
        return population
    
    def _calculate_fitness(self, solution: Dict[int, int]) -> float:
        """Вычисляет приспособленность решения"""
        # Упрощенная функция приспособленности
        # В реальности здесь должна быть более сложная логика
        try:
            total_score = 0.0
            count = 0
            
            for assignment_id, shift_id in solution.items():
                assignment = self.db.query(ShiftAssignment).filter(
                    ShiftAssignment.id == assignment_id
                ).first()
                
                if assignment and assignment.ai_score:
                    total_score += assignment.ai_score
                    count += 1
            
            return total_score / count if count > 0 else 0.0
            
        except Exception as e:
            logger.error(f"Ошибка вычисления приспособленности: {e}")
            return 0.0
    
    def _tournament_selection(self, population: List[Dict[int, int]], fitness_scores: List[float]) -> List[Dict[int, int]]:
        """Турнирная селекция"""
        selected = []
        tournament_size = 3
        
        for _ in range(len(population)):
            tournament_indices = random.sample(range(len(population)), 
                                             min(tournament_size, len(population)))
            winner_idx = max(tournament_indices, key=lambda i: fitness_scores[i])
            selected.append(population[winner_idx].copy())
        
        return selected
    
    def _crossover(self, parent1: Dict[int, int], parent2: Dict[int, int]) -> Tuple[Dict[int, int], Dict[int, int]]:
        """Скрещивание двух решений"""
        child1 = parent1.copy()
        child2 = parent2.copy()
        
        # Простое одноточечное скрещивание
        keys = list(parent1.keys())
        if len(keys) > 1:
            crossover_point = random.randint(1, len(keys) - 1)
            
            for i, key in enumerate(keys):
                if i >= crossover_point:
                    child1[key] = parent2[key]
                    child2[key] = parent1[key]
        
        return child1, child2
    
    def _mutate(self, solution: Dict[int, int]) -> Dict[int, int]:
        """Мутация решения"""
        mutated = solution.copy()
        
        # Изменяем случайное назначение
        if mutated:
            assignment_id = random.choice(list(mutated.keys()))
            available_shifts = self._get_available_shifts_for_assignment(assignment_id)
            if available_shifts:
                mutated[assignment_id] = random.choice(available_shifts)
        
        return mutated
    
    def _apply_genetic_solution(self, assignments: List[ShiftAssignment], solution: Dict[int, int]) -> List[Dict[str, Any]]:
        """Применяет решение генетического алгоритма"""
        changes = []
        
        for assignment in assignments:
            if assignment.id in solution:
                new_shift_id = solution[assignment.id]
                if new_shift_id != assignment.shift_id:
                    success = self._move_assignment_to_shift(assignment, new_shift_id)
                    if success:
                        changes.append({
                            "assignment_id": assignment.id,
                            "from_shift": assignment.shift_id,
                            "to_shift": new_shift_id,
                            "algorithm": "genetic"
                        })
        
        return changes
    
    # Методы для алгоритма отжига
    
    def _calculate_solution_cost(self, solution: Dict[int, int]) -> float:
        """Вычисляет стоимость решения (чем меньше, тем лучше)"""
        # Обратная функция приспособленности
        fitness = self._calculate_fitness(solution)
        return 1.0 - fitness if fitness > 0 else 1.0
    
    def _generate_neighbor_solution(self, solution: Dict[int, int]) -> Dict[int, int]:
        """Генерирует соседнее решение для алгоритма отжига"""
        neighbor = solution.copy()
        
        # Небольшое случайное изменение
        if neighbor:
            assignment_id = random.choice(list(neighbor.keys()))
            available_shifts = self._get_available_shifts_for_assignment(assignment_id)
            if available_shifts:
                neighbor[assignment_id] = random.choice(available_shifts)
        
        return neighbor
    
    def _apply_annealing_solution(self, assignments: List[ShiftAssignment], solution: Dict[int, int]) -> List[Dict[str, Any]]:
        """Применяет решение алгоритма отжига"""
        changes = []
        
        for assignment in assignments:
            if assignment.id in solution:
                new_shift_id = solution[assignment.id]
                if new_shift_id != assignment.shift_id:
                    success = self._move_assignment_to_shift(assignment, new_shift_id)
                    if success:
                        changes.append({
                            "assignment_id": assignment.id,
                            "from_shift": assignment.shift_id,
                            "to_shift": new_shift_id,
                            "algorithm": "simulated_annealing"
                        })
        
        return changes
    
    # Вспомогательные методы
    
    def _get_available_shifts_for_assignment(self, assignment_id: int) -> List[int]:
        """Получает доступные смены для назначения"""
        try:
            active_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.status.in_(['active', 'planned']),
                    Shift.current_request_count < self.constraints['max_requests_per_shift']
                )
            ).all()
            
            return [shift.id for shift in active_shifts]
            
        except Exception as e:
            logger.error(f"Ошибка получения доступных смен: {e}")
            return []
    
    def _move_assignment_to_shift(self, assignment: ShiftAssignment, new_shift_id: int) -> bool:
        """Перемещает назначение на новую смену"""
        try:
            old_shift_id = assignment.shift_id
            
            # Обновляем назначение
            assignment.shift_id = new_shift_id
            assignment.assignment_reason += f" (оптимизировано со смены {old_shift_id})"
            
            # Обновляем счетчики нагрузки
            old_shift = self.db.query(Shift).filter(Shift.id == old_shift_id).first()
            if old_shift:
                old_shift.current_request_count = max(0, old_shift.current_request_count - 1)
            
            new_shift = self.db.query(Shift).filter(Shift.id == new_shift_id).first()
            if new_shift:
                new_shift.current_request_count += 1
                
                # Обновляем исполнителя заявки
                request = self.db.query(Request).filter(Request.id == assignment.request_id).first()
                if request:
                    request.executor_id = new_shift.user_id
            
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка перемещения назначения: {e}")
            return False
    
    def _find_better_shift_for_assignment(self, assignment: ShiftAssignment) -> Optional[int]:
        """Находит лучшую смену для назначения"""
        try:
            request = self.db.query(Request).filter(Request.id == assignment.request_id).first()
            if not request:
                return None
            
            from uk_management_bot.services.smart_dispatcher import SmartDispatcher
            dispatcher = SmartDispatcher(self.db)
            
            active_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.status.in_(['active', 'planned']),
                    Shift.id != assignment.shift_id,
                    Shift.current_request_count < self.constraints['max_requests_per_shift']
                )
            ).all()
            
            best_shift_id = None
            best_score = assignment.ai_score or 0
            
            for shift in active_shifts:
                score = dispatcher.calculate_assignment_score(request, shift)
                if score.total_score > best_score * 1.1:  # Требуем минимум 10% улучшения
                    best_score = score.total_score
                    best_shift_id = shift.id
            
            return best_shift_id
            
        except Exception as e:
            logger.error(f"Ошибка поиска лучшей смены: {e}")
            return None
    
    def _move_request_between_shifts(self, from_shift_id: int, to_shift_id: int) -> Optional[int]:
        """Перемещает заявку между сменами"""
        try:
            # Находим подходящую заявку для перемещения
            assignment = self.db.query(ShiftAssignment).filter(
                and_(
                    ShiftAssignment.shift_id == from_shift_id,
                    ShiftAssignment.status == 'active'
                )
            ).order_by(ShiftAssignment.ai_score.asc()).first()
            
            if assignment:
                success = self._move_assignment_to_shift(assignment, to_shift_id)
                return assignment.request_id if success else None
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка перемещения заявки между сменами: {e}")
            return None
    
    def _emergency_unload_shift(self, shift_id: int) -> Dict[str, Any]:
        """Экстренная разгрузка конкретной смены"""
        try:
            assignments = self.db.query(ShiftAssignment).filter(
                and_(
                    ShiftAssignment.shift_id == shift_id,
                    ShiftAssignment.status == 'active'
                )
            ).all()
            
            moved_requests = 0
            errors = []
            
            for assignment in assignments:
                available_shifts = self._get_available_shifts_for_assignment(assignment.id)
                available_shifts = [s for s in available_shifts if s != shift_id]
                
                if available_shifts:
                    # Выбираем наименее загруженную смену
                    target_shift_id = min(available_shifts, key=lambda s: self._get_shift_workload(s))
                    success = self._move_assignment_to_shift(assignment, target_shift_id)
                    
                    if success:
                        moved_requests += 1
                    else:
                        errors.append(f"Ошибка перемещения заявки {assignment.request_id}")
                else:
                    errors.append(f"Нет доступных смен для заявки {assignment.request_id}")
            
            return {
                "shift_id": shift_id,
                "moved_requests": moved_requests,
                "total_requests": len(assignments),
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Ошибка экстренной разгрузки смены {shift_id}: {e}")
            return {"error": str(e)}
    
    def _emergency_global_rebalance(self) -> Dict[str, Any]:
        """Общее экстренное перебалансирование"""
        try:
            # Быстрое перераспределение с жестким лимитом времени
            start_time = datetime.now()
            time_limit = 30  # секунд
            
            result = self.redistribute_workload(0.2)  # Более мягкий лимит баланса
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            if processing_time > time_limit:
                logger.warning(f"Экстренное перебалансирование превысило лимит времени: {processing_time:.2f}с")
            
            result['emergency_mode'] = True
            result['time_limit_exceeded'] = processing_time > time_limit
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка общего экстренного перебалансирования: {e}")
            return {"error": str(e), "emergency_mode": True}
    
    def _get_shift_workload(self, shift_id: int) -> int:
        """Получает текущую нагрузку смены"""
        try:
            shift = self.db.query(Shift).filter(Shift.id == shift_id).first()
            return shift.current_request_count if shift else 0
        except Exception as e:
            logger.error(f"Ошибка получения нагрузки смены {shift_id}: {e}")
            return 0
    
    def _empty_optimization_result(self, algorithm: str) -> OptimizationResult:
        """Создает пустой результат оптимизации"""
        return OptimizationResult(
            initial_assignments=0,
            optimized_assignments=0,
            improvement_score=0.0,
            processing_time=0.0,
            changes_made=[],
            metrics_before={},
            metrics_after={},
            algorithm_used=algorithm
        )