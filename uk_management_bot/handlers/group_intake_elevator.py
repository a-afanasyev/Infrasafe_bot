"""Групповой приём: фаза «лифт» для категории ``elevator`` (Ф4b, T9).

Вклинивается в callback-фазу ``handlers/group_intake.py`` ПОСЛЕ «Да» автора
(и ре-гейта): вместо немедленного ``save_request`` кандидат переводится в одну
из фаз и ОСТАЁТСЯ под тем же Redis-ключом ``(chat_id, message_id промпта)`` —
тот же механизм, что у выбора адреса ``gint:addr:<n>`` (pending.store_candidate
под ключом нажатого сообщения); промпт редактируется на месте.

Фазы (``candidate[FIELD_PHASE]``):
  * ``elevator_building`` — адрес автора на уровне двора: «уточните дом»,
    кнопки ``gint:bld:<n>`` (индекс в серверном ``building_options``; житель —
    дома двора с его approved-квартирами, staff — дома двора из справочника);
  * ``elevator_pick`` — ``gint:elv:{elevator_id}``: введённые лифты дома; id
    проверяется сервером (``ensure_elevator_usable_sync(building_id=…)`` по
    ``elevator_building_id`` из кандидата, не из callback);
  * ``elevator_operational`` — ``gint:op:1|0``: «лифт сейчас работает?»; ответ →
    GETDEL + ре-гейт + штатное создание с ``elevator_id``/``elevator_operational``.

Р18/Р18a: самообслуживанием считается ЖИЛАЯ группа. Пока запрет включён
(тумблер ``allow_resident_requests_under_works`` выключен), лифт «В ремонте»/
«На ТО» до вопроса «работает?» не доходит: в группу уходит тот же блокирующий
текст, что в личном боте, кандидат снимается, заявка не создаётся. Тумблер
включён — прежнее поведение: мягкая подсказка и обычный вопрос.

**Staff-группа (``GROUP_KIND_STAFF``) — персонал**: тот же признак, что уже
включает ``acceptance_mode=manager`` и роль ``staff_group``, снимает и запрет
Р18 (``allow_under_works=True`` в ``_create_from_candidate``). Иначе сотрудник
не смог бы доложить о происшествии в кабине лифта, который уже в ремонте.

Автоподстановка: ровно один введённый лифт в подъезде квартиры автора (или
единственный в доме) — сразу вопрос «работает?». Дом без лифтов — сообщение,
заявки нет. Отвечает ТОЛЬКО автор сообщения (проверка в group_intake_callback —
и в staff-группе, где «Да» может нажать коллега).

Единый дедлайн: на «Да» в кандидата пишется ``phase_deadline`` (epoch, now +
``ELEVATOR_ANSWER_TIMEOUT``). Его описывают ТРИ согласованных механизма:
  * one-shot ``asyncio``-задача (реестр по ключу промпта, отменяется при ответе
    или завершении без заявки) — по истечении GETDEL + правка промпта
    «заявка не оформлена»;
  * Redis-TTL каждой записи фазы = остаток до дедлайна + ``TTL_GRACE`` (шаги
    внутри фазы окно НЕ продлевают); страховка на потерю таймера (рестарт);
  * ленивая проверка ``is_expired`` на нажатии — после дедлайна «устарело»,
    заявки нет, даже если запись ещё жива за счёт grace.

Двухшаговый расчёт (дом, подъезд → лифты) переиспользует ``load_elevator_step``
личного бота (T7): ``selected_address`` приводится к форме FSM-``data``. Флаг
выключен / категория не «лифт» — модуль не участвует.
"""

from __future__ import annotations

