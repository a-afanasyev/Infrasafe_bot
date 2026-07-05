"""FSM создания заявки обходчиком (план «Обходчик», 2026-06).

Отдельный flow со своими callback-префиксами `insp_*` и StateFilter, чтобы
глобальные не-стейт-фильтрованные хендлеры applicant-flow
(`category_*`/`confirm_*`/`urgency_*` в handlers/requests.py) его НЕ перехватывали.

Обходчик заводит building-level заявку с любого активного двора/дома (двор→дом),
принадлежность не требуется. Доступ — только approved-обходчик (гейт на входе и
перед сохранением). Адрес/FK/source считает сервер (resolve_request_address,
source="inspector").
"""
import logging

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from uk_management_bot.database.session import session_scope
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.models.building import Building
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.requests import (
    CATEGORY_KEYS,
    URGENCY_KEYS,
    get_cancel_keyboard,
    get_media_keyboard,
)
from uk_management_bot.services.request_address import (
    resolve_request_address_sync,
    AddressResolutionError,
)

logger = logging.getLogger(__name__)

router = Router()

PAGE_SIZE = 8

# Тексты-триггеры входа (RU/UZ), совпадают с main_menu.inspector_create.
INSPECTOR_CREATE_TEXTS = {
    get_text("main_menu.inspector_create", language="ru"),
    get_text("main_menu.inspector_create", language="uz"),
}


class InspectorRequestStates(StatesGroup):
    yard = State()
    building = State()
    category = State()
    description = State()
    urgency = State()
    media = State()
    confirm = State()


# ───────────────────────────── helpers ───────────────────────────────


async def _lang(event) -> str:
    """Язык пользователя (best-effort)."""
    try:
        from uk_management_bot.handlers.requests import _get_user_language

        if isinstance(event, CallbackQuery):
            return await _get_user_language(callback=event)
        return await _get_user_language(message=event)
    except Exception:
        return "ru"


def _approved_inspector(telegram_id: int) -> bool:
    from uk_management_bot.api.dependencies import _parse_user_roles

    with session_scope() as db:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user or user.status != "approved":
            return False
        return "inspector" in _parse_user_roles(user)


def _active_yards() -> list[tuple[int, str]]:
    with session_scope() as db:
        yards = db.query(Yard).filter(Yard.is_active.is_(True)).order_by(Yard.name).all()
        return [(y.id, y.name) for y in yards]


def _active_buildings(yard_id: int) -> list[tuple[int, str]]:
    with session_scope() as db:
        yard = db.query(Yard).filter(Yard.id == yard_id, Yard.is_active.is_(True)).first()
        if not yard:
            return []
        buildings = (
            db.query(Building)
            .filter(Building.yard_id == yard_id, Building.is_active.is_(True))
            .order_by(Building.address)
            .all()
        )
        return [(b.id, b.address) for b in buildings]


def _paged_keyboard(items: list[tuple[int, str]], prefix: str, page: int, language: str,
                    emoji: str) -> InlineKeyboardMarkup:
    pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    chunk = items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    rows = [[InlineKeyboardButton(text=f"{emoji} {label}", callback_data=f"{prefix}:{iid}")]
            for iid, label in chunk]
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}_page:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="insp_noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}_page:{page + 1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton(
        text=get_text("buttons.cancel", language=language), callback_data="insp_cancel"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _category_keyboard(language: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=get_text(loc, language=language), callback_data=f"insp_cat:{key}"
    )] for key, loc in CATEGORY_KEYS.items()]
    rows.append([InlineKeyboardButton(
        text=get_text("buttons.cancel", language=language), callback_data="insp_cancel"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _urgency_keyboard(language: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=get_text(loc, language=language), callback_data=f"insp_urg:{key}"
    )] for key, loc in URGENCY_KEYS.items()]
    rows.append([InlineKeyboardButton(
        text=get_text("buttons.cancel", language=language), callback_data="insp_cancel"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=get_text("buttons.confirm", language=language), callback_data="insp_confirm_yes"),
        InlineKeyboardButton(text=get_text("buttons.cancel", language=language), callback_data="insp_cancel"),
    ]])


# ───────────────────────────── entry ─────────────────────────────────


