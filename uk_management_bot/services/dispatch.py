"""Авто-dispatch новой заявки: подобрать дежурного, иначе адресовать группе.

Специализация берётся по категории (`CATEGORY_TO_SPECIALIZATION`), дальше:

* есть дежурный (нужная специализация + активная смена, покрывающая её,
  наименее загружен — тот же `select_executor`, что у авто-менеджера) →
  `SYSTEM_DISPATCH_ASSIGN` на конкретного человека, «Новая»→«В работе»;
* дежурного нет → `ASSIGN_GROUP`: заявка ОСТАЁТСЯ «Новая», проставляется
  только группа-специализация. Её видят дежурные нужной специализации и может
  взять любой из них (`EXECUTOR_CLAIM`), а менеджер видит её в «Новых».

Инвариант — решение владельца 2026-08-17: **«В работе» ⟺ у заявки есть
исполнитель**. Раньше этот хелпер безусловно ставил ГРУППОВОЕ назначение со
статусом «В работе», `executor_id` оставался пустым, и незабранная заявка
висела ничьей: на продах так накопилось девять таких, старейшая с 16 июня.

Best-effort: ошибка dispatch (нет seeded system-user, нет маппинга категории,
гонка статуса и т.п.) НЕ валит уже-созданную заявку — она остаётся «Новая»
(менеджер назначит вручную). Вызывается ПОСЛЕ commit создания: бот —
`save_request` (sync), API/TWA/обходчик — `_persist_request` (async).

realtime: бот-путь создания realtime не публикует вовсе (только outbox-webhook,
который run_command тоже эмитит), поэтому sync-хелпер ограничивается dispatch'ем.
API-путь публикует `request.created` (Новая), и async-хелпер до-публикует:
`request.status_changed` — когда дежурный найден и статус реально изменился,
иначе `request.updated` (изменилась карточка, статус тот же).
"""

from __future__ import annotations

import logging
from typing import Optional

from uk_management_bot.constants.categories import CATEGORY_TO_SPECIALIZATION
from uk_management_bot.utils.request_workflow import (
    Action,
    ActionCommand,
    PrincipalRef,
)

logger = logging.getLogger(__name__)


def _dispatch_principal() -> PrincipalRef:
    return PrincipalRef(kind="system", user_id=None,
                        source="dispatcher", system_actor="dispatcher")


def _assign_executor_command(request_number: str, executor_id: int) -> ActionCommand:
    return ActionCommand(
        command_id=f"dispatch:{request_number}",
        action=Action.SYSTEM_DISPATCH_ASSIGN,
        payload={"executor_id": executor_id},
    )


def _assign_group_command(request_number: str, specialization: str) -> ActionCommand:
    return ActionCommand(
        command_id=f"dispatch:{request_number}",
        action=Action.ASSIGN_GROUP,
        payload={"group": specialization},
    )


def pick_duty_executor_id(specialization: str, db=None,
                          exclude_user_ids: frozenset[int] = frozenset(),
                          strict: bool = False) -> Optional[int]:
    """id дежурного под специализацию — тем же подбором, что у авто-менеджера.

    Возвращается именно id, а не ORM-объект: сессия здесь своя и закрывается
    сразу, а detached-инстанс дальше всё равно нельзя использовать.

    `exclude_user_ids` — кого не предлагать (переназначение исключает текущего
    исполнителя, иначе резолвится тот же человек).

    `strict` — режим вызывающего. По умолчанию False: best-effort, как и весь
    dispatch, который идёт ПОСЛЕ commit создания заявки и не вправе её уронить
    (ошибка → None → заявка остаётся «Новая» с групповым назначением, то есть
    достаётся дежурным и менеджеру). Для ИНТЕРАКТИВНОГО действия это неверно:
    там `None` означает «нет дежурного» и так и печатается человеку, поэтому
    авария БД показалась бы как пустой результат. `strict=True` поднимает
    исключение, чтобы вызывающий отличил «никого нет» от «не смогли посмотреть».
    """
    from uk_management_bot.services.auto_manager.rule_engine import select_executor
    from uk_management_bot.utils.datetime_utils import utc_now

    def _run(session) -> Optional[int]:
        candidate = select_executor(session, specialization, utc_now(),
                                    exclude_user_ids=exclude_user_ids)
        return candidate.id if candidate is not None else None

    try:
        if db is not None:
            return _run(db)
        from uk_management_bot.database.session import SessionLocal
        session = SessionLocal()
        try:
            return _run(session)
        finally:
            session.close()
    except Exception as e:
        if strict:
            raise
        logger.warning("[DISPATCH] подбор дежурного под '%s' не выполнен: %s",
                       specialization, e)
        return None


