"""AUD5-ARCH-3 волна 4, block-move: скоринг оптимизации расписания из
services/shift_planning_service.py (код байт-в-байт)."""

from datetime import date
from typing import List

from uk_management_bot.utils.business_time import (
    business_day_window,
    to_business,
)

from uk_management_bot.database.models.shift import Shift
import logging

logger = logging.getLogger(__name__)


class ScoringMixin:
    def _calculate_optimization_score(self, target_date: date) -> float:
        """Вычисляет оценку оптимизации расписания для даты"""
        try:
            # Получаем смены на дату (бизнес-окно дня)
            day_start, day_end = business_day_window(target_date)
            shifts = self.db.query(Shift).filter(
                Shift.planned_start_time >= day_start,
                Shift.planned_start_time < day_end,
                Shift.status.in_(['planned', 'active'])
            ).all()
            
            if not shifts:
                return 0.0
            
            total_score = 0.0
            factors = 0
            
            # Фактор 1: Покрытие времени (вес 30%)
            hour_coverage = self._calculate_hour_coverage(shifts)
            coverage_score = len(hour_coverage) / 24.0 * 100
            total_score += coverage_score * 0.3
            factors += 1
            
            # Фактор 2: Загруженность исполнителей (вес 25%)
            load_balance_score = self._calculate_load_balance_score(shifts)
            total_score += load_balance_score * 0.25
            factors += 1
            
            # Фактор 3: Покрытие специализаций (вес 25%)
            specialization_score = self._calculate_specialization_coverage_score(shifts)
            total_score += specialization_score * 0.25
            factors += 1
            
            # Фактор 4: Эффективность (вес 20%)
            efficiency_score = self._calculate_efficiency_score(shifts)
            total_score += efficiency_score * 0.2
            factors += 1
            
            return round(total_score, 2)
            
        except Exception as e:
            logger.error(f"Ошибка вычисления оценки оптимизации: {e}")
            return 0.0
    
    def _calculate_hour_coverage(self, shifts: List[Shift]) -> List[int]:
        """Вычисляет покрытие по часам"""
        covered_hours = set()
        
        for shift in shifts:
            if shift.planned_start_time and shift.planned_end_time:
                # Часы бизнес-зоны — как в get_coverage_gaps (ARCH-135(б))
                start_hour = to_business(shift.planned_start_time).hour
                end_hour = to_business(shift.planned_end_time).hour

                current_hour = start_hour
                while current_hour != end_hour:
                    covered_hours.add(current_hour)
                    current_hour = (current_hour + 1) % 24

        return list(covered_hours)
    
    def _calculate_load_balance_score(self, shifts: List[Shift]) -> float:
        """Вычисляет оценку балансировки нагрузки"""
        if not shifts:
            return 100.0
        
        # Подсчитываем нагрузку по исполнителям
        executor_loads = {}
        for shift in shifts:
            if shift.user_id:
                executor_loads[shift.user_id] = executor_loads.get(shift.user_id, 0) + 1
        
        if not executor_loads:
            return 50.0  # Смены без назначения
        
        loads = list(executor_loads.values())
        if len(loads) == 1:
            return 100.0  # Идеальная балансировка для одного исполнителя
        
        # Вычисляем стандартное отклонение нагрузки
        mean_load = sum(loads) / len(loads)
        variance = sum((load - mean_load) ** 2 for load in loads) / len(loads)
        std_dev = variance ** 0.5
        
        # Преобразуем в оценку (чем меньше отклонение, тем лучше)
        max_possible_std = mean_load  # Максимальное возможное отклонение
        balance_score = max(0, 100 - (std_dev / max_possible_std) * 100)
        
        return round(balance_score, 2)
    
    def _calculate_specialization_coverage_score(self, shifts: List[Shift]) -> float:
        """Вычисляет оценку покрытия специализаций"""
        if not shifts:
            return 0.0
        
        # Собираем все покрываемые специализации
        all_specializations = set()
        for shift in shifts:
            if shift.specialization_focus:
                all_specializations.update(shift.specialization_focus)
        
        # Считаем, что основных специализаций 5
        main_specializations = {'electric', 'plumbing', 'hvac', 'maintenance', 'security'}
        covered_main = len(all_specializations.intersection(main_specializations))
        
        return (covered_main / len(main_specializations)) * 100
    
    def _calculate_efficiency_score(self, shifts: List[Shift]) -> float:
        """Вычисляет оценку эффективности"""
        if not shifts:
            return 0.0
        
        total_score = 0.0
        count = 0
        
        for shift in shifts:
            # Базовая оценка эффективности
            efficiency = shift.efficiency_score or 75.0  # По умолчанию средняя оценка
            total_score += efficiency
            count += 1
        
        return total_score / count if count > 0 else 75.0
