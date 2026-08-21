"""Исправление ФИО чужого профиля менеджером — общий флоу двух разделов.

Вход один (`rename_user_<origin>_<id>`), карточек две: житель («Пользователи»)
и сотрудник («Сотрудники»). `origin` нужен только чтобы знать, куда вернуть
менеджера после сохранения, — сама операция от раздела не зависит, поле-то
одно. Отдельный модуль, а не по копии в каждом разделе: копии здесь уже
расходились (у сотрудника правка ФИО была, у жителя не было вовсе, валидации
не было ни там ни там).

Что записать и что занести в аудит, решает `services/users/rename.py` — тот же
писатель, что у дашборда. Здесь только Telegram-IO, локализация и границы
сессии.

Право: `has_admin_access` (admin ИЛИ manager) — как у соседних операций
админ-контура бота (одобрение, блокировка, роли). У HTTP-эндпоинтов той же
операции право уже `manager`, потому что весь раздел «Сотрудники» в API
manager-only; расхождение осознанное — каждая поверхность следует своей
конвенции, и обе строже, чем сама операция требует.
"""

import html
import logging
from dataclasses import dataclass
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db
from uk_management_bot.services.users.rename import (
    RenameForbidden,
    apply_rename,
    ensure_renamable,
    plan_rename,
)
from uk_management_bot.states.user_rename import UserRenameStates
from uk_management_bot.utils.auth_helpers import has_admin_access, parse_roles_safe
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.person_name import (
    MAX_FULL_NAME_LEN,
    InvalidFullName,
    validate_full_name,
)
from uk_management_bot.utils.user_names import display_name, full_name

logger = logging.getLogger(__name__)

router = Router()

#: `res` — карточка жителя, `emp` — карточка сотрудника. Строгий regex, а не
#: startswith: открытый префикс уже приводил к перехвату чужих callback'ов
#: (BUG-179), и callback_data присылает клиент, а не наша клавиатура.
ENTRY_PATTERN = r"^rename_user_(res|emp)_\d+$"

#: Прежний вход правки ФИО сотрудника. Кнопка его больше не рисует, но
#: клавиатуры, уже отрисованные в чатах менеджеров, шлют именно его — «мёртвый
#: по генератору кнопки» не значит «закрытый вход» (BUG-150/154/158). Ведёт в
#: тот же флоу с origin=emp.
LEGACY_EMPLOYEE_PATTERN = r"^edit_employee_name_\d+$"

#: Куда вернуть менеджера после сохранения — по разделу, из которого пришли.
_BACK_CALLBACK = {
    "res": "back_to_user_details_{user_id}",
    "emp": "edit_employee_{user_id}",
}

#: Повод отказа валидации → ключ локали.
_INVALID_TEXT_KEY = {
    "empty": "user_rename.error_empty",
    "no_letters": "user_rename.error_no_letters",
    "too_long": "user_rename.error_too_long",
}


@dataclass(frozen=True)
class _Target:
    """Снимок цели, вынесенный из сессии (ORM наружу не отдаём)."""

    id: int
    label: str
    current_full_name: Optional[str]
    roles: list


@dataclass(frozen=True)
class _Result:
    """Итог записи. `status`: ok | unchanged | not_found | forbidden."""

    status: str
    old_full_name: Optional[str] = None
    new_full_name: Optional[str] = None


def _parse_entry(data: str) -> tuple[str, int]:
    """`rename_user_res_42` → ("res", 42). Формат гарантирован фильтром.

    Legacy-вход `edit_employee_name_42` разбирается тем же местом — иначе
    появилось бы второе определение того, что такое «цель переименования».
    """
    if data.startswith("edit_employee_name_"):
        return "emp", int(data.rsplit("_", 1)[1])
    _, _, origin, raw_id = data.split("_", 3)
    return origin, int(raw_id)


def _back_keyboard(origin: str, user_id: int, language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=get_text("buttons.back", language=language),
        callback_data=_BACK_CALLBACK[origin].format(user_id=user_id),
    )]])


# ═══ sync-юниты (целиком внутри одной сессии) ═══

def _load_target(session, user_id: int) -> Optional[_Target]:
    user = session.query(User).filter(User.id == user_id).first()
    if user is None:
        return None
    return _Target(
        id=user.id,
        label=display_name(user) or f"#{user.id}",
        current_full_name=full_name(user),
        roles=parse_roles_safe(user.roles),
    )


