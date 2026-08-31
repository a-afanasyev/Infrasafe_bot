"""Менеджер: смена исполнителя уже назначенной заявки (канон MANAGER_ASSIGN).

Почему отдельный модуль, а не довесок к ``assignment.py``: тот пишет мимо
канона исторически, а здесь — три фазы вокруг ``run_command_sync``, и мешать
их в одном файле значило бы прятать разницу.

ТРИ ФАЗЫ — не стилистика, а условие корректности.

``run_command_sync`` открывает СВОЮ сессию (FOR UPDATE + patch/audit/outbox в
одной транзакции). Если звать его внутри ``run_db``-юнита, а следом в той же
фазе собирать уведомления на той же внешней сессии, то identity map вернёт УЖЕ
ЗАГРУЖЕННЫЙ инстанс заявки со старыми атрибутами: получателем «вам назначена
заявка» окажется снятый исполнитель, а новый не узнает ничего. Ровно то, что
запрещает докстринг ``CommandOutcome``: «Адаптер строит ответ/UI/уведомления ИЗ
него, НЕ перечитывая stale-объекты своей внешней сессии».

СНЯТЫЙ ИСПОЛНИТЕЛЬ БЕРЁТСЯ ПОСЛЕ КОМАНДЫ. Преflight не годится источником:
между фазами другой менеджер успевает назначить B вместо A, наша команда
заменит B на C, а «вас сняли» уехало бы A. Единственная истина о том, кого
фактически сняли, — снимок под FOR UPDATE внутри самой команды,
``outcome.old_state.executor_id``.

Отсюда же следует, что ``same_executor`` из преflight'а — только UX-защита.
Гарантированный отказ живёт в ядре (BUG-180): ``plan_transition`` под тем же
локом бросает ``SameExecutor``, и хендлер показывает тот же честный текст.
Корректность уведомлений от этого не зависит: решение шлём/не шлём принимается
по факту из ``old_state``.
"""
from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass, field
from typing import Optional

from aiogram import F
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