import asyncio
import html
import logging
import time
from dataclasses import dataclass
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models import Apartment, Building, UserApartment, Yard
from uk_management_bot.database.models.monitored_group import GROUP_KIND_STAFF
from uk_management_bot.database.session import run_db
from uk_management_bot.handlers.requests.create_elevator import (
    ElevatorOption,
    load_elevator_step,
    parse_int,
    to_option,
)
from uk_management_bot.handlers.requests.elevator_works_block import (
    WorksBlock,
    works_blocked_sync,
    works_blocked_text,
)
from uk_management_bot.keyboards.elevators import (
    build_group_elevator_operational_keyboard,
    build_group_elevator_pick_keyboard,
)
from uk_management_bot.keyboards.group_intake import build_options_keyboard
from uk_management_bot.services.elevator_service import (
    ELEVATOR_CATEGORY,
    ElevatorValidationError,
    ensure_elevator_usable_sync,
    is_under_works,
    status_label,
)
from uk_management_bot.services.group_intake import pending
from uk_management_bot.services.group_intake.links import bot_link
from uk_management_bot.services.request_address import format_building_address
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

PHASE_BUILDING = "elevator_building"
PHASE_PICK = "elevator_pick"
PHASE_OPERATIONAL = "elevator_operational"
ELEVATOR_PHASES = frozenset({PHASE_BUILDING, PHASE_PICK, PHASE_OPERATIONAL})

# Поля кандидата, которыми владеет фаза лифта.
FIELD_PHASE = "phase"
FIELD_DEADLINE = "phase_deadline"
FIELD_BUILDING_OPTIONS = "building_options"
FIELD_BUILDING_ID = "elevator_building_id"
FIELD_ELEVATOR_ID = "elevator_id"
FIELD_ENTRANCE = "elevator_entrance"
FIELD_NUMBER = "elevator_number"
FIELD_OPERATIONAL = "elevator_operational"

# Ждём ответа автора (дом → лифт → «работает?») с момента «Да».
ELEVATOR_ANSWER_TIMEOUT = 30 * 60
# Запас Redis-TTL сверх дедлайна: проснувшийся таймер ещё застаёт кандидата и
# редактирует промпт; нажатие в окне grace ловит is_expired.
TTL_GRACE = 60
# TTL первой записи фазы (на «Да»); дальше — остаток до дедлайна + grace.
ELEVATOR_PHASE_TTL = ELEVATOR_ANSWER_TIMEOUT + TTL_GRACE
# Домов двора в выборе (staff — справочник целиком может быть большим).
_MAX_BUILDING_OPTIONS = 8
# action-части callback_data (после ``gint:``).
_ACTION_BUILDING = "bld:"
_ACTION_ELEVATOR = "elv:"
_ACTION_OPERATIONAL = "op:"
_TEXT = "group_intake.elevator."


@dataclass(frozen=True)
class GroupElevatorStep:
    """Что показать после «Да»: ``building`` (уточнить дом) | ``none`` (лифтов
    нет) | ``auto`` (лифт выбран) | ``ok`` (выбор лифта). ``address`` — адрес
    после (авто)уточнения дома, им заменяется ``selected_address``."""

    verdict: str
    address: dict
    building_id: Optional[int] = None
    options: tuple[ElevatorOption, ...] = ()
    auto: Optional[ElevatorOption] = None
    dispatch_phone: str = ""
    building_options: tuple[dict, ...] = ()
    # Р18a: автолифт под работами И запрет включён.
    works_blocked: bool = False


# ══════════════════════════════════════════════════════════════════════════
# Предикаты и дедлайн (без БД)
# ══════════════════════════════════════════════════════════════════════════


def is_group_elevator_flow(candidate: dict) -> bool:
    """Фаза лифта — только для категории «лифт» при включённом флаге."""
    return bool(settings.ELEVATORS_ENABLED) and candidate.get("category") == ELEVATOR_CATEGORY


def is_staff_candidate(candidate: dict) -> bool:
    """Staff-группа = персонал: тот же признак, что даёт менеджерскую приёмку."""
    return candidate.get("kind") == GROUP_KIND_STAFF


def blocks_under_works(candidate: dict) -> bool:
    """Р18 применяется только к жилой группе (самообслуживание)."""
    return not is_staff_candidate(candidate)


