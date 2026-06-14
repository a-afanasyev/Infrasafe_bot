"""
Обработчики для работы с непринятыми заявками (для менеджеров)

Включает:
- Напоминание заявителю о необходимости принять заявку
- Принятие заявки менеджером за заявителя (с обязательным комментарием, без звезд)
- Возврат к списку непринятых заявок
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.keyboards.admin import get_manager_main_keyboard, get_manager_request_list_kb
from uk_management_bot.states.request_acceptance import ManagerAcceptanceStates
from uk_management_bot.utils.workflow_predicates import (
    is_awaiting_applicant,
    awaiting_applicant_clause,
)
from uk_management_bot.utils.helpers import get_text
# 2a-final fix D: используем канонический has_admin_access (читает user.roles
# JSON), вместо локального shadow на устаревшем user.role.
from uk_management_bot.utils.auth_helpers import has_admin_access

import logging

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("unaccepted_remind_"))
async def handle_remind_applicant(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Напомнить заявителю о необходимости принять заявку"""
    try:
        # Проверяем права доступа
        lang = language
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("unaccepted.handlers.no_permission", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("unaccepted_remind_", "")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer(get_text("unaccepted.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем что заявка действительно непринята (ожидает приёмки заявителем)
        if not is_awaiting_applicant(request):
            await callback.answer(get_text("unaccepted.handlers.request_already_processed", language=lang), show_alert=True)
            return

        # Получаем заявителя
        applicant = db.query(User).filter(User.id == request.user_id).first()

        if not applicant:
            await callback.answer(get_text("unaccepted.handlers.applicant_not_found", language=lang), show_alert=True)
            return

        # Формируем уведомление заявителю
        completed_at = request.completed_at if request.completed_at else request.updated_at
        if completed_at:
            if completed_at.tzinfo is None:
                from datetime import timezone as dt_tz
                completed_at = completed_at.replace(tzinfo=dt_tz.utc)
            completed_str = completed_at.strftime('%d.%m.%Y %H:%M')
        else:
            completed_str = get_text("unaccepted.handlers.unknown_time", language=lang)

        notification_text = get_text("unaccepted.handlers.reminder_notification", language=lang).format(
            request_number=request.request_number,
            category=request.category,
            address=request.address or get_text("unaccepted.handlers.not_specified", language=lang),
            completed_str=completed_str
        )

        # Создаём клавиатуру с кнопкой просмотра
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=get_text("unaccepted.handlers.btn_view_request", language=lang),
                callback_data=f"view_completed_{request.request_number}"
            )]
        ])

        # Отправляем уведомление заявителю
        try:
            await callback.bot.send_message(
                chat_id=applicant.telegram_id,
                text=notification_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

            await callback.answer(get_text("unaccepted.handlers.reminder_sent", language=lang), show_alert=True)

            logger.info(f"Отправлено напоминание заявителю {applicant.telegram_id} о заявке {request_number}")

        except Exception as send_error:
            logger.error(f"Ошибка отправки напоминания заявителю: {send_error}")
            await callback.answer(get_text("unaccepted.handlers.reminder_failed", language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка обработки напоминания заявителю: {e}")
        lang = language
        await callback.answer(get_text("unaccepted.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("unaccepted_accept_"))
async def handle_manager_accept_request(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Менеджер принимает заявку за заявителя (требуется комментарий)"""
    try:
        lang = language
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("unaccepted.handlers.no_permission", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("unaccepted_accept_", "")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer(get_text("unaccepted.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем что заявка действительно непринята (ожидает приёмки заявителем)
        if not is_awaiting_applicant(request):
            await callback.answer(get_text("unaccepted.handlers.request_already_processed", language=lang), show_alert=True)
            return

        # Сохраняем номер заявки в состояние
        await state.update_data(request_number=request_number)

        # Переводим в состояние ожидания комментария
        await state.set_state(ManagerAcceptanceStates.awaiting_manager_acceptance_comment)

        await callback.message.edit_text(
            get_text("unaccepted.handlers.accept_for_applicant_prompt", language=lang).format(
                request_number=request_number
            ),
            parse_mode="HTML"
        )

        await callback.answer()

        logger.info(f"Менеджер {callback.from_user.id} начал принятие заявки {request_number} за заявителя")

    except Exception as e:
        logger.error(f"Ошибка начала принятия заявки менеджером: {e}")
        lang = language
        await callback.answer(get_text("unaccepted.handlers.error_occurred", language=lang), show_alert=True)


@router.message(ManagerAcceptanceStates.awaiting_manager_acceptance_comment)
async def process_manager_acceptance_comment(message: Message, state: FSMContext, db: Session, user: User = None, language: str = "ru"):
    """Обработка комментария менеджера при принятии заявки за заявителя"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        lang = language
        if not request_number:
            await message.answer(get_text("unaccepted.handlers.request_number_not_found", language=lang))
            await state.clear()
            return

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await message.answer(get_text("unaccepted.handlers.request_not_found", language=lang))
            await state.clear()
            return

        # Проверяем что заявка всё ещё непринята (ожидает приёмки заявителем)
        if not is_awaiting_applicant(request):
            await message.answer(get_text("unaccepted.handlers.request_already_processed", language=lang))
            await state.clear()
            return

        comment = message.text.strip()

        if len(comment) < 10:
            await message.answer(
                get_text("unaccepted.handlers.comment_too_short", language=lang)
            )
            return

        # Канонический force-accept (PR2a-4): MANAGER_FORCE_ACCEPT
        # (Исполнено/Возвращена → Принято) через единый layer. Под каноном
        # (модель A) статус «Принято» сам по себе истина — manager_confirmed
        # больше не выставляем (исторические поля, PR0 Р6). Форматированный
        # комментарий менеджера дописывается в manager_confirmation_notes
        # внутри run_command (Op.APPEND).
        manager_comment = (
            f"\n\n--- ПРИНЯТО МЕНЕДЖЕРОМ {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} ---\n"
            f"👨‍💼 Менеджер: {user.first_name or 'Unknown'} {user.last_name or ''}\n"
            f"💬 Комментарий: {comment}\n"
            f"⚠️ Заявка принята без оценки заявителя"
        )

        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef,
            NotAuthorized, InvalidTransition, RepeatRejected, RepeatConflict,
            WorkflowError)
        try:
            run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=(user.id if user else None),
                             source="telegram"),
                ActionCommand(
                    f"force-accept-{request_number}",
                    Action.MANAGER_FORCE_ACCEPT,
                    {"reason": comment, "confirmation_notes": manager_comment},
                ),
            )
        except RequestNotFound:
            await message.answer(get_text("unaccepted.handlers.request_not_found", language=lang))
            await state.clear()
            return
        except (NotAuthorized, InvalidTransition, RepeatRejected, RepeatConflict):
            await message.answer(get_text("unaccepted.handlers.request_already_processed", language=lang))
            await state.clear()
            return
        except WorkflowError as e:
            logger.error(f"MANAGER_FORCE_ACCEPT отклонён для {request_number}: {e}")
            await message.answer(get_text("unaccepted.handlers.error_accepting_request", language=lang))
            await state.clear()
            return

        # Уведомляем заявителя
        applicant = db.query(User).filter(User.id == request.user_id).first()

        if applicant:
            try:
                await message.bot.send_message(
                    chat_id=applicant.telegram_id,
                    text=get_text("unaccepted.handlers.applicant_notification", language=lang).format(
                        request_number=request_number,
                        category=request.category,
                        address=request.address or get_text("unaccepted.handlers.not_specified", language=lang),
                        comment=comment
                    ),
                    parse_mode="HTML"
                )
            except Exception as send_error:
                logger.error(f"Ошибка отправки уведомления заявителю: {send_error}")

        # Уведомляем исполнителя (если назначен)
        if request.executor_id:
            executor = db.query(User).filter(User.id == request.executor_id).first()
            if executor:
                try:
                    await message.bot.send_message(
                        chat_id=executor.telegram_id,
                        text=get_text("unaccepted.handlers.executor_notification", language=lang).format(
                            request_number=request_number,
                            category=request.category
                        ),
                        parse_mode="HTML"
                    )
                except Exception as send_error:
                    logger.error(f"Ошибка отправки уведомления исполнителю: {send_error}")

        await message.answer(
            get_text("unaccepted.handlers.request_accepted_by_manager", language=lang).format(
                request_number=request_number
            ),
            reply_markup=get_manager_main_keyboard(language=lang),
            parse_mode="HTML"
        )

        await state.clear()

        logger.info(f"Менеджер {user.id if user else 'Unknown'} принял заявку {request_number} за заявителя с комментарием: {comment[:50]}...")

    except Exception as e:
        logger.error(f"Ошибка обработки принятия заявки менеджером: {e}")
        lang = language
        await message.answer(get_text("unaccepted.handlers.error_accepting_request", language=lang))
        await state.clear()


@router.callback_query(F.data == "unaccepted_back_to_list")
async def handle_back_to_unaccepted_list(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Возврат к списку непринятых заявок"""
    try:
        # Проверяем права доступа
        lang = language
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("unaccepted.handlers.no_permission", language=lang), show_alert=True)
            return

        # Получаем список непринятых заявок
        q = (
            db.query(Request)
            .filter(awaiting_applicant_clause())
            .order_by(
                Request.completed_at.desc().nullslast(),
                Request.updated_at.desc().nullslast(),
                Request.created_at.desc()
            )
        )
        requests = q.limit(20).all()

        if not requests:
            await callback.message.edit_text(
                get_text("unaccepted.handlers.no_unaccepted_requests", language=lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Форматируем список
        items = []
        now = datetime.now(timezone.utc)

        for r in requests:
            completed_at = r.completed_at if r.completed_at else r.updated_at
            if completed_at:
                if completed_at.tzinfo is None:
                    from datetime import timezone as dt_tz
                    completed_at = completed_at.replace(tzinfo=dt_tz.utc)

                waiting_time = now - completed_at
                days = waiting_time.days
                hours = waiting_time.seconds // 3600
                minutes = (waiting_time.seconds % 3600) // 60

                if days > 0:
                    time_str = f"{days}д {hours}ч"
                elif hours > 0:
                    time_str = f"{hours}ч {minutes}м"
                else:
                    time_str = f"{minutes}м"
            else:
                time_str = "неизв."

            item = {
                "request_number": r.request_number,
                "category": r.category,
                "address": r.address or get_text("unaccepted.handlers.address_not_specified", language=lang),
                "status": f"⏳ {time_str}"
            }
            items.append(item)

        await callback.message.edit_text(
            get_text("unaccepted.handlers.unaccepted_list_title", language=lang).format(count=len(requests)),
            reply_markup=get_manager_request_list_kb(items, 1, 1),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к списку непринятых заявок: {e}")
        lang = language
        await callback.answer(get_text("unaccepted.handlers.error_occurred", language=lang), show_alert=True)
