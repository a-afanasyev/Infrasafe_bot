"""Ответ заявителя на уточнение менеджера (команда ``/reply_<номер>``).

AUD3-07/AUD5-ARCH-1: DB-фаза каждого хендлера — цельный sync unit-of-work,
исполняемый в worker-потоке через ``run_db``; наружу выходят DTO/скаляры, а не
ORM-строки (у ORM-объекта вне потока нет живой сессии). Рассылка менеджерам
раскроена по B3 (BUG-155 п.2): юнит собирает адресатов и тексты на языке каждого
получателя, отправка идёт в async-слое через ``send_to_user``.

Оба хендлера живые: команду ``/reply_{request_number}`` заявителю диктует
живое уведомление об уточнении (``admin.handlers.notify_user_clarification`` —
handlers/admin/actions.py + services/workflow_notifications.py), а второй
хендлер срабатывает по FSM-состоянию, которое ставит первый.
"""

from dataclasses import dataclass
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import logging

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db
from uk_management_bot.utils.helpers import get_text, get_user_language
from uk_management_bot.utils.datetime_utils import utc_now
from uk_management_bot.utils.business_time import fmt_datetime

router = Router()
logger = logging.getLogger(__name__)

class ReplyStates(StatesGroup):
    waiting_for_reply_text = State()


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки.
# ==========================================================================

@dataclass(frozen=True)
class _ClarificationPrompt:
    """Поля заявки для приглашения ввести ответ."""
    category: str
    address: Optional[str]


@dataclass(frozen=True)
class _ManagerNotice:
    """Готовое уведомление менеджеру: адресат + текст на ЕГО языке (B3)."""
    telegram_id: int
    text: str


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# ==========================================================================

def _load_reply_prompt(db, request_number: str, telegram_id: int) -> tuple:
    """-> ('request_not_found'|'no_permission'|'not_in_clarification', None)
       | ('ok', _ClarificationPrompt)."""
    # Получаем заявку
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return ("request_not_found", None)

    # Проверяем, что пользователь является заявителем
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user or user.id != request.user_id:
        return ("no_permission", None)

    # Проверяем, что заявка в статусе уточнения
    if request.status != "Уточнение":
        return ("not_in_clarification", None)

    return ("ok", _ClarificationPrompt(category=request.category, address=request.address))


def _load_reply_gate(db, request_number: str, telegram_id: int) -> str:
    """-> 'request_not_found' | 'no_permission' | 'ok'.

    Отдельный проход перед проверкой текста ответа: исторически заявка и права
    проверялись ДО ``message.text.strip()``, и порядок ответов пользователю
    зависит от этого (канон волны 4: gate → context)."""
    # Получаем заявку
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return "request_not_found"

    # Получаем пользователя
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user or user.id != request.user_id:
        return "no_permission"

    return "ok"


def _apply_reply(db, request_number: str, telegram_id: int, reply_text: str, lang: str) -> tuple:
    """-> ('request_not_found'|'no_permission', []) | ('ok', [_ManagerNotice, ...]).

    Коммитит примечание и возвращает готовые уведомления менеджерам: тексты
    рендерятся здесь (нужна сессия — язык каждого получателя), отправка идёт в
    async-слое (B3-раскрой).
    """
    # Получаем заявку
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return ("request_not_found", [])

    # Получаем пользователя
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user or user.id != request.user_id:
        return ("no_permission", [])

    # Формируем имя заявителя
    applicant_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if not applicant_name:
        applicant_label = get_text("clarification.applicant_label", language=lang)
        applicant_name = f"{applicant_label} {user.telegram_id}"

    # Добавляем ответ в примечания заявки
    timestamp = fmt_datetime(utc_now())
    reply_label = get_text("clarification.reply_label", language=lang)
    new_note = f"\n\n--- {reply_label} {timestamp} ---\n"
    new_note += f"👤 {applicant_name}:\n"
    new_note += f"{reply_text}\n"

    # Обновляем примечания
    if request.notes:
        request.notes += new_note
    else:
        request.notes = new_note

    request.updated_at = utc_now()
    db.commit()

    # Собираем адресатов уведомления. BUG-155 п.2: здесь стоял вызов
    # NotificationService.send_notification_to_user — метода с таким именем у
    # сервиса нет, AttributeError гасился локальным except'ом, и менеджеры об
    # ответе заявителя не узнавали НИКОГДА. Отправка вынесена в async-слой
    # (B3-раскрой): текст на языке КАЖДОГО получателя собирается здесь, в
    # сессии, сеть — за пределами юнита.
    notices: list[_ManagerNotice] = []
    try:
        managers = db.query(User).filter(
            User.roles.contains('manager') | User.roles.contains('admin')
        ).all()

        for manager in managers:
            try:
                if not manager.telegram_id:
                    continue
                manager_lang = get_user_language(manager.telegram_id, db)
                notification_text = get_text("clarification.manager_notification", language=manager_lang).format(
                    request_number=request.request_number,
                    category=request.category,
                    address=request.address,
                    reply_text=reply_text
                )
                notices.append(_ManagerNotice(telegram_id=manager.telegram_id, text=notification_text))
            except Exception as e:
                logger.error(f"Ошибка подготовки уведомления менеджеру {manager.id}: {e}")

    except Exception as e:
        logger.error(f"Ошибка подготовки уведомлений менеджерам: {e}")

    return ("ok", notices)


