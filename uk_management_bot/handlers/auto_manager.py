"""Бот-UI «Автоматический менеджер» (авто-назначение ночных заявок).

Экран статуса + inline-кнопки для менеджера/админа: вкл/выкл, просмотр режима
(в Фазе 1 функционален только «по правилу» — режим «ИИ» заблокирован до Фазы 2,
гейт — наличие ANTHROPIC_API_KEY) и FSM-ввод окна работы HH:MM-HH:MM.

Один файл = один Router() — по паттерну handlers/feedback.py / handlers/my_shifts.py
(а не пакет handlers/shift_management/ с общим _router.py — фича маленькая,
общий роутер на несколько файлов не нужен).

`updated_by` во всех записях конфига — DB `user.id` (внутренний PK), НЕ
Telegram ID: middlewares/auth.py кладёт в data["user"] ORM-объект User, поэтому
`user.id` из DI-параметров хендлера — то самое значение, что ждёт
`save_config_sync`.
"""
from contextlib import contextmanager
import logging

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from uk_management_bot.database.session import session_scope
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.services.auto_manager.config import (
    load_config_sync,
    save_config_sync,
    validate_config,
)
from uk_management_bot.states.auto_manager import AutoManagerStates
from uk_management_bot.utils.helpers import get_text, get_user_language

logger = logging.getLogger(__name__)
router = Router()


@contextmanager
def _db_scope(db):
    """Сессия для хендлера: инъецированная (не закрываем) либо свежая
    ``session_scope()`` (закроется на выходе). Паттерн — клон
    handlers/shift_management/shared.py::_db_scope.
    """
    if db is not None:
        yield db
    else:
        with session_scope() as scoped:
            yield scoped


# ─────────────────────────────── рендеринг экрана ───────────────────────────────

def _status_text(cfg: dict, lang: str) -> str:
    enabled_label = get_text(
        "auto_manager.status.enabled_on" if cfg["enabled"] else "auto_manager.status.enabled_off",
        language=lang,
    )
    # Phase-1 упрощение: строка всегда показывает «по правилу», не читая
    # cfg["mode"] — сегодня это безвредно (ни бот, ни дашборд не умеют
    # писать mode="ai"), но raw PUT в API Task 7 технически может это
    # сохранить. Phase 2 сделает эту строку mode-aware (AI-доступность).
    mode_label = get_text("auto_manager.status.mode_rule", language=lang)

    title = get_text("auto_manager.status.title", language=lang)
    body = get_text(
        "auto_manager.status.body",
        language=lang,
        enabled=enabled_label,
        mode=mode_label,
        window_start=cfg["window_start"],
        window_end=cfg["window_end"],
        timezone=cfg["timezone"],
        max_requests=cfg["max_requests_per_run"],
    )
    return f"{title}\n\n{body}"


def _status_keyboard(cfg: dict, lang: str) -> InlineKeyboardMarkup:
    toggle_label = get_text(
        "auto_manager.keyboards.toggle_off" if cfg["enabled"] else "auto_manager.keyboards.toggle_on",
        language=lang,
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_label, callback_data="auto_manager_toggle")],
        [InlineKeyboardButton(
            text=get_text("auto_manager.keyboards.mode_ai_blocked", language=lang),
            callback_data="auto_manager_mode_ai",
        )],
        [InlineKeyboardButton(
            text=get_text("auto_manager.keyboards.change_window", language=lang),
            callback_data="auto_manager_change_window",
        )],
        [InlineKeyboardButton(
            text=get_text("auto_manager.keyboards.back", language=lang),
            # Реюзаем существующий shared-хендлер handle_back_to_shifts
            # (handlers/shift_management/schedule.py) — не заводим дубликат
            # с тем же телом (edit_text главного меню + state.clear()).
            callback_data="back_to_shifts",
        )],
    ])


def _window_cancel_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=get_text("auto_manager.keyboards.back", language=lang),
            callback_data="back_to_shifts",
        )],
    ])


async def _render_status(callback: CallbackQuery, db, lang: str) -> None:
    cfg = load_config_sync(db)
    await callback.message.edit_text(
        _status_text(cfg, lang),
        reply_markup=_status_keyboard(cfg, lang),
        parse_mode="HTML",
    )


# ─────────────────────────────────── хендлеры ───────────────────────────────────

