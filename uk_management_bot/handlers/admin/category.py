"""Менеджер: смена категории заявки из карточки (канон MANAGER_CHANGE_CATEGORY).

Три фазы — как у переназначения (``reassignment.py``), и по той же причине:
оркестратор ``change_category_sync`` открывает СВОИ сессии (команда под
FOR UPDATE, затем best-effort передиспетч, затем свежее чтение), и всё, что
показывается менеджеру, берётся из ``CategoryChangeResult``, а не из
перечитывания заявки на внешней сессии (stale identity map — урок PR #477).

Кнопка «Переназначить» на экране итога — только если ``can_reassign``:
канон пускает MANAGER_ASSIGN из «Новая»/«В работе», в «Закуп»/«Уточнение»/
«Выполнена» она дала бы отказ. Там — предупреждение без кнопки.
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

from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db
from uk_management_bot.keyboards.admin import get_category_picker_keyboard
from uk_management_bot.keyboards.requests import (
    SELECTABLE_CATEGORY_KEYS,
    get_category_display,
    resolve_category_key,
)
from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.services.request_number_service import REQUEST_NUMBER_CORE
from uk_management_bot.utils.auth_helpers import has_admin_access, has_manager_role
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.request_workflow import is_terminal, normalize_status
from uk_management_bot.utils.user_names import display_name

from ._router import router

logger = logging.getLogger(__name__)

MENU_PREFIX = "req_category_menu_"
SET_PREFIX = "req_category_set_"
# Коммит-вход — строгий регекс (урок BUG-179: открытый префикс перехватывает
# соседей). Ключ категории — только [a-z_], как в SELECTABLE_CATEGORY_KEYS.
SET_PATTERN = rf"^{SET_PREFIX}{REQUEST_NUMBER_CORE}_[a-z_]+$"


# ══════════════════════════════════════════════════════════════════════════
# DTO — то, что пересекает границу run_db (ORM за неё не выходит)
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CategoryView:
    verdict: str                       # ok | request_not_found | bad_status
    request_number: str = ""
    current_key: Optional[str] = None
    current_label: str = ""


@dataclass(frozen=True)
class CategoryAftermath:
    messages: list = field(default_factory=list)   # [(telegram_id, text)]
    executor_name: str = ""


# ══════════════════════════════════════════════════════════════════════════
# Sync-юниты (worker-поток через run_db)
# ══════════════════════════════════════════════════════════════════════════


def _category_view(db: Session, request_number: str, lang: str) -> CategoryView:
    svc = AdminHandlerService(db)
    request = svc.get_request_by_number(request_number)
    if request is None:
        return CategoryView("request_not_found", request_number)
    if is_terminal(normalize_status(request)):
        return CategoryView("bad_status", request_number)
    current_key = resolve_category_key(request.category) if request.category else None
    label = get_category_display(current_key, lang) if current_key else "—"
    return CategoryView("ok", request_number, current_key, label)


def _aftermath(db: Session, request_number: str, result, lang: str) -> CategoryAftermath:
    """Фаза 3 на СВЕЖЕЙ сессии: тексты уведомлений и имя исполнителя от факта."""
    from uk_management_bot.services.workflow_notifications import (
        collect_notify_messages_sync,
    )

    messages = collect_notify_messages_sync(db, request_number, result.post_commit_intents)
    name = ""
    if result.executor_id is not None:
        user = AdminHandlerService(db).get_user_by_id(result.executor_id)
        name = (display_name(user) or f"ID{result.executor_id}") if user else f"ID{result.executor_id}"
    return CategoryAftermath(messages=messages, executor_name=name)


def _spec_label(spec: Optional[str], lang: str) -> str:
    if not spec:
        return ""
    label = get_text(f"specializations.{spec}", language=lang)
    return spec if label.startswith("specializations.") else label


# ══════════════════════════════════════════════════════════════════════════
# Общий async-путь
# ══════════════════════════════════════════════════════════════════════════


async def _guard(callback: CallbackQuery, roles, user, lang) -> bool:
    """`has_admin_access` держит authz-ратчет; роль manager — требование канона."""
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(
            get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
        return False
    if not has_manager_role(roles=roles, user=user):
        await callback.answer(
            get_text("admin.handlers.category_manager_only", language=lang), show_alert=True)
        return False
    return True


async def _answer_verdict(callback: CallbackQuery, verdict: str, lang: str) -> None:
    keys = {
        "request_not_found": "admin.handlers.request_not_found",
        "bad_status": "admin.handlers.category_bad_status",
    }
    await callback.answer(
        get_text(keys.get(verdict, "admin.handlers.error_occurred"), language=lang),
        show_alert=True)


def _back_to_card_keyboard(request_number: str, lang: str,
                           with_reassign: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if with_reassign:
        rows.append([InlineKeyboardButton(
            text=get_text("admin.keyboards.reassign_request", language=lang),
            callback_data=f"req_reassign_menu_{request_number}")])
    rows.append([InlineKeyboardButton(
        text=get_text("admin.keyboards.back_to_request", language=lang),
        callback_data=f"mview_{request_number}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit(callback: CallbackQuery, text: str,
                markup: Optional[InlineKeyboardMarkup] = None) -> None:
    """Перерисовка экрана; ловим весь `TelegramAPIError` (см. reassignment._edit)."""
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            try:
                await callback.message.answer(text, reply_markup=markup, parse_mode="HTML")
            except TelegramAPIError as send_error:
                logger.warning("Экран не перерисован: %s", send_error)
    except TelegramAPIError as e:
        logger.warning("Экран не перерисован: %s", e)
    try:
        await callback.answer()
    except TelegramAPIError:
        pass


def _result_text(result, after: CategoryAftermath, lang: str) -> str:
    number = html.escape(result.request_number)
    if result.no_op:
        return get_text("admin.handlers.category_same", language=lang,
                        request_number=number)
    old_label = get_category_display(result.old_category, lang) if result.old_category else "—"
    parts = [get_text("admin.handlers.category_success", language=lang).format(
        request_number=number,
        old_label=html.escape(old_label),
        new_label=html.escape(get_category_display(result.new_category, lang)),
    )]
    dispatch = result.dispatch
    if dispatch is not None and dispatch.kind == "assigned":
        parts.append(get_text("admin.handlers.category_redispatched_executor",
                              language=lang).format(executor=html.escape(after.executor_name)))
    elif dispatch is not None and dispatch.kind == "grouped":
        parts.append(get_text("admin.handlers.category_redispatched_group",
                              language=lang).format(
            spec=html.escape(_spec_label(dispatch.specialization, lang))))
    if result.executor_spec_mismatch:
        parts.append(get_text("admin.handlers.category_spec_mismatch", language=lang))
    return "\n\n".join(parts)


async def _deliver(callback: CallbackQuery, result, after: CategoryAftermath, lang: str) -> None:
    """Post-commit best-effort: уведомления, realtime, экран итога."""
    from uk_management_bot.services.workflow_notifications import send_notify_messages

    await send_notify_messages(callback.bot, after.messages)

    if not result.no_op:
        # Канон realtime не выпускает (публичный статус не менялся); диспетч
        # при переводе в «В работе» публикует status_changed сам.
        try:
            from uk_management_bot.services.redis_pubsub import publish_request_event

            await publish_request_event("request.updated", {"number": result.request_number})
        except Exception as e:
            logger.debug("realtime publish для %s пропущен: %s", result.request_number, e)

    with_reassign = result.executor_spec_mismatch and result.can_reassign
    await _edit(callback, _result_text(result, after, lang),
                _back_to_card_keyboard(result.request_number, lang, with_reassign))


# ══════════════════════════════════════════════════════════════════════════
# Хендлеры
# ══════════════════════════════════════════════════════════════════════════


@router.callback_query(F.data.startswith(MENU_PREFIX))
async def handle_category_menu(callback: CallbackQuery, roles: list = None,
                               active_role: str = None, user: User = None,
                               language: str = "ru"):
    """Picker категорий с пометкой текущей."""
    lang = language
    try:
        if not await _guard(callback, roles, user, lang):
            return
        request_number = callback.data[len(MENU_PREFIX):]
        view = await run_db(lambda s: _category_view(s, request_number, lang), db=None)
        if view.verdict != "ok":
            await _answer_verdict(callback, view.verdict, lang)
            return
        text = get_text("admin.handlers.category_menu_title", language=lang).format(
            request_number=html.escape(request_number),
            current=html.escape(view.current_label),
        )
        await _edit(callback, text,
                    get_category_picker_keyboard(request_number, view.current_key, lang))
    except Exception as e:
        logger.error("Ошибка меню категории: %s", e, exc_info=True)
        await callback.answer(
            get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.regexp(SET_PATTERN))
async def handle_category_set(callback: CallbackQuery, roles: list = None,
                              active_role: str = None, user: User = None,
                              language: str = "ru"):
    """Коммит: команда канона + передиспетч в потоке, aftermath на свежей сессии."""
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.services.category_change import change_category_sync
    from uk_management_bot.services.workflow_runner import RequestNotFound
    from uk_management_bot.utils.request_workflow import (
        InvalidTransition,
        NotAuthorized,
        PayloadInvalid,
        PrincipalRef,
        WorkflowError,
    )

    lang = language
    try:
        if not await _guard(callback, roles, user, lang):
            return
        request_number, _, key = callback.data[len(SET_PREFIX):].rpartition("_")
        # callback_data шлёт КЛИЕНТ — набор ключей проверяется сервером.
        if key not in SELECTABLE_CATEGORY_KEYS:
            await callback.answer(
                get_text("admin.handlers.category_unknown", language=lang), show_alert=True)
            return

        try:
            # ФАЗЫ 1–2: команда + передиспетч + свежее чтение — целиком в потоке.
            result = await asyncio.to_thread(
                change_category_sync,
                SessionLocal,
                request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                key,
                command_id=callback.id,
            )
        except RequestNotFound:
            await callback.answer(
                get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return
        except InvalidTransition:
            await callback.answer(
                get_text("admin.handlers.category_bad_status", language=lang), show_alert=True)
            return
        except PayloadInvalid:
            await callback.answer(
                get_text("admin.handlers.category_unknown", language=lang), show_alert=True)
            return
        except NotAuthorized:
            await callback.answer(
                get_text("admin.handlers.category_manager_only", language=lang), show_alert=True)
            return
        except WorkflowError as e:
            logger.info("MANAGER_CHANGE_CATEGORY отклонён для %s: %s", request_number, e)
            await callback.answer(
                get_text("admin.handlers.category_rejected", language=lang), show_alert=True)
            return

        # ФАЗА 3: свежая сессия.
        after = await run_db(lambda s: _aftermath(s, request_number, result, lang), db=None)
        await _deliver(callback, result, after, lang)
    except Exception as e:
        logger.error("Ошибка смены категории: %s", e, exc_info=True)
        await callback.answer(
            get_text("admin.handlers.error_occurred", language=lang), show_alert=True)
