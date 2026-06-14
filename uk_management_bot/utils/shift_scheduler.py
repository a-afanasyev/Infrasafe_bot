"""
Планировщик задач для системы смен - автоматическое выполнение фоновых операций
"""

import logging
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from uk_management_bot.database.session import SessionLocal
from uk_management_bot.services.shift_planning_service import ShiftPlanningService
from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
from uk_management_bot.services.shift_transfer_service import ShiftTransferService
from uk_management_bot.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class ShiftScheduler:
    """Планировщик задач для автоматизации работы с сменами"""

    def __init__(self, notification_service: Optional[NotificationService] = None):
        self.scheduler = AsyncIOScheduler()
        self.notification_service = notification_service
        self.is_running = False

        # Статистика выполнения задач
        self.task_stats = {
            'auto_create_shifts': {'success': 0, 'failed': 0, 'last_run': None},
            'rebalance_assignments': {'success': 0, 'failed': 0, 'last_run': None},
            'process_transfers': {'success': 0, 'failed': 0, 'last_run': None},
            'cleanup_expired': {'success': 0, 'failed': 0, 'last_run': None},
            'notify_upcoming': {'success': 0, 'failed': 0, 'last_run': None},
            'auto_assign_requests': {'success': 0, 'failed': 0, 'last_run': None},
            'sync_assignments': {'success': 0, 'failed': 0, 'last_run': None}
        }

    def setup_jobs(self):
        """Настройка всех задач планировщика"""
        try:
            # 1. Автоматическое создание смен (каждый день в 00:30)
            self.scheduler.add_job(
                self._auto_create_shifts,
                CronTrigger(hour=0, minute=30),
                id='auto_create_shifts',
                name='Автоматическое создание смен',
                max_instances=1,
                coalesce=True
            )

            # 2. Перебалансировка назначений (каждый день в 06:00)
            self.scheduler.add_job(
                self._rebalance_daily_assignments,
                CronTrigger(hour=6, minute=0),
                id='rebalance_assignments',
                name='Перебалансировка назначений',
                max_instances=1,
                coalesce=True
            )

            # 3. Обработка истекших передач (каждые 2 часа)
            self.scheduler.add_job(
                self._process_expired_transfers,
                IntervalTrigger(hours=2),
                id='process_transfers',
                name='Обработка истекших передач',
                max_instances=1,
                coalesce=True
            )

            # 4. Очистка устаревших данных (каждую неделю в воскресенье в 02:00)
            self.scheduler.add_job(
                self._cleanup_expired_data,
                CronTrigger(day_of_week=6, hour=2, minute=0),
                id='cleanup_expired',
                name='Очистка устаревших данных',
                max_instances=1,
                coalesce=True
            )

            # 5. Уведомления о предстоящих сменах (каждые 30 минут с 08:00 до 20:00)
            self.scheduler.add_job(
                self._notify_upcoming_shifts,
                CronTrigger(hour='8-20', minute='0,30'),
                id='notify_upcoming',
                name='Уведомления о предстоящих сменах',
                max_instances=1,
                coalesce=True
            )

            # 6. Автоназначение исполнителей на незаполненные смены (каждые 15 минут)
            self.scheduler.add_job(
                self._auto_assign_empty_shifts,
                IntervalTrigger(minutes=15),
                id='auto_assign_empty',
                name='Автоназначение на пустые смены',
                max_instances=1,
                coalesce=True
            )

            # 8. Автоназначение заявок исполнителям смен (каждые 10 минут)
            self.scheduler.add_job(
                self._auto_assign_requests_to_executors,
                IntervalTrigger(minutes=10),
                id='auto_assign_requests',
                name='Автоназначение заявок исполнителям',
                max_instances=1,
                coalesce=True
            )

            # 9. Синхронизация назначений заявок со сменами (каждые 30 минут)
            self.scheduler.add_job(
                self._sync_request_assignments,
                IntervalTrigger(minutes=30),
                id='sync_assignments',
                name='Синхронизация назначений со сменами',
                max_instances=1,
                coalesce=True
            )

            # 7. Еженедельное планирование (понедельник в 08:00)
            self.scheduler.add_job(
                self._weekly_planning,
                CronTrigger(day_of_week=0, hour=8, minute=0),
                id='weekly_planning',
                name='Еженедельное планирование',
                max_instances=1,
                coalesce=True
            )

            logger.info("Задачи планировщика смен настроены успешно")

        except Exception as e:
            logger.error(f"Ошибка настройки задач планировщика: {e}")

    async def start(self):
        """Запуск планировщика"""
        try:
            if not self.is_running:
                self.setup_jobs()
                self.scheduler.start()
                self.is_running = True
                logger.info("Планировщик смен запущен")

                # Отправляем уведомление о запуске
                if self.notification_service:
                    await self.notification_service.send_system_notification(
                        "🤖 Планировщик смен запущен",
                        "Автоматическое управление сменами активировано"
                    )

        except Exception as e:
            logger.error(f"Ошибка запуска планировщика: {e}")

    async def stop(self):
        """Остановка планировщика"""
        try:
            if self.is_running:
                self.scheduler.shutdown()
                self.is_running = False
                logger.info("Планировщик смен остановлен")

        except Exception as e:
            logger.error(f"Ошибка остановки планировщика: {e}")

    async def get_status(self) -> Dict[str, Any]:
        """Получить статус планировщика"""
        jobs_info = []

        if self.is_running:
            for job in self.scheduler.get_jobs():
                jobs_info.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                    'trigger': str(job.trigger)
                })

        return {
            'is_running': self.is_running,
            'jobs_count': len(jobs_info),
            'jobs': jobs_info,
            'stats': self.task_stats
        }

    async def _auto_create_shifts(self):
        """Автоматическое создание смен на ближайшие дни"""
        task_name = 'auto_create_shifts'
        try:
            logger.info("Запуск автосоздания смен...")

            db = SessionLocal()
            try:
                planning_service = ShiftPlanningService(db)

                # Создаем смены на следующие 7 дней
                result = planning_service.auto_create_shifts(days_ahead=7)

                self.task_stats[task_name]['success'] += 1
                self.task_stats[task_name]['last_run'] = datetime.now()

                logger.info(f"Автосоздание смен завершено: {result['total_created']} смен создано")

                # Отправляем уведомление если создано много смен
                if self.notification_service and result['total_created'] > 10:
                    await self.notification_service.send_manager_notification(
                        "🏗️ Автосоздание смен завершено",
                        f"Создано {result['total_created']} новых смен на ближайшие 7 дней"
                    )
            finally:
                db.close()

        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = datetime.now()
            logger.error(f"Ошибка автосоздания смен: {e}")

    async def _rebalance_daily_assignments(self):
        """Ежедневная перебалансировка назначений"""
        task_name = 'rebalance_assignments'
        try:
            logger.info("Запуск перебалансировки назначений...")

            db = SessionLocal()
            try:
                planning_service = ShiftPlanningService(db)

                # Перебалансируем назначения на сегодня и завтра
                today = date.today()
                tomorrow = today + timedelta(days=1)

                results = []
                for target_date in [today, tomorrow]:
                    result = planning_service.rebalance_daily_assignments(target_date)
                    results.append(result)

                self.task_stats[task_name]['success'] += 1
                self.task_stats[task_name]['last_run'] = datetime.now()

                total_rebalanced = sum(r.get('rebalanced_shifts', 0) for r in results)
                logger.info(f"Перебалансировка завершена: {total_rebalanced} назначений изменено")
            finally:
                db.close()

        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = datetime.now()
            logger.error(f"Ошибка перебалансировки назначений: {e}")

    async def _process_expired_transfers(self):
        """Обработка истекших передач смен"""
        task_name = 'process_transfers'
        try:
            logger.info("Обработка истекших передач...")

            db = SessionLocal()
            try:
                transfer_service = ShiftTransferService(db)

                # Обрабатываем передачи старше 24 часов без ответа
                result = await transfer_service.process_expired_transfers(hours_threshold=24)

                self.task_stats[task_name]['success'] += 1
                self.task_stats[task_name]['last_run'] = datetime.now()

                if result['processed_count'] > 0:
                    logger.info(f"Обработано {result['processed_count']} истекших передач")

                    # Уведомляем менеджеров
                    if self.notification_service:
                        await self.notification_service.send_manager_notification(
                            "⏰ Обработка истекших передач",
                            f"Автоматически обработано {result['processed_count']} передач"
                        )
            finally:
                db.close()

        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = datetime.now()
            logger.error(f"Ошибка обработки истекших передач: {e}")

    async def _cleanup_expired_data(self):
        """Очистка устаревших данных"""
        task_name = 'cleanup_expired'
        try:
            logger.info("Запуск очистки устаревших данных...")

            db = SessionLocal()
            try:
                # Удаляем завершенные передачи старше 30 дней
                cutoff_date = datetime.now() - timedelta(days=30)

                from uk_management_bot.database.models.shift_transfer import ShiftTransfer
                expired_transfers = db.query(ShiftTransfer).filter(
                    ShiftTransfer.status.in_(['completed', 'cancelled']),
                    ShiftTransfer.completed_at < cutoff_date
                ).count()

                # Удаляем (или помечаем как архивные)
                db.query(ShiftTransfer).filter(
                    ShiftTransfer.status.in_(['completed', 'cancelled']),
                    ShiftTransfer.completed_at < cutoff_date
                ).delete()

                db.commit()

                self.task_stats[task_name]['success'] += 1
                self.task_stats[task_name]['last_run'] = datetime.now()

                logger.info(f"Очистка завершена: удалено {expired_transfers} записей передач")
            finally:
                db.close()

        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = datetime.now()
            logger.error(f"Ошибка очистки данных: {e}")

    async def _notify_upcoming_shifts(self):
        """Уведомления о предстоящих сменах"""
        task_name = 'notify_upcoming'
        try:
            if not self.notification_service:
                return

            db = SessionLocal()
            try:
                from uk_management_bot.database.models.shift import Shift
                from uk_management_bot.database.models.user import User

                # Ищем смены, которые начинаются в течение следующих 2 часов
                now = datetime.now()
                upcoming_threshold = now + timedelta(hours=2)

                upcoming_shifts = db.query(Shift).join(User).filter(
                    Shift.start_time.between(now, upcoming_threshold),
                    Shift.status == 'planned',
                    Shift.user_id.isnot(None)
                ).all()

                notifications_sent = 0
                for shift in upcoming_shifts:
                    try:
                        time_until = shift.start_time - now
                        hours = int(time_until.total_seconds() / 3600)
                        minutes = int((time_until.total_seconds() % 3600) / 60)

                        await self.notification_service.send_shift_reminder(
                            executor_id=shift.user_id,
                            shift=shift,
                            time_until=f"{hours}ч {minutes}м"
                        )
                        notifications_sent += 1

                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления для смены {shift.id}: {e}")

                self.task_stats[task_name]['success'] += 1
                self.task_stats[task_name]['last_run'] = datetime.now()

                if notifications_sent > 0:
                    logger.info(f"Отправлено {notifications_sent} уведомлений о предстоящих сменах")
            finally:
                db.close()

        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = datetime.now()
            logger.error(f"Ошибка отправки уведомлений: {e}")

    async def _auto_assign_empty_shifts(self):
        """Автоназначение исполнителей на пустые смены"""
        try:
            db = SessionLocal()
            try:
                from uk_management_bot.database.models.shift import Shift

                # Ищем смены без исполнителей, которые начинаются в течение 48 часов
                now = datetime.now()
                assignment_threshold = now + timedelta(hours=48)

                empty_shifts = db.query(Shift).filter(
                    Shift.user_id.is_(None),
                    Shift.status == 'planned',
                    Shift.start_time.between(now, assignment_threshold)
                ).limit(10).all()  # Ограничиваем количество для производительности

                if empty_shifts:
                    assignment_service = ShiftAssignmentService(db)
                    result = assignment_service.auto_assign_executors_to_shifts(
                        shifts=empty_shifts,
                        force_reassign=False
                    )

                    if result['stats']['assigned'] > 0:
                        logger.info(f"Автоназначено {result['stats']['assigned']} исполнителей на пустые смены")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Ошибка автоназначения на пустые смены: {e}")

    async def _weekly_planning(self):
        """Еженедельное планирование смен"""
        try:
            logger.info("Запуск еженедельного планирования...")

            db = SessionLocal()
            try:
                planning_service = ShiftPlanningService(db)

                # Планируем следующую неделю
                next_monday = date.today() + timedelta(days=7 - date.today().weekday())
                result = planning_service.plan_weekly_schedule(next_monday)

                logger.info(f"Еженедельное планирование завершено: {result['statistics']['total_shifts']} смен запланировано")

                # Уведомляем менеджеров о результатах планирования
                if self.notification_service and result['statistics']['total_shifts'] > 0:
                    await self.notification_service.send_manager_notification(
                        "📅 Еженедельное планирование",
                        f"Запланировано {result['statistics']['total_shifts']} смен на следующую неделю"
                    )
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Ошибка еженедельного планирования: {e}")

    async def _auto_assign_requests_to_executors(self):
        """Автоматическое назначение заявок исполнителям смен"""
        task_name = 'auto_assign_requests'
        try:
            logger.info("Запуск автоназначения заявок исполнителям...")

            db = SessionLocal()
            try:
                assignment_service = ShiftAssignmentService(db)

                # Назначаем заявки на сегодня и завтра
                today = date.today()
                tomorrow = today + timedelta(days=1)

                total_assigned = 0
                for target_date in [today, tomorrow]:
                    result = assignment_service.auto_assign_requests_to_shift_executors(target_date)

                    if result['status'] == 'success':
                        total_assigned += result.get('assigned_requests', 0)

                self.task_stats[task_name]['success'] += 1
                self.task_stats[task_name]['last_run'] = datetime.now()

                if total_assigned > 0:
                    logger.info(f"Автоназначение заявок завершено: {total_assigned} заявок назначено")

                    # Уведомляем менеджеров о значительных назначениях
                    if self.notification_service and total_assigned > 5:
                        await self.notification_service.send_manager_notification(
                            "📋 Автоназначение заявок",
                            f"Автоматически назначено {total_assigned} заявок исполнителям смен"
                        )
            finally:
                db.close()

        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = datetime.now()
            logger.error(f"Ошибка автоназначения заявок: {e}")

    async def _sync_request_assignments(self):
        """Синхронизация назначений заявок со сменами"""
        task_name = 'sync_assignments'
        try:
            logger.info("Запуск синхронизации назначений...")

            db = SessionLocal()
            try:
                assignment_service = ShiftAssignmentService(db)

                # Синхронизируем на сегодня и завтра
                today = date.today()
                tomorrow = today + timedelta(days=1)

                total_reassigned = 0
                for target_date in [today, tomorrow]:
                    result = assignment_service.sync_request_assignments_with_shifts(target_date)

                    if result['status'] == 'success':
                        total_reassigned += result.get('reassigned', 0)

                self.task_stats[task_name]['success'] += 1
                self.task_stats[task_name]['last_run'] = datetime.now()

                if total_reassigned > 0:
                    logger.info(f"Синхронизация завершена: {total_reassigned} переназначений")

                    # Уведомляем менеджеров о переназначениях
                    if self.notification_service and total_reassigned > 0:
                        await self.notification_service.send_manager_notification(
                            "🔄 Синхронизация назначений",
                            f"Переназначено {total_reassigned} заявок в соответствии со сменами"
                        )
            finally:
                db.close()

        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = datetime.now()
            logger.error(f"Ошибка синхронизации назначений: {e}")


# Глобальный экземпляр планировщика
_scheduler_instance: Optional[ShiftScheduler] = None


def get_scheduler() -> ShiftScheduler:
    """Получить глобальный экземпляр планировщика"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = ShiftScheduler()
    return _scheduler_instance


async def start_scheduler(notification_service: Optional[NotificationService] = None):
    """Запустить планировщик смен"""
    scheduler = get_scheduler()
    if notification_service:
        scheduler.notification_service = notification_service
    await scheduler.start()


async def stop_scheduler():
    """Остановить планировщик смен"""
    scheduler = get_scheduler()
    await scheduler.stop()


async def get_scheduler_status() -> Dict[str, Any]:
    """Получить статус планировщика"""
    scheduler = get_scheduler()
    return await scheduler.get_status()