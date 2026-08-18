"""
Обработчики для управления комментариями к заявкам
Обеспечивает функциональность добавления и просмотра комментариев

AUD3-07/AUD5-ARCH-1: DB-фаза каждого хендлера — цельный sync unit-of-work,
исполняемый в worker-потоке через ``run_db``; наружу выходят DTO/скаляры, а не
ORM-строки (у ORM-объекта вне потока нет живой сессии). ``CommentService``
целиком живёт внутри юнитов: и запись (``add_comment`` коммитит сам), и
форматирование (``format_comments_for_display`` доигрывает автора каждого
комментария запросом по своей сессии). Сеть/рендер (edit_text, answer) — всегда
в async-слое, вне сессии.
"""

import logging
from dataclasses import dataclass, field
from typing import List

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db
from uk_management_bot.states.request_comments import RequestCommentStates
from uk_management_bot.services.comment_service import CommentService
from uk_management_bot.services.request_access import has_request_access_sync
from uk_management_bot.keyboards.request_comments import (
    get_comment_type_keyboard,
    get_comment_confirmation_keyboard,
    get_comments_list_keyboard
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.utils.constants import (
    COMMENT_TYPE_CLARIFICATION, COMMENT_TYPE_PURCHASE, COMMENT_TYPE_REPORT
)

router = Router()
logger = logging.getLogger(__name__)


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки.
# ==========================================================================

@dataclass(frozen=True)
class _AddCommentContext:
    """Роли автора, снятые каноническим парсером — для FSM-состояния."""
    user_roles: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class _CommentsView:
    """Готовый текст истории комментариев + номер заявки для клавиатуры."""
    request_number: str
    formatted_comments: str


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# ==========================================================================

def _load_add_comment_context(db, request_number: str, telegram_id: int) -> tuple:
    """-> ('request_not_found'|'user_not_found'|'no_access', None)
       | ('ok', _AddCommentContext)."""
    # Проверяем существование заявки
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return ("request_not_found", None)

    # Пользователь ищется по telegram_id, а НЕ по id: `callback.from_user.id`
    # это Telegram-идентификатор, а `users.id` — обычный serial. Прежний
    # `User.id == callback.from_user.id` не находил никого, и хендлер всегда
    # отвечал «пользователь не найден» (тестами не покрыт).
    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if not user:
        return ("user_not_found", None)

    # Права — канон `utils/request_access` (П5). В прежней копии правил
    # `request.user_id` сравнивался с Telegram-id, роль проверялась
    # подстрокой по JSON-тексту `user.roles`, а назначения через
    # RequestAssignment не учитывались вовсе.
    has_access = has_request_access_sync(db, user, request)

    if not has_access:
        return ("no_access", None)

    # Роли — через канон-парсер: раньше сюда клался сырой JSON-текст
    # `user.roles`, потому что проверка прав рядом тоже работала с ним как со
    # строкой.
    return ("ok", _AddCommentContext(user_roles=parse_roles_safe(user.roles)))


def _load_request_exists(db, request_number: str) -> bool:
    """-> True, если заявка с таким номером есть."""
    # Получаем заявку
    request = db.query(Request).filter(Request.request_number == request_number).first()
    return request is not None


def _apply_comment(db, request_number: str, author_telegram_id: int, comment_text: str, comment_type: str) -> str:
    """-> 'request_not_found' | 'author_not_found' | 'no_access' | 'ok'. Коммитит CommentService.add_comment.

    ⚠️ Права проверяются ЗДЕСЬ, в точке записи, а не только на входе в цепочку.
    Так было: авторизация стояла ровно один раз, в `handle_add_comment_start`, а
    номер заявки жил в разделяемом ключе состояния — подмена ключа между шагами
    отправляла комментарий в ЧУЖУЮ заявку (секревью 2026-08-18). Именованный
    ключ `comment_request_number` эту подмену закрывает, но полагаться на «нас
    уже авторизовали» в точке записи нельзя: любой новый вход в цепочку снова
    открыл бы дыру, а этот слой её держит независимо.

    Исключения ``add_comment`` (ValueError валидации, ошибки записи) намеренно
    НЕ гасятся: они всплывают наружу через run_db в общий ``except`` хендлера —
    ровно как всплывали при прямом вызове на middleware-сессии.

    BUG-155 п.1: сюда передавался Telegram-id автора, а ``add_comment`` ищет
    ``User.id == user_id`` (обычный serial) и на несовпадении бросал
    ValueError — подтверждение комментария в проде падало в алерт «ошибка»
    всегда. Резолв telegram_id → users.id делается здесь, в той же сессии.
    """
    # Получаем заявку для получения ID
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return "request_not_found"

    author = db.query(User).filter(User.telegram_id == author_telegram_id).first()
    if not author:
        return "author_not_found"

    if not has_request_access_sync(db, author, request):
        return "no_access"

    # Создаем сервис комментариев
    comment_service = CommentService(db)

    # Добавляем комментарий
    comment_service.add_comment(
        request_id=request.request_number,
        user_id=author.id,
        comment_text=comment_text,
        comment_type=comment_type
    )

    return "ok"


def _load_comments_view(db, request_number: str, telegram_id: int, lang: str) -> tuple:
    """-> ('request_not_found'|'user_not_found'|'no_access'|'no_comments', None)
       | ('ok', _CommentsView).

    Форматирование остаётся ВНУТРИ юнита: ``format_comments_for_display``
    дочитывает автора каждого комментария запросом по той же сессии, а сами
    комментарии — ORM-строки, наружу их выпускать нельзя.
    """
    # Проверяем существование заявки
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return ("request_not_found", None)

    # Пользователь ищется по telegram_id, а НЕ по id: `callback.from_user.id`
    # это Telegram-идентификатор, а `users.id` — обычный serial. Прежний
    # `User.id == callback.from_user.id` не находил никого, и хендлер всегда
    # отвечал «пользователь не найден» (тестами не покрыт).
    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if not user:
        return ("user_not_found", None)

    # Права — канон `utils/request_access` (П5). В прежней копии правил
    # `request.user_id` сравнивался с Telegram-id, роль проверялась
    # подстрокой по JSON-тексту `user.roles`, а назначения через
    # RequestAssignment не учитывались вовсе.
    has_access = has_request_access_sync(db, user, request)

    if not has_access:
        return ("no_access", None)

    # Получаем комментарии
    comment_service = CommentService(db)
    comments = comment_service.get_request_comments(request.request_number, limit=20)

    if not comments:
        return ("no_comments", None)

    # Форматируем комментарии для отображения
    formatted_comments = comment_service.format_comments_for_display(comments, lang)

    return (
        "ok",
        _CommentsView(
            request_number=request.request_number,
            formatted_comments=formatted_comments,
        ),
    )


def _load_comments_by_type_view(db, request_number: str, comment_type: str, telegram_id: int, lang: str) -> tuple:
    """-> ('request_not_found'|'user_not_found'|'no_access'|'no_comments', None) | ('ok', _CommentsView).

    Проверка прав добавлена 2026-08-18: номер заявки приходит из callback_data,
    и без неё это чтение чужой переписки. Хендлер сейчас недостижим (перекрыт
    префиксом `view_comments_`, см. ⚠️ у него) — но недостижимость чинится
    порядком регистрации, а дыра осталась бы.
    """
    # Проверяем существование заявки
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return ("request_not_found", None)

    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return ("user_not_found", None)

    if not has_request_access_sync(db, user, request):
        return ("no_access", None)

    # Получаем комментарии определенного типа
    comment_service = CommentService(db)
    comments = comment_service.get_comments_by_type(request.request_number, comment_type)

    if not comments:
        return ("no_comments", None)

    # Форматируем комментарии для отображения
    formatted_comments = comment_service.format_comments_for_display(comments, lang)

    return (
        "ok",
        _CommentsView(
            request_number=request.request_number,
            formatted_comments=formatted_comments,
        ),
    )


def _load_all_comments_view(db, request_number: str, telegram_id: int, lang: str) -> tuple:
    """-> ('request_not_found'|'user_not_found'|'no_access'|'no_comments', None) | ('ok', _CommentsView).

    Проверка прав добавлена 2026-08-18. Раньше её здесь не было «исторически»,
    и это отличало возврат к списку от входа в него: `back_to_comments_<номер>`
    отдавал переписку по ЛЮБОЙ заявке — примитив для этого не нужен, номер идёт
    прямо из callback_data.
    """
    # Получаем заявку
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return ("request_not_found", None)

    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return ("user_not_found", None)

    if not has_request_access_sync(db, user, request):
        return ("no_access", None)

    # Получаем все комментарии
    comment_service = CommentService(db)
    comments = comment_service.get_request_comments(request.request_number, limit=20)

    if not comments:
        return ("no_comments", None)

    # Форматируем комментарии для отображения
    formatted_comments = comment_service.format_comments_for_display(comments, lang)

    return (
        "ok",
        _CommentsView(
            request_number=request.request_number,
            formatted_comments=formatted_comments,
        ),
    )


@router.callback_query(F.data.startswith("add_comment_"))
async def handle_add_comment_start(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Начало процесса добавления комментария"""
    lang = language

    try:
        # Получаем ID заявки
        request_number = callback.data.split("_")[-1]

        verdict, ctx = await run_db(
            lambda s: _load_add_comment_context(s, request_number, callback.from_user.id),
            db=_db,
        )

        if verdict == "request_not_found":
            await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
            return

        if verdict == "user_not_found":
            await callback.answer(get_text("comments.user_not_found", language=lang), show_alert=True)
            return

        if verdict == "no_access":
            await callback.answer(get_text("comments.no_permission_to_add", language=lang), show_alert=True)
            return

        # Сохраняем данные в состоянии.
        #
        # ⚠️ Ключ ИМЕНОВАННЫЙ (`comment_request_number`), а не общий
        # `request_number`. Общий пишут чужие флоу — в частности живой
        # `return_request_<любой номер>` (`handlers/request_acceptance.py`), где
        # номер берётся из клиентского callback_data без проверки владения. Пока
        # цепочка читала общий ключ, это была подмена цели между шагами:
        # комментарий уезжал в чужую заявку (секревью 2026-08-18). Родня уже
        # именованных `edit_materials_request_number`, `return_to_work_number`,
        # `executor_request_number` — они этим примитивом не поднимаются.
        await state.update_data(
            comment_request_number=request_number,
            user_roles=ctx.user_roles,
        )

        # Показываем выбор типа комментария
        keyboard = get_comment_type_keyboard(lang)

        await callback.message.edit_text(
            get_text("comments.select_type", language=lang),
            reply_markup=keyboard
        )

        # Переходим в состояние выбора типа комментария
        await state.set_state(RequestCommentStates.waiting_for_comment_type)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала добавления комментария: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

@router.callback_query(RequestCommentStates.waiting_for_comment_type, F.data.startswith("comment_type_"))
async def handle_comment_type_selection(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Обработка выбора типа комментария"""
    lang = language

    try:
        # Получаем тип комментария из callback data
        comment_type = callback.data.split("_", 2)[2]

        # Сохраняем тип комментария в состоянии
        await state.update_data(comment_type=comment_type)

        # Получаем промпт для комментария
        comment_prompt = get_comment_prompt(comment_type, lang)

        await callback.message.edit_text(comment_prompt)

        # Переходим в состояние ввода комментария
        await state.set_state(RequestCommentStates.waiting_for_comment)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора типа комментария: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

@router.message(RequestCommentStates.waiting_for_comment)
async def handle_comment_input(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка ввода комментария"""
    lang = language

    try:
        # Получаем текст комментария
        comment_text = message.text.strip()

        if not comment_text:
            await message.answer(get_text("comments.comment_text_empty", language=lang))
            return

        if len(comment_text) < 5:
            await message.answer(get_text("comments.comment_text_too_short", language=lang))
            return

        # Сохраняем комментарий в состоянии
        await state.update_data(comment_text=comment_text)

        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("comment_request_number")
        comment_type = data.get("comment_type")

        exists = await run_db(lambda s: _load_request_exists(s, request_number), db=_db)
        if not exists:
            await message.answer(get_text("requests.request_not_found", language=lang))
            return

        # Показываем подтверждение
        keyboard = get_comment_confirmation_keyboard(lang)

        confirmation_text = get_text("comments.confirmation", language=lang).format(
            request_id=request_number,
            comment_type=get_comment_type_display_name(comment_type, lang),
            comment_text=comment_text[:100] + "..." if len(comment_text) > 100 else comment_text
        )

        await message.answer(confirmation_text, reply_markup=keyboard)

        # Переходим в состояние подтверждения
        await state.set_state(RequestCommentStates.waiting_for_confirmation)

    except Exception as e:
        logger.error(f"Ошибка ввода комментария: {e}")
        await message.answer(get_text("common.error_occurred", language=lang).format(error=str(e)))

@router.callback_query(RequestCommentStates.waiting_for_confirmation, F.data == "confirm_comment")
async def handle_comment_confirmation(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Подтверждение добавления комментария"""
    lang = language

    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("comment_request_number")
        comment_type = data.get("comment_type")
        comment_text = data.get("comment_text")

        if not all([request_number, comment_type, comment_text]):
            await callback.answer(get_text("comments.comment_data_not_found", language=lang), show_alert=True)
            return

        verdict = await run_db(
            lambda s: _apply_comment(
                s, request_number, callback.from_user.id, comment_text, comment_type
            ),
            db=_db,
        )

        if verdict == "request_not_found":
            await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
            return

        if verdict == "author_not_found":
            await callback.answer(get_text("errors.user_not_found", language=lang), show_alert=True)
            return

        if verdict == "no_access":
            await callback.answer(get_text("comments.no_permission_to_add", language=lang), show_alert=True)
            return

        # Показываем сообщение об успехе
        success_text = get_text("comments.success", language=lang).format(
            request_id=request_number,
            comment_type=get_comment_type_display_name(comment_type, lang)
        )

        await callback.message.edit_text(success_text)

        # Очищаем состояние
        await state.clear()

        await callback.answer(get_text("comments.comment_added_alert", language=lang))

    except Exception as e:
        logger.error(f"Ошибка подтверждения комментария: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

@router.callback_query(F.data == "cancel_comment")
async def handle_comment_cancellation(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена добавления комментария"""
    lang = language

    try:
        # Очищаем состояние
        await state.clear()

        await callback.message.edit_text(get_text("comments.comment_cancelled", language=lang))
        await callback.answer(get_text("comments.comment_cancelled_alert", language=lang))

    except Exception as e:
        logger.error(f"Ошибка отмены комментария: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("view_comments_"))
async def handle_view_comments(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Просмотр комментариев заявки"""
    lang = language

    try:
        # Получаем ID заявки
        request_number = callback.data.split("_")[-1]

        verdict, view = await run_db(
            lambda s: _load_comments_view(s, request_number, callback.from_user.id, lang),
            db=_db,
        )

        if verdict == "request_not_found":
            await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
            return

        if verdict == "user_not_found":
            await callback.answer(get_text("comments.user_not_found", language=lang), show_alert=True)
            return

        if verdict == "no_access":
            await callback.answer(get_text("comments.no_permission_to_view", language=lang), show_alert=True)
            return

        if verdict == "no_comments":
            await callback.answer(get_text("comments.no_comments_yet", language=lang), show_alert=True)
            return

        # Показываем комментарии
        keyboard = get_comments_list_keyboard(view.request_number, lang)

        await callback.message.edit_text(
            view.formatted_comments,
            reply_markup=keyboard
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра комментариев: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

# ⚠️ Предсуществующий дефект (сохранён 1:1): этот фильтр перекрыт хендлером
# `view_comments_` выше — он зарегистрирован в ЭТОМ же роутере раньше, а
# `view_comments_by_type_...` начинается с `view_comments_`, поэтому aiogram
# отдаёт апдейт первому. Кнопки типов (keyboards/request_comments.py) в проде
# показывают всю историю вместо выборки по типу; сам хендлер недостижим.
@router.callback_query(F.data.startswith("view_comments_by_type_"))
async def handle_view_comments_by_type(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Просмотр комментариев определенного типа"""
    lang = language

    try:
        # Получаем данные из callback
        parts = callback.data.split("_")
        request_number = parts[-1]
        comment_type = "_".join(parts[4:-1])  # Объединяем части типа комментария

        verdict, view = await run_db(
            lambda s: _load_comments_by_type_view(
                s, request_number, comment_type, callback.from_user.id, lang
            ),
            db=_db,
        )

        if verdict == "request_not_found":
            await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
            return

        if verdict == "user_not_found":
            await callback.answer(get_text("comments.user_not_found", language=lang), show_alert=True)
            return

        if verdict == "no_access":
            await callback.answer(get_text("comments.no_permission_to_view", language=lang), show_alert=True)
            return

        if verdict == "no_comments":
            await callback.answer(get_text("comments.no_comments_of_type", language=lang), show_alert=True)
            return

        # Показываем комментарии
        keyboard = get_comments_list_keyboard(view.request_number, lang)

        await callback.message.edit_text(
            view.formatted_comments,
            reply_markup=keyboard
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра комментариев по типу: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("back_to_comments_"))
async def handle_back_to_comments(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Возврат к списку комментариев"""
    lang = language

    try:
        # Получаем ID заявки
        request_number = callback.data.split("_")[-1]

        # Права проверяются так же, как на входе `view_comments_` (2026-08-18).
        # Раньше их здесь не было: кто прислал callback_data, тот и видел
        # историю переписки по любой заявке.
        verdict, view = await run_db(
            lambda s: _load_all_comments_view(s, request_number, callback.from_user.id, lang),
            db=_db,
        )

        if verdict == "request_not_found":
            await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
            return

        if verdict == "user_not_found":
            await callback.answer(get_text("comments.user_not_found", language=lang), show_alert=True)
            return

        if verdict == "no_access":
            await callback.answer(get_text("comments.no_permission_to_view", language=lang), show_alert=True)
            return

        if verdict == "no_comments":
            await callback.answer(get_text("comments.no_comments_yet", language=lang), show_alert=True)
            return

        # Показываем комментарии
        keyboard = get_comments_list_keyboard(view.request_number, lang)

        await callback.message.edit_text(
            view.formatted_comments,
            reply_markup=keyboard
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к комментариям: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

# Вспомогательные функции

def get_comment_prompt(comment_type: str, language: str = "ru") -> str:
    """Получение промпта для комментария в зависимости от типа"""
    prompt_keys = {
        COMMENT_TYPE_CLARIFICATION: "comments.prompt_clarification",
        COMMENT_TYPE_PURCHASE: "comments.prompt_purchase",
        COMMENT_TYPE_REPORT: "comments.prompt_report",
        "general": "comments.prompt_general"
    }

    key = prompt_keys.get(comment_type, prompt_keys["general"])
    return get_text(key, language=language)

def get_comment_type_display_name(comment_type: str, language: str = "ru") -> str:
    """Получение отображаемого названия типа комментария"""
    display_name_keys = {
        COMMENT_TYPE_CLARIFICATION: "comments.type_clarification",
        COMMENT_TYPE_PURCHASE: "comments.type_purchase",
        COMMENT_TYPE_REPORT: "comments.type_report",
        "general": "comments.type_general"
    }

    key = display_name_keys.get(comment_type, "comments.type_comment")
    return get_text(key, language=language)