@router.callback_query(F.data == "auto_manager_menu")
@require_role(['admin', 'manager'])
async def handle_auto_manager_menu(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Экран статуса автоменеджера — точка входа с главного меню смен."""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            await state.clear()
            await _render_status(callback, db, lang)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка экрана автоменеджера: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("auto_manager.menu_load_error", language=lang), show_alert=True)


@router.callback_query(F.data == "auto_manager_toggle")
@require_role(['admin', 'manager'])
async def handle_auto_manager_toggle(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Немедленное вкл/выкл — без подтверждения (простой флип-и-перерисовка)."""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            cfg = load_config_sync(db)
            updated = {**cfg, "enabled": not cfg["enabled"]}
            saved = save_config_sync(db, updated, updated_by=user.id if user else None)

            toast_key = (
                "auto_manager.toggle_enabled_toast" if saved["enabled"]
                else "auto_manager.toggle_disabled_toast"
            )

            await callback.message.edit_text(
                _status_text(saved, lang),
                reply_markup=_status_keyboard(saved, lang),
                parse_mode="HTML",
            )
            await callback.answer(get_text(toast_key, language=lang))
    except Exception as e:
        logger.error(f"Ошибка переключения автоменеджера: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("auto_manager.menu_load_error", language=lang), show_alert=True)


@router.callback_query(F.data == "auto_manager_mode_ai")
@require_role(['admin', 'manager'])
async def handle_auto_manager_mode_ai(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """«ИИ (скоро)» — Фаза 1: заблокирован. Никогда не пишет mode="ai" в БД,
    даже при повторном/двойном тапе или доставке протухшей клавиатуры —
    единственное действие здесь — показать hint-тост, конфиг не читается и
    не сохраняется.
    """
    try:
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("auto_manager.ai_mode_hint", language=lang), show_alert=False)
    except Exception as e:
        logger.error(f"Ошибка hint'а ИИ-режима: {e}")
        await callback.answer()


@router.callback_query(F.data == "auto_manager_change_window")
@require_role(['admin', 'manager'])
async def handle_auto_manager_change_window(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Вход в FSM-ввод нового окна работы HH:MM-HH:MM."""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            await callback.message.edit_text(
                get_text("auto_manager.window_input.prompt", language=lang),
                reply_markup=_window_cancel_keyboard(lang),
                parse_mode="HTML",
            )
            await state.set_state(AutoManagerStates.entering_window)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка запроса нового окна автоменеджера: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("auto_manager.menu_load_error", language=lang), show_alert=True)


@router.message(StateFilter(AutoManagerStates.entering_window))
@require_role(['admin', 'manager'])
async def handle_auto_manager_window_input(message: Message, state: FSMContext, db=None, roles: list = None, user=None):
    """Парсинг HH:MM-HH:MM. Валидация — той же ``validate_config``, что и у
    API/шедулера (не реализуем свой regex/strptime повторно). Невалидный ввод
    не падает и не портит конфиг — остаёмся в ``entering_window`` и просим
    повторить.
    """
    try:
        with _db_scope(db) as db:
            lang = get_user_language(message.from_user.id, db)

            raw = (message.text or "").strip()
            parts = raw.split("-")
            if len(parts) != 2:
                await message.answer(
                    get_text("auto_manager.window_input.invalid_format", language=lang),
                    parse_mode="HTML",
                )
                return

            window_start, window_end = parts[0].strip(), parts[1].strip()

            current = load_config_sync(db)
            candidate = {**current, "window_start": window_start, "window_end": window_end}

            try:
                validate_config(candidate)
            except ValueError as e:
                await message.answer(
                    get_text("auto_manager.window_input.validation_error", language=lang, error=str(e)),
                )
                return

            saved = save_config_sync(db, candidate, updated_by=user.id if user else None)

            await message.answer(
                get_text(
                    "auto_manager.window_input.success",
                    language=lang,
                    window_start=saved["window_start"],
                    window_end=saved["window_end"],
                ),
                parse_mode="HTML",
            )
            await state.clear()

            await message.answer(
                _status_text(saved, lang),
                reply_markup=_status_keyboard(saved, lang),
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"Ошибка ввода окна автоменеджера: {e}")
        lang = get_user_language(message.from_user.id, db) if db else "ru"
        await message.answer(get_text("auto_manager.menu_load_error", language=lang))

