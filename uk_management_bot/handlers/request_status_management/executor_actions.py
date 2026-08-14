"""Обработчик ввода материалов (живой путь «Закуп»).

AUD5-ARCH-3 (волна 12): перенос 1:1 из handlers/request_status_management.py.
BUG-137: мёртвые хендлеры take_to_work_/purchase_materials_ ретайрены —
их callback'и в проде не генерировались. Живой вход: менеджерский «Закуп»
(handlers/admin/actions.py, purchase_<NNN>) ставит стейт
RequestStatusStates.waiting_for_materials, ввод ловит handle_materials_input.
"""

import logging

from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.database.models.user import User
from uk_management_bot.states.request_status import RequestStatusStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.status_display import get_status_with_emoji

from ._router import router
from ._units import _apply_purchase

logger = logging.getLogger(__name__)


@router.message(RequestStatusStates.waiting_for_materials)
async def handle_materials_input(message: Message, state: FSMContext, language: str = "ru", user: User = None, *, _db=None):
    """Обработка ввода списка материалов"""
    try:
        lang = language
        # Получаем список материалов (BUG-145: guard на не-текст — фото/стикер
        # в стейте ввода ронял хендлер AttributeError; образец — completion.py)
        materials = message.text.strip() if message.text else ""

        if not materials:
            await message.answer(get_text("request_status_mgmt.handlers.please_enter_materials", language=lang))
            return

        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        actor_tg = message.from_user.id
        commenter_id = user.id if user else None
        res = await run_db(
            lambda s: _apply_purchase(s, request_number, materials, actor_tg, commenter_id),
            db=_db,
        )

        if res.outcome == "no_request":
            await message.answer(get_text("request_status_mgmt.handlers.request_not_found", language=lang))
            return
        if res.outcome == "fail":
            await message.answer(f"❌ {res.fail_message}")
            await state.clear()
            return

        # Показываем подтверждение с текущими данными
        confirmation_text = get_text("request_status_mgmt.handlers.purchase_status_set", language=lang).format(request_number=request_number)

        if res.requested_materials:
            confirmation_text += get_text("request_status_mgmt.handlers.requested_materials", language=lang).format(materials=res.requested_materials)

        if res.manager_comment:
            confirmation_text += get_text("request_status_mgmt.handlers.manager_comment", language=lang).format(comment=res.manager_comment)

        confirmation_text += get_text("request_status_mgmt.handlers.new_input", language=lang).format(materials=materials)

        await message.answer(confirmation_text)

        if res.active_requests:
            # Показываем список активных заявок
            text = get_text("request_status_mgmt.handlers.active_requests_header", language=lang)
            for i, r in enumerate(res.active_requests, 1):
                addr = r.address[:40] + ("…" if len(r.address) > 40 else "")
                text += f"{i}. {get_status_with_emoji(r.status, language=lang)} #{r.request_number} - {r.category}\n"
                text += f"   📍 {addr}\n\n"

            from uk_management_bot.keyboards.admin import get_manager_main_keyboard
            await message.answer(text, reply_markup=get_manager_main_keyboard(language=lang))

        # Очищаем состояние
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка сохранения материалов: {e}")
        await message.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)))
