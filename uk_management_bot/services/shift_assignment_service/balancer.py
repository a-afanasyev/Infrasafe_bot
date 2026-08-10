from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Any
from sqlalchemy import and_
from sqlalchemy.orm import Session

from uk_management_bot.utils.business_time import (
    business_day_window,
    business_today,
)

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import (
    get_user_roles,
)
from uk_management_bot.utils.constants import ROLE_EXECUTOR
import logging

from .scoring import ScoringEngine

logger = logging.getLogger(__name__)


class WorkloadBalancer:
    """Балансировка нагрузки исполнителей (извлечено из ShiftAssignmentService, ARC-03).
    Владеет ребаланс-мутациями (shift.user_id + db.commit); зависит от ScoringEngine."""

    def __init__(self, db: Session, scoring_engine: 'ScoringEngine'):
        self.db = db
        self.scoring_engine = scoring_engine

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
                target_date = business_today() + timedelta(days=1)

            logger.info(f"Начало балансировки нагрузки на {target_date}")

            # Получаем все смены на указанную дату (бизнес-окно дня)
            day_start, day_end = business_day_window(target_date)
            shifts = self.db.query(Shift).filter(
                and_(
                    Shift.planned_start_time >= day_start,
                    Shift.planned_start_time < day_end,
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
                        shift.assigned_at = datetime.now(timezone.utc)

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
            ROLE_EXECUTOR in get_user_roles(executor) and
            executor.status == 'approved' and
            self.scoring_engine._calculate_availability_score(shift, executor) > 0.5
        )
