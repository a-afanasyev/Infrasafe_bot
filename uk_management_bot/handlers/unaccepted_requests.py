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
from uk_management_bot.services.auth_service import AuthService

import logging

router = Router()
logger = logging.getLogger(__name__)


def has_admin_access(roles: list = None, user: User = None) -> bool:
    """Проверка прав администратора/менеджера"""
    if not roles and not user:
        return False
    if roles and ("admin" in roles or "manager" in roles):
        return True
    if user and (user.role in ["admin", "manager"]):
        return True
    return False


@router.callback_query(F.data.startswith("unaccepted_remind_"))
async def handle_remind_applicant(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Напомнить заявителю о необходимости принять заявку"""
    try:
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения операции", show_alert=True)
            return

        request_number = callback.data.replace("unaccepted_remind_", "")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Проверяем что заявка действительно непринята
        if request.status != "Выполнена" or not request.manager_confirmed or request.is_returned:
            await callback.answer("Заявка уже обработана", show_alert=True)
            return

        # Получаем заявителя
        applicant = db.query(User).filter(User.id == request.user_id).first()

        if not applicant:
            await callback.answer("Заявитель не найден", show_alert=True)
            return

        # Формируем уведомление заявителю
        completed_at = request.completed_at if request.completed_at else request.updated_at
        if completed_at:
            if completed_at.tzinfo is None:
                from datetime import timezone as dt_tz
                completed_at = completed_at.replace(tzinfo=dt_tz.utc)
            completed_str = completed_at.strftime('%d.%m.%Y %H:%M')
        else:
            completed_str = "неизвестно"

        notification_text = (
            f"🔔 <b>Напоминание о приёмке заявки</b>\n\n"
            f"📋 Заявка #{request.request_number}\n"
            f"📂 Категория: {request.category}\n"
            f"📍 Адрес: {request.address or 'Не указан'}\n"
            f"✅ Завершена: {completed_str}\n\n"
            f"<b>Пожалуйста, примите выполненную работу или верните заявку на доработку.</b>\n\n"
            f"Для просмотра деталей и приёмки перейдите в раздел \"✅ Ожидают приёмки\"."
        )

        # Создаём клавиатуру с кнопкой просмотра
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="👁️ Просмотреть заявку",
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

            await callback.answer("✅ Напоминание отправлено заявителю", show_alert=True)

            logger.info(f"Отправлено напоминание заявителю {applicant.telegram_id} о заявке {request_number}")

        except Exception as send_error:
            logger.error(f"Ошибка отправки напоминания заявителю: {send_error}")
            await callback.answer("❌ Не удалось отправить напоминание", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка обработки напоминания заявителю: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("unaccepted_accept_"))
async def handle_manager_accept_request(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Менеджер принимает заявку за заявителя (требуется комментарий)"""
    try:
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения операции", show_alert=True)
            return

        request_number = callback.data.replace("unaccepted_accept_", "")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Проверяем что заявка действительно непринята
        if request.status != "Выполнена" or not request.manager_confirmed or request.is_returned:
            await callback.answer("Заявка уже обработана", show_alert=True)
            return

        # Сохраняем номер заявки в состояние
        await state.update_data(request_number=request_number)

        # Переводим в состояние ожидания комментария
        await state.set_state(ManagerAcceptanceStates.awaiting_manager_acceptance_comment)

        await callback.message.edit_text(
            f"✅ <b>Принятие заявки за заявителя</b>\n\n"
            f"📋 Заявка #{request_number}\n\n"
            f"<b>Обязательно укажите комментарий</b> (причину принятия за заявителя):\n\n"
            f"<i>Например: \"Заявитель не отвечает более 3 дней\", \"Заявитель на связи подтвердил выполнение\" и т.д.</i>",
            parse_mode="HTML"
        )

        await callback.answer()

        logger.info(f"Менеджер {callback.from_user.id} начал принятие заявки {request_number} за заявителя")

    except Exception as e:
        logger.error(f"Ошибка начала принятия заявки менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.message(ManagerAcceptanceStates.awaiting_manager_acceptance_comment)
async def process_manager_acceptance_comment(message: Message, state: FSMContext, db: Session, user: User = None):
    """Обработка комментария менеджера при принятии заявки за заявителя"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        if not request_number:
            await message.answer("❌ Ошибка: номер заявки не найден")
            await state.clear()
            return

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await message.answer("❌ Заявка не найдена")
            await state.clear()
            return

        # Проверяем что заявка всё ещё непринята
        if request.status != "Выполнена" or not request.manager_confirmed or request.is_returned:
            await message.answer("❌ Заявка уже обработана")
            await state.clear()
            return

        comment = message.text.strip()

        if len(comment) < 10:
            await message.answer(
                "❌ Комментарий слишком короткий (минимум 10 символов).\n\n"
                "Пожалуйста, укажите подробную причину принятия заявки за заявителя:"
            )
            return

        # Принимаем заявку от имени менеджера
        request.status = "Принято"
        request.manager_confirmed = True
        request.manager_confirmed_by = user.id if user else None
        request.manager_confirmed_at = datetime.now(timezone.utc)

        # Добавляем комментарий менеджера (БЕЗ звёзд)
        manager_comment = (
            f"\n\n--- ПРИНЯТО МЕНЕДЖЕРОМ {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} ---\n"
            f"👨‍💼 Менеджер: {user.first_name or 'Unknown'} {user.last_name or ''}\n"
            f"💬 Комментарий: {comment}\n"
            f"⚠️ Заявка принята без оценки заявителя"
        )

        if request.manager_confirmation_notes:
            request.manager_confirmation_notes += manager_comment
        else:
            request.manager_confirmation_notes = manager_comment

        db.commit()

        # Уведомляем заявителя
        applicant = db.query(User).filter(User.id == request.user_id).first()

        if applicant:
            try:
                await message.bot.send_message(
                    chat_id=applicant.telegram_id,
                    text=(
                        f"✅ <b>Заявка принята менеджером</b>\n\n"
                        f"📋 Заявка #{request_number}\n"
                        f"📂 Категория: {request.category}\n"
                        f"📍 Адрес: {request.address or 'Не указан'}\n\n"
                        f"💬 Комментарий менеджера:\n{comment}\n\n"
                        f"Спасибо за использование нашего сервиса!"
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
                        text=(
                            f"✅ <b>Заявка принята</b>\n\n"
                            f"📋 Заявка #{request_number}\n"
                            f"📂 Категория: {request.category}\n\n"
                            f"Заявка была принята менеджером."
                        ),
                        parse_mode="HTML"
                    )
                except Exception as send_error:
                    logger.error(f"Ошибка отправки уведомления исполнителю: {send_error}")

        await message.answer(
            f"✅ <b>Заявка #{request_number} принята</b>\n\n"
            f"Заявка принята от имени менеджера без оценки заявителя.\n"
            f"Комментарий добавлен в историю заявки.",
            reply_markup=get_manager_main_keyboard(),
            parse_mode="HTML"
        )

        await state.clear()

        logger.info(f"Менеджер {user.id if user else 'Unknown'} принял заявку {request_number} за заявителя с комментарием: {comment[:50]}...")

    except Exception as e:
        logger.error(f"Ошибка обработки принятия заявки менеджером: {e}")
        await message.answer("❌ Произошла ошибка при принятии заявки")
        await state.clear()


@router.callback_query(F.data == "unaccepted_back_to_list")
async def handle_back_to_unaccepted_list(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Возврат к списку непринятых заявок"""
    try:
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для просмотра списка", show_alert=True)
            return

        # Получаем список непринятых заявок
        q = (
            db.query(Request)
            .filter(
                Request.status == "Выполнена",
                Request.manager_confirmed == True,
                Request.is_returned == False
            )
            .order_by(
                Request.completed_at.desc().nullslast(),
                Request.updated_at.desc().nullslast(),
                Request.created_at.desc()
            )
        )
        requests = q.limit(20).all()

        if not requests:
            await callback.message.edit_text(
                "⏳ <b>Непринятых заявок нет</b>\n\n"
                "Все выполненные заявки приняты заявителями.",
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
                "address": r.address or "Адрес не указан",
                "status": f"⏳ {time_str}"
            }
            items.append(item)

        await callback.message.edit_text(
            f"⏳ <b>Непринятые заявки</b> ({len(requests)}):\n\n"
            f"<i>Время указывает сколько заявка ожидает принятия</i>",
            reply_markup=get_manager_request_list_kb(items, 1, 1),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к списку непринятых заявок: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
