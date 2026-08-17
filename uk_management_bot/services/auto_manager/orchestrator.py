"""Auto-manager orchestrator — авто-назначение ночных заявок дежурным.

`AutoManagerOrchestrator` — один экземпляр на процесс (создаётся в
`ShiftScheduler.__init__`, PR-задача 6 — здесь НЕ подключается): держит
между tick-ами анти-starvation keyset-курсоры по двум очередям + cooldown
(`_retry_after`) + дедуп уведомлений менеджерам (`_notified`).

Две очереди, свой курсор у каждой:
  * "main" — status=«В работе», executor_id IS NULL, есть активное
    групповое назначение (Request.assignment_type=="group" — держится в
    синхроне с активной строкой RequestAssignment ДВУМЯ живыми писателями:
    workflow_runner'ом (см. _apply_domain_op_sync create_assignment/
    promote_group_assignment) и services/assignment_service.py (второй
    канонический писатель, используемый handlers/admin/assignment.py,
    handlers/admin/shared.py::auto_assign_request_by_category,
    handlers/request_assignment.py, smart_dispatcher.py,
    shift_transfer_service.py). ⚠️ `assign_to_group` до этой фичи НЕ обнулял
    `Request.executor_id` при переходе в group (асимметрично с
    `assign_to_executor`, который его ставит) — устаревший individual
    executor_id пережил бы переход в group, и main-очередь (executor_id IS
    NULL) молча пропускала бы такую заявку. Исправлено в этом же PR
    (assignment_service.py::assign_to_group теперь явно обнуляет executor_id) —
    инвариант «оба писателя зеркалят обе стороны» теперь держится по факту,
    а не только для workflow_runner'а.
    Фильтр по Request.assignment_type вместо джойна RequestAssignment
    безопасен именно потому, что ОБА писателя держат инвариант, а не потому,
    что писатель один. Есть один пограничный случай: shift_assignment_service.
    py::sync_request_assignments_with_shifts (планировщик) отменяет строки
    RequestAssignment напрямую, не трогая поля Request, но её фильтр matчит
    только строки с конкретным executor_id (SQL `NULL NOT IN (...)` не
    матчит) — group-заявки (executor_id IS NULL, ровно фильтр main-очереди)
    она не трогает никогда, так что для main-очереди устаревания не возникает,
    но это следствие фильтра, а не осведомлённости писателя об этом инварианте.
    Специализация = Request.assigned_group.
  * "residual" — status=«Новая», executor_id IS NULL, assignment_type IS
    NULL (немаппированные категории/сбои dispatch при создании). Резерву
    очереди гарантируется max(1, limit // 4) слотов, если очередь непуста.

Keyset-курсор `(created_at, request_number)` + wrap-around (см.
`_process_queue`) гарантируют, что курсор всегда продвигается за последней
ВЗЯТОЙ В ОБРАБОТКУ заявкой независимо от исхода — недостижимых «хвостов»
нет, даже если ни одна заявка в очереди не находит дежурного.

Назначение — единственный канонический write-path (`run_command_sync`,
system-принципал "auto_manager"): SYSTEM_AUTO_PROMOTE для main-очереди,
SYSTEM_DISPATCH_ASSIGN (executor или group) для residual.
"""

from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from uk_management_bot.constants.categories import get_specialization_for_category
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import SessionLocal
from uk_management_bot.keyboards.requests import get_category_display, resolve_category_key
from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.services.auto_manager.config import is_window_active, load_config_sync
from uk_management_bot.services.auto_manager.rule_engine import (
    build_duty_snapshot,
    select_executor,
)
from uk_management_bot.services.workflow_runner import (
    RequestNotFound,
    WorkflowError,
    run_command_sync,
)
from uk_management_bot.utils.auth_helpers import get_user_roles
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
    ROLE_MANAGER,
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.request_workflow import Action, ActionCommand, PrincipalRef
from uk_management_bot.utils.telegram_client import SEND_TIMEOUT

logger = logging.getLogger(__name__)