from uk_management_bot.constants.categories import get_specialization_for_category
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db
from uk_management_bot.keyboards.admin import get_executors_by_category_keyboard
from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.services.request_number_service import REQUEST_NUMBER_CORE
from uk_management_bot.utils.auth_helpers import (
    get_user_roles,
    has_admin_access,
    has_manager_role,
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.specializations import (
    matches_required_specs,
    parse_specializations,
)
from uk_management_bot.utils.user_names import display_name
from uk_management_bot.utils.workflow_predicates import is_reassignable

from ._router import router

logger = logging.getLogger(__name__)

# Префиксы. Взаимно непересекающиеся startswith; коммит-вход — строгий регекс,
# иначе он подошёл бы под собственный `req_reassign_to_` у чужих данных
# (урок BUG-179: открытый префикс перехватывает соседей).
MENU_PREFIX = "req_reassign_menu_"
DUTY_PREFIX = "req_reassign_duty_"
PICK_PREFIX = "req_reassign_pick_"
TO_PREFIX = "req_reassign_to_"
TO_PATTERN = rf"^{TO_PREFIX}{REQUEST_NUMBER_CORE}_\d+$"


# ══════════════════════════════════════════════════════════════════════════
# DTO — то, что пересекает границу run_db (ORM за неё не выходит)
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Preflight:
    """Итог фазы 1. Всё здесь — только для текстов и решения «звать ли команду»."""

    verdict: str
    request_number: str = ""
    new_executor_id: Optional[int] = None
    new_executor_name: str = ""
    current_executor_name: str = ""
    assignment_kind: str = "none"  # individual | group | none
    group_label: str = ""
    specialization: Optional[str] = None


@dataclass(frozen=True)
class Aftermath:
    """Итог фазы 3 — собран на СВЕЖЕЙ сессии, уже после коммита команды."""

    messages: list = field(default_factory=list)     # [(telegram_id, text)]
    old_notice: Optional[tuple] = None               # (telegram_id, text)
    old_label: str = ""
    new_executor_name: str = ""


@dataclass(frozen=True)
class Candidate:
    """Кандидат для клавиатуры: ORM наружу не отдаём."""

    id: int
    first_name: Optional[str]
    last_name: Optional[str]
    username: Optional[str]


# ══════════════════════════════════════════════════════════════════════════
# Sync-юниты (worker-поток через run_db)
# ══════════════════════════════════════════════════════════════════════════


def _assignment_view(db: Session, request_number: str, lang: str) -> Preflight:
    """Что показывать в меню: текущее назначение + пригодность статуса."""
    svc = AdminHandlerService(db)
    request = svc.get_request_by_number(request_number)
    if not request:
        return Preflight("request_not_found")
    if not is_reassignable(request):
        return Preflight("bad_status", request_number=request_number)

    kind, current_name, group_label = "none", "", ""
    assignment = svc.get_active_assignment(request_number)
    if assignment is not None:
        if assignment.assignment_type == "individual" and assignment.executor_id:
            kind = "individual"
            executor = svc.get_user_by_id(assignment.executor_id)
            current_name = display_name(executor) or "" if executor else ""
        elif assignment.assignment_type == "group":
            kind = "group"
            group_label = _spec_label(assignment.group_specialization, lang)
    if kind == "none" and request.executor_id is not None:
        # Заявка назначена до миграции 011: активной строки RequestAssignment
        # нет, но исполнитель у заявки есть. Без этого фолбэка меню сказало бы
        # «не был назначен» о человеке, который заявку ведёт, и переназначение
        # выглядело бы первичным назначением.
        kind = "individual"
        executor = svc.get_user_by_id(request.executor_id)
        current_name = display_name(executor) or "" if executor else ""

    return Preflight(
        "ok",
        request_number=request_number,
        current_executor_name=current_name,
        assignment_kind=kind,
        group_label=group_label,
        specialization=get_specialization_for_category(request.category),
    )


def _preflight(db: Session, request_number: str, new_executor_id: int,
               lang: str) -> Preflight:
    """UX-проверки перед командой. Гонку не закрывает — см. докстринг модуля."""
    view = _assignment_view(db, request_number, lang)
    if view.verdict != "ok":
        return view

    svc = AdminHandlerService(db)
    request = svc.get_request_by_number(request_number)
    executor = svc.get_user_by_id(new_executor_id)
    if executor is None or executor.status != "approved":
        return Preflight("executor_not_found", request_number=request_number)
    if "executor" not in set(get_user_roles(executor) or []):
        return Preflight("executor_not_found", request_number=request_number)
    if request.executor_id is not None and request.executor_id == new_executor_id:
        return Preflight("same_executor", request_number=request_number,
                         current_executor_name=view.current_executor_name)

    return Preflight(
        "ok",
        request_number=request_number,
        new_executor_id=new_executor_id,
        new_executor_name=display_name(executor) or f"ID{executor.id}",
        current_executor_name=view.current_executor_name,
        assignment_kind=view.assignment_kind,
        group_label=view.group_label,
        specialization=view.specialization,
    )


def _candidates(db: Session, request_number: str, lang: str) -> tuple:
    """`(Preflight, [Candidate])` — кандидаты БЕЗ текущего исполнителя."""
    view = _assignment_view(db, request_number, lang)
    if view.verdict != "ok":
        return view, []

    svc = AdminHandlerService(db)
    request = svc.get_request_by_number(request_number)
    spec = get_specialization_for_category(request.category)
    current_id = request.executor_id

    out = []
    for ex in svc.list_approved_executors():
        if current_id is not None and ex.id == current_id:
            continue
        # BUG-166: подбор только общим предикатом (джокер `universal`).
        if not matches_required_specs(parse_specializations(ex), {spec}):
            continue
        out.append(Candidate(id=ex.id, first_name=ex.first_name,
                             last_name=ex.last_name, username=ex.username))
    return view, out


def _resolve_duty(db: Session, request_number: str, lang: str) -> Preflight:
    """Дежурный под специализацию заявки, ИСКЛЮЧАЯ текущего исполнителя."""
    from uk_management_bot.services.dispatch import pick_duty_executor_id

    view = _assignment_view(db, request_number, lang)
    if view.verdict != "ok":
        return view

    svc = AdminHandlerService(db)
    request = svc.get_request_by_number(request_number)
    spec = get_specialization_for_category(request.category)
    exclude = frozenset({request.executor_id}) if request.executor_id else frozenset()

    try:
        # strict=True: для интерактивного действия None означает «нет
        # дежурного» и так и печатается. Без режима авария БД показалась бы
        # менеджеру пустым результатом.
        duty_id = pick_duty_executor_id(spec, db=db, exclude_user_ids=exclude,
                                        strict=True)
    except Exception as e:
        logger.warning("Подбор дежурного для %s не выполнен: %s", request_number, e)
        return Preflight("duty_lookup_failed", request_number=request_number,
                         specialization=_spec_label(spec, lang))
    if duty_id is None:
        return Preflight("no_duty", request_number=request_number,
                         specialization=_spec_label(spec, lang))
    return _preflight(db, request_number, duty_id, lang)


def _aftermath(db: Session, request_number: str, outcome, lang: str) -> Aftermath:
    """Фаза 3 на СВЕЖЕЙ сессии: получатели и подписи считаются от факта."""
    from uk_management_bot.services.workflow_notifications import (
        collect_notify_messages_sync,
        collect_reassigned_away_sync,
    )

    messages = collect_notify_messages_sync(
        db, request_number, outcome.post_commit_intents)

    svc = AdminHandlerService(db)
    request = svc.get_request_by_number(request_number)
    new_name = ""
    if request is not None and request.executor_id:
        new_name = display_name(svc.get_user_by_id(request.executor_id)) or ""

    old_id = getattr(outcome.old_state, "executor_id", None)
    old_notice = None
    old_label = ""
    if old_id is not None:
        old_user = svc.get_user_by_id(old_id)
        old_label = (display_name(old_user) or f"ID{old_id}") if old_user else f"ID{old_id}"
        # Тот же человек остался исполнителем — снимать было некого. Сборка
        # текста общая с API-путём (BUG-181): workflow_notifications.
        if request is not None and request.executor_id != old_id:
            old_notice = collect_reassigned_away_sync(db, request_number, old_id)
    else:
        # Читать здесь СТАРОЕ групповое назначение бессмысленно: команда уже
        # закоммитила create_assignment, который перевёл прошлую активную
        # строку в "cancelled" и вставил новую individual. get_active_assignment
        # вернул бы именно её. Подпись «откуда» для этого случая берётся из
        # факта «исполнителя не было» — экран успеха здесь и так использует
        # шаблон без {old_label}.
        old_label = get_text("admin.handlers.reassign_from_unassigned", language=lang)

    return Aftermath(messages=messages, old_notice=old_notice,
                     old_label=old_label, new_executor_name=new_name)


def _spec_label(spec: Optional[str], lang: str) -> str:
    if not spec:
        return ""
    label = get_text(f"specializations.{spec}", language=lang)
    # get_text на отсутствующем ключе возвращает САМ КЛЮЧ — тогда честнее сырое.
    return spec if label.startswith("specializations.") else label


# ══════════════════════════════════════════════════════════════════════════
# Общий async-путь коммита
# ══════════════════════════════════════════════════════════════════════════


async def _guard(callback: CallbackQuery, roles, user, lang) -> bool:
    """`has_admin_access` держит authz-ратчет, роль manager — требование канона.

    `has_admin_access` пропускает и чистый `admin`, а MANAGER_ASSIGN разрешён
    только менеджеру (`_is_manager`): без второй проверки админ дошёл бы до
    команды и получил NotAuthorized в виде общей ошибки.
    """
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(
            get_text("admin.handlers.no_access_actions", language=lang),
            show_alert=True)
        return False
    if not has_manager_role(roles=roles, user=user):
        await callback.answer(
            get_text("admin.handlers.reassign_manager_only", language=lang),
            show_alert=True)
        return False
    return True


async def _answer_verdict(callback: CallbackQuery, pre: Preflight, lang: str) -> None:
    texts = {
        "request_not_found": get_text("admin.handlers.request_not_found", language=lang),
        "bad_status": get_text("admin.handlers.reassign_bad_status", language=lang),
        "executor_not_found": get_text(
            "admin.handlers.request_or_executor_not_found", language=lang),
        "same_executor": get_text(
            "admin.handlers.reassign_same_executor", language=lang),
        "no_duty": get_text("admin.handlers.reassign_no_duty", language=lang).format(
            spec=pre.specialization or ""),
        "duty_lookup_failed": get_text(
            "admin.handlers.reassign_duty_lookup_failed", language=lang),
    }
    await callback.answer(
        texts.get(pre.verdict, get_text("admin.handlers.error_occurred", language=lang)),
        show_alert=True)


async def _commit_reassign(callback: CallbackQuery, user: User,
                           lang: str, pre: Preflight) -> None:
    """Фазы 2 и 3 + экран успеха. `pre` уже прошёл проверки фазы 1."""
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.services.workflow_runner import (
        RequestNotFound, run_command_sync,
    )
    from uk_management_bot.utils.request_workflow import (
        Action, ActionCommand, PrincipalRef, SameExecutor, WorkflowError,
    )

    request_number = pre.request_number
    try:
        # ФАЗА 2: команда в своей сессии, целиком в потоке (db-фаза сюда не лезет).
        outcome = await asyncio.to_thread(
            run_command_sync,
            SessionLocal,
            request_number,
            PrincipalRef(kind="user", user_id=user.id, source="telegram"),
            ActionCommand(callback.id, Action.MANAGER_ASSIGN,
                          {"executor_id": pre.new_executor_id}),
        )
    except RequestNotFound:
        await callback.answer(
            get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
        return
    except SameExecutor:
        # BUG-180: гонку преflight не закрывает — между фазами другой менеджер
        # успел назначить того же человека. Ядро отказало под локом; текст —
        # тот же, что у UX-отказа фазы 1.
        await callback.answer(
            get_text("admin.handlers.reassign_same_executor", language=lang),
            show_alert=True)
        return
    except WorkflowError as e:
        logger.info("MANAGER_ASSIGN отклонён для %s: %s", request_number, e)
        await callback.answer(
            get_text("admin.handlers.reassign_rejected", language=lang), show_alert=True)
        return

    # ФАЗА 3: свежая сессия, всё считается от факта перехода.
    after = await run_db(lambda s: _aftermath(s, request_number, outcome, lang))

    await _deliver(callback, request_number, outcome, after, lang)


async def _deliver(callback: CallbackQuery, request_number: str, outcome,
                   after: Aftermath, lang: str) -> None:
    """Post-commit best-effort: уведомления, realtime, экран успеха."""
    from uk_management_bot.services.notification_service import send_to_user
    from uk_management_bot.services.workflow_notifications import send_notify_messages

    await send_notify_messages(callback.bot, after.messages)

    if after.old_notice is not None:
        telegram_id, text = after.old_notice
        try:
            await send_to_user(callback.bot, telegram_id, text)
        except Exception as e:  # сбой одного получателя не роняет остальное
            logger.warning("Уведомление снятому исполнителю %s не ушло: %s",
                           telegram_id, e)

    # Канон выпускает realtime только при смене ПУБЛИЧНОГО статуса
    # (planner._build_events). «В работе»→«В работе» его не меняет, а канбану
    # карточку перерисовать надо — публикуем сами. Проверяем именно ОТСУТСТВИЕ
    # интента, иначе на «Новая»→«В работе» вышел бы дубль.
    if not any(getattr(i, "kind", None) == "realtime"
               for i in outcome.post_commit_intents):
        try:
            from uk_management_bot.services.redis_pubsub import publish_request_event

            await publish_request_event("request.updated", {"number": request_number})
        except Exception as e:
            logger.debug("realtime publish для %s пропущен: %s", request_number, e)

    # Канон вернул no_op. Для MANAGER_ASSIGN этот случай теперь закрыт раньше
    # (гонка «тот же исполнитель» бросает SameExecutor из ядра — BUG-180),
    # ветка оставлена защитной: no_op значит «ничего не менялось и интентов
    # нет», и рисовать «переназначена» значило бы соврать об изменении.
    if getattr(outcome, "no_op", False):
        await _edit(callback,
                    get_text("admin.handlers.reassign_same_executor", language=lang),
                    _back_to_card_keyboard(request_number, lang))
        return

    # Текст выбирается ПО ФАКТУ, а не по входу: один и тот же юнит обслуживает
    # первичное назначение (снимать было некого) и переназначение.
    if getattr(outcome.old_state, "executor_id", None) is None:
        text = get_text(
            "admin.handlers.reassign_assigned_success", language=lang).format(
            request_number=html.escape(request_number),
            new_executor=html.escape(after.new_executor_name or ""),
        )
    else:
        text = get_text("admin.handlers.reassign_success", language=lang).format(
            request_number=html.escape(request_number),
            old_label=html.escape(after.old_label or ""),
            new_executor=html.escape(after.new_executor_name or ""),
        )
    await _edit(callback, text, _back_to_card_keyboard(request_number, lang))


def _menu_back_keyboard(request_number: str, lang: str) -> InlineKeyboardMarkup:
    """Возврат в меню переназначения (тупиковых экранов быть не должно)."""
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=get_text("admin.keyboards.back_nav", language=lang),
        callback_data=f"{MENU_PREFIX}{request_number}")]])