def is_elevator_action(action: str) -> bool:
    return action.startswith((_ACTION_BUILDING, _ACTION_ELEVATOR, _ACTION_OPERATIONAL))


def parse_operational(candidate: dict, action: str) -> Optional[bool]:
    """``op:1|0`` в фазе «работает?» → bool; иначе None (crafted / не та фаза)."""
    if candidate.get(FIELD_PHASE) != PHASE_OPERATIONAL:
        return None
    value = action[len(_ACTION_OPERATIONAL):]
    if value not in ("0", "1"):
        return None
    return value == "1"


def _now() -> float:
    return time.time()


def _deadline_of(candidate: dict) -> Optional[float]:
    deadline = candidate.get(FIELD_DEADLINE)
    return float(deadline) if isinstance(deadline, (int, float)) else None


def is_expired(candidate: dict) -> bool:
    """Нажатие после дедлайна фазы — «устарело», даже если запись ещё жива (grace)."""
    deadline = _deadline_of(candidate)
    return deadline is not None and _now() > deadline


def _phase_ttl(payload: dict) -> int:
    """Redis-TTL записи фазы: остаток до дедлайна + grace; окно не продлевается."""
    deadline = _deadline_of(payload)
    remaining = ELEVATOR_ANSWER_TIMEOUT if deadline is None else deadline - _now()
    return max(1, int(remaining)) + TTL_GRACE


# ══════════════════════════════════════════════════════════════════════════
# Sync-юниты (run_db)
# ══════════════════════════════════════════════════════════════════════════


def _building_option(address_id: int, address_type: str, building: Building) -> dict:
    label = format_building_address(building)
    return {"type": address_type, "id": address_id, "label_public": label, "label_full": label}


def _resident_building_options(db: Session, user_db_id: int, yard_id: int) -> list[dict]:
    """Дома двора, где у автора есть approved-квартира; по дому — одна квартира
    (primary → свежая), адрес заявки станет квартирным (подъезд известен)."""
    rows = db.execute(
        select(Apartment, UserApartment)
        .join(UserApartment, UserApartment.apartment_id == Apartment.id)
        .join(Apartment.building)
        .join(Building.yard)
        .options(contains_eager(Apartment.building).contains_eager(Building.yard))
        .where(
            UserApartment.user_id == user_db_id,
            UserApartment.status == "approved",
            Apartment.is_active.is_(True),
            Building.is_active.is_(True),
            Building.yard_id == yard_id,
        )
        .order_by(
            UserApartment.is_primary.desc(), UserApartment.requested_at.desc(), UserApartment.id.desc()
        )
    ).all()
    by_building: dict[int, dict] = {}
    for apartment, _link in rows:
        if apartment.building_id not in by_building:
            by_building[apartment.building_id] = _building_option(
                apartment.id, "apartment", apartment.building
            )
    return sorted(by_building.values(), key=lambda option: option["label_public"])


def _staff_building_options(db: Session, yard_id: int) -> list[dict]:
    """Staff-репорт: дома двора из справочника (принадлежность не требуется)."""
    rows = db.execute(
        select(Building)
        .join(Building.yard)
        .options(contains_eager(Building.yard))
        .where(Building.yard_id == yard_id, Building.is_active.is_(True), Yard.is_active.is_(True))
        .order_by(Building.address)
        .limit(_MAX_BUILDING_OPTIONS)
    ).scalars().all()
    return [_building_option(building.id, "building", building) for building in rows]


def _yard_building_options(
    db: Session, candidate: dict, user_db_id: Optional[int], yard_id: int
) -> list[dict]:
    if is_staff_candidate(candidate):
        return _staff_building_options(db, yard_id)
    if user_db_id is None:
        return []  # житель без внутреннего id — домов не подобрать
    return _resident_building_options(db, user_db_id, yard_id)


def _step_data(address: dict) -> dict:
    """``selected_address`` → ``data`` в форме FSM для ``load_elevator_step``."""
    if address["type"] == "apartment":
        return {"address_type": "apartment", "apartment_id": address["id"]}
    return {"address_type": address["type"], "address_id": address["id"]}


