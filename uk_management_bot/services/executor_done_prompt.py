"""Личка исполнителю «какую заявку закрыли?» и ежедневное напоминание (Фаза 4).

Исполнители пишут в рабочую группу «сделал #ариза» вместо закрытия заявки.
Этот модуль — общая часть трёх путей, которые ведут их к закрытию:

* «готово» в группе (``handlers/group_intake_done``, процесс группового бота)
  → личка ОСНОВНЫМ ботом со списком заявок в работе;
* ежедневное напоминание в 18:00 по бизнес-зоне (``utils/shift_scheduler``);
* «Закончить смену» в боте и TWA — то же напоминание, если есть незакрытые.

Кнопки списка — web_app на ``/uk/twa/exec/tasks/{n}?action=done`` (экран
«Готово» выбирает фронт) и «Все» на ``/uk/twa/exec``. Фото-путь (фото прямо в
«готово»-сообщении) шлёт callback-кнопки ``exdone:{n}``, их обрабатывает
``handlers/executor_done`` в процессе основного бота.

Напоминание — не чаще раза в день на заявку: ключ Redis
``exec_remind:{номер}:{бизнес-дата}`` (SET NX, TTL > суток). Сообщение уходит,
только если в списке есть заявка, о которой сегодня ещё не напоминали. Redis
недоступен → fail-open (напоминание уйдёт): оба триггера сами ограничены
(раз в день по крону и по факту конца смены), а потерянное напоминание хуже
редкого дубля.

Сеть и Bot API: ошибки логируются только классом исключения — текст
исключения httpx/aiohttp может нести URL с токеном бота.
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Sequence

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import get_user_roles
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_IN_PROGRESS,
    ROLE_EXECUTOR,
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.twa_links import executor_done_links_markup
from uk_management_bot.utils.workflow_predicates import status_in_clause

logger = logging.getLogger(__name__)

# «Незакрытые» для списка, фото-пути и напоминаний — ТОЛЬКО «В работе»
# (решение владельца): EXECUTOR_COMPLETE канон пускает лишь отсюда, а
# «Возвращена» разбирает менеджер (MANAGER_RETURN_TO_WORK) — исполнителю с
# ней делать нечего, напоминать о ней — шум.
OPEN_STATUSES = (REQUEST_STATUS_IN_PROGRESS,)

MAX_BUTTONS = 5
# Callback фото-пути; обработчик — handlers/executor_done (основной бот).
CB_CLOSE_PREFIX = "exdone:"

_MAX_HOUSE_LABEL = 28
REMIND_KEY_PREFIX = "exec_remind"
# Больше суток: ключ дня живёт до следующего бизнес-дня с запасом.
REMIND_TTL_SECONDS = 36 * 3600


@dataclass(frozen=True)
class OpenTask:
    number: str
    label: str  # «дом · кв N» — простой текст (подпись кнопки, не HTML)


@dataclass(frozen=True)
class Executor:
    user_id: int
    telegram_id: int
    lang: str


@dataclass(frozen=True)
class Recipient:
    executor: Executor
    tasks: tuple[OpenTask, ...]  # первые MAX_BUTTONS
    numbers: tuple[str, ...]  # все незакрытые — для дедупа напоминания
    total: int


# ───────────────────────── sync-юниты (run_db) ─────────────────────────


def _is_executor(user: Optional[User]) -> bool:
    return (
        user is not None
        and user.status == "approved"
        and user.deleted_at is None
        and bool(user.telegram_id)
        and ROLE_EXECUTOR in get_user_roles(user)
    )


def _executor_dto(user: User) -> Executor:
    return Executor(user_id=user.id, telegram_id=user.telegram_id, lang=user.language or "ru")


def executor_by_telegram_sync(db, telegram_id: int) -> Optional[Executor]:
    """Approved-сотрудник с ролью executor по telegram_id, иначе None."""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    return _executor_dto(user) if _is_executor(user) else None


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def short_label(request: Request, lang: str) -> str:
    """Коротко «дом · кв N» (сырой текст — экранирует вызывающий при HTML)."""
    apartment = request.apartment_obj
    building = request.building_obj or (apartment.building if apartment else None)
    house = building.address if building is not None else (request.address or "")
    house = _clip(" ".join(house.split()), _MAX_HOUSE_LABEL)
    if apartment is not None and apartment.apartment_number:
        apt = get_text("executor_done.apt_short", language=lang)
        return f"{house} · {apt} {apartment.apartment_number}"  # html-raw: подпись кнопки (простой текст); в HTML — через _task_lines (escape)
    return house


def _task(request: Request, lang: str) -> OpenTask:
    return OpenTask(number=request.request_number, label=short_label(request, lang))


def _open_requests_query(statuses: Iterable[str]):
    return (
        select(Request)
        .where(status_in_clause(statuses), Request.executor_id.isnot(None))
        .order_by(Request.created_at.desc(), Request.request_number.desc())
    )


def open_tasks_sync(db, user_id: int, lang: str,
                    statuses: Sequence[str] = OPEN_STATUSES) -> tuple[tuple[OpenTask, ...], int]:
    """(первые MAX_BUTTONS заявок исполнителя в ``statuses``, всего таких)."""
    rows = db.execute(
        _open_requests_query(statuses).where(Request.executor_id == user_id)
    ).scalars().all()
    return tuple(_task(r, lang) for r in rows[:MAX_BUTTONS]), len(rows)


def _recipient(user: User, requests: list[Request]) -> Recipient:
    executor = _executor_dto(user)
    return Recipient(
        executor=executor,
        tasks=tuple(_task(r, executor.lang) for r in requests[:MAX_BUTTONS]),
        numbers=tuple(r.request_number for r in requests),
        total=len(requests),
    )


def recipient_sync(db, user_id: int) -> Optional[Recipient]:
    """Незакрытые заявки одного исполнителя (конец смены); None — слать нечего."""
    user = db.get(User, user_id)
    if not _is_executor(user):
        return None
    requests = db.execute(
        _open_requests_query(OPEN_STATUSES).where(Request.executor_id == user_id)
    ).scalars().all()
    return _recipient(user, list(requests)) if requests else None


def all_recipients_sync(db) -> list[Recipient]:
    """Все исполнители с незакрытыми заявками (ежедневное напоминание)."""
    by_executor: dict[int, list[Request]] = {}
    for request in db.execute(_open_requests_query(OPEN_STATUSES)).scalars().all():
        by_executor.setdefault(request.executor_id, []).append(request)
    if not by_executor:
        return []
    users = db.execute(select(User).where(User.id.in_(by_executor))).scalars().all()
    return [_recipient(u, by_executor[u.id]) for u in users if _is_executor(u)]


# ───────────────────────── тексты и разметка ─────────────────────────


def _link_pairs(tasks: Sequence[OpenTask]) -> list[tuple[str, str]]:
    return [(t.number, f"#{t.number} · {t.label}") for t in tasks]


def links_markup(tasks: Sequence[OpenTask], lang: str) -> Optional[InlineKeyboardMarkup]:
    """web_app «Готово» по заявкам + «Все»."""
    return executor_done_links_markup(_link_pairs(tasks), lang)


def close_callback_data(request_number: str) -> str:
    return f"{CB_CLOSE_PREFIX}{request_number}"


def photo_pick_markup(tasks: Sequence[OpenTask]) -> InlineKeyboardMarkup:
    """Callback-кнопки «закрыть этим фото» по заявкам в работе."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=close_callback_data(number))]
        for number, label in _link_pairs(tasks)
    ])


