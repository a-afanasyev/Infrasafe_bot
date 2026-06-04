"""Обработчики обратной связи (жалобы / пожелания).

Кнопка главного меню «Обратная связь» → FSM-диалог: тип → текст → необязательное
фото → подтверждение. На подтверждении обращение сохраняется в БД, фото (если
есть) — best-effort в media-service, менеджеры уведомляются в Telegram.
"""
import logging

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.orm import Session

from uk_management_bot.database.models.user import User
from uk_management_bot.states.feedback import FeedbackStates
from uk_management_bot.services.feedback_service import (
    FEEDBACK_TYPES,
    build_manager_notify_text,
    create_feedback_sync,
    manager_telegram_ids_sync,
)
from uk_management_bot.services.notification_service import deliver_feedback_to_managers
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.media_helpers import upload_telegram_file_to_media_service
from uk_management_bot.utils.button_texts import get_feedback_texts

router = Router()
logger = logging.getLogger(__name__)

FEEDBACK_TEXTS = get_feedback_texts()
_MIN_TEXT_LEN = 10


def _type_keyboard(lang: str):
    kb = InlineKeyboardBuilder()
    kb.button(text=get_text("feedback.type_complaint", language=lang), callback_data="fb_type:complaint")
    kb.button(text=get_text("feedback.type_wish", language=lang), callback_data="fb_type:wish")
    kb.button(text=get_text("feedback.btn_cancel", language=lang), callback_data="fb_cancel")
    kb.adjust(2, 1)
    return kb.as_markup()


def _skip_keyboard(lang: str):
    kb = InlineKeyboardBuilder()
    kb.button(text=get_text("feedback.skip_photo", language=lang), callback_data="fb_skip_photo")
    kb.button(text=get_text("feedback.btn_cancel", language=lang), callback_data="fb_cancel")
    kb.adjust(1)
    return kb.as_markup()


def _confirm_keyboard(lang: str):
    kb = InlineKeyboardBuilder()
    kb.button(text=get_text("feedback.btn_send", language=lang), callback_data="fb_confirm")
    kb.button(text=get_text("feedback.btn_cancel", language=lang), callback_data="fb_cancel")
    kb.adjust(2)
    return kb.as_markup()


def _author_name(user: User) -> str:
    parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(p for p in parts if p).strip()
    return name or (f"@{user.username}" if user.username else f"id{user.telegram_id}")


@router.message(F.text.in_(FEEDBACK_TEXTS))
async def feedback_entry(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Старт диалога обратной связи."""
    await state.clear()
    await message.answer(
        get_text("feedback.prompt_type", language=language),
        reply_markup=_type_keyboard(language),
    )
    await state.set_state(FeedbackStates.waiting_for_type)


@router.callback_query(F.data.startswith("fb_type:"), FeedbackStates.waiting_for_type)
async def feedback_type(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    type_ = callback.data.split(":", 1)[1]
    await state.update_data(type_=type_)
    await callback.message.edit_text(get_text("feedback.prompt_text", language=language))
    await state.set_state(FeedbackStates.waiting_for_text)
    await callback.answer()


@router.message(FeedbackStates.waiting_for_text, F.text)
async def feedback_text(message: Message, state: FSMContext, language: str = "ru"):
    text = (message.text or "").strip()
    if len(text) < _MIN_TEXT_LEN:
        await message.answer(get_text("feedback.validation_short", language=language))
        return
    await state.update_data(text=text)
    await message.answer(
        get_text("feedback.prompt_photo", language=language),
        reply_markup=_skip_keyboard(language),
    )
    await state.set_state(FeedbackStates.waiting_for_photo)


async def _show_confirm(message: Message, state: FSMContext, language: str):
    data = await state.get_data()
    label = get_text(
        "feedback.type_complaint" if data.get("type_") == "complaint" else "feedback.type_wish",
        language=language,
    )
    preview = data.get("text", "")
    if len(preview) > 200:
        preview = preview[:200] + "…"
    photo_note = " 📎" if data.get("photo_file_id") else ""
    body = f"{get_text('feedback.confirm', language=language)}\n\n{label}{photo_note}\n\n{preview}"
    await message.answer(body, reply_markup=_confirm_keyboard(language))
    await state.set_state(FeedbackStates.waiting_for_confirm)


@router.message(FeedbackStates.waiting_for_photo, F.photo)
async def feedback_photo(message: Message, state: FSMContext, language: str = "ru"):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await _show_confirm(message, state, language)


@router.callback_query(F.data == "fb_skip_photo", FeedbackStates.waiting_for_photo)
async def feedback_skip_photo(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    await state.update_data(photo_file_id=None)
    try:
        await callback.message.delete()  # косметика — старое сообщение может не удалиться
    except Exception:
        pass
    await _show_confirm(callback.message, state, language)
    await callback.answer()


@router.callback_query(F.data == "fb_confirm", FeedbackStates.waiting_for_confirm)
async def feedback_confirm(
    callback: CallbackQuery, state: FSMContext, db: Session, bot: Bot, language: str = "ru"
):
    data = await state.get_data()
    type_ = data.get("type_")
    text = data.get("text")
    photo_file_id = data.get("photo_file_id")

    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    # type_ приходит из FSM (callback fb_type:*) — валидируем против белого списка,
    # чтобы крафтнутый callback не записал произвольный тип в БД.
    if not user or type_ not in FEEDBACK_TYPES or not text:
        await callback.answer(get_text("feedback.cancelled", language=language), show_alert=True)
        await state.clear()
        return

    fb = create_feedback_sync(
        db, user_id=user.id, type_=type_, text=text, media_files=[], source="bot"
    )

    # Фото → media-service (best-effort, для просмотра в дашборде). Падение не валит сохранение.
    if photo_file_id:
        try:
            media = await upload_telegram_file_to_media_service(
                bot,
                file_id=photo_file_id,
                request_number=f"fb-{fb.id}",
                category="feedback_photo",
                uploaded_by=user.id,
            )
            if media and media.get("media_file", {}).get("id"):
                fb.media_files = [media["media_file"]["id"]]
                db.commit()
        except Exception as e:
            logger.warning("feedback %s: media-service upload failed: %s", fb.id, e)

    # Уведомление менеджерам исходным Telegram file_id (без повторной загрузки).
    try:
        ids = manager_telegram_ids_sync(db)
        notify_text = build_manager_notify_text(
            type_=type_, text=text, author_name=_author_name(user),
            has_photo=bool(photo_file_id), lang="ru",
        )
        await deliver_feedback_to_managers(
            bot, telegram_ids=ids, text=notify_text, photo=photo_file_id if photo_file_id else None
        )
    except Exception as e:
        logger.warning("feedback %s: manager notify failed: %s", fb.id, e)

    await callback.message.edit_text(get_text("feedback.success", language=language))
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "fb_cancel")
async def feedback_cancel(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    await state.clear()
    try:
        await callback.message.edit_text(get_text("feedback.cancelled", language=language))
    except Exception:
        await callback.message.answer(get_text("feedback.cancelled", language=language))
    await callback.answer()