def load_group_elevator_step_sync(
    db: Session, candidate: dict, user_db_id: Optional[int]
) -> GroupElevatorStep:
    """Двор → дома на выбор (один — берётся сразу); дом/квартира → лифты."""
    address = candidate["selected_address"]
    if address["type"] == "yard":
        options = _yard_building_options(db, candidate, user_db_id, address["id"])
        if len(options) != 1:
            return GroupElevatorStep("building", address, building_options=tuple(options))
        address = options[0]
    step = load_elevator_step(
        db, _step_data(address), blocks_under_works=blocks_under_works(candidate)
    )
    return GroupElevatorStep(
        step.verdict, address, step.building_id, step.options, step.auto, step.dispatch_phone,
        works_blocked=step.works_blocked,
    )


def pick_group_elevator_sync(
    db: Session, building_id: Optional[int], elevator_id: int, *, blocks: bool = True
) -> tuple[Optional[ElevatorOption], bool, str]:
    """Лифт по id из callback (введённый и ТОГО дома) + вердикт Р18a + телефон.

    ``blocks=False`` — staff-группа (персонал): не блокируем и конфиг не читаем.
    Конфиг и телефон вообще читаются только когда лифт под работами.
    """
    if building_id is None:
        return (None, False, "")
    try:
        elevator = ensure_elevator_usable_sync(db, elevator_id, building_id=building_id)
    except ElevatorValidationError as exc:
        logger.info("group_intake.elevator: лифт %s отклонён для дома %s: %s",
                    elevator_id, building_id, exc)
        return (None, False, "")
    option = to_option(elevator)
    blocked, phone = works_blocked_sync(db, option.status) if blocks else (False, "")
    return (option, blocked, phone)


# ══════════════════════════════════════════════════════════════════════════
# Async: показ шагов (кандидат — под тем же ключом)
# ══════════════════════════════════════════════════════════════════════════


def _phase_payload(candidate: dict, **changes) -> dict:
    """Новый payload кандидата без ``v`` (версию ставит store_candidate)."""
    base = {key: value for key, value in candidate.items() if key != "v"}
    return {**base, **changes}


def _none_text(step: GroupElevatorStep, lang: str) -> str:
    if step.verdict != "none":
        return get_text(_TEXT + "no_buildings", language=lang)
    if step.dispatch_phone:
        return get_text(_TEXT + "none_in_building_phone", language=lang,
                        phone=html.escape(step.dispatch_phone))
    return get_text(_TEXT + "none_in_building", language=lang)


def _need_building_text(step: GroupElevatorStep, lang: str) -> str:
    text = get_text(_TEXT + "need_building", language=lang)
    if len(step.building_options) >= _MAX_BUILDING_OPTIONS:
        # Список упёрся в кап — нужного дома в нём может не быть.
        text += get_text(_TEXT + "need_building_more", language=lang)
    return text


async def _finish_without_request(callback: CallbackQuery, text: str) -> None:
    """Фаза закончилась без заявки: кандидат снят, таймер отменён, промпт — текст."""
    chat_id, message_id = callback.message.chat.id, callback.message.message_id
    await pending.pop_candidate(chat_id, message_id)
    cancel_elevator_timeout(chat_id, message_id)
    await callback.message.edit_text(text)


async def reject_expired(callback: CallbackQuery, lang: str) -> None:
    """Нажатие после дедлайна: «устарело», заявки нет."""
    await _finish_without_request(callback, get_text("group_intake.expired", language=lang))


async def _store_phase(callback: CallbackQuery, payload: dict, lang: str) -> bool:
    """Сохранить фазу под ключом промпта с TTL до дедлайна; сбой → «устарело»."""
    stored = await pending.store_candidate(
        callback.message.chat.id, callback.message.message_id, payload, ttl=_phase_ttl(payload),
    )
    if not stored:
        await reject_expired(callback, lang)
    return stored