def _task_lines(tasks: Sequence[OpenTask]) -> str:
    """Список текстом — дубль кнопок на случай, если web_app недоступен."""
    return "\n".join(f"• #{t.number} — {html.escape(t.label)}" for t in tasks)


def which_closed_text(tasks: Sequence[OpenTask], lang: str) -> str:
    return get_text("executor_done.which_closed", language=lang) + "\n\n" + _task_lines(tasks)


def reminder_text(recipient: Recipient) -> str:
    lang = recipient.executor.lang
    return (
        get_text("executor_done.reminder", language=lang, n=recipient.total)
        + "\n\n" + _task_lines(recipient.tasks)
    )


# ───────────────────────── отправка ─────────────────────────


async def send_safely(send, *, telegram_id: int, what: str) -> bool:
    """Выполнить отправку Bot API; False — не доставлено. Не бросает.

    Forbidden (исполнитель не запускал основного бота / заблокировал) — тихий
    info-лог. Прочее — warning с классом исключения, без текста (токен в URL).
    """
    try:
        await send()
        return True
    except TelegramForbiddenError:
        logger.info("executor_done: %s — бот недоступен получателю tg=%s", what, telegram_id)
    except Exception as exc:  # noqa: BLE001 — best-effort доставка
        logger.warning("executor_done: %s не доставлено tg=%s: %s",
                       what, telegram_id, type(exc).__name__)
    return False


