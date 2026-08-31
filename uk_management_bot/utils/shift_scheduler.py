"""
Планировщик задач для системы смен - автоматическое выполнение фоновых операций
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone

from uk_management_bot.utils.business_time import business_today
from typing import Optional, Dict, Any, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from uk_management_bot.database.session import SessionLocal
from uk_management_bot.services.auto_manager.orchestrator import AutoManagerOrchestrator
from uk_management_bot.services.shift_planning_service import ShiftPlanningService
from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
from uk_management_bot.services.shift_transfer_service import ShiftTransferService
from uk_management_bot.services.notification_service import NotificationService
from uk_management_bot.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ShiftReminder:
    """Готовое напоминание — плоские значения, без ORM-объектов.

    Из рабочего потока наружу отдаём только такие DTO: ORM-объект пережил бы
    `close()` своей сессии лишь до первого обращения к незагруженному полю, и
    падение вылезло бы уже в сетевой фазе, далеко от причины.
    """
    executor_id: int
    start_time: datetime
    time_until: str


class ShiftScheduler:
    """Планировщик задач для автоматизации работы с сменами"""

    def __init__(self, notification_service: Optional[NotificationService] = None, bot=None):
        self.scheduler = AsyncIOScheduler()
        # Инжектируемый сервис (тестовый seam). В проде остаётся None, а
        # уведомления строятся per-job на свежей сессии через self._notifier().
        self.notification_service = notification_service
        self._bot = bot
        self.is_running = False

        # Единственный экземпляр на процесс — держит между tick-ами
        # анти-starvation курсоры/cooldown/дедуп уведомлений (Task 6).
        self._auto_manager = AutoManagerOrchestrator(bot=bot, notification_service=notification_service)

        # Статистика выполнения задач
        self.task_stats = {
            'activate_scheduled': {'success': 0, 'failed': 0, 'last_run': None},
            'auto_create_shifts': {'success': 0, 'failed': 0, 'last_run': None},
            'rebalance_assignments': {'success': 0, 'failed': 0, 'last_run': None},
            'process_transfers': {'success': 0, 'failed': 0, 'last_run': None},
            'cleanup_expired': {'success': 0, 'failed': 0, 'last_run': None},
            'notify_upcoming': {'success': 0, 'failed': 0, 'last_run': None},
            'work_reports_sync': {'success': 0, 'failed': 0, 'last_run': None}
        }

    @property
    def _notifications_enabled(self) -> bool:
        """Уведомления включены, если инжектирован сервис (тесты) или задан бот (прод)."""
        return self.notification_service is not None or self._bot is not None

    def _notifier(self, db) -> NotificationService:
        """Вернуть инжектированный сервис (тесты) либо построить свежий per-job
        сервис на сессии job'а + едином диспетчерском боте (COD-02)."""
        if self.notification_service is not None:
            return self.notification_service
        return NotificationService(db, bot=self._bot)

    async def _notify_managers(self, title: str, body: str) -> None:
        """Сетевая фаза job'а: ПОСЛЕ db-фазы и на СВОЕЙ короткой сессии.

        Сессия рабочего потока сюда не приезжает намеренно (AUD5-CODE-5):
        `Session` не рассчитана на использование из двух потоков, а «открыли в
        потоке — дописали в event loop» выглядит именно так. Оставшийся здесь
        sync-запрос один и маленький (telegram_id менеджеров) — на фоне
        пакетов планирования он не считается.
        """
        if not self._notifications_enabled:
            return
        if self.notification_service is not None:
            await self.notification_service.send_manager_notification(title, body)
            return
        db = SessionLocal()
        try:
            await NotificationService(db, bot=self._bot).send_manager_notification(title, body)
        finally:
            db.close()

    def setup_jobs(self):
        """Настройка всех задач планировщика"""
        try:
            # 0. Жизненный цикл смен по РАСПИСАНИЮ (решение владельца 2026-08-24):
            #    planned с исполнителем в наступившем окне → active;
            #    active с истёкшим end_time → completed. Без этой джобы
            #    расписание было декоративным: все потребители «кто на смене»
            #    (_on_shift_filter, select_executor, профиль) требуют active,
            #    а planned→active не переводил никто — сотрудники из
            #    расписания не получали заявок («в профиле без смены»).
            self.scheduler.add_job(
                self._activate_scheduled_shifts,
                IntervalTrigger(minutes=3),
                id='activate_scheduled',
                name='Активация смен по расписанию',
                max_instances=1,
                coalesce=True
            )

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

            # 5. Уведомления о предстоящих сменах — круглосуточно каждые 30 мин.
            #    Раньше стоял CronTrigger(hour='8-20') — планировщик живёт в UTC
            #    контейнера, так что это было 13:00–01:30 по Ташкенту, и окно
            #    «за ≤2 часа до начала» утренних смен (старт 08:00–09:00
            #    местного = 03:00–04:00 UTC) не попадало в график НИКОГДА —
            #    утренние напоминания не отправлялись (SHIFTS.md, находка №2).
            #    Когда есть что слать — решает сам фильтр «смены в ближайшие
            #    2 часа»: ночью смен нет — джоба молчит сама.
            self.scheduler.add_job(
                self._notify_upcoming_shifts,
                IntervalTrigger(minutes=30),
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

            # Джобы №8 (автоназначение заявок исполнителям) и №9 (синхронизация
            # назначений со сменами) ретайрены — BUG-148: их путь
            # (RequestAssignmentEngine → smart_assign_request → SmartDispatcher)
            # был мёртв с рождения и всегда отчитывался failed. Реальное
            # авто-назначение — auto_manager_tick ниже.

            # 10. Автоматический менеджер — назначение дежурных на ночные заявки (каждые 2 минуты)
            self.scheduler.add_job(
                self._auto_manager_tick,
                IntervalTrigger(minutes=2),
                id='auto_manager_tick',
                name='Автоматический менеджер — назначение дежурных',
                max_instances=1,
                coalesce=True
            )

            # 11. Визуальные отчёты «до/после» — автопост/автопубликация/отзыв
            #     (каждые 10 минут). Без этой задачи тумблер «Автопост» ничего
            #     не автоматизировал: черновики создавались только когда
            #     менеджер вручную жал «Синхронизировать» на своей странице, а
            #     отзыв возвращённых заявок — только когда кто-то открывал
            #     публичную витрину.
            self.scheduler.add_job(
                self._work_reports_tick,
                IntervalTrigger(minutes=10),
                id='work_reports_sync',
                name='Отчёты о работах — автопост и автопубликация',
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

                # Отправляем уведомление о запуске (короткоживущая сессия)
                if self._notifications_enabled:
                    from uk_management_bot.database.session import session_scope
                    with session_scope() as db:
                        await self._notifier(db).send_system_notification(
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

    def _auto_create_shifts_sync(self) -> int:
        """DB-фаза целиком в рабочем потоке: сессия и создаётся, и закрывается тут."""
        db = SessionLocal()
        try:
            result = ShiftPlanningService(db).auto_create_shifts(days_ahead=7)
            return int(result['total_created'])
        finally:
            db.close()

    async def _auto_create_shifts(self):
        """Автоматическое создание смен на ближайшие дни"""
        task_name = 'auto_create_shifts'
        try:
            logger.info("Запуск автосоздания смен...")

            total_created = await asyncio.to_thread(self._auto_create_shifts_sync)

            self.task_stats[task_name]['success'] += 1
            self.task_stats[task_name]['last_run'] = utc_now()

            logger.info(f"Автосоздание смен завершено: {total_created} смен создано")

            # Отправляем уведомление если создано много смен
            if total_created > 10:
                await self._notify_managers(
                    "🏗️ Автосоздание смен завершено",
                    f"Создано {total_created} новых смен на ближайшие 7 дней"
                )

        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = utc_now()
            logger.error(f"Ошибка автосоздания смен: {e}")

    def _rebalance_daily_assignments_sync(self) -> int:
        db = SessionLocal()
        try:
            planning_service = ShiftPlanningService(db)

            # Перебалансируем назначения на сегодня и завтра (бизнес-день:
            # date.today() в UTC-контейнере с 19:00Z кормил бы движки
            # вчерашним «сегодня» — ARCH-135(б))
            today = business_today()
            tomorrow = today + timedelta(days=1)

            results = [
                planning_service.rebalance_daily_assignments(target_date)
                for target_date in (today, tomorrow)
            ]
            return sum(r.get('rebalanced_shifts', 0) for r in results)
        finally:
            db.close()

    async def _rebalance_daily_assignments(self):
        """Ежедневная перебалансировка назначений"""
        task_name = 'rebalance_assignments'
        try:
            logger.info("Запуск перебалансировки назначений...")

            total_rebalanced = await asyncio.to_thread(self._rebalance_daily_assignments_sync)

            self.task_stats[task_name]['success'] += 1
            self.task_stats[task_name]['last_run'] = utc_now()

            logger.info(f"Перебалансировка завершена: {total_rebalanced} назначений изменено")

        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = utc_now()
            logger.error(f"Ошибка перебалансировки назначений: {e}")

    async def _process_expired_transfers(self):
        """Обработка истекших передач смен.

        Единственный job, оставшийся на event loop: `process_expired_transfers`
        — async-метод сервиса, он сам чередует db-фазу и рассылку (BUG-BOT-036:
        уведомления строго после commit). Затолкать его в поток нельзя, а
        разделять публичный контракт сервиса — задача другого пункта. Запрос
        здесь один и по узкому окну (pending/assigned старше 24 ч), в отличие от
        пакетов планирования.
        """
        task_name = 'process_transfers'
        try:
            logger.info("Обработка истекших передач...")

            db = SessionLocal()
            try:
                transfer_service = ShiftTransferService(db)

                # Обрабатываем передачи старше 24 часов без ответа
                result = await transfer_service.process_expired_transfers(hours_threshold=24)

                self.task_stats[task_name]['success'] += 1
                self.task_stats[task_name]['last_run'] = utc_now()

                processed = result['processed_count']
            finally:
                db.close()

            if processed > 0:
                logger.info(f"Обработано {processed} истекших передач")
                await self._notify_managers(
                    "⏰ Обработка истекших передач",
                    f"Автоматически обработано {processed} передач"
                )

        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = utc_now()
            logger.error(f"Ошибка обработки истекших передач: {e}")

    def _cleanup_expired_data_sync(self) -> int:
        db = SessionLocal()
        try:
            # Удаляем завершенные передачи старше 30 дней
            cutoff_date = utc_now() - timedelta(days=30)

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
            return expired_transfers
        finally:
            db.close()

    async def _cleanup_expired_data(self):
        """Очистка устаревших данных"""
        task_name = 'cleanup_expired'
        try:
            logger.info("Запуск очистки устаревших данных...")

            expired_transfers = await asyncio.to_thread(self._cleanup_expired_data_sync)

            self.task_stats[task_name]['success'] += 1
            self.task_stats[task_name]['last_run'] = utc_now()

            logger.info(f"Очистка завершена: удалено {expired_transfers} записей передач")

        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = utc_now()
            logger.error(f"Ошибка очистки данных: {e}")

    def _collect_upcoming_reminders(self) -> List[_ShiftReminder]:
        """DB-фаза: подобрать смены и СРАЗУ свернуть их в плоские DTO."""
        db = SessionLocal()
        try:
            from uk_management_bot.database.models.shift import Shift
            from uk_management_bot.database.models.user import User

            # Срез [now+90м, now+120м): при 30-минутном тике каждая смена
            # попадает РОВНО в один тик — одно напоминание, за ~2 часа до
            # начала. Раньше бралось всё окно [now, now+2ч] — та же смена
            # напоминалась каждые 30 минут, до пяти раз подряд; с переводом
            # джобы на круглосуточный тик (находка №2) этот спам стал бы
            # ежеутренним. Границы полуинтервала намеренно: inclusive снизу,
            # exclusive сверху — соседние тики не пересекаются.
            # QA-04: tz-aware now — Shift.start_time это timestamptz; naive
            # now ронял `shift.start_time - now` ("can't subtract offset-naive
            # and offset-aware datetimes") → уведомления не уходили.
            now = utc_now()
            slice_start = now + timedelta(minutes=90)
            slice_end = now + timedelta(minutes=120)

            upcoming_shifts = db.query(Shift).join(User).filter(
                Shift.start_time >= slice_start,
                Shift.start_time < slice_end,
                Shift.status == 'planned',
                Shift.user_id.isnot(None)
            ).all()

            reminders = []
            for shift in upcoming_shifts:
                # Канон business_time: naive из БД трактуется как UTC (sqlite
                # в тест-харнессе отдаёт timestamptz без tzinfo; Postgres — с).
                start = shift.start_time if shift.start_time.tzinfo \
                    else shift.start_time.replace(tzinfo=dt_timezone.utc)
                left = start - now
                hours = int(left.total_seconds() / 3600)
                minutes = int((left.total_seconds() % 3600) / 60)
                reminders.append(_ShiftReminder(
                    executor_id=shift.user_id,
                    start_time=start,
                    time_until=f"{hours}ч {minutes}м",
                ))
            return reminders
        finally:
            db.close()

    async def _notify_upcoming_shifts(self):
        """Уведомления о предстоящих сменах"""
        task_name = 'notify_upcoming'
        try:
            if not self._notifications_enabled:
                return

            reminders = await asyncio.to_thread(self._collect_upcoming_reminders)

            notifications_sent = 0
            if reminders:
                db = None if self.notification_service is not None else SessionLocal()
                notifier = self._notifier(db)
                try:
                    for reminder in reminders:
                        try:
                            # Сервис читает у `shift` только `start_time`, поэтому
                            # сюда уходит DTO, а не ORM-объект закрытой сессии.
                            await notifier.send_shift_reminder(
                                executor_id=reminder.executor_id,
                                shift=reminder,
                                time_until=reminder.time_until,
                            )
                            notifications_sent += 1
                        except Exception as e:
                            logger.error(
                                f"Ошибка отправки уведомления исполнителю "
                                f"{reminder.executor_id}: {e}"
                            )
                finally:
                    if db is not None:
                        db.close()

            self.task_stats[task_name]['success'] += 1
            self.task_stats[task_name]['last_run'] = utc_now()

            if notifications_sent > 0:
                logger.info(f"Отправлено {notifications_sent} уведомлений о предстоящих сменах")

        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = utc_now()
            logger.error(f"Ошибка отправки уведомлений: {e}")

    def _activate_scheduled_shifts_sync(self) -> tuple:
        """DB-фаза активации по расписанию. Идемпотентные bulk-update'ы:

        - planned + есть исполнитель + окно наступило → active. Смены без
          исполнителя не активируются (нечего активировать — их заполняет
          автоназначение), у planned end_time задан всегда (NULL > now = NULL
          отфильтрует сам SQL).
        - active + end_time истёк → completed. Ad-hoc смены («Начать смену»
          без расписания) имеют end_time NULL и НЕ трогаются — их завершает
          человек кнопкой, как раньше.
        """
        db = SessionLocal()
        try:
            from uk_management_bot.database.models.shift import Shift

            now = utc_now()
            activated = (
                db.query(Shift)
                .filter(
                    Shift.status == 'planned',
                    Shift.user_id.isnot(None),
                    Shift.start_time <= now,
                    Shift.end_time > now,
                )
                .update({Shift.status: 'active'}, synchronize_session=False)
            )
            completed = (
                db.query(Shift)
                .filter(
                    Shift.status == 'active',
                    Shift.end_time.isnot(None),
                    Shift.end_time <= now,
                )
                .update({Shift.status: 'completed'}, synchronize_session=False)
            )
            db.commit()
            return activated, completed
        finally:
            db.close()

    async def _activate_scheduled_shifts(self):
        """Активация смен по расписанию (см. setup_jobs, джоба №0)."""
        task_name = 'activate_scheduled'
        try:
            activated, completed = await asyncio.to_thread(
                self._activate_scheduled_shifts_sync
            )
            self.task_stats[task_name]['success'] += 1
            self.task_stats[task_name]['last_run'] = utc_now()
            if activated or completed:
                logger.info(
                    "Смены по расписанию: активировано %s, завершено %s",
                    activated, completed,
                )
        except Exception as e:
            self.task_stats[task_name]['failed'] += 1
            self.task_stats[task_name]['last_run'] = utc_now()
            logger.error(f"Ошибка активации смен по расписанию: {e}")

    def _auto_assign_empty_shifts_sync(self) -> int:
        db = SessionLocal()
        try:
            from uk_management_bot.database.models.shift import Shift

            # Ищем смены без исполнителей, которые начинаются в течение 48 часов
            # AUD5-CODE-3: Shift.start_time — timestamptz; naive now мис-сравнивался.
            now = utc_now()
            assignment_threshold = now + timedelta(hours=48)

            empty_shifts = db.query(Shift).filter(
                Shift.user_id.is_(None),
                Shift.status == 'planned',
                Shift.start_time.between(now, assignment_threshold)
            ).limit(10).all()  # Ограничиваем количество для производительности

            if not empty_shifts:
                return 0

            result = ShiftAssignmentService(db).auto_assign_executors_to_shifts(
                shifts=empty_shifts,
                force_reassign=False
            )
            # Ключа 'stats' в ответе сервиса не существует ни в одной ветке —
            # старое чтение result['stats']['assigned'] валило каждый непустой
            # тик KeyError'ом и теряло счётчик (SHIFTS.md, находка №3; тот же
            # класс, что BUG-184).
            return int(result.get('successful_assignments', 0))
        finally:
            db.close()

    async def _auto_assign_empty_shifts(self):
        """Автоназначение исполнителей на пустые смены"""
        try:
            assigned = await asyncio.to_thread(self._auto_assign_empty_shifts_sync)
            if assigned > 0:
                logger.info(f"Автоназначено {assigned} исполнителей на пустые смены")

        except Exception as e:
            logger.error(f"Ошибка автоназначения на пустые смены: {e}")

    def _weekly_planning_sync(self) -> int:
        db = SessionLocal()
        try:
            # Планируем следующую неделю (от бизнес-«сегодня»)
            next_monday = business_today() + timedelta(days=7 - business_today().weekday())
            result = ShiftPlanningService(db).plan_weekly_schedule(next_monday)
            return int(result['statistics']['total_shifts'])
        finally:
            db.close()

    async def _weekly_planning(self):
        """Еженедельное планирование смен"""
        try:
            logger.info("Запуск еженедельного планирования...")

            total_shifts = await asyncio.to_thread(self._weekly_planning_sync)

            logger.info(f"Еженедельное планирование завершено: {total_shifts} смен запланировано")

            # Уведомляем менеджеров о результатах планирования
            if total_shifts > 0:
                await self._notify_managers(
                    "📅 Еженедельное планирование",
                    f"Запланировано {total_shifts} смен на следующую неделю"
                )

        except Exception as e:
            logger.error(f"Ошибка еженедельного планирования: {e}")

    async def _auto_manager_tick(self):
        """Тик автоматического менеджера — назначение дежурных на ночные заявки.

        `AutoManagerOrchestrator.run_once()` управляет собственной сессией
        (`SessionLocal()`) внутри себя, поэтому здесь own db-сессия не нужна.
        """
        try:
            await self._auto_manager.run_once()
        except Exception as e:
            logger.error(f"Ошибка тика автоматического менеджера: {e}")

    async def _work_reports_tick(self):
        """Тик визуальных отчётов «до/после».

        Делает то же, что `POST /api/v2/work-reports/sync`, но без человека:
        наполняет очередь черновиками, публикует готовые (если включена
        автопубликация) и снимает публикации с заявок, переставших
        удовлетворять предикату. До появления этой задачи «Автопост» ничего не
        автоматизировал — черновик создавался только по нажатию кнопки
        менеджером, а отзыв срабатывал лишь на промахе кэша публичной ленты.

        ⚠️ С включённым `autopublish` фотографии жителей уезжают в открытую
        ленту без просмотра человеком. Анонимизируется только адрес (дом/двор
        без квартиры); что попало в кадр — код не проверяет. Режим включён
        владельцем осознанно (решение 2026-07-25).

        Фазы изолированы друг от друга: сбой одной не должен отменять
        остальные — они независимы, а media-service нужен только двум из них.
        Здесь своя async-сессия: сервис-функции work_report_service асинхронные,
        в отличие от остальных задач планировщика на `SessionLocal`.
        """
        from uk_management_bot.config.settings import settings
        if not settings.WORK_REPORTS_ENABLED:
            return

        from uk_management_bot.database.session import AsyncSessionLocal
        if AsyncSessionLocal is None:
            # SQLite dev-режим — async-движка нет (см. database/session.py).
            logger.debug("Отчёты о работах: async-сессия недоступна, тик пропущен")
            return

        from uk_management_bot.integrations import get_media_client
        from uk_management_bot.services import work_report_service

        task_name = 'work_reports_sync'
        media_client = get_media_client()
        summary: Dict[str, Any] = {}
        failed = False

        async with AsyncSessionLocal() as db:
            try:
                summary['sync'] = await work_report_service.sync_pending_drafts(db)
            except Exception as e:
                failed = True
                logger.error(f"Отчёты о работах: синк черновиков не прошёл: {e}")
                await db.rollback()

            if media_client is not None:
                try:
                    summary['autopublish'] = await work_report_service.autopublish_ready_drafts(
                        db, media_client, triggered_by=None
                    )
                except Exception as e:
                    failed = True
                    logger.error(f"Отчёты о работах: автопубликация не прошла: {e}")
                    await db.rollback()

            try:
                summary['revoked'] = await work_report_service.revoke_stale_publications(db)
            except Exception as e:
                failed = True
                logger.error(f"Отчёты о работах: отзыв устаревших публикаций не прошёл: {e}")
                await db.rollback()

            if media_client is not None:
                try:
                    # Догрев превью — страховка к прогреву в publish_report:
                    # покрывает отчёты, опубликованные при недоступном
                    # media-service, и кэш, вытесненный лимитом или рестартом.
                    summary['warmed'] = await work_report_service.warm_recent_previews(
                        db, media_client
                    )
                except Exception as e:
                    logger.warning(f"Отчёты о работах: догрев превью не прошёл: {e}")

                try:
                    summary['reconcile'] = await work_report_service.reconcile_publication_locks(
                        db, media_client
                    )
                except Exception as e:
                    # Сверка локов — фоновая гигиена, её сбой не должен
                    # окрашивать тик в failed: полезная работа выше уже сделана.
                    logger.warning(f"Отчёты о работах: сверка локов не прошла: {e}")
                    await db.rollback()

        created = (summary.get('sync') or {}).get('created', 0)
        published = (summary.get('autopublish') or {}).get('published', 0)
        revoked = summary.get('revoked', 0)
        if created or published or revoked:
            logger.info(
                "Отчёты о работах: создано %s, опубликовано %s, снято %s",
                created, published, revoked,
            )

        self.task_stats[task_name]['failed' if failed else 'success'] += 1
        self.task_stats[task_name]['last_run'] = utc_now()


# Глобальный экземпляр планировщика
_scheduler_instance: Optional[ShiftScheduler] = None


def get_scheduler() -> ShiftScheduler:
    """Получить глобальный экземпляр планировщика"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = ShiftScheduler()
    return _scheduler_instance


async def start_scheduler(notification_service: Optional[NotificationService] = None, bot=None):
    """Запустить планировщик смен.

    Прод передаёт ``bot`` (единый диспетчерский) — уведомления строятся per-job.
    ``notification_service`` сохранён для инъекции в тестах (backward-compat).
    """
    scheduler = get_scheduler()
    if notification_service is not None:
        scheduler.notification_service = notification_service
    if bot is not None:
        scheduler._bot = bot
    await scheduler.start()


async def stop_scheduler():
    """Остановить планировщик смен"""
    scheduler = get_scheduler()
    await scheduler.stop()


async def get_scheduler_status() -> Dict[str, Any]:
    """Получить статус планировщика"""
    scheduler = get_scheduler()
    return await scheduler.get_status()