# Анти-starvation cooldown после «нет дежурного» — не жечь слоты на одной и
# той же заявке ни в forward-scan (phase1), ни при wrap-around (phase2), дать
# шанс другим кандидатам этого тика. Проверяется ОБЕИМИ фазами одинаково —
# см. `_process_queue`: курсор может двигаться нелинейно (регрессировать
# назад после wrap-around'а предыдущего тика), так что enforcement cooldown'а
# не должен зависеть от монотонности курсора, только от `self._retry_after`.
_RETRY_COOLDOWN = timedelta(minutes=15)

# TTL дедупа уведомлений approved-менеджерам про одну и ту же «нет дежурного».
_NOTIFY_TTL = timedelta(hours=12)

# Over-fetch батч — ограниченный (не безусловный SELECT *), но с запасом на
# случай, что несколько первых строк батча уже in-cooldown/taken. Используется
# И phase1 (forward-scan), и phase2 (wrap-around): если бы phase1 брал ровно
# `slots` строк без запаса, cooldown-фильтр внутри него мог бы недобрать тик,
# даже когда чуть дальше по курсору есть готовые кандидаты — то же
# анти-starvation соображение, что и у исходного wrap-around'а.
_WRAP_BATCH_MULTIPLIER = 5

_AUTO_MANAGER_PRINCIPAL = PrincipalRef(
    kind="system", user_id=None, source="auto_manager", system_actor="auto_manager")


# ── AUD6-P2-01: план тика ────────────────────────────────────────────────────
# Вся работа с БД собирается в примитивы ВНУТРИ db-фазы (worker-поток, сессия
# закрывается до единого await) — рассылка и realtime идут после, по снимкам.
# ORM-объекты через границу потока/сессии не проносятся намеренно: detached-
# инстансы с lazy-полями — ровно тот класс ошибок, от которого уходим.

@dataclass
class _ExecutorNotifyJob:
    telegram_id: int
    language: str
    request_number: str
    category: str
    address: str


@dataclass
class _ManagerNotifyJob:
    recipients: list[tuple[int, str]]  # (telegram_id, language)
    request_number: str
    specialization: str


@dataclass
class _TickPlan:
    kanban_refreshes: list[str] = field(default_factory=list)
    executor_notifies: list[_ExecutorNotifyJob] = field(default_factory=list)
    manager_notifies: list[_ManagerNotifyJob] = field(default_factory=list)


def _now_utc() -> datetime:
    """Тонкий seam для monkeypatch в тестах (advance «now» между тиками)."""
    return datetime.now(timezone.utc)


def _main_queue_filter():
    return and_(
        Request.status == REQUEST_STATUS_IN_PROGRESS,
        Request.executor_id.is_(None),
        Request.assignment_type == "group",
    )


def _residual_queue_filter():
    return and_(
        Request.status == REQUEST_STATUS_NEW,
        Request.executor_id.is_(None),
        Request.assignment_type.is_(None),
    )