def _back_to_card_keyboard(request_number: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=get_text("admin.keyboards.back_to_request", language=lang),
        callback_data=f"mview_{request_number}")]])


async def _edit(callback: CallbackQuery, text: str,
                markup: Optional[InlineKeyboardMarkup] = None) -> None:
    """Перерисовка экрана. Ловим весь `TelegramAPIError`, а не только
    `TelegramBadRequest`: сетевые/серверные ошибки aiogram — его СИБЛИНГИ, не
    подклассы. Пропущенный `TelegramNetworkError` на этом вызове улетал бы в
    общий except хендлера и показывал менеджеру «Ошибка» ПОСЛЕ уже
    закоммиченного переназначения и уже отправленных уведомлений."""
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            try:
                await callback.message.answer(text, reply_markup=markup,
                                              parse_mode="HTML")
            except TelegramAPIError as send_error:
                logger.warning("Экран не перерисован: %s", send_error)
    except TelegramAPIError as e:
        logger.warning("Экран не перерисован: %s", e)
    try:
        await callback.answer()
    except TelegramAPIError:
        pass


# ══════════════════════════════════════════════════════════════════════════
# Хендлеры
# ══════════════════════════════════════════════════════════════════════════


@router.callback_query(F.data.startswith(MENU_PREFIX))
async def handle_reassign_menu(callback: CallbackQuery, roles: list = None,
                               active_role: str = None, user: User = None,
                               language: str = "ru"):
    """Меню переназначения: дежурному / конкретному / назад к карточке."""
    lang = language
    try:
        if not await _guard(callback, roles, user, lang):
            return
        request_number = callback.data[len(MENU_PREFIX):]
        view = await run_db(
            lambda s: _assignment_view(s, request_number, lang), db=None)
        if view.verdict != "ok":
            await _answer_verdict(callback, view, lang)
            return

        current = view.current_executor_name or view.group_label or get_text(
            "admin.handlers.reassign_from_unassigned", language=lang)
        text = get_text("admin.handlers.reassign_menu_title", language=lang).format(
            request_number=html.escape(request_number),
            current=html.escape(current),
        )
        await _edit(callback, text, _menu_keyboard(request_number, lang))
    except Exception as e:
        logger.error("Ошибка меню переназначения: %s", e, exc_info=True)
        await callback.answer(
            get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


def _menu_keyboard(request_number: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=get_text("admin.keyboards.assign_duty_specialist", language=lang),
            callback_data=f"{DUTY_PREFIX}{request_number}")],
        [InlineKeyboardButton(
            text=get_text("admin.keyboards.assign_specific_executor", language=lang),
            callback_data=f"{PICK_PREFIX}{request_number}")],
        [InlineKeyboardButton(
            text=get_text("admin.keyboards.back_to_request", language=lang),
            callback_data=f"mview_{request_number}")],
    ])


