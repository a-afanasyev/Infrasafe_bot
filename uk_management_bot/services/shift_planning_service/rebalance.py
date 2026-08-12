"""AUD5-ARCH-3 волна 4, block-move: интеграция с автоназначением из
services/shift_planning_service.py (код байт-в-байт)."""

from datetime import date
from typing import Optional, Dict, Any

from uk_management_bot.utils.business_time import (
    business_day_window,
    business_today,
)

from uk_management_bot.database.models.shift import Shift
import logging

logger = logging.getLogger(__name__)


class RebalanceMixin:
    # ========== ИНТЕГРАЦИЯ С АВТОНАЗНАЧЕНИЕМ ==========

    def rebalance_daily_assignments(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Перебалансирует назначения исполнителей на смены для указанной даты

        Args:
            target_date: Дата для перебалансировки (по умолчанию - сегодня)

        Returns:
            Dict с результатами перебалансировки
        """
        try:
            if target_date is None:
                target_date = business_today()

            logger.info(f"Начинаем перебалансировку назначений на {target_date}")

            # Получаем все смены на указанную дату (бизнес-окно дня)
            day_start, day_end = business_day_window(target_date)
            daily_shifts = self.db.query(Shift).filter(
                Shift.start_time >= day_start,
                Shift.start_time < day_end,
                Shift.status.in_(['planned', 'active'])
            ).all()

            if not daily_shifts:
                return {
                    'status': 'no_shifts',
                    'message': f'Нет смен для перебалансировки на {target_date}',
                    'rebalanced_shifts': 0
                }

            # Применяем балансировку нагрузки
            balance_results = self.assignment_service.balance_executor_workload(target_date)

            # Собираем статистику
            results = {
                'status': 'success',
                'target_date': str(target_date),
                'total_shifts': len(daily_shifts),
                'rebalanced_shifts': balance_results.get('rebalanced_count', 0),
                'balance_improvements': balance_results.get('improvements', []),
                'warnings': balance_results.get('warnings', [])
            }

            logger.info(f"Перебалансировка завершена: {results}")
            return results

        except Exception as e:
            logger.error(f"Ошибка перебалансировки назначений: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'target_date': str(target_date) if target_date else None
            }
