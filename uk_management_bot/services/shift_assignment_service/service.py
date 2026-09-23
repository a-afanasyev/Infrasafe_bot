from datetime import datetime, date, timezone
from typing import List, Dict, Any
from sqlalchemy import and_
from sqlalchemy.orm import Session

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import (
    legacy_role_filter,
)
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.services.assignment_service import AssignmentService
from uk_management_bot.services.notification_service import NotificationService
from uk_management_bot.utils.constants import ROLE_EXECUTOR
import logging

from .scoring import ScoringEngine
from .balancer import WorkloadBalancer
from .conflicts import ConflictDetector

logger = logging.getLogger(__name__)


class ShiftAssignmentService:
    """
    Сервис для автоматического назначения исполнителей на смены
    Использует ИИ-алгоритмы для оптимального распределения нагрузки
    """

    def __init__(self, db: Session):
        self.db = db
        self.assignment_service = AssignmentService(db)
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

        self.scoring_engine = ScoringEngine(db, self.weights)
        self.workload_balancer = WorkloadBalancer(db, self.scoring_engine)
        self.conflict_detector = ConflictDetector(db, self.scoring_engine)

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
            executor_scores = self.scoring_engine._evaluate_executors_for_shift(shift, available_executors)

            if not executor_scores:
                return {
                    'success': False,
                    'shift_id': shift.id,
                    'error': 'Нет подходящих исполнителей'
                }

            # Сортируем по убыванию оценки
            executor_scores.sort(key=lambda x: x.total_score, reverse=True)

            # AUD3-13: перебираем кандидатов, а не только топового. Агрегатный
            # score и hard-конфликты — РАЗНЫЕ измерения: лучший по score может
            # провалить отдельную проверку (роль, пересечение окон, статус), и
            # раньше смена в этом случае оставалась НЕназначенной при живом
            # втором кандидате без конфликтов.
            #
            # Границу severity не двигаем: low/medium назначению не мешали и не
            # мешают — иначе «перебор» стал бы тихим изменением политики, при
            # котором топовый кандидат уступает место второму из-за пустяка.
            best_executor = None
            conflicts = []
            attempted: List[int] = []
            first_blocking_conflicts = None
            for candidate in executor_scores:
                attempted.append(candidate.executor_id)
                candidate_conflicts = self.conflict_detector._check_assignment_conflicts(
                    shift, candidate.executor_id
                )
                blocking = bool(candidate_conflicts) and any(
                    c.severity in ['high', 'critical'] for c in candidate_conflicts
                )
                if blocking:
                    if first_blocking_conflicts is None:
                        # Причиной отказа считаем конфликты ТОПОВОГО кандидата:
                        # именно его менеджер ожидал увидеть назначенным.
                        first_blocking_conflicts = candidate_conflicts
                    logger.info(
                        "Смена %s: кандидат %s отклонён hard-конфликтом, пробуем следующего",
                        shift.id, candidate.executor_id,
                    )
                    continue
                best_executor = candidate
                conflicts = candidate_conflicts
                break

            if best_executor is None:
                return {
                    'success': False,
                    'shift_id': shift.id,
                    'conflicts': [
                        self.conflict_detector._conflict_to_dict(c)
                        for c in (first_blocking_conflicts or [])
                    ],
                    # Одиночное поле — прежний контракт (его читает
                    # handlers/shift_management/assignment_a.py); список нужен,
                    # чтобы по отчёту было видно, что перебор действительно был.
                    'attempted_executor': attempted[0] if attempted else None,
                    'attempted_executors': attempted,
                }

            # AUD5-ARCH-7: между выборкой смены и этой записью менеджер мог
            # назначить исполнителя вручную. API-путь держит строку под
            # `FOR UPDATE` (`api/shifts/service.get_shift_for_update`), а
            # планировщик читал `user_id IS NULL` без блокировки и писал
            # безусловно — ручное назначение молча затиралось системным, без
            # следа в аудите. Поэтому compare-and-set: перечитываем строку под
            # блокировкой и пишем, только если она в том же состоянии, в каком
            # мы её выбрали. `populate_existing()` обязателен — иначе Query
            # вернёт объект из identity map с прежним (устаревшим) `user_id`.
            expected_user_id = shift.user_id
            locked = (
                self.db.query(Shift)
                .filter(Shift.id == shift.id)
                .populate_existing()
                .with_for_update()
                .first()
            )
            if locked is None or locked.user_id != expected_user_id:
                self.db.rollback()
                logger.info(
                    "Смена %s изменилась во время подбора (было %s, стало %s) — "
                    "автоназначение отменено",
                    shift.id, expected_user_id,
                    None if locked is None else locked.user_id,
                )
                return {
                    'success': False,
                    'shift_id': shift.id,
                    'error': 'shift_changed_meanwhile',
                    'attempted_executor': best_executor.executor_id,
                    'attempted_executors': attempted,
                }

            # Дальше работаем с перечитанной строкой: обычно это тот же объект,
            # что и `shift` (identity map), но если вызывающий передал
            # отсоединённый объект — правка ушла бы в никуда.
            shift = locked

            # Выполняем назначение
            shift.user_id = best_executor.executor_id
            shift.assigned_at = datetime.now(timezone.utc)
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

    # ========== МЕТОДЫ БАЛАНСИРОВКИ НАГРУЗКИ ==========

    def balance_executor_workload(self, target_date: date = None) -> Dict[str, Any]:
        return self.workload_balancer.balance_executor_workload(target_date)


    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

    def _get_available_executors(self) -> List[User]:
        """Получает список доступных исполнителей"""
        return self.db.query(User).filter(
            and_(
                legacy_role_filter(ROLE_EXECUTOR),
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
                    # AUD3-11: planned_start_time = DateTime(timezone=True); сравнение
                    # с naive datetime.now() семантически хрупко (зависит от session TZ).
                    Shift.planned_start_time >= datetime.now(timezone.utc)
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
                # AUD3-12: исполнителя НЕ снимаем до попытки. Прежний порядок
                # («обнулить, потом пытаться») ломался о то, что
                # `_assign_single_shift` коммитит внутри себя: при неудачной
                # попытке смена оставалась грязной, и СЛЕДУЮЩИЙ удачный
                # внутренний commit (для другой смены пачки) записывал это
                # обнуление — смена молча теряла исполнителя без единой записи в
                # аудите. Внешний `rollback()` тут бесполезен: коммит уже был.
                #
                # Спекулятивная мутация не нужна и технически: overlap-проверка
                # (`_calculate_availability_score`) исключает саму эту смену
                # условием `Shift.id != shift.id`, поэтому «занятость» текущим
                # исполнителем кандидату не мешает.
                #
                # Отсутствующего исключаем из кандидатов: `_get_available_executors`
                # отдаёт всех approved-исполнителей, и без фильтра он мог быть
                # «назначен» на свою же смену — no-op под видом успеха.
                available_executors = [
                    ex for ex in self._get_available_executors() if ex.id != executor_id
                ]
                assignment_result = self._assign_single_shift(shift, available_executors)

                if assignment_result['success']:
                    results['reassigned'] += 1
                    results['details'].append({
                        'shift_id': shift.id,
                        'new_executor': assignment_result['executor_id'],
                        'status': 'reassigned'
                    })
                else:
                    # Замены нет — снимаем исполнителя ЯВНО и со следом в аудите.
                    # Итог в БД тот же, что раньше получался случайно, но теперь
                    # это решение: смена видна как непокрытая, и понятно почему.
                    shift.user_id = None
                    shift.assigned_at = None
                    shift.assigned_by_user_id = None
                    self.db.add(AuditLog(
                        user_id=executor_id,
                        action="SHIFT_UNASSIGNED_NO_REPLACEMENT",
                        details={
                            "shift_id": shift.id,
                            "absent_executor_id": executor_id,
                            "reason": reason,
                            "assignment_error": assignment_result.get('error'),
                            "attempted_executors": assignment_result.get('attempted_executors', []),
                        }
                    ))
                    results['failed'] += 1
                    results['details'].append({
                        'shift_id': shift.id,
                        'status': 'failed',
                        'reason': assignment_result.get('error', 'Unknown error'),
                        'unassigned': True,
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
            # AUD3-12: rollback обязателен — до этой точки в сессии могли остаться
            # незакоммиченные мутации (явное снятие исполнителя, записи аудита).
            # Без него они уедут в БД с первым же commit'ом любого следующего
            # вызова по этой сессии, то есть ровно тем механизмом, который и был
            # исходным дефектом — только на error-path.
            try:
                self.db.rollback()
            except Exception:
                logger.warning("Не удалось откатить сессию после сбоя переназначения",
                               exc_info=True)
            logger.error(f"Ошибка переназначения смен для исполнителя {executor_id}: {e}")
            return {'error': str(e)}

    # Прокси «интеграции с системой заявок» ретайрены (BUG-148): их путь
    # (RequestAssignmentEngine → smart_assign_request → SmartDispatcher) был
    # мёртв с рождения — планировочные джобы №8/№9 сняты вместе с ним.