def _specialization_for(category: Optional[str]) -> Optional[str]:
    if not category:
        return None
    return CATEGORY_TO_SPECIALIZATION.get(category)


def _auto_assign_enabled_sync(db=None) -> bool:
    """Флаг автоназначения; любая ошибка чтения → False.

    Fail-safe направление: не сумели прочитать конфиг — не раздаём. Заявка
    останется «Новая» и достанется человеку; молча раздавать её при сломанной
    БД было бы хуже. Чтение обязано быть best-effort по той же причине, что и
    сам dispatch: оно идёт ПОСЛЕ commit создания заявки и не вправе её уронить.
    """
    from uk_management_bot.services.auto_manager.config import is_auto_assign_enabled_sync
    try:
        if db is not None:
            return is_auto_assign_enabled_sync(db)
        from uk_management_bot.database.session import SessionLocal
        session = SessionLocal()
        try:
            return is_auto_assign_enabled_sync(session)
        finally:
            session.close()
    except Exception as e:
        logger.warning("[DISPATCH] конфиг автоназначения недоступен, считаю выключенным: %s", e)
        return False


async def _auto_assign_enabled_async(db=None) -> bool:
    """Асинхронный аналог — то же fail-safe направление."""
    from uk_management_bot.services.auto_manager.config import is_auto_assign_enabled
    try:
        if db is not None:
            return await is_auto_assign_enabled(db)
        from uk_management_bot.database.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await is_auto_assign_enabled(session)
    except Exception as e:
        logger.warning("[DISPATCH] конфиг автоназначения недоступен, считаю выключенным: %s", e)
        return False


def auto_dispatch_new_request_sync(request_number: str,
                                   category: Optional[str],
                                   *, _db=None) -> None:
    """Бот-путь: подобрать дежурного и назначить его (best-effort).

    Дежурный найден → «Новая»→«В работе» с ним. Не найден → заявка ОСТАЁТСЯ
    «Новая», проставляется только группа-специализация: её видят дежурные
    нужной специализации и может взять любой из них, а менеджер видит её в
    «Новых». Инвариант «В работе ⟺ есть исполнитель» (решение владельца
    2026-08-17): раньше здесь безусловно ставилось групповое назначение со
    статусом «В работе», и незабранная заявка висела ничьей.

    `_db` — seam для тестов; в проде сессия открывается здесь же. Прокинуть
    сессию вызывающего нельзя: точки вызова передают только номер и категорию,
    а `run_command_sync` всё равно открывает свою — читать флаг на короткой
    сессии дешевле, чем менять контракт трёх вызывающих.
    """
    spec = _specialization_for(category)
    if not spec:
        return
    if not _auto_assign_enabled_sync(_db):
        logger.info("[DISPATCH] автоназначение выключено — %s остаётся «Новая»",
                    request_number)
        return
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.services.workflow_runner import run_command_sync

    executor_id = pick_duty_executor_id(spec, _db)
    if executor_id is not None:
        command = _assign_executor_command(request_number, executor_id)
        done = "назначена дежурному id=%s ('%s')" % (executor_id, spec)
    else:
        command = _assign_group_command(request_number, spec)
        done = "оставлена «Новая» для группы '%s' — дежурного нет" % spec
    try:
        outcome = run_command_sync(SessionLocal, request_number,
                                   _dispatch_principal(), command)
        logger.info("[DISPATCH] Заявка %s %s", request_number, done)
    except Exception as e:  # best-effort — не валим создание заявки
        logger.warning("[DISPATCH] авто-назначение %s ('%s') не выполнено: %s",
                       request_number, spec, e)
        return
    if executor_id is not None:
        _notify_assigned_sync(request_number, outcome)