@router.message(F.text.startswith("/reply_"))
async def handle_reply_command(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка команды ответа на уточнение"""
    lang = language

    try:
        # Извлекаем ID заявки из команды
        command_parts = message.text.split("_")
        if len(command_parts) != 2:
            await message.answer(get_text("clarification.invalid_command_format", language=lang))
            return

        request_number = command_parts[1]

        verdict, prompt = await run_db(
            lambda s: _load_reply_prompt(s, request_number, message.from_user.id), db=_db
        )

        if verdict == "request_not_found":
            await message.answer(get_text("requests.request_not_found", language=lang))
            return

        if verdict == "no_permission":
            await message.answer(get_text("clarification.no_permission_to_reply", language=lang))
            return

        if verdict == "not_in_clarification":
            await message.answer(get_text("clarification.not_in_clarification_status", language=lang))
            return

        # Сохраняем ID заявки в состоянии
        await state.update_data(request_number=request_number)

        # Запрашиваем текст ответа
        await message.answer(
            get_text("clarification.enter_reply_prompt", language=lang).format(
                request_number=request_number,
                category=prompt.category,
                address=prompt.address
            ),
            reply_markup=None
        )

        # Устанавливаем состояние ожидания ответа
        await state.set_state(ReplyStates.waiting_for_reply_text)

        logger.info(f"Запрошен ответ на уточнение для заявки {request_number} от пользователя {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки команды ответа: {e}")
        await message.answer(get_text("common.error", language=lang))

@router.message(ReplyStates.waiting_for_reply_text)
async def handle_reply_text(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка текста ответа от заявителя"""
    lang = language

    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        if not request_number:
            await message.answer(get_text("clarification.error_request_not_found", language=lang))
            await state.clear()
            return

        verdict = await run_db(
            lambda s: _load_reply_gate(s, request_number, message.from_user.id), db=_db
        )

        if verdict == "request_not_found":
            await message.answer(get_text("requests.request_not_found", language=lang))
            await state.clear()
            return

        if verdict == "no_permission":
            await message.answer(get_text("clarification.no_permission_to_reply", language=lang))
            await state.clear()
            return

        # Получаем текст ответа
        reply_text = message.text.strip()

        if not reply_text:
            await message.answer(get_text("clarification.reply_text_empty", language=lang))
            return

        verdict, manager_notices = await run_db(
            lambda s: _apply_reply(s, request_number, message.from_user.id, reply_text, lang),
            db=_db,
        )

        if verdict == "request_not_found":
            await message.answer(get_text("requests.request_not_found", language=lang))
            await state.clear()
            return

        if verdict == "no_permission":
            await message.answer(get_text("clarification.no_permission_to_reply", language=lang))
            await state.clear()
            return

        # Открытая доска узнаёт об ответе только через WS: у канбана нет иного
        # пути обновления, поэтому без этой публикации менеджер не увидел бы ни
        # свежих примечаний, ни индикатора непрочитанного. Тип события фронт уже
        # слушает (useKanban) — правок в SPA не нужно. Публикуем здесь, а не в
        # юните: publish_request_event асинхронна, а DB-фаза идёт в потоке.
        # Best-effort: мёртвый Redis не должен стоить жителю его ответа.
        try:
            from uk_management_bot.services.redis_pubsub import publish_request_event

            await publish_request_event("request.updated", {"number": request_number})
        except Exception as e:
            logger.debug(f"realtime publish для {request_number} пропущен: {e}")

        # Уведомляем менеджеров (B3: сеть вне сессии, best-effort — сбой
        # отдельного получателя не должен ронять ответ заявителю).
        from uk_management_bot.services.notification_service import send_to_user

        for notice in manager_notices:
            try:
                await send_to_user(message.bot, notice.telegram_id, notice.text)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления менеджеру {notice.telegram_id}: {e}")

        logger.info(
            f"Уведомления об ответе по заявке {request_number} отправлены менеджерам: {len(manager_notices)}"
        )

        # Подтверждаем заявителю
        reply_preview = reply_text[:100] + ('...' if len(reply_text) > 100 else '')
        await message.answer(
            get_text("clarification.reply_sent_confirmation", language=lang).format(
                request_number=request_number,
                reply_preview=reply_preview
            )
        )

        # Очищаем состояние
        await state.clear()

        logger.info(f"Ответ на уточнение по заявке {request_number} добавлен пользователем {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки ответа на уточнение: {e}")
        await message.answer(get_text("clarification.error_sending_reply", language=lang))
        await state.clear()