@router.message(F.text.in_(INSPECTOR_CREATE_TEXTS))
async def start_inspector_request(message: Message, state: FSMContext):
    lang = await _lang(message)
    if not _approved_inspector(message.from_user.id):
        await message.answer(get_text("inspector.only_approved", language=lang))
        return
    yards = _active_yards()
    if not yards:
        await message.answer(get_text("inspector.no_yards", language=lang))
        return
    await state.set_state(InspectorRequestStates.yard)
    await message.answer(get_text("inspector.starting", language=lang), reply_markup=ReplyKeyboardRemove())
    await message.answer(
        get_text("inspector.select_yard", language=lang),
        reply_markup=_paged_keyboard(yards, "insp_yard", 0, lang, "🏘️"),
    )


@router.callback_query(F.data.startswith("insp_yard_page:"), InspectorRequestStates.yard)
async def inspector_yard_page(callback: CallbackQuery, state: FSMContext):
    lang = await _lang(callback)
    page = int(callback.data.split(":", 1)[1])
    await callback.message.edit_reply_markup(
        reply_markup=_paged_keyboard(_active_yards(), "insp_yard", page, lang, "🏘️")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("insp_yard:"), InspectorRequestStates.yard)
async def inspector_yard_selected(callback: CallbackQuery, state: FSMContext):
    lang = await _lang(callback)
    yard_id = int(callback.data.split(":", 1)[1])
    buildings = _active_buildings(yard_id)
    if not buildings:
        await callback.answer(get_text("inspector.no_buildings", language=lang), show_alert=True)
        return
    await state.update_data(yard_id=yard_id)
    await state.set_state(InspectorRequestStates.building)
    await callback.message.edit_text(get_text("inspector.select_building", language=lang))
    await callback.message.answer(
        get_text("inspector.select_building", language=lang),
        reply_markup=_paged_keyboard(buildings, "insp_bld", 0, lang, "🏢"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("insp_bld_page:"), InspectorRequestStates.building)
async def inspector_building_page(callback: CallbackQuery, state: FSMContext):
    lang = await _lang(callback)
    page = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    await callback.message.edit_reply_markup(
        reply_markup=_paged_keyboard(_active_buildings(data.get("yard_id")), "insp_bld", page, lang, "🏢")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("insp_bld:"), InspectorRequestStates.building)
async def inspector_building_selected(callback: CallbackQuery, state: FSMContext):
    lang = await _lang(callback)
    building_id = int(callback.data.split(":", 1)[1])

    # Резолв при выборе (дом+двор активны). Принадлежность для inspector не нужна.
    with session_scope() as db:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer(get_text("errors.default", language=lang), show_alert=True)
            return
        try:
            resolved = resolve_request_address_sync(db, user.id, "inspector", "building", building_id)
        except AddressResolutionError:
            await callback.answer(get_text("requests.address_not_available", language=lang), show_alert=True)
            return

    await state.update_data(
        address_type="building", address_id=building_id, address=resolved.canonical_address,
    )
    await state.set_state(InspectorRequestStates.category)
    await callback.message.edit_text(
        get_text("requests.address_selected", language=lang, address=resolved.canonical_address)
    )
    await callback.message.answer(
        get_text("requests.select_category", language=lang), reply_markup=_category_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("insp_cat:"), InspectorRequestStates.category)
async def inspector_category_selected(callback: CallbackQuery, state: FSMContext):
    lang = await _lang(callback)
    category_key = callback.data.split(":", 1)[1]
    if category_key not in CATEGORY_KEYS:
        await callback.answer(get_text("errors.default", language=lang), show_alert=True)
        return
    await state.update_data(category=category_key)
    await state.set_state(InspectorRequestStates.description)
    await callback.message.edit_text(get_text("requests.description", language=lang))
    await callback.message.answer(
        get_text("requests.description", language=lang), reply_markup=get_cancel_keyboard(language=lang)
    )
    await callback.answer()


@router.message(InspectorRequestStates.description)
async def inspector_description(message: Message, state: FSMContext):
    lang = await _lang(message)
    text = (message.text or "").strip()
    if message.text == get_text("buttons.cancel", language=lang):
        await _cancel(message, state, lang)
        return
    if len(text) < 5:
        await message.answer(get_text("requests.description", language=lang))
        return
    await state.update_data(description=text)
    await state.set_state(InspectorRequestStates.urgency)
    await message.answer(get_text("requests.select_urgency", language=lang), reply_markup=_urgency_keyboard(lang))


@router.callback_query(F.data.startswith("insp_urg:"), InspectorRequestStates.urgency)
async def inspector_urgency_selected(callback: CallbackQuery, state: FSMContext):
    lang = await _lang(callback)
    urgency_key = callback.data.split(":", 1)[1]
    if urgency_key not in URGENCY_KEYS:
        await callback.answer(get_text("errors.default", language=lang), show_alert=True)
        return
    await state.update_data(urgency=urgency_key)
    # Шаг медиа (паритет с applicant-flow): фото/видео до 5, затем «Продолжить».
    await state.set_state(InspectorRequestStates.media)
    await callback.message.edit_text(
        get_text("requests.select_urgency", language=lang) + " ✅"
    )
    await callback.message.answer(
        get_text("requests.send_photo_or_video", language=lang),
        reply_markup=get_media_keyboard(language=lang),
    )
    await callback.answer()


@router.message(InspectorRequestStates.media, F.photo | F.video)
async def inspector_media(message: Message, state: FSMContext):
    lang = await _lang(message)
    data = await state.get_data()
    media_files = data.get("media_files", [])
    if len(media_files) >= 5:
        await message.answer(get_text("requests.max_5_files", language=lang))
        return
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    media_files.append(file_id)
    await state.update_data(media_files=media_files)
    await message.answer(
        get_text("requests.file_added", language=lang).replace("{...}", str(len(media_files))),
        reply_markup=get_media_keyboard(language=lang),
    )


@router.message(InspectorRequestStates.media)
async def inspector_media_text(message: Message, state: FSMContext):
    lang = await _lang(message)
    if message.text == get_text("buttons.cancel", language=lang):
        await _cancel(message, state, lang)
        return
    if message.text == get_text("buttons.continue", language=lang):
        await state.set_state(InspectorRequestStates.confirm)
        data = await state.get_data()
        media_count = len(data.get("media_files", []))
        summary = get_text(
            "inspector.confirm_summary", language=lang,
            address=data.get("address", ""),
            category=get_text(CATEGORY_KEYS.get(data.get("category"), ""), language=lang),
            urgency=get_text(URGENCY_KEYS.get(data.get("urgency"), ""), language=lang),
            description=data.get("description", ""),
        )
        if media_count:
            summary += f"\n📸 Файлов: {media_count}"
        # Убираем reply-клавиатуру медиа и показываем inline-подтверждение.
        await message.answer(summary, reply_markup=ReplyKeyboardRemove())
        await message.answer(
            get_text("buttons.confirm", language=lang) + "?", reply_markup=_confirm_keyboard(lang)
        )
        return
    await message.answer(
        get_text("requests.send_photo_or_video", language=lang),
        reply_markup=get_media_keyboard(language=lang),
    )


@router.callback_query(F.data == "insp_confirm_yes", InspectorRequestStates.confirm)
async def inspector_confirm(callback: CallbackQuery, state: FSMContext):
    lang = await _lang(callback)
    if not _approved_inspector(callback.from_user.id):
        await callback.answer(get_text("inspector.only_approved", language=lang), show_alert=True)
        await state.clear()
        return
    data = await state.get_data()
    from uk_management_bot.handlers.requests import save_request

    with session_scope() as db:
        request_number = await save_request(
            data, callback.from_user.id, db, callback.bot,
            source="inspector", role="inspector",
        )

    await state.clear()
    if request_number:
        await callback.message.edit_text(
            get_text("requests.request_created_success", language=lang)
        )
    else:
        await callback.message.edit_text(get_text("errors.request_save_failed", language=lang))
    await callback.answer()


@router.callback_query(F.data == "insp_cancel")
async def inspector_cancel_cb(callback: CallbackQuery, state: FSMContext):
    lang = await _lang(callback)
    await _cancel(callback.message, state, lang)
    await callback.answer()


@router.callback_query(F.data == "insp_noop")
async def inspector_noop(callback: CallbackQuery):
    await callback.answer()


async def _cancel(message: Message, state: FSMContext, lang: str):
    await state.clear()
    from uk_management_bot.keyboards.base import get_user_contextual_keyboard

    await message.answer(
        get_text("requests.request_creation_cancelled", language=lang),
        reply_markup=get_user_contextual_keyboard(message.chat.id),
    )