def _blocked_text(option: ElevatorOption, dispatch_phone: str, lang: str) -> str:
    return works_blocked_text(
        WorksBlock(
            entrance=option.entrance, number=option.number, status=option.status,
            status_since=option.status_since, dispatch_phone=dispatch_phone,
        ),
        lang,
    )


async def _show_operational(
    callback: CallbackQuery, base: dict, option: ElevatorOption, lang: str,
    *, works_blocked: bool = False, dispatch_phone: str = "",
) -> bool:
    """Зафиксировать лифт в кандидате и спросить «работает?».

    Р18: пока запрет включён, по лифту в работах заявка самообслуживания не
    создаётся — отвечаем в группу блокирующим текстом и снимаем кандидата.
    Запрет выключен — прежняя мягкая подсказка перед вопросом.
    """
    if works_blocked:
        await _finish_without_request(callback, _blocked_text(option, dispatch_phone, lang))
        return False
    payload = _phase_payload(base, **{
        FIELD_PHASE: PHASE_OPERATIONAL, FIELD_BUILDING_OPTIONS: None,
        FIELD_ELEVATOR_ID: option.id, FIELD_ENTRANCE: option.entrance, FIELD_NUMBER: option.number,
    })
    if not await _store_phase(callback, payload, lang):
        return False
    text = get_text(_TEXT + "operational_prompt", language=lang,
                    entrance=option.entrance, elevator=option.number)
    if is_under_works(option.status):
        # Запрет выключен тумблером — прежняя мягкая подсказка (Р18a).
        hint = get_text(_TEXT + "works_hint", language=lang,
                        status=html.escape(status_label(option.status, lang)))
        text = f"{hint}\n{text}"
    await callback.message.edit_text(
        text, reply_markup=build_group_elevator_operational_keyboard(lang)
    )
    return True


async def _show_building_choice(
    callback: CallbackQuery, candidate: dict, step: GroupElevatorStep, lang: str
) -> bool:
    if not step.building_options:
        await _finish_without_request(callback, _none_text(step, lang))
        return False
    payload = _phase_payload(candidate, **{
        FIELD_PHASE: PHASE_BUILDING, FIELD_BUILDING_OPTIONS: list(step.building_options),
    })
    if not await _store_phase(callback, payload, lang):
        return False
    await callback.message.edit_text(
        _need_building_text(step, lang),
        reply_markup=build_options_keyboard(step.building_options, f"gint:{_ACTION_BUILDING}"),
    )
    return True


async def _apply_step(
    callback: CallbackQuery, candidate: dict, step: GroupElevatorStep, lang: str
) -> bool:
    """Показать шаг по вердикту; True — ждём ответа автора (кандидат в фазе)."""
    if step.verdict == "building":
        return await _show_building_choice(callback, candidate, step, lang)
    if step.verdict not in ("auto", "ok"):
        await _finish_without_request(callback, _none_text(step, lang))
        return False
    base = _phase_payload(candidate, **{
        "selected_address": step.address, FIELD_BUILDING_ID: step.building_id,
        FIELD_BUILDING_OPTIONS: None,
    })
    if step.verdict == "auto":
        return await _show_operational(
            callback, base, step.auto, lang,
            works_blocked=step.works_blocked, dispatch_phone=step.dispatch_phone,
        )
    if not await _store_phase(callback, {**base, FIELD_PHASE: PHASE_PICK}, lang):
        return False
    await callback.message.edit_text(
        get_text(_TEXT + "pick_prompt", language=lang),
        reply_markup=build_group_elevator_pick_keyboard(step.options, lang),
    )
    return True


# ══════════════════════════════════════════════════════════════════════════
# Async: точки входа из group_intake_callback
# ══════════════════════════════════════════════════════════════════════════


