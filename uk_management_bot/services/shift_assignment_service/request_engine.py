from datetime import datetime, date, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from uk_management_bot.utils.business_time import (
    business_day_window,
    business_today,
)

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.assignment_service import AssignmentService
import logging

logger = logging.getLogger(__name__)


class RequestAssignmentEngine:
    """Matching заявок к сменам/исполнителям (извлечено из ShiftAssignmentService, ARC-03).
    AssignmentService создаётся локально внутри метода (как раньше)."""

    def __init__(self, db: Session):
        self.db = db

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
                target_date = business_today()

            logger.info(f"Автоназначение заявок исполнителям на {target_date}")

            # Бизнес-окно дня — одно для смен и заявок
            day_start, day_end = business_day_window(target_date)

            # Получаем активные смены на дату
            active_shifts = self.db.query(Shift).filter(
                Shift.start_time >= day_start,
                Shift.start_time < day_end,
                Shift.status.in_(['planned', 'active']),
                Shift.user_id.isnot(None)
            ).all()

            # Получаем неназначенные заявки
            unassigned_requests = self.db.query(Request).filter(
                Request.status == 'new',
                Request.created_at >= day_start,
                Request.created_at < day_end,
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
                target_date = business_today()

            logger.info(f"Синхронизация назначений заявок со сменами на {target_date}")

            # Получаем заявки с назначениями, где исполнитель не работает в этот день
            from uk_management_bot.database.models.request_assignment import RequestAssignment

            day_start, day_end = business_day_window(target_date)
            mismatched_assignments = self.db.query(RequestAssignment).join(
                Request, RequestAssignment.request_number == Request.request_number
            ).filter(
                RequestAssignment.status == 'active',
                Request.created_at >= day_start,
                Request.created_at < day_end,
                ~RequestAssignment.executor_id.in_(
                    self.db.query(Shift.user_id).filter(
                        Shift.start_time >= day_start,
                        Shift.start_time < day_end,
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
                    assignment.cancelled_at = datetime.now(timezone.utc)

                    # Пытаемся найти новое назначение
                    self.auto_assign_requests_to_shift_executors(target_date)

                    results['reassigned'] += 1
                    results['details'].append({
                        'request_id': assignment.request_number,
                        'old_executor': assignment.executor_id,
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
