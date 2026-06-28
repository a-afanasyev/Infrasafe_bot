"""Раздел «Контроль доступа» для жителя (applicant) — ТЗ §4(п.4), §6.4, §16.2.

Бот без бизнес-логики (§4.4): хендлеры лишь собирают ввод и зовут общий слой
``access_control.services.resident`` НА СВОЕЙ sync-сессии БД (общая база). Проверки
владения квартирой/зоной и аудит (§9.7) делает сервис — тот же, что и REST/TWA
(единый API §4 п.4-5). Граница доступа (§6.4): только роль ``applicant`` и только
свои ``approved``-квартиры; чужая квартира/пропуск → доменное исключение сервиса →
понятная ошибка пользователю. ПД (номера/адреса) в логи НЕ пишем (§11).

Меню: «Мои авто», «Подать заявку на авто», «Мои заявки», «Заказать пропуск»,
«Мои пропуска» (+отмена), «Проезды».

НЕ здесь (отдельная фаза): уведомления manager→житель о решении по заявке
(кросс-сервис) — см. TODO в _finalize_vehicle_request; клавиатуры охраны; одноразовые коды.
"""
from __future__ import annotations

import datetime as dt
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.orm import Session

from access_control.services.resident import (
    ApartmentNotOwned,
    DecisionNotFound,
    EntryNotOwned,
    PassNotFound,
    PassNotOwned,
    ZoneNotResolved,
    approved_apartments,
    cancel_resident_pass,
    confirm_disputed_entry,
    create_resident_pass,
    create_resident_request,
    list_resident_events,
    list_resident_passes,
    list_resident_requests,
    list_resident_vehicles,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.states.access_control import (
    PassOrderStates,
    VehicleRequestStates,
)
from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.utils.button_texts import get_access_control_texts
from uk_management_bot.utils.helpers import get_text

router = Router()
logger = logging.getLogger(__name__)

# Тексты кнопки главного меню (для F.text.in_()), все языки.
ACCESS_CONTROL_TEXTS = get_access_control_texts()

RESIDENT_ROLE = "applicant"
PASS_TYPES = ("taxi", "guest", "delivery")
RELATION_TYPES = ("owner", "tenant", "family", "service")
# Пресеты срока действия пропуска: суффикс callback → часы (§6.4 — temporary pass).
PASS_DURATIONS: dict[str, int] = {"2h": 2, "6h": 6, "24h": 24, "72h": 72}

_PLATE_MAX_LEN = 32
_EVENTS_LIMIT = 10


# --------------------------- резолв / клавиатуры ---------------------------


def _resolve_resident(db: Session, telegram_id: int) -> User | None:
    """Пользователь по telegram_id с ролью applicant (§6.4). Иначе None.

    Роли читаем из ``user.roles`` (JSON-массив) через ``parse_roles_safe`` —
    устаревшее ``user.role`` не используем (CLAUDE.md).
    """
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user is None:
        return None
    if RESIDENT_ROLE not in parse_roles_safe(user.roles):
        return None
    return user


def _menu_keyboard(language: str):
    kb = InlineKeyboardBuilder()
    kb.button(text=get_text("access_control.btn_vehicles", language=language),
              callback_data="ac_menu:vehicles")
    kb.button(text=get_text("access_control.btn_new_vehicle", language=language),
              callback_data="ac_menu:new_vehicle")
    kb.button(text=get_text("access_control.btn_requests", language=language),
              callback_data="ac_menu:requests")
    kb.button(text=get_text("access_control.btn_order_pass", language=language),
              callback_data="ac_menu:order_pass")
    kb.button(text=get_text("access_control.btn_passes", language=language),
              callback_data="ac_menu:passes")
    kb.button(text=get_text("access_control.btn_events", language=language),
              callback_data="ac_menu:events")
    kb.adjust(2)
    return kb.as_markup()


def _relation_keyboard(language: str):
    kb = InlineKeyboardBuilder()
    for rel in RELATION_TYPES:
        kb.button(text=get_text(f"access_control.relation.{rel}", language=language),
                  callback_data=f"ac_rel:{rel}")
    kb.adjust(2)
    return kb.as_markup()


def _pass_type_keyboard(language: str):
    kb = InlineKeyboardBuilder()
    for pt in PASS_TYPES:
        kb.button(text=get_text(f"access_control.pass_type.{pt}", language=language),
                  callback_data=f"ac_pass_type:{pt}")
    kb.adjust(3)
    return kb.as_markup()


def _skip_plate_keyboard(language: str):
    kb = InlineKeyboardBuilder()
    kb.button(text=get_text("access_control.btn_skip_plate", language=language),
              callback_data="ac_pass_skip_plate")
    kb.adjust(1)
    return kb.as_markup()


def _duration_keyboard(language: str):
    kb = InlineKeyboardBuilder()
    for key in PASS_DURATIONS:
        kb.button(text=get_text(f"access_control.duration.{key}", language=language),
                  callback_data=f"ac_pass_dur:{key}")
    kb.adjust(2)
    return kb.as_markup()


def _apartment_keyboard(apartments: list[dict], prefix: str, language: str):
    kb = InlineKeyboardBuilder()
    for apt in apartments:
        label = get_text("access_control.apartment_label", language=language,
                         number=apt.get("apartment_number"))
        kb.button(text=label, callback_data=f"{prefix}:{apt['id']}")
    kb.adjust(1)
    return kb.as_markup()


# --------------------------- entry / меню ---------------------------


@router.message(F.text.in_(ACCESS_CONTROL_TEXTS))
async def access_control_entry(message: Message, state: FSMContext, db: Session,
                               language: str = "ru"):
    """Открыть меню контроля доступа (только applicant — §6.4)."""
    await state.clear()
    user = _resolve_resident(db, message.from_user.id)
    if user is None:
        await message.answer(get_text("access_control.not_resident", language=language))
        return
    await message.answer(
        get_text("access_control.menu_title", language=language),
        reply_markup=_menu_keyboard(language),
    )


# --------------------------- READ-списки ---------------------------


@router.callback_query(F.data == "ac_menu:vehicles")
async def ac_vehicles(callback: CallbackQuery, db: Session, language: str = "ru"):
    user = _resolve_resident(db, callback.from_user.id)
    if user is None:
        await callback.answer(get_text("access_control.not_resident", language=language),
                              show_alert=True)
        return
    rows, _total = list_resident_vehicles(db, user_id=user.id)
    await callback.message.answer(_render_vehicles(rows, language))
    await callback.answer()


@router.callback_query(F.data == "ac_menu:requests")
async def ac_requests(callback: CallbackQuery, db: Session, language: str = "ru"):
    user = _resolve_resident(db, callback.from_user.id)
    if user is None:
        await callback.answer(get_text("access_control.not_resident", language=language),
                              show_alert=True)
        return
    rows, _total = list_resident_requests(db, user_id=user.id)
    await callback.message.answer(_render_requests(rows, language))
    await callback.answer()


@router.callback_query(F.data == "ac_menu:passes")
async def ac_passes(callback: CallbackQuery, db: Session, language: str = "ru"):
    user = _resolve_resident(db, callback.from_user.id)
    if user is None:
        await callback.answer(get_text("access_control.not_resident", language=language),
                              show_alert=True)
        return
    rows, _total = list_resident_passes(db, user_id=user.id)
    markup = _passes_cancel_keyboard(rows, language)
    await callback.message.answer(_render_passes(rows, language), reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "ac_menu:events")
async def ac_events(callback: CallbackQuery, db: Session, language: str = "ru"):
    user = _resolve_resident(db, callback.from_user.id)
    if user is None:
        await callback.answer(get_text("access_control.not_resident", language=language),
                              show_alert=True)
        return
    rows, _total = list_resident_events(db, user_id=user.id, limit=_EVENTS_LIMIT)
    await callback.message.answer(_render_events(rows, language))
    await callback.answer()


# --------------------------- FSM: заявка на авто ---------------------------


@router.callback_query(F.data == "ac_menu:new_vehicle")
async def ac_new_vehicle(callback: CallbackQuery, state: FSMContext, db: Session,
                         language: str = "ru"):
    user = _resolve_resident(db, callback.from_user.id)
    if user is None:
        await callback.answer(get_text("access_control.not_resident", language=language),
                              show_alert=True)
        return
    apartments = approved_apartments(db, user.id)
    if not apartments:
        await callback.answer(get_text("access_control.no_apartments", language=language),
                              show_alert=True)
        return
    await state.update_data(apartments=apartments)
    await callback.message.answer(get_text("access_control.vehicle.ask_plate", language=language))
    await state.set_state(VehicleRequestStates.waiting_for_plate)
    await callback.answer()


@router.message(VehicleRequestStates.waiting_for_plate, F.text)
async def ac_vehicle_plate(message: Message, state: FSMContext, language: str = "ru"):
    plate = (message.text or "").strip()
    if not plate or len(plate) > _PLATE_MAX_LEN:
        await message.answer(get_text("access_control.vehicle.invalid_plate", language=language))
        return
    await state.update_data(plate=plate)
    await message.answer(
        get_text("access_control.vehicle.ask_relation", language=language),
        reply_markup=_relation_keyboard(language),
    )
    await state.set_state(VehicleRequestStates.waiting_for_relation)


@router.callback_query(F.data.startswith("ac_rel:"), VehicleRequestStates.waiting_for_relation)
async def ac_vehicle_relation(callback: CallbackQuery, state: FSMContext, db: Session,
                              language: str = "ru"):
    relation = callback.data.split(":", 1)[1]
    if relation not in RELATION_TYPES:
        await callback.answer()
        return
    await state.update_data(relation=relation)
    data = await state.get_data()
    apartments = data.get("apartments", [])
    if len(apartments) == 1:
        await _finalize_vehicle_request(
            callback.message, state, db,
            apartment_id=apartments[0]["id"], telegram_id=callback.from_user.id,
            language=language,
        )
    else:
        await callback.message.answer(
            get_text("access_control.choose_apartment", language=language),
            reply_markup=_apartment_keyboard(apartments, "ac_veh_apt", language),
        )
        await state.set_state(VehicleRequestStates.waiting_for_apartment)
    await callback.answer()


@router.callback_query(F.data.startswith("ac_veh_apt:"), VehicleRequestStates.waiting_for_apartment)
async def ac_vehicle_apartment(callback: CallbackQuery, state: FSMContext, db: Session,
                               language: str = "ru"):
    apartment_id = int(callback.data.split(":", 1)[1])
    await _finalize_vehicle_request(
        callback.message, state, db,
        apartment_id=apartment_id, telegram_id=callback.from_user.id, language=language,
    )
    await callback.answer()


async def _finalize_vehicle_request(message: Message, state: FSMContext, db: Session, *,
                                    apartment_id: int, telegram_id: int, language: str):
    data = await state.get_data()
    plate = data.get("plate")
    relation = data.get("relation")
    user = _resolve_resident(db, telegram_id)
    if user is None or not plate:
        await message.answer(get_text("access_control.error", language=language))
        await state.clear()
        return
    try:
        req = create_resident_request(
            db,
            actor_user_id=user.id,
            apartment_id=apartment_id,
            plate_number_original=plate,
            relation_type=relation,
        )
    except ApartmentNotOwned:
        await message.answer(get_text("access_control.foreign_apartment", language=language))
        await state.clear()
        return
    await state.clear()
    # TODO (отдельная фаза): уведомление менеджеру о новой заявке и обратное
    # уведомление жителю о решении — кросс-сервис, здесь не реализуется.
    await message.answer(
        get_text("access_control.vehicle.created", language=language,
                 plate=req.plate_number_normalized)
    )


# --------------------------- FSM: заказ пропуска ---------------------------


@router.callback_query(F.data == "ac_menu:order_pass")
async def ac_order_pass(callback: CallbackQuery, state: FSMContext, db: Session,
                        language: str = "ru"):
    user = _resolve_resident(db, callback.from_user.id)
    if user is None:
        await callback.answer(get_text("access_control.not_resident", language=language),
                              show_alert=True)
        return
    apartments = approved_apartments(db, user.id)
    if not apartments:
        await callback.answer(get_text("access_control.no_apartments", language=language),
                              show_alert=True)
        return
    await state.update_data(apartments=apartments)
    await callback.message.answer(
        get_text("access_control.pass.ask_type", language=language),
        reply_markup=_pass_type_keyboard(language),
    )
    await state.set_state(PassOrderStates.waiting_for_type)
    await callback.answer()


@router.callback_query(F.data.startswith("ac_pass_type:"), PassOrderStates.waiting_for_type)
async def ac_pass_type(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    pass_type = callback.data.split(":", 1)[1]
    if pass_type not in PASS_TYPES:
        await callback.answer()
        return
    await state.update_data(pass_type=pass_type)
    await callback.message.answer(
        get_text("access_control.pass.ask_plate", language=language),
        reply_markup=_skip_plate_keyboard(language),
    )
    await state.set_state(PassOrderStates.waiting_for_plate)
    await callback.answer()


@router.message(PassOrderStates.waiting_for_plate, F.text)
async def ac_pass_plate(message: Message, state: FSMContext, language: str = "ru"):
    plate = (message.text or "").strip()
    if not plate or len(plate) > _PLATE_MAX_LEN:
        await message.answer(get_text("access_control.vehicle.invalid_plate", language=language))
        return
    await state.update_data(plate=plate)
    await _ask_pass_duration(message, state, language)


@router.callback_query(F.data == "ac_pass_skip_plate", PassOrderStates.waiting_for_plate)
async def ac_pass_skip_plate(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    await state.update_data(plate=None)
    await _ask_pass_duration(callback.message, state, language)
    await callback.answer()


async def _ask_pass_duration(message: Message, state: FSMContext, language: str):
    await message.answer(
        get_text("access_control.pass.ask_duration", language=language),
        reply_markup=_duration_keyboard(language),
    )
    await state.set_state(PassOrderStates.waiting_for_valid_until)


@router.callback_query(F.data.startswith("ac_pass_dur:"), PassOrderStates.waiting_for_valid_until)
async def ac_pass_duration(callback: CallbackQuery, state: FSMContext, db: Session,
                           language: str = "ru"):
    key = callback.data.split(":", 1)[1]
    hours = PASS_DURATIONS.get(key)
    if not hours:
        await callback.answer()
        return
    await state.update_data(hours=hours)
    data = await state.get_data()
    apartments = data.get("apartments", [])
    if len(apartments) == 1:
        await _finalize_pass(
            callback.message, state, db,
            apartment_id=apartments[0]["id"], telegram_id=callback.from_user.id,
            language=language,
        )
    else:
        await callback.message.answer(
            get_text("access_control.choose_apartment", language=language),
            reply_markup=_apartment_keyboard(apartments, "ac_pass_apt", language),
        )
        await state.set_state(PassOrderStates.waiting_for_apartment)
    await callback.answer()


@router.callback_query(F.data.startswith("ac_pass_apt:"), PassOrderStates.waiting_for_apartment)
async def ac_pass_apartment(callback: CallbackQuery, state: FSMContext, db: Session,
                            language: str = "ru"):
    apartment_id = int(callback.data.split(":", 1)[1])
    await _finalize_pass(
        callback.message, state, db,
        apartment_id=apartment_id, telegram_id=callback.from_user.id, language=language,
    )
    await callback.answer()


async def _finalize_pass(message: Message, state: FSMContext, db: Session, *,
                         apartment_id: int, telegram_id: int, language: str):
    data = await state.get_data()
    pass_type = data.get("pass_type")
    plate = data.get("plate")
    hours = data.get("hours")
    user = _resolve_resident(db, telegram_id)
    if user is None or pass_type not in PASS_TYPES or not hours:
        await message.answer(get_text("access_control.error", language=language))
        await state.clear()
        return
    valid_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours)
    try:
        created = create_resident_pass(
            db,
            actor_user_id=user.id,
            apartment_id=apartment_id,
            pass_type=pass_type,
            valid_until=valid_until,
            plate_number_original=plate,
        )
    except ApartmentNotOwned:
        await message.answer(get_text("access_control.foreign_apartment", language=language))
        await state.clear()
        return
    except ZoneNotResolved:
        await message.answer(get_text("access_control.pass.zone_not_resolved", language=language))
        await state.clear()
        return
    await state.clear()
    ap = created.access_pass
    # §9.3: гостевой пропуск без номера → показываем одноразовый код РОВНО ОДИН раз
    # (житель передаёт его гостю). В БД хранится только хэш, код больше не доступен.
    if created.one_time_code is not None:
        await message.answer(
            get_text("access_control.pass.created_with_code", language=language,
                     until=_fmt_dt(ap.valid_until), code=created.one_time_code)
        )
        return
    await message.answer(
        get_text("access_control.pass.created", language=language,
                 type=get_text(f"access_control.pass_type.{ap.pass_type}", language=language),
                 until=_fmt_dt(ap.valid_until))
    )


# --------------------------- отмена пропуска ---------------------------


@router.callback_query(F.data.startswith("ac_cancel_pass:"))
async def ac_cancel_pass(callback: CallbackQuery, db: Session, language: str = "ru"):
    user = _resolve_resident(db, callback.from_user.id)
    if user is None:
        await callback.answer(get_text("access_control.not_resident", language=language),
                              show_alert=True)
        return
    pass_id = int(callback.data.split(":", 1)[1])
    try:
        cancel_resident_pass(db, actor_user_id=user.id, pass_id=pass_id)
    except PassNotFound:
        await callback.answer(get_text("access_control.pass.not_found", language=language),
                              show_alert=True)
        return
    except PassNotOwned:
        await callback.answer(get_text("access_control.foreign_pass", language=language),
                              show_alert=True)
        return
    await callback.answer(get_text("access_control.pass.cancelled", language=language),
                          show_alert=True)


# --------------------------- спорный въезд (§9.4) ---------------------------
#
# Бот шлёт жителю уведомление о спорном въезде с кнопками «Подтвердить/Отклонить»
# (см. services/access_notify_subscriber.build_reply_markup, callback_data
# ``acc_dispute:{decision_id}:{confirm|deny}``). Нажатие фиксируется ОБЩИМ сервисом
# ``confirm_disputed_entry`` на своей sync-сессии. Ответ СОВЕЩАТЕЛЬНЫЙ (§9.5): бот
# шлагбаум НЕ открывает, только фиксирует мнение жителя. Идемпотентно: повтор —
# upsert последнего ответа в сервисе. ПД (номер) в логи не пишем (§11).

_DISPUTE_RESPONSES = ("confirm", "deny")


@router.callback_query(F.data.startswith("acc_dispute:"))
async def ac_dispute_response(callback: CallbackQuery, db: Session, language: str = "ru"):
    """Зафиксировать ответ жителя на спорный въезд (§6.4, §9.4). Идемпотентно."""
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[2] not in _DISPUTE_RESPONSES:
        await callback.answer()
        return
    response = parts[2]
    try:
        decision_id = int(parts[1])
    except ValueError:
        await callback.answer()
        return

    user = _resolve_resident(db, callback.from_user.id)
    if user is None:
        await callback.answer(
            get_text("access_control.not_resident", language=language), show_alert=True
        )
        return

    try:
        confirm_disputed_entry(
            db, actor_user_id=user.id, decision_id=decision_id, response=response
        )
    except (DecisionNotFound, EntryNotOwned):
        # Чужой/недоступный въезд — не раскрываем детали, чужое сообщение не правим.
        await callback.answer(
            get_text("access_control.dispute.error", language=language), show_alert=True
        )
        return
    except Exception:  # noqa: BLE001 — сбой сервиса не должен ронять хендлер
        logger.warning("disputed entry response failed (no PD)")
        await callback.answer(
            get_text("access_control.error", language=language), show_alert=True
        )
        return

    answered = get_text(
        f"access_control.dispute.answered_{response}", language=language
    )
    await callback.answer(answered)
    # Правим сообщение и убираем клавиатуру (edit_text без reply_markup снимает кнопки).
    try:
        await callback.message.edit_text(answered)
    except Exception:  # noqa: BLE001 — сообщение могло устареть/быть недоступно
        pass


# --------------------------- рендер (без ПД в логах) ---------------------------


def _fmt_dt(value: dt.datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


def _render_vehicles(rows: list[dict], language: str) -> str:
    if not rows:
        return get_text("access_control.vehicles_empty", language=language)
    lines = [get_text("access_control.vehicles_title", language=language)]
    for r in rows:
        plate = r.get("plate_number_normalized") or r.get("plate_number_original") or "—"
        make = " ".join(p for p in (r.get("make"), r.get("color")) if p)
        status = r.get("status") or "—"
        suffix = f" — {make}" if make else ""
        lines.append(f"• {plate}{suffix} ({status})")
    return "\n".join(lines)


def _render_requests(rows: list[dict], language: str) -> str:
    if not rows:
        return get_text("access_control.requests_empty", language=language)
    lines = [get_text("access_control.requests_title", language=language)]
    for r in rows:
        plate = r.get("plate_number_normalized") or "—"
        status = r.get("status") or "—"
        lines.append(f"• {plate} — {status}")
    return "\n".join(lines)


def _render_passes(rows: list[dict], language: str) -> str:
    if not rows:
        return get_text("access_control.passes_empty", language=language)
    lines = [get_text("access_control.passes_title", language=language)]
    for r in rows:
        pt = get_text(f"access_control.pass_type.{r.get('pass_type')}", language=language)
        plate = r.get("plate_number_normalized") or "—"
        status = r.get("status") or "—"
        until = _fmt_dt(r.get("valid_until"))
        lines.append(f"• {pt} {plate} — {status} (до {until})")
    return "\n".join(lines)


def _passes_cancel_keyboard(rows: list[dict], language: str):
    active = [r for r in rows if r.get("status") == "active"]
    if not active:
        return None
    kb = InlineKeyboardBuilder()
    for r in active:
        plate = r.get("plate_number_normalized") or str(r.get("id"))
        kb.button(
            text=get_text("access_control.btn_cancel_pass", language=language, plate=plate),
            callback_data=f"ac_cancel_pass:{r['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def _render_events(rows: list[dict], language: str) -> str:
    if not rows:
        return get_text("access_control.events_empty", language=language)
    lines = [get_text("access_control.events_title", language=language)]
    for r in rows:
        when = _fmt_dt(r.get("occurred_at"))
        direction = get_text(f"access_control.direction.{r.get('direction')}", language=language)
        decision = r.get("decision") or "—"
        lines.append(f"• {when} — {direction} — {decision}")
    return "\n".join(lines)