def _write_rename(session, *, target_id: int, actor_tg_id: Optional[int], new_full_name: str) -> _Result:
    """Запись под локом строки + аудит + commit. Валидация уже прошла снаружи."""
    target = (
        session.query(User).filter(User.id == target_id).with_for_update().first()
    )
    if target is None:
        return _Result(status="not_found")

    try:
        ensure_renamable(target)
    except RenameForbidden:
        return _Result(status="forbidden")

    actor_id = None
    if actor_tg_id is not None:
        actor = session.query(User).filter(User.telegram_id == actor_tg_id).first()
        actor_id = actor.id if actor else None

    plan = plan_rename(target, new_full_name)
    if not apply_rename(session, target, plan, actor_id=actor_id):
        return _Result(status="unchanged", old_full_name=plan.old_full_name,
                       new_full_name=plan.new_full_name)
    session.commit()
    return _Result(status="ok", old_full_name=plan.old_full_name,
                   new_full_name=plan.new_full_name)


# ═══ хендлеры ═══

@router.callback_query(F.data.regexp(ENTRY_PATTERN) | F.data.regexp(LEGACY_EMPLOYEE_PATTERN))
async def handle_rename_start(
    callback: CallbackQuery,
    state: FSMContext,
    roles: list = None,
    active_role: str = None,
    user: User = None,
    language: str = "ru",
    *,
    _db=None,
):
    """Открыть форму исправления ФИО."""
    lang = language

    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text("errors.permission_denied", language=lang), show_alert=True)
        return

    try:
        origin, target_id = _parse_entry(callback.data)
        target = await run_db(lambda s: _load_target(s, target_id), db=_db)

        if target is None:
            await callback.answer(get_text("errors.user_not_found", language=lang), show_alert=True)
            return

        # Отказ показывается ДО формы: дать ввести ФИО и отвергнуть после —
        # худший из вариантов.
        try:
            ensure_renamable(target)
        except RenameForbidden:
            await callback.answer(
                get_text("user_rename.forbidden_privileged", language=lang), show_alert=True
            )
            return

        await state.update_data(target_user_id=target_id, origin=origin)
        await state.set_state(UserRenameStates.waiting_for_full_name)

        await callback.message.edit_text(
            get_text("user_rename.prompt", language=lang).format(
                user_label=html.escape(target.label),
                current_name=html.escape(target.current_full_name
                                         or get_text("user_rename.no_name", language=lang)),
            ),
            reply_markup=_back_keyboard(origin, target_id, lang),
            parse_mode="HTML",
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка открытия формы исправления ФИО: {e}")
        await callback.answer(get_text("errors.unknown_error", language=lang), show_alert=True)


@router.message(UserRenameStates.waiting_for_full_name)
async def handle_rename_input(
    message: Message,
    state: FSMContext,
    roles: list = None,
    active_role: str = None,
    user: User = None,
    language: str = "ru",
    *,
    _db=None,
):
    """Принять новое ФИО, записать, показать итог."""
    lang = language

    # Право перепроверяется на шаге записи: между открытием формы и вводом
    # менеджера могли разжаловать, а состояние FSM это переживёт.
    if not has_admin_access(roles=roles, user=user):
        await state.clear()
        await message.answer(get_text("errors.permission_denied", language=lang))
        return

    data = await state.get_data()
    target_id = data.get("target_user_id")
    origin = data.get("origin")
    if not target_id or origin not in _BACK_CALLBACK:
        await state.clear()
        await message.answer(get_text("errors.unknown_error", language=lang))
        return

    try:
        new_full_name = validate_full_name(message.text)
    except InvalidFullName as exc:
        # Состояние НЕ сбрасывается: менеджер поправит ввод следующим
        # сообщением, а не начнёт с карточки заново.
        # `replace`, а не `.format`: плейсхолдер есть только у одного из трёх
        # текстов, а фигурная скобка в любом другом уронила бы форматирование.
        text = get_text(_INVALID_TEXT_KEY.get(exc.code, "errors.unknown_error"), language=lang)
        await message.answer(text.replace("{max_len}", str(MAX_FULL_NAME_LEN)))
        return

    try:
        result = await run_db(
            lambda s: _write_rename(
                s,
                target_id=target_id,
                actor_tg_id=message.from_user.id if message.from_user else None,
                new_full_name=new_full_name,
            ),
            db=_db,
        )
    except Exception as e:
        logger.error(f"Ошибка записи ФИО пользователя {target_id}: {e}")
        await state.clear()
        await message.answer(get_text("errors.unknown_error", language=lang))
        return

    await state.clear()

    if result.status == "not_found":
        await message.answer(get_text("errors.user_not_found", language=lang))
        return
    if result.status == "forbidden":
        await message.answer(get_text("user_rename.forbidden_privileged", language=lang))
        return

    key = "user_rename.unchanged" if result.status == "unchanged" else "user_rename.saved"
    await message.answer(
        get_text(key, language=lang).format(
            old_name=html.escape(result.old_full_name
                                 or get_text("user_rename.no_name", language=lang)),
            new_name=html.escape(result.new_full_name or ""),
        ),
        reply_markup=_back_keyboard(origin, target_id, lang),
        parse_mode="HTML",
    )