async def auto_dispatch_new_request_async(request_number: str,
                                          category: Optional[str],
                                          *, _db=None) -> None:
    """API/TWA/обходчик: то же, что sync-путь, плюс realtime для канбана."""
    spec = _specialization_for(category)
    if not spec:
        return
    if not await _auto_assign_enabled_async(_db):
        logger.info("[DISPATCH] автоназначение выключено — %s остаётся «Новая»",
                    request_number)
        return
    import asyncio

    from uk_management_bot.database.session import AsyncSessionLocal
    from uk_management_bot.services.workflow_runner import run_command_async

    # Подбор дежурного — sync-код (`select_executor` ходит через Session), и
    # здесь мы в event loop'е. Отдельный поток, а не прямой вызов: блокировать
    # loop синхронными запросами к БД в этом проекте уже было дефектом (BUG-157).
    executor_id = await asyncio.to_thread(pick_duty_executor_id, spec, None)
    if executor_id is not None:
        command = _assign_executor_command(request_number, executor_id)
        done = "назначена дежурному id=%s ('%s')" % (executor_id, spec)
    else:
        command = _assign_group_command(request_number, spec)
        done = "оставлена «Новая» для группы '%s' — дежурного нет" % spec
    try:
        outcome = await run_command_async(
            AsyncSessionLocal, request_number, _dispatch_principal(), command)
        logger.info("[DISPATCH] Заявка %s %s", request_number, done)
    except Exception as e:  # best-effort — не валим создание заявки
        logger.warning("[DISPATCH] авто-назначение %s ('%s') не выполнено: %s",
                       request_number, spec, e)
        return
    if executor_id is not None:
        await _publish_status_changed(outcome, request_number)
        from uk_management_bot.services.workflow_notifications import (
            dispatch_notify_intents_detached,
        )
        try:
            await dispatch_notify_intents_detached(
                request_number, outcome.post_commit_intents)
        except Exception as e:  # уведомление не вправе ронять назначение
            logger.warning("[DISPATCH] уведомление о назначении %s пропущено: %s",
                           request_number, e)
    else:
        # Статус НЕ менялся — заявка осталась «Новая». Публиковать
        # `status_changed` здесь было бы ложью; канбану нужно обновить карточку
        # из-за появившейся группы.
        await _publish_updated(request_number)


def _notify_assigned_sync(request_number: str, outcome) -> None:
    """Сообщить назначенному дежурному и жителю (best-effort).

    Без этого заявка была бы назначена человеку, который об этом не узнает: из
    пула свободных она уже ушла (`executor_id` не NULL), а создание заявки само
    исполнителей не уведомляет. До инварианта уведомлять было некого — группу
    видели все дежурные сразу.
    """
    import asyncio

    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.services.workflow_notifications import (
        dispatch_notify_intents_sync,
    )
    session = SessionLocal()
    try:
        asyncio.run(dispatch_notify_intents_sync(
            session, request_number, outcome.post_commit_intents))
    except Exception as e:  # уведомление не вправе ронять назначение
        logger.warning("[DISPATCH] уведомление о назначении %s пропущено: %s",
                       request_number, e)
    finally:
        session.close()


async def _publish_updated(request_number: str) -> None:
    """Карточка изменилась без смены статуса (появилась группа)."""
    from uk_management_bot.services.redis_pubsub import publish_request_event
    try:
        await publish_request_event("request.updated", {"number": request_number})
    except Exception as e:  # realtime best-effort
        logger.debug("[DISPATCH] realtime publish %s пропущен: %s",
                     request_number, e)


async def _publish_status_changed(outcome, request_number: str) -> None:
    """До-публикация realtime для канбана (Новая уже эмитнута при создании)."""
    from uk_management_bot.services.redis_pubsub import publish_request_event
    from uk_management_bot.utils.request_workflow import normalize_status
    for ev in outcome.post_commit_intents:
        if ev.kind != "realtime":
            continue
        try:
            await publish_request_event("request.status_changed", {
                "number": request_number,
                "old_status": normalize_status(outcome.old_state),
                "new_status": ev.data.get("status"),
            })
        except Exception as e:  # realtime best-effort
            logger.debug("[DISPATCH] realtime publish %s пропущен: %s",
                         request_number, e)