async def start_elevator_phase(
    callback: CallbackQuery, bot: Bot, candidate: dict, user_db_id: int, lang: str,
    *, _db=None,
) -> None:
    """После «Да» и ре-гейта: дедлайн, шаг, таймер ожидания."""
    step = await run_db(
        lambda s: load_group_elevator_step_sync(s, candidate, user_db_id), db=_db
    )
    armed = {**candidate, FIELD_DEADLINE: int(_now()) + ELEVATOR_ANSWER_TIMEOUT}
    if await _apply_step(callback, armed, step, lang):
        schedule_elevator_timeout(
            bot, callback.message.chat.id, callback.message.message_id, lang
        )


async def handle_building_pick(
    callback: CallbackQuery, candidate: dict, action: str, lang: str, *, _db=None
) -> None:
    """``gint:bld:<n>`` — индекс в серверном списке домов; id клиент не шлёт."""
    if candidate.get(FIELD_PHASE) != PHASE_BUILDING:
        return
    options = candidate.get(FIELD_BUILDING_OPTIONS) or []
    index = parse_int(action[len(_ACTION_BUILDING):])
    if index is None or not 0 <= index < len(options):
        return
    narrowed = {**candidate, "selected_address": options[index]}
    step = await run_db(lambda s: load_group_elevator_step_sync(s, narrowed, None), db=_db)
    await _apply_step(callback, candidate, step, lang)


async def handle_elevator_pick(
    callback: CallbackQuery, candidate: dict, action: str, lang: str, *, _db=None
) -> None:
    """``gint:elv:{id}`` — лифт проверяется сервером по дому из кандидата."""
    if candidate.get(FIELD_PHASE) != PHASE_PICK:
        return
    elevator_id = parse_int(action[len(_ACTION_ELEVATOR):])
    if elevator_id is None:
        return
    option, works_blocked, dispatch_phone = await run_db(
        lambda s: pick_group_elevator_sync(
            s, candidate.get(FIELD_BUILDING_ID), elevator_id,
            blocks=blocks_under_works(candidate),
        ),
        db=_db,
    )
    if option is None:
        return
    await _show_operational(
        callback, candidate, option, lang,
        works_blocked=works_blocked, dispatch_phone=dispatch_phone,
    )


# ══════════════════════════════════════════════════════════════════════════
# Таймаут ожидания ответа
# ══════════════════════════════════════════════════════════════════════════

_timeout_tasks: dict[tuple[int, int], asyncio.Task] = {}


def _forget_task(key: tuple[int, int], task: asyncio.Task) -> None:
    if _timeout_tasks.get(key) is task:
        del _timeout_tasks[key]


def schedule_elevator_timeout(bot: Bot, chat_id: int, message_id: int, lang: str) -> asyncio.Task:
    """One-shot задача по ключу промпта; реестр держит ссылку до завершения."""
    key = (chat_id, message_id)
    task = asyncio.create_task(_expire_elevator_prompt(bot, chat_id, message_id, lang))
    _timeout_tasks[key] = task
    task.add_done_callback(lambda done: _forget_task(key, done))
    return task


def cancel_elevator_timeout(chat_id: int, message_id: int) -> bool:
    """Ответ пришёл (или фаза закрыта) — таймер больше не нужен. True = отменён."""
    task = _timeout_tasks.pop((chat_id, message_id), None)
    if task is None:
        return False
    task.cancel()
    return True


async def _expire_elevator_prompt(bot: Bot, chat_id: int, message_id: int, lang: str) -> None:
    """Нет ответа за таймаут → кандидат снят (GETDEL), промпт: «не оформлена»."""
    await asyncio.sleep(ELEVATOR_ANSWER_TIMEOUT)
    candidate = await pending.get_candidate(chat_id, message_id)
    if candidate is None or candidate.get(FIELD_PHASE) not in ELEVATOR_PHASES:
        return
    if await pending.pop_candidate(chat_id, message_id) is None:
        return  # ответ успел прийти параллельно — заявку создаёт он
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=get_text(_TEXT + "timeout", language=lang, link=bot_link()),
        )
    except TelegramAPIError as exc:
        logger.debug("group_intake.elevator: промпт таймаута не отредактирован: %s",
                     type(exc).__name__)