@router.callback_query(F.data.startswith(PICK_PREFIX))
async def handle_reassign_pick(callback: CallbackQuery, roles: list = None,
                               active_role: str = None, user: User = None,
                               language: str = "ru"):
    """Список кандидатов без текущего исполнителя."""
    lang = language
    try:
        if not await _guard(callback, roles, user, lang):
            return
        request_number = callback.data[len(PICK_PREFIX):]
        view, candidates = await run_db(
            lambda s: _candidates(s, request_number, lang), db=None)
        if view.verdict != "ok":
            await _answer_verdict(callback, view, lang)
            return

        if not candidates:
            # Пустой список — не «ошибка», а объяснимое состояние, и чаще всего
            # оно значит «подходящий был один, и это текущий исполнитель».
            # Без текста менеджер видел бы «Подходящих исполнителей: 0» и
            # кликабельную заглушку `no_executors`, у которой хендлера нет
            # вовсе — то есть вечные «часики».
            await _edit(
                callback,
                get_text("admin.handlers.reassign_no_candidates",
                         language=lang).format(
                    request_number=html.escape(request_number)),
                _menu_back_keyboard(request_number, lang))
            return

        text = get_text("admin.handlers.reassign_pick_title", language=lang).format(
            request_number=html.escape(request_number), count=len(candidates))
        markup = get_executors_by_category_keyboard(
            request_number, "", candidates, language=lang,
            callback_prefix=TO_PREFIX,
            back_callback_data=f"{MENU_PREFIX}{request_number}",
        )
        await _edit(callback, text, markup)
    except Exception as e:
        logger.error("Ошибка списка кандидатов: %s", e, exc_info=True)
        await callback.answer(
            get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith(DUTY_PREFIX))
