"""Завершение работы: запрос отчёта, медиа отчёта, приём текста отчёта.

AUD5-ARCH-3 (волна 12): перенос 1:1 из handlers/request_status_management.py.
Два message-хендлера на одном стейте waiting_for_completion_report:
media-вариант (F.photo | F.video) регистрируется ДО текстового — порядок
исходника сохранён.
"""

import logging

from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.database.models.user import User
from uk_management_bot.states.request_status import RequestStatusStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.constants import ROLE_EXECUTOR

from ._router import router
from ._units import _has_role, _apply_completion, _notify_request_completed

logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("complete_work_"))
async def handle_complete_work(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Завершение работы по заявке"""
    try:
        lang = language
        # Проверяем права доступа
        actor_tg = callback.from_user.id
        if not await run_db(lambda s: _has_role(s, actor_tg, ROLE_EXECUTOR), db=_db):
            await callback.answer(get_text("request_status_mgmt.handlers.no_permission", language=lang), show_alert=True)
            return

        request_number = callback.data.split("_")[-1]

        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            action="complete_work"
        )

        # Запрашиваем отчет о выполнении
        await callback.message.edit_text(
            get_text("request_status_mgmt.handlers.enter_completion_report", language=lang)
        )

        # Переходим в состояние ввода отчета
        await state.set_state(RequestStatusStates.waiting_for_completion_report)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка завершения работы: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.message(RequestStatusStates.waiting_for_completion_report, F.photo | F.video)
async def handle_completion_report_media(message: Message, state: FSMContext, language: str = "ru", user: User = None):
    """Обработка фото/видео в отчете о выполнении"""
    try:
        lang = language
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        if not request_number:
            await message.answer(get_text("request_status_mgmt.handlers.request_not_found_in_state", language=lang))
            return

        # Получаем file_id
        if message.photo:
            file_id = message.photo[-1].file_id
            file_type = "photo"
        else:
            file_id = message.video.file_id
            file_type = "video"

        # Сохраняем file_id в FSM
        report_media = data.get('report_media', [])
        if len(report_media) >= 5:
            await message.answer(get_text("request_status_mgmt.handlers.max_files_reached", language=lang))
            return

        report_media.append(file_id)
        await state.update_data(report_media=report_media)

        # Загружаем файл в Media Service
        from uk_management_bot.utils.media_helpers import upload_report_file_to_media_service
        try:
            await upload_report_file_to_media_service(
                bot=message.bot,
                file_id=file_id,
                request_number=request_number,
                report_type=f"completion_{file_type}",
                description=f"Фото/видео отчета #{len(report_media)}",
                uploaded_by=user.id if user else None
            )
            logger.info(f"Файл отчета загружен в Media Service для заявки {request_number}")
        except Exception as e:
            logger.error(f"Ошибка загрузки файла отчета в Media Service: {e}")

        await message.answer(
            get_text("request_status_mgmt.handlers.file_added", language=lang).format(
                count=len(report_media), max=5
            )
        )

    except Exception as e:
        logger.error(f"Ошибка обработки медиа отчета: {e}")
        await message.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)))


@router.message(RequestStatusStates.waiting_for_completion_report)
async def handle_completion_report_input(message: Message, state: FSMContext, language: str = "ru", user: User = None, *, _db=None):
    """Обработка ввода отчета о выполнении"""
    try:
        lang = language
        # Получаем отчет
        report = message.text.strip() if message.text else ""

        if not report:
            await message.answer(get_text("request_status_mgmt.handlers.please_enter_report", language=lang))
            return

        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        report_media = data.get("report_media", [])

        # Отчёт (completion_report — workflow-поле канона, PR2c): собираем текст
        # ЛОКАЛЬНО и передаём в payload канон-команды; прямую ORM-запись убрали.
        full_report = report
        if report_media:
            full_report += "\n" + get_text("request_status_mgmt.handlers.attached_files", language=lang).format(count=len(report_media))

        actor_tg = message.from_user.id
        commenter_id = user.id if user else None
        outcome, fail_message, request_user_id = await run_db(
            lambda s: _apply_completion(s, request_number, full_report, actor_tg, commenter_id),
            db=_db,
        )

        if outcome == "no_request":
            await message.answer(get_text("request_status_mgmt.handlers.request_not_found", language=lang))
            return
        if outcome == "fail":
            await message.answer(get_text("request_status_mgmt.handlers.work_completion_failed", language=lang).format(message=fail_message))
            await state.clear()
            return

        # Отправляем уведомление заявителю (исторически бьётся AttributeError —
        # см. докстринг _notify_request_completed; except ниже ловит как раньше).
        await run_db(
            lambda s: _notify_request_completed(s, request_number, request_user_id), db=_db
        )

        # Показываем подтверждение
        success_text = get_text("request_status_mgmt.handlers.work_completed", language=lang).format(
            request_id=request_number
        )

        await message.answer(success_text)

        # Очищаем состояние
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка завершения работы: {e}")
        await message.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)))