class AutoManagerOrchestrator:
    """Один экземпляр на процесс — держит cursor/cooldown/dedup state между tick-ами."""

    def __init__(self, bot=None, notification_service=None):
        # Мирроит seam ShiftScheduler.__init__: self._bot — прод-инъекция
        # общего диспетчерского бота, notification_service — тестовый seam
        # (принят для конструкторской совместимости с будущим wiring'ом в
        # ShiftScheduler, Task 6; собственные уведомления этого класса идут
        # через _get_bot()/raw send_message, как auto_assign_request_by_category,
        # а не через NotificationService-абстракцию).
        self._bot = bot
        self.notification_service = notification_service

        # Анти-starvation keyset-курсоры — свой на очередь, живут между tick-ами.
        self._cursor_main: Optional[tuple[datetime, str]] = None
        self._cursor_residual: Optional[tuple[datetime, str]] = None

        # request_number -> «не пытаться раньше этого времени» (нет дежурного).
        self._retry_after: dict[str, datetime] = {}
        # request_number -> когда последний раз уведомили менеджеров (dedup TTL).
        self._notified: dict[str, datetime] = {}
        # Кэш получателей-менеджеров на ОДИН тик (сбрасывается в _db_phase).
        self._managers_cache: Optional[list[tuple[int, str]]] = None

    def _get_bot(self):
        if self._bot is not None:
            return self._bot
        from uk_management_bot.services.notification_service import _get_shared_bot
        return _get_shared_bot()

    # ------------------------------------------------------------------ #
    # Публичный вход
    # ------------------------------------------------------------------ #

    async def run_once(self) -> None:
        now = _now_utc()
        # AUD6-P2-01: раньше весь тик — sync-SQLAlchemy ПРЯМО на event loop'е
        # бота (job каждые 2 мин), а сессия жила и через await bot.send_message
        # (flood-wait Telegram = минуты idle-in-transaction). Теперь вся работа
        # с БД — в worker-потоке одной sync-фазой, сессия закрывается до
        # единого await; рассылка и realtime идут после, по примитивам плана.
        plan = await asyncio.to_thread(self._db_phase, now)
        if plan is None:
            return
        for request_number in plan.kanban_refreshes:
            await self._publish_kanban_refresh(request_number)
        for job in plan.executor_notifies:
            await self._send_executor_notify(job)
        for job in plan.manager_notifies:
            await self._send_manager_notify(job)

    def _db_phase(self, now: datetime) -> Optional[_TickPlan]:
        """Sync-фаза тика: конфиг, очереди, назначения. Никаких await внутри."""
        db = SessionLocal()
        try:
            cfg = load_config_sync(db)
            if not cfg["enabled"] or not is_window_active(cfg, now):
                return None

            self._prune_expired(now)

            limit = cfg["max_requests_per_run"]
            has_residual = db.query(Request.request_number).filter(
                _residual_queue_filter()).first() is not None

            if has_residual:
                # AUD6-P3-22: резерв residual — потолок, а не вытеснение main:
                # при limit=1 прежняя формула отдавала единственный слот
                # residual-очереди, и main не обрабатывалась вообще.
                residual_slots = min(max(1, limit // 4), max(0, limit - 1))
            else:
                residual_slots = 0
            main_slots = limit - residual_slots

            plan = _TickPlan()
            # AUD6-P2-14: срез дежурства (кандидаты, активные смены, нагрузка)
            # собирается ТРЕМЯ запросами один раз на тик — не на каждую заявку.
            snapshot = build_duty_snapshot(db, now)
            self._managers_cache = None

            if main_slots > 0:
                self._process_queue(db, now, "main", main_slots, snapshot, plan)
            if residual_slots > 0:
                self._process_queue(db, now, "residual", residual_slots, snapshot, plan)
            return plan
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Cooldown/dedup housekeeping
    # ------------------------------------------------------------------ #

    def _prune_expired(self, now: datetime) -> None:
        """Не строго обязательно для корректности — ограничивает рост словарей
        на долгоживущем процессе. Просроченные записи и так игнорируются
        по месту (сравнение с `now`)."""
        self._retry_after = {k: v for k, v in self._retry_after.items() if v > now}
        self._notified = {k: v for k, v in self._notified.items() if now - v < _NOTIFY_TTL}

    def _get_cursor(self, queue: str) -> Optional[tuple[datetime, str]]:
        return self._cursor_main if queue == "main" else self._cursor_residual

    def _set_cursor(self, queue: str, value: tuple[datetime, str]) -> None:
        if queue == "main":
            self._cursor_main = value
        else:
            self._cursor_residual = value

    # ------------------------------------------------------------------ #
    # Per-queue processing: keyset forward scan + wrap-around
    # ------------------------------------------------------------------ #

    def _process_queue(self, db: Session, now: datetime, queue: str, slots: int,
                       snapshot, plan: _TickPlan) -> None:
        filt = _main_queue_filter() if queue == "main" else _residual_queue_filter()
        cursor = self._get_cursor(queue)

        q = db.query(Request).filter(filt)
        if cursor is not None:
            c_at, c_num = cursor
            q = q.filter(or_(
                Request.created_at > c_at,
                and_(Request.created_at == c_at, Request.request_number > c_num),
            ))
        # Over-fetch (не просто `limit(slots)`) — та же причина, что и у
        # phase2's wrap_batch_size: строки в cooldown (см. ниже) не должны
        # приводить к недобору тика, если дальше по курсору есть
        # действительно готовые кандидаты. Без over-fetch'а cooldown-фильтр
        # ниже мог бы «съесть» слоты впустую вместо того, чтобы заглянуть
        # чуть дальше вперёд — анти-starvation цель этого модуля именно
        # «не тратить слоты тика на безнадёжные заявки», а не наоборот.
        phase1_batch_size = slots * _WRAP_BATCH_MULTIPLIER
        phase1_rows = (
            q.order_by(Request.created_at, Request.request_number)
            .limit(phase1_batch_size)
            .all()
        )

        taken: list[Request] = []
        taken_numbers: set[str] = set()
        for row in phase1_rows:
            if len(taken) >= slots:
                break
            cooldown_until = self._retry_after.get(row.request_number)
            if cooldown_until is not None and cooldown_until > now:
                continue
            taken.append(row)
            taken_numbers.add(row.request_number)

        if len(taken) < slots:
            remaining = slots - len(taken)
            wrap_batch_size = max(slots * _WRAP_BATCH_MULTIPLIER, slots + remaining)
            wrap_rows = (
                db.query(Request).filter(filt)
                .order_by(Request.created_at, Request.request_number)
                .limit(wrap_batch_size)
                .all()
            )
            extra_taken = 0
            for row in wrap_rows:
                if extra_taken >= remaining:
                    break
                if row.request_number in taken_numbers:
                    continue
                cooldown_until = self._retry_after.get(row.request_number)
                if cooldown_until is not None and cooldown_until > now:
                    continue
                taken.append(row)
                taken_numbers.add(row.request_number)
                extra_taken += 1

        for req in taken:
            self._process_item(db, req, queue, now, snapshot, plan)

        if taken:
            last = taken[-1]
            self._set_cursor(queue, (last.created_at, last.request_number))

    # ------------------------------------------------------------------ #
    # Per-item assignment
    # ------------------------------------------------------------------ #

    async def _publish_kanban_refresh(self, request_number: str) -> None:
        """Best-effort realtime nudge so an open Kanban tab refetches.

        `run_command_sync` (like every other bot/sync call site) discards its
        `CommandOutcome.post_commit_intents` — only `services/dispatch.py`'s
        ASYNC half and `api/requests/router.py` publish realtime events, so no
        bot-driven action currently pushes live Kanban updates today. Unlike a
        one-off manual bot click though, this orchestrator can run many
        assignments unattended overnight, so a manager watching an open Kanban
        would otherwise see stale executors for an unbounded time. `run_once`
        is itself `async def`, so — unlike a plain sync bot handler — it CAN
        await the async publish helper directly here.

        Publishes the same minimal `"request.updated"` event the API layer
        already uses for non-status-changing updates (`api/requests/router.py`,
        `api/shifts/router.py`, `api/shifts/executor_router.py` — payload is
        just `{"number": ...}`, `useKanban.ts` ignores the payload and simply
        invalidates its query on any of 4 event types). Deliberately NOT
        re-deriving `_build_events`' actual EventIntents from the discarded
        outcome — that would require re-opening/re-reading the row outside its
        original transaction; "updated" alone is sufficient to trigger a
        refetch for both the group→individual promotion (no public status
        change, so `_build_events` wouldn't even produce a webhook/realtime
        intent) and the Новая→В работе residual-queue case.
        """
        try:
            from uk_management_bot.services.redis_pubsub import publish_request_event
            await publish_request_event("request.updated", {"number": request_number})
        except Exception as e:  # realtime — best-effort, mirrors dispatch.py
            logger.debug("[AUTO_MANAGER] realtime publish %s пропущен: %s",
                         request_number, e)

    def _process_item(self, db: Session, req: Request, queue: str, now: datetime,
                      snapshot, plan: _TickPlan) -> None:
        if queue == "main":
            self._process_main_item(db, req, now, snapshot, plan)
        else:
            self._process_residual_item(db, req, now, snapshot, plan)

    @staticmethod
    def _queue_executor_notify(plan: _TickPlan, candidate: User, req: Request) -> None:
        """Снимок-примитивы для рассылки после закрытия сессии (AUD6-P2-01)."""
        plan.executor_notifies.append(_ExecutorNotifyJob(
            telegram_id=candidate.telegram_id,
            language=candidate.language or "ru",
            request_number=req.request_number,
            category=req.category,
            address=req.address or "",
        ))

    @staticmethod
    def _bump_load(snapshot, executor_id: int) -> None:
        """Внутритиковый учёт назначений (AUD6-P2-14): срез нагрузки снят один
        раз на тик, поэтому успешное назначение инкрементирует его вручную —
        иначе пачка однотипных заявок в одном тике ушла бы одному исполнителю."""
        snapshot.load_by_user[executor_id] = snapshot.load_by_user.get(executor_id, 0) + 1

    def _process_main_item(self, db: Session, req: Request, now: datetime,
                           snapshot, plan: _TickPlan) -> None:
        specialization = req.assigned_group
        candidate = select_executor(db, specialization, now, snapshot=snapshot)

        if candidate is None:
            self._retry_after[req.request_number] = now + _RETRY_COOLDOWN
            self._queue_manager_notify(db, req, specialization, now, plan)
            return

        command = ActionCommand(
            command_id=f"auto_manager:{req.request_number}",
            action=Action.SYSTEM_AUTO_PROMOTE,
            payload={"executor_id": candidate.id},
        )
        try:
            run_command_sync(SessionLocal, req.request_number,
                             _AUTO_MANAGER_PRINCIPAL, command, now=now)
        except (WorkflowError, RequestNotFound) as e:
            # Гонка: менеджер/другой процесс уже переназначил заявку между
            # выбором кандидата и нашим write — нормальный исход, НЕ «нет
            # дежурного» (дежурный был, просто опоздали) — без manager-notify.
            logger.debug("[AUTO_MANAGER] SYSTEM_AUTO_PROMOTE %s пропущен: %s",
                         req.request_number, e)
            return

        self._bump_load(snapshot, candidate.id)
        plan.kanban_refreshes.append(req.request_number)
        self._queue_executor_notify(plan, candidate, req)

    def _process_residual_item(self, db: Session, req: Request, now: datetime,
                               snapshot, plan: _TickPlan) -> None:
        specialization = get_specialization_for_category(req.category)
        candidate = select_executor(db, specialization, now, snapshot=snapshot)

        if candidate is not None:
            command = ActionCommand(
                command_id=f"auto_manager:{req.request_number}",
                action=Action.SYSTEM_DISPATCH_ASSIGN,
                payload={"executor_id": candidate.id},
            )
            try:
                run_command_sync(SessionLocal, req.request_number,
                                 _AUTO_MANAGER_PRINCIPAL, command, now=now)
            except (WorkflowError, RequestNotFound) as e:
                logger.debug("[AUTO_MANAGER] SYSTEM_DISPATCH_ASSIGN(executor) %s пропущен: %s",
                             req.request_number, e)
                return
            self._bump_load(snapshot, candidate.id)
            plan.kanban_refreshes.append(req.request_number)
            self._queue_executor_notify(plan, candidate, req)
            return

        # Нет дежурного — адресуем группе, НЕ меняя статус (тот же канонический
        # путь, что services/dispatch.py при создании заявки). Инвариант
        # «В работе ⟺ есть исполнитель»: раньше здесь стоял
        # SYSTEM_DISPATCH_ASSIGN с группой, и заявка уезжала в «В работе» без
        # человека — это был второй производитель ничьих заявок после пути
        # создания. Best-effort: пишем cooldown/уведомляем менеджеров независимо
        # от исхода записи — факт «нет индивидуального дежурного» верен в обоих
        # случаях.
        command = ActionCommand(
            command_id=f"auto_manager:{req.request_number}",
            action=Action.ASSIGN_GROUP,
            payload={"group": specialization},
        )
        try:
            run_command_sync(SessionLocal, req.request_number,
                             _AUTO_MANAGER_PRINCIPAL, command, now=now)
        except (WorkflowError, RequestNotFound) as e:
            logger.debug("[AUTO_MANAGER] ASSIGN_GROUP %s пропущен: %s",
                         req.request_number, e)
        else:
            # Статус не менялся (заявка осталась «Новая»), но на карточке
            # появилась группа — канбан без refresh покажет её без специализации.
            plan.kanban_refreshes.append(req.request_number)

        self._retry_after[req.request_number] = now + _RETRY_COOLDOWN
        self._queue_manager_notify(db, req, specialization, now, plan)

    # ------------------------------------------------------------------ #
    # Notifications (best-effort, mirror handlers/admin/shared.py)
    # ------------------------------------------------------------------ #

    def _queue_manager_notify(self, db: Session, req: Request, specialization: str,
                              now: datetime, plan: _TickPlan) -> None:
        """Db-фаза: dedup TTL + получатели-примитивы; отправка — после тика."""
        last_notified = self._notified.get(req.request_number)
        if last_notified is not None and now - last_notified < _NOTIFY_TTL:
            return

        # AUD6-P2-14: список менеджеров — один раз на тик, а не на каждую
        # «нет дежурного»-заявку (list_approved_users — полная выборка).
        if self._managers_cache is None:
            svc = AdminHandlerService(db)
            self._managers_cache = [
                (u.telegram_id, u.language or "ru")
                for u in svc.list_approved_users()
                if ROLE_MANAGER in get_user_roles(u) and u.telegram_id
            ]

        plan.manager_notifies.append(_ManagerNotifyJob(
            recipients=list(self._managers_cache),
            request_number=req.request_number,
            specialization=specialization,
        ))
        # Once per request (not per manager) — см. docstring класса. Метка
        # ставится в db-фазе: рассылка best-effort, а дедуп обязан сработать
        # и при частично упавшей отправке.
        self._notified[req.request_number] = now

    async def _send_executor_notify(self, job: _ExecutorNotifyJob) -> None:
        try:
            bot = self._get_bot()
            lang = job.language
            # job.address — свободный пользовательский текст; экранируем перед
            # интерполяцией в parse_mode="HTML" (тот же html.escape-паттерн,
            # что services/feedback_service.py/notification_service.py) — иначе
            # `<`/`>`/`&` в адресе могли бы сломать отправку сообщения Telegram.
            text = get_text("auto_manager.assigned_notification", language=lang).format(
                request_number=job.request_number,
                category=get_category_display(resolve_category_key(job.category), language=lang),
                address=html.escape(job.address),
            )
            await bot.send_message(chat_id=job.telegram_id, text=text, parse_mode="HTML")
        except Exception as e:  # best-effort — не валим tick из-за уведомления
            logger.warning("[AUTO_MANAGER] уведомление исполнителю tg=%s (заявка %s) не отправлено: %s",
                          job.telegram_id, job.request_number, e)

    async def _send_manager_notify(self, job: _ManagerNotifyJob) -> None:
        bot = self._get_bot()
        for telegram_id, language in job.recipients:
            try:
                # Язык получателя, не жёстко "ru" — у каждого менеджера свой
                # User.language (UZ-переводы уже добавлены в locale-файлы).
                text = get_text("auto_manager.no_duty_executor", language=language).format(
                    request_number=job.request_number, specialization=job.specialization,
                )
                # Цикл по получателям: без per-call предела медленный Telegram
                # растягивает tick на N × session-таймаут (AUD3-09).
                await bot.send_message(
                    chat_id=telegram_id,
                    text=text,
                    parse_mode="HTML",
                    request_timeout=SEND_TIMEOUT,
                )
            except Exception as e:  # best-effort per-recipient
                logger.warning("[AUTO_MANAGER] уведомление менеджеру tg=%s (заявка %s) не отправлено: %s",
                              telegram_id, job.request_number, e)