async def handle_reassign_duty(callback: CallbackQuery, roles: list = None,
                               active_role: str = None, user: User = None,
                               language: str = "ru"):
    """Переназначение дежурному: резолв конкретного человека, затем канон."""
    lang = language
    try:
        if not await _guard(callback, roles, user, lang):
            return
        request_number = callback.data[len(DUTY_PREFIX):]
        pre = await run_db(lambda s: _resolve_duty(s, request_number, lang), db=None)
        if pre.verdict != "ok":
            await _answer_verdict(callback, pre, lang)
            return
        await _commit_reassign(callback, user, lang, pre)
    except Exception as e:
        logger.error("Ошибка переназначения дежурному: %s", e, exc_info=True)
        await callback.answer(
            get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.regexp(TO_PATTERN))
async def handle_reassign_to(callback: CallbackQuery, roles: list = None,
                             active_role: str = None, user: User = None,
                             language: str = "ru"):
    """Коммит переназначения на выбранного исполнителя."""
    lang = language
    try:
        if not await _guard(callback, roles, user, lang):
            return
        payload = callback.data[len(TO_PREFIX):]
        request_number, _, raw_id = payload.rpartition("_")
        new_executor_id = int(raw_id)

        pre = await run_db(
            lambda s: _preflight(s, request_number, new_executor_id, lang), db=None)
        if pre.verdict != "ok":
            await _answer_verdict(callback, pre, lang)
            return
        await _commit_reassign(callback, user, lang, pre)
    except Exception as e:
        logger.error("Ошибка переназначения исполнителя: %s", e, exc_info=True)
        await callback.answer(
            get_text("admin.handlers.error_assigning", language=lang), show_alert=True)