async def send_open_tasks_prompt(bot, executor: Executor,
                                 tasks: Sequence[OpenTask]) -> bool:
    """«Какую заявку закрыли?» + кнопки, либо «нет заявок в работе»."""
    if not tasks:
        text = get_text("executor_done.no_open_tasks", language=executor.lang)
        markup = None
    else:
        text = which_closed_text(tasks, executor.lang)
        markup = links_markup(tasks, executor.lang)
    return await send_safely(
        lambda: bot.send_message(executor.telegram_id, text, reply_markup=markup),
        telegram_id=executor.telegram_id, what="список заявок",
    )


# ───────────────────────── напоминание ─────────────────────────


def _remind_key(request_number: str, day: date) -> str:
    return f"{REMIND_KEY_PREFIX}:{request_number}:{day.isoformat()}"


async def _get_redis():
    from uk_management_bot.services.redis_pubsub import get_pubsub_redis

    return await get_pubsub_redis()


async def claim_fresh_numbers(numbers: Sequence[str], day: date) -> list[str]:
    """Номера, о которых сегодня ещё не напоминали (и пометить их). Fail-open."""
    try:
        redis = await _get_redis()
        fresh = []
        for number in numbers:
            if await redis.set(_remind_key(number, day), "1", nx=True, ex=REMIND_TTL_SECONDS):
                fresh.append(number)
        return fresh
    except Exception as exc:  # noqa: BLE001 — см. докстринг модуля (fail-open)
        logger.warning("executor_done: Redis недоступен для дедупа напоминаний: %s",
                       type(exc).__name__)
        return list(numbers)


async def send_reminder(bot, recipient: Recipient, *, day: Optional[date] = None) -> bool:
    """Одно сообщение «N не закрыты» со списком; False — не слали/не доставлено."""
    from uk_management_bot.utils.business_time import business_today

    if not await claim_fresh_numbers(recipient.numbers, day or business_today()):
        return False
    executor = recipient.executor
    text = reminder_text(recipient)
    markup = links_markup(recipient.tasks, executor.lang)
    return await send_safely(
        lambda: bot.send_message(executor.telegram_id, text, reply_markup=markup),
        telegram_id=executor.telegram_id, what="напоминание",
    )


async def remind_after_shift_end(bot, user_id: Optional[int], *, _db=None) -> None:
    """Напоминание после «Закончить смену». Best-effort: не бросает и не
    влияет на уже завершённую смену."""
    if user_id is None or bot is None:
        return
    try:
        from uk_management_bot.database.session import run_db

        recipient = await run_db(lambda s: recipient_sync(s, user_id), db=_db)
        if recipient is not None:
            await send_reminder(bot, recipient)
    except Exception as exc:  # noqa: BLE001
        logger.warning("executor_done: напоминание после смены не отправлено user=%s: %s",
                       user_id, type(exc).__name__)
