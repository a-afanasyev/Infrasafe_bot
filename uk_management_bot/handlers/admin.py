from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session

from uk_management_bot.keyboards.admin import (
    get_manager_main_keyboard,
    get_manager_requests_inline,
    get_manager_request_list_kb,
    get_invite_role_keyboard,
    get_invite_specialization_keyboard,
    get_invite_expiry_keyboard,
    get_invite_confirmation_keyboard,
    get_completed_requests_submenu,
    get_assignment_type_keyboard,
    get_executors_by_category_keyboard,
)
from uk_management_bot.keyboards.base import get_main_keyboard, get_user_contextual_keyboard
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.request_service import RequestService
from uk_management_bot.services.invite_service import InviteService
from uk_management_bot.services.notification_service import async_notify_request_status_changed
from uk_management_bot.database.session import get_db
from uk_management_bot.utils.constants import (
    SPECIALIZATION_ELECTRIC,
    SPECIALIZATION_PLUMBING,
    SPECIALIZATION_SECURITY,
    SPECIALIZATION_CLEANING,
    SPECIALIZATION_OTHER,
)
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.utils.auth_helpers import has_admin_access
from datetime import datetime

router = Router()
logger = logging.getLogger(__name__)

class ManagerStates(StatesGroup):
    cancel_reason = State()
    clarify_reason = State()
    waiting_for_clarification_text = State()
    waiting_for_materials_edit = State()

from uk_management_bot.states.invite_creation import InviteCreationStates


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

async def auto_assign_request_by_category(request: Request, db: Session, manager: User):
    """
    Автоматически назначает заявку исполнителям по категории/специализации
    
    Args:
        request: Заявка для назначения
        db: Сессия базы данных
        manager: Менеджер, который назначает заявку
    """
    try:
        from uk_management_bot.database.models.request_assignment import RequestAssignment
        import json
        
        # Маппинг категорий заявок на специализации
        category_to_specialization = {
            "Сантехника": "plumber",
            "Электрика": "electrician", 
            "Благоустройство": "landscaping",
            "Уборка": "cleaning",
            "Безопасность": "security",
            "Ремонт": "repair",
            "Установка": "installation",
            "Обслуживание": "maintenance",
            "HVAC": "hvac"
        }
        
        # Определяем специализацию по категории заявки
        specialization = category_to_specialization.get(request.category)
        if not specialization:
            logger.warning(f"Неизвестная категория заявки: {request.category}")
            return
        
        # Находим исполнителей с нужной специализацией
        executors = db.query(User).filter(
            User.active_role == "executor",
            User.status == "approved"
        ).all()
        
        matching_executors = []
        for executor in executors:
            if executor.specialization:
                try:
                    # Парсим специализации исполнителя
                    if isinstance(executor.specialization, str):
                        executor_specializations = json.loads(executor.specialization)
                    else:
                        executor_specializations = executor.specialization
                    
                    # Проверяем, есть ли нужная специализация
                    if specialization in executor_specializations:
                        matching_executors.append(executor)
                except (json.JSONDecodeError, TypeError):
                    # Если специализация - просто строка
                    if executor.specialization == specialization:
                        matching_executors.append(executor)
        
        if not matching_executors:
            logger.warning(f"Не найдено исполнителей для специализации {specialization}")
            return
        
        # Проверяем, есть ли уже назначение для этой заявки
        existing_assignment = db.query(RequestAssignment).filter(
            RequestAssignment.request_number == request.request_number,
            RequestAssignment.status == "active"
        ).first()
        
        if existing_assignment:
            logger.info(f"Заявка {request.request_number} уже назначена, пропускаем")
            return
        
        # Дополнительная проверка на групповые назначения для той же специализации
        existing_group_assignment = db.query(RequestAssignment).filter(
            RequestAssignment.request_number == request.request_number,
            RequestAssignment.assignment_type == "group",
            RequestAssignment.group_specialization == specialization,
            RequestAssignment.status == "active"
        ).first()
        
        if existing_group_assignment:
            logger.info(f"Заявка {request.request_number} уже назначена группе {specialization}, пропускаем")
            return
        
        # Создаем групповое назначение
        assignment = RequestAssignment(
            request_number=request.request_number,
            assignment_type="group",
            group_specialization=specialization,
            status="active",
            created_by=manager.id
        )
        
        db.add(assignment)
        
        # Обновляем поля заявки
        request.assignment_type = "group"
        request.assigned_group = specialization
        request.assigned_at = datetime.now()
        request.assigned_by = manager.id
        
        logger.info(f"Заявка {request.request_number} автоматически назначена группе {specialization} ({len(matching_executors)} исполнителей)")
        
    except Exception as e:
        logger.error(f"Ошибка автоматического назначения заявки {request.request_number}: {e}")


# ===== ОБРАБОТЧИКИ ПРОСМОТРА ЗАЯВОК ДЛЯ МЕНЕДЖЕРОВ =====

@router.callback_query(F.data.startswith("mview_"))
async def handle_manager_view_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка просмотра деталей заявки для менеджеров"""
    try:
        logger.info(f"Обработка просмотра заявки менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для просмотра заявок", show_alert=True)
            return
        
        request_number = callback.data.replace("mview_", "")
        
        # Получаем заявку из базы данных
        request = db.query(Request).filter(Request.request_number == request_number).first()
        
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Получаем информацию о пользователе, создавшем заявку
        request_user = db.query(User).filter(User.id == request.user_id).first()
        if request_user:
            # Формируем полное имя из first_name и last_name
            full_name_parts = []
            if request_user.first_name:
                full_name_parts.append(request_user.first_name)
            if request_user.last_name:
                full_name_parts.append(request_user.last_name)
            user_info = " ".join(full_name_parts) if full_name_parts else f"Пользователь {request_user.telegram_id}"
        else:
            user_info = "Неизвестный пользователь"
        
        # Формируем детальную информацию о заявке
        message_text = f"📋 Заявка #{request.request_number}\n\n"
        message_text += f"👤 Заявитель: {user_info}\n"
        message_text += f"📱 Telegram ID: {request_user.telegram_id if request_user else 'N/A'}\n"
        message_text += f"📂 Категория: {request.category}\n"
        message_text += f"📊 Статус: {request.status}\n"
        message_text += f"📍 Адрес: {request.address}\n"
        message_text += f"📝 Описание: {request.description}\n"
        message_text += f"⚡ Срочность: {request.urgency}\n"
        if request.apartment:
            message_text += f"🏠 Квартира: {request.apartment}\n"
        message_text += f"📅 Создана: {request.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        if request.updated_at:
            message_text += f"🔄 Обновлена: {request.updated_at.strftime('%d.%m.%Y %H:%M')}\n"
        if request.notes:
            message_text += f"💬 Примечания: {request.notes}\n"

        # Проверяем наличие медиафайлов
        media_files = request.media_files if request.media_files else []
        completion_media = request.completion_media if request.completion_media else []
        has_media = len(media_files) > 0 or len(completion_media) > 0

        # Создаем клавиатуру действий для менеджера
        from uk_management_bot.keyboards.admin import get_manager_request_actions_keyboard, get_manager_completed_request_actions_keyboard

        # Для исполненных заявок (ожидающих подтверждения) - специальная клавиатура
        if request.status == "Выполнена":
            actions_kb = get_manager_completed_request_actions_keyboard(request.request_number, is_returned=request.is_returned)

            # Добавляем кнопку медиа если есть
            rows = list(actions_kb.inline_keyboard)
            if has_media:
                rows.append([InlineKeyboardButton(text="📎 Медиа", callback_data=f"media_{request.request_number}")])
            rows.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data="mreq_back_to_list")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        else:
            # Для обычных заявок - стандартная клавиатура
            actions_kb = get_manager_request_actions_keyboard(request.request_number, has_media=has_media)

            # Добавляем кнопку "Назад к списку"
            rows = list(actions_kb.inline_keyboard)
            rows.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data="mreq_back_to_list")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
        logger.info(f"Показаны детали заявки {request.request_number} менеджеру {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки просмотра заявки менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("media_"))
async def handle_view_request_media(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка просмотра медиафайлов заявки"""
    try:
        from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

        logger.info(f"Просмотр медиафайлов заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для просмотра медиафайлов", show_alert=True)
            return

        request_number = callback.data.replace("media_", "")

        # Получаем заявку из базы данных
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Проверяем наличие медиафайлов и парсим JSON
        import json

        media_files = []
        if request.media_files:
            try:
                media_files = json.loads(request.media_files) if isinstance(request.media_files, str) else request.media_files
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Ошибка парсинга media_files для заявки {request.request_number}: {e}")

        completion_media = []
        if request.completion_media:
            try:
                completion_media = json.loads(request.completion_media) if isinstance(request.completion_media, str) else request.completion_media
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Ошибка парсинга completion_media для заявки {request.request_number}: {e}")

        if not media_files and not completion_media:
            await callback.answer("📎 К этой заявке не прикреплены медиафайлы", show_alert=True)
            return

        # Отправляем медиафайлы при создании заявки
        if media_files:
            await callback.message.answer(
                f"📎 <b>Медиафайлы при создании заявки #{request.request_number}</b>",
                parse_mode="HTML"
            )

            # Если файлов больше 1, отправляем группой
            if len(media_files) > 1:
                media_group = []
                for idx, media_item in enumerate(media_files):
                    # Извлекаем file_id из объекта или используем как строку
                    file_id = media_item.get("file_id") if isinstance(media_item, dict) else media_item

                    try:
                        # Пробуем как фото
                        if idx == 0:
                            media_group.append(InputMediaPhoto(media=file_id, caption=f"Фото {idx+1}/{len(media_files)}"))
                        else:
                            media_group.append(InputMediaPhoto(media=file_id))
                    except:
                        # Если не получилось как фото, пробуем как документ
                        if idx == 0:
                            media_group.append(InputMediaDocument(media=file_id, caption=f"Файл {idx+1}/{len(media_files)}"))
                        else:
                            media_group.append(InputMediaDocument(media=file_id))

                if media_group:
                    await callback.message.answer_media_group(media=media_group)
            else:
                # Один файл - отправляем отдельно
                file_id = media_files[0].get("file_id") if isinstance(media_files[0], dict) else media_files[0]
                try:
                    await callback.message.answer_photo(photo=file_id)
                except:
                    try:
                        await callback.message.answer_document(document=file_id)
                    except Exception as e:
                        logger.error(f"Ошибка отправки медиафайла: {e}")
                        await callback.message.answer("❌ Не удалось отправить медиафайл")

        # Отправляем медиафайлы при завершении заявки
        if completion_media:
            await callback.message.answer(
                f"📎 <b>Медиафайлы при завершении заявки #{request.request_number}</b>",
                parse_mode="HTML"
            )

            # Если файлов больше 1, отправляем группой
            if len(completion_media) > 1:
                media_group = []
                for idx, media_item in enumerate(completion_media):
                    # Извлекаем file_id из объекта или используем как строку
                    file_id = media_item.get("file_id") if isinstance(media_item, dict) else media_item

                    try:
                        # Пробуем как фото
                        if idx == 0:
                            media_group.append(InputMediaPhoto(media=file_id, caption=f"Фото {idx+1}/{len(completion_media)}"))
                        else:
                            media_group.append(InputMediaPhoto(media=file_id))
                    except:
                        # Если не получилось как фото, пробуем как документ
                        if idx == 0:
                            media_group.append(InputMediaDocument(media=file_id, caption=f"Файл {idx+1}/{len(completion_media)}"))
                        else:
                            media_group.append(InputMediaDocument(media=file_id))

                if media_group:
                    await callback.message.answer_media_group(media=media_group)
            else:
                # Один файл - отправляем отдельно
                file_id = completion_media[0].get("file_id") if isinstance(completion_media[0], dict) else completion_media[0]
                try:
                    await callback.message.answer_photo(photo=file_id)
                except:
                    try:
                        await callback.message.answer_document(document=file_id)
                    except Exception as e:
                        logger.error(f"Ошибка отправки медиафайла при завершении: {e}")
                        await callback.message.answer("❌ Не удалось отправить медиафайл")

        await callback.answer("✅ Медиафайлы отправлены")
        logger.info(f"Отправлены медиафайлы заявки {request.request_number} менеджеру {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка просмотра медиафайлов заявки: {e}")
        await callback.answer("Произошла ошибка при загрузке медиафайлов", show_alert=True)


@router.callback_query(F.data.startswith("confirm_completed_"))
async def handle_manager_confirm_completed(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Менеджер подтверждает выполнение заявки"""
    try:
        from datetime import datetime
        from uk_management_bot.services.notification_service import NotificationService

        logger.info(f"Подтверждение выполнения заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для подтверждения заявок", show_alert=True)
            return

        request_number = callback.data.replace("confirm_completed_", "")
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Подтверждаем выполнение
        old_status = request.status
        request.status = "Выполнена"  # Статус "Выполнена" - подтверждено менеджером, ждёт приёмки заявителем
        request.manager_confirmed = True
        request.manager_confirmed_by = user.id
        request.manager_confirmed_at = datetime.now()
        db.commit()

        # Уведомление через сервис (отправит заявителю, исполнителю и в канал)
        try:
            from aiogram import Bot
            bot = Bot.get_current()
            await async_notify_request_status_changed(bot, db, request, old_status, "Выполнена")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

        # Дополнительное уведомление заявителю с инструкцией
        applicant = request.user
        if applicant and applicant.telegram_id:
            try:
                from aiogram import Bot
                bot = Bot.get_current()

                notification_text = (
                    f"✅ <b>Ваша заявка #{request.format_number_for_display()} выполнена!</b>\n\n"
                    f"Пожалуйста, ознакомьтесь с результатами работы и примите заявку.\n"
                    f"Перейдите в раздел '✅ Ожидают приёмки' в главном меню."
                )

                await bot.send_message(applicant.telegram_id, notification_text)
                logger.info(f"✅ Уведомление о подтверждении заявки {request.request_number} отправлено заявителю {applicant.telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления заявителю: {e}")

        await callback.message.edit_text(
            f"✅ Заявка #{request.request_number} подтверждена!\n\n"
            f"Статус изменён на 'Выполнена'.\n"
            f"Заявитель получил уведомление о необходимости приёмки."
        )

        logger.info(f"Заявка {request.request_number} подтверждена менеджером {user.id}")

    except Exception as e:
        logger.error(f"Ошибка подтверждения выполнения заявки: {e}")
        if db:
            db.rollback()
        await callback.answer("Произошла ошибка при подтверждении", show_alert=True)


@router.callback_query(F.data.startswith("reconfirm_completed_"))
async def handle_manager_reconfirm_completed(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Менеджер повторно подтверждает выполнение возвратной заявки"""
    try:
        from datetime import datetime
        from uk_management_bot.services.notification_service import NotificationService

        logger.info(f"Повторное подтверждение возвратной заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для подтверждения заявок", show_alert=True)
            return

        request_number = callback.data.replace("reconfirm_completed_", "")
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Сбрасываем флаг возврата и повторно подтверждаем
        old_status = "Исполнено (возвращена)"
        request.status = "Выполнена"
        request.is_returned = False  # Снимаем флаг возврата
        request.manager_confirmed = True
        request.manager_confirmed_by = user.id
        request.manager_confirmed_at = datetime.now()
        db.commit()

        # Уведомление через сервис (отправит заявителю, исполнителю и в канал)
        try:
            from aiogram import Bot
            bot = Bot.get_current()
            await async_notify_request_status_changed(bot, db, request, old_status, "Выполнена")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

        # Дополнительное уведомление заявителю с инструкцией
        applicant = request.user
        if applicant and applicant.telegram_id:
            try:
                from aiogram import Bot
                bot = Bot.get_current()

                notification_text = (
                    f"✅ <b>Ваша заявка #{request.format_number_for_display()} выполнена повторно!</b>\n\n"
                    f"Замечания учтены. Пожалуйста, ознакомьтесь с результатами и примите заявку.\n"
                    f"Перейдите в раздел '✅ Ожидают приёмки' в главном меню."
                )

                await bot.send_message(applicant.telegram_id, notification_text)
                logger.info(f"✅ Уведомление о повторном подтверждении заявки {request.request_number} отправлено заявителю {applicant.telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления заявителю: {e}")

        await callback.message.edit_text(
            f"✅ Возвратная заявка #{request.request_number} подтверждена повторно!\n\n"
            f"Статус изменён на 'Выполнена'.\n"
            f"Заявитель получил уведомление."
        )

        logger.info(f"Возвратная заявка {request.request_number} подтверждена повторно менеджером {user.id}")

    except Exception as e:
        logger.error(f"Ошибка повторного подтверждения заявки: {e}")
        if db:
            db.rollback()
        await callback.answer("Произошла ошибка при подтверждении", show_alert=True)


@router.callback_query(F.data.startswith("return_to_work_"))
async def handle_manager_return_to_work(callback: CallbackQuery, db: Session, roles: list = None, user: User = None):
    """Менеджер возвращает заявку в работу"""
    try:
        logger.info(f"Возврат заявки в работу менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для изменения статуса заявок", show_alert=True)
            return

        request_number = callback.data.replace("return_to_work_", "")
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Возвращаем в работу
        old_status = request.status
        request.status = "В работе"
        request.is_returned = False  # Снимаем флаг возврата если был
        request.manager_confirmed = False
        db.commit()

        # Уведомление через сервис (отправит заявителю, исполнителю и в канал)
        try:
            from aiogram import Bot
            bot = Bot.get_current()
            await async_notify_request_status_changed(bot, db, request, old_status, "В работе")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

        await callback.message.edit_text(
            f"🔄 Заявка #{request.request_number} возвращена в работу.\n\n"
            f"Статус изменён на 'В работе'."
        )

        logger.info(f"Заявка {request.request_number} возвращена в работу менеджером {user.id}")

    except Exception as e:
        logger.error(f"Ошибка возврата заявки в работу: {e}")
        if db:
            db.rollback()
        await callback.answer("Произошла ошибка при изменении статуса", show_alert=True)


@router.callback_query(F.data.startswith("mreq_page_"))
async def handle_manager_request_pagination(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка пагинации списков заявок для менеджеров"""
    try:
        logger.info(f"Обработка пагинации заявок менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для просмотра заявок", show_alert=True)
            return
        
        # Парсим данные пагинации
        page_data = callback.data.replace("mreq_page_", "")
        
        if page_data == "curr":
            await callback.answer("Текущая страница")
            return
        
        current_page = int(page_data)
        
        # Определяем тип списка заявок (новые, активные, архив)
        # Пока что показываем активные заявки
        active_statuses = ["В работе", "Закуп", "Уточнение"]
        q = (
            db.query(Request)
            .filter(Request.status.in_(active_statuses))
            .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
        )
        
        # Вычисляем общее количество страниц
        total_requests = q.count()
        requests_per_page = 10
        total_pages = max(1, (total_requests + requests_per_page - 1) // requests_per_page)
        
        if current_page < 1 or current_page > total_pages:
            await callback.answer("Страница не найдена", show_alert=True)
            return
        
        # Получаем заявки для текущей страницы
        requests = q.offset((current_page - 1) * requests_per_page).limit(requests_per_page).all()
        
        if not requests:
            await callback.answer("Нет заявок на этой странице", show_alert=True)
            return
        
        items = [{"request_number": r.request_number, "category": r.category, "address": r.address, "status": r.status} for r in requests]
        
        # Обновляем сообщение с новой страницей
        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
        new_keyboard = get_manager_request_list_kb(items, current_page, total_pages)
        
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        
        logger.info(f"Показана страница {current_page} заявок менеджеру {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки пагинации заявок менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "mreq_back_to_list")
async def handle_manager_back_to_list(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Возврат из деталей заявки к списку для менеджеров"""
    try:
        logger.info(f"Возврат к списку заявок менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для просмотра заявок", show_alert=True)
            return
        
        # Определяем, из какого списка мы пришли, по статусу заявки
        # Получаем текущую заявку из сообщения
        message_text = callback.message.text
        if "Заявка #" in message_text:
            # Извлекаем номер заявки из текста сообщения
            import re
            match = re.search(r'Заявка #(\d{6}-\d{3})', message_text)
            if match:
                request_number = match.group(1)
                request = db.query(Request).filter(Request.request_number == request_number).first()
                if request:
                    # Определяем тип списка по статусу заявки
                    if request.status == "Новая":
                        # Возвращаемся к новым заявкам
                        q = (
                            db.query(Request)
                            .filter(Request.status == "Новая")
                            .order_by(Request.created_at.desc())
                        )
                        requests = q.limit(10).all()
                        
                        if not requests:
                            await callback.message.edit_text("Нет новых заявок")
                            return
                        
                        items = [{"request_number": r.request_number, "category": r.category, "address": r.address, "status": r.status} for r in requests]
                        
                        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
                        keyboard = get_manager_request_list_kb(items, 1, 1)
                        
                        await callback.message.edit_text("🆕 Новые заявки:", reply_markup=keyboard)
                        return
                    elif request.status == "Выполнена":
                        # Возвращаемся к исполненным заявкам
                        q = (
                            db.query(Request)
                            .filter(Request.status == "Выполнена")
                            .order_by(
                                Request.is_returned.desc(),  # Возвратные заявки показываем первыми
                                Request.updated_at.desc().nullslast(),
                                Request.created_at.desc()
                            )
                        )
                        requests = q.limit(10).all()

                        if not requests:
                            await callback.message.edit_text("Нет исполненных заявок")
                            return

                        # Добавляем пометку "возвратная" для возвратных заявок
                        items = []
                        for r in requests:
                            item = {
                                "request_number": r.request_number,
                                "category": r.category,
                                "address": r.address,
                                "status": r.status
                            }
                            if r.is_returned:
                                item["suffix"] = " 🔄"
                            items.append(item)

                        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
                        keyboard = get_manager_request_list_kb(items, 1, 1)

                        await callback.message.edit_text("✅ Исполненные заявки:", reply_markup=keyboard)
                        return
                    elif request.status in ["В работе", "Закуп", "Уточнение"]:
                        # Возвращаемся к активным заявкам
                        active_statuses = ["В работе", "Закуп", "Уточнение"]
                        q = (
                            db.query(Request)
                            .filter(Request.status.in_(active_statuses))
                            .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
                        )
                        requests = q.limit(10).all()

                        if not requests:
                            await callback.message.edit_text("Нет активных заявок")
                            return

                        items = [{"request_number": r.request_number, "category": r.category, "address": r.address, "status": r.status} for r in requests]

                        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
                        keyboard = get_manager_request_list_kb(items, 1, 1)

                        await callback.message.edit_text("🔄 Активные заявки:", reply_markup=keyboard)
                        return
        
        # Если не удалось определить тип списка, показываем активные заявки по умолчанию
        active_statuses = ["В работе", "Закуп", "Уточнение"]
        q = (
            db.query(Request)
            .filter(Request.status.in_(active_statuses))
            .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
        )
        requests = q.limit(10).all()
        
        if not requests:
            await callback.message.edit_text("Нет активных заявок")
            return
        
        items = [{"request_number": r.request_number, "category": r.category, "address": r.address, "status": r.status} for r in requests]
        
        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
        keyboard = get_manager_request_list_kb(items, 1, 1)
        
        await callback.message.edit_text("🔄 Активные заявки:", reply_markup=keyboard)
        
        logger.info(f"Возврат к списку заявок выполнен для менеджера {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка возврата к списку заявок: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.message(F.text == "🧪 Тест middleware")
async def test_middleware(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, user_status: str = None):
    """Тестовый обработчик для проверки middleware"""
    
    # Логирование параметров middleware для отладки
    logger.debug(f"Admin panel access check: roles={roles}, active_role={active_role}, user_id={message.from_user.id}")
    
    # Проверяем доступ к админ панели
    has_access = False
    if roles:
        has_access = any(role in ['admin', 'manager'] for role in roles)
    elif user and user.roles:
        try:
            import json
            user_roles = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
            has_access = any(role in ['admin', 'manager'] for role in user_roles)
        except:
            pass
    
    print(f"🔧 Доступ к админ панели: {'✅ Есть' if has_access else '❌ Нет'}")
    
    await message.answer(f"Тест middleware:\nroles={roles}\nactive_role={active_role}\nuser={'Есть' if user else 'Нет'}\nhas_access={'Да' if has_access else 'Нет'}")

@router.message(F.text == "🔧 Админ панель")
async def open_admin_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, user_status: str = None):
    """Открыть админ панель"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    await message.answer("Панель менеджера", reply_markup=get_manager_main_keyboard())


@router.message(F.text == "👥 Управление пользователями")  
async def open_user_management_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Открыть панель управления пользователями"""
    lang = message.from_user.language_code or 'ru'
    
    # ОТЛАДКА
    logger.debug(f"User management panel opened: user_id={message.from_user.id}, roles={roles}, user_status={user.status if user else None}")
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Импортируем здесь, чтобы избежать циклических импортов
    try:
        from uk_management_bot.handlers.user_management import open_user_management
        await open_user_management(message, db, roles, active_role, user)
    except ImportError as e:
        logger.error(f"Ошибка импорта open_user_management: {e}")
        await message.answer(
            get_text("errors.unknown_error", language=lang)
        )
    except Exception as e:
        logger.error(f"Ошибка в open_user_management: {e}")
        await message.answer(
            get_text("errors.unknown_error", language=lang)
        )


@router.message(F.text == "👷 Управление сотрудниками")
async def open_employee_management_panel(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Открыть панель управления сотрудниками"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    try:
        # Получаем статистику сотрудников
        from uk_management_bot.services.user_management_service import UserManagementService
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_employee_stats()
        
        # Показываем главное меню управления сотрудниками
        from uk_management_bot.keyboards.employee_management import get_employee_management_main_keyboard
        
        await message.answer(
            "👷 Панель управления сотрудниками",
            reply_markup=get_employee_management_main_keyboard(stats, lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка открытия панели управления сотрудниками: {e}")
        await message.answer("Произошла ошибка при открытии панели управления сотрудниками")


@router.message(F.text == "🆕 Новые заявки")
async def list_new_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать новые заявки"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Новые заявки: только "Новая" (🆕)
    q = (
        db.query(Request)
        .filter(Request.status == "Новая")
        .order_by(Request.created_at.desc())
    )
    requests = q.limit(10).all()
    
    if not requests:
        await message.answer("Нет новых заявок", reply_markup=get_manager_main_keyboard())
        return
    
    items = [{"request_number": r.request_number, "category": r.category, "address": r.address, "status": r.status} for r in requests]
    await message.answer("🆕 Новые заявки:", reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text == "🔄 Активные заявки")
async def list_active_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать активные заявки"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    active_statuses = ["В работе", "Закуп", "Уточнение"]
    q = (
        db.query(Request)
        .filter(Request.status.in_(active_statuses))
        .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
    )
    requests = q.limit(10).all()
    
    if not requests:
        await message.answer("Нет активных заявок", reply_markup=get_manager_main_keyboard())
        return
    
    items = [{"request_number": r.request_number, "category": r.category, "address": r.address, "status": r.status} for r in requests]
    await message.answer("🔄 Активные заявки:", reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text == "✅ Исполненные заявки")
async def show_completed_requests_menu(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать подменю для исполненных заявок"""
    lang = message.from_user.language_code or 'ru'

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Получаем статистику
    total_completed = db.query(Request).filter(Request.status == "Выполнена").count()
    returned_count = db.query(Request).filter(
        Request.status == "Выполнена",
        Request.is_returned == True
    ).count()

    stats_text = (
        f"✅ <b>Исполненные заявки</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"📋 Всего исполненных: {total_completed}\n"
        f"🔄 Возвращённых: {returned_count}\n\n"
        f"Выберите раздел:"
    )

    await message.answer(stats_text, reply_markup=get_completed_requests_submenu(), parse_mode="HTML")


@router.message(F.text == "📋 Все исполненные")
async def list_all_completed_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать все исполненные заявки"""
    lang = message.from_user.language_code or 'ru'

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Все исполненные заявки: статус "Выполнена"
    q = (
        db.query(Request)
        .filter(Request.status == "Выполнена")
        .order_by(
            Request.is_returned.desc(),  # Возвратные заявки показываем первыми
            Request.updated_at.desc().nullslast(),
            Request.created_at.desc()
        )
    )
    requests = q.limit(10).all()

    if not requests:
        await message.answer("Нет исполненных заявок", reply_markup=get_completed_requests_submenu())
        return

    # Добавляем пометку "возвратная" для возвратных заявок
    items = []
    for r in requests:
        item = {
            "request_number": r.request_number,
            "category": r.category,
            "address": r.address,
            "status": "🔄 Возвратная" if r.is_returned else r.status
        }
        items.append(item)

    await message.answer("📋 Все исполненные заявки:", reply_markup=get_manager_request_list_kb(items, 1, 1))


@router.message(F.text == "🔄 Возвращённые")
async def list_returned_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать только возвращённые заявки"""
    lang = message.from_user.language_code or 'ru'

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    # Только возвращённые заявки
    q = (
        db.query(Request)
        .filter(
            Request.status == "Выполнена",
            Request.is_returned == True
        )
        .order_by(
            Request.returned_at.desc().nullslast(),
            Request.updated_at.desc().nullslast(),
            Request.created_at.desc()
        )
    )
    requests = q.limit(10).all()

    if not requests:
        await message.answer(
            "✅ Нет возвращённых заявок\n\nВсе заявки обработаны!",
            reply_markup=get_completed_requests_submenu()
        )
        return

    items = []
    for r in requests:
        # Форматируем информацию о возврате
        return_info = ""
        if r.returned_at:
            return_info = f" • {r.returned_at.strftime('%d.%m %H:%M')}"

        item = {
            "request_number": r.request_number,
            "category": r.category,
            "address": r.address,
            "status": f"🔄 Возврат{return_info}"
        }
        items.append(item)

    await message.answer(
        f"🔄 <b>Возвращённые заявки</b> ({len(requests)}):",
        reply_markup=get_manager_request_list_kb(items, 1, 1),
        parse_mode="HTML"
    )


@router.message(F.text == "🔙 Назад в меню")
async def back_to_main_menu(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Вернуться в главное меню менеджера"""
    lang = message.from_user.language_code or 'ru'

    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return

    await message.answer("🔧 Панель менеджера", reply_markup=get_manager_main_keyboard())


@router.message(F.text == "📦 Архив")
async def list_archive_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать архивные заявки"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Архив: только Выполнена (⭐) и Отменена (❌)
    archive_statuses = ["Выполнена", "Подтверждена", "Отменена"]
    q = (
        db.query(Request)
        .filter(Request.status.in_(archive_statuses))
        .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
    )
    requests = q.limit(10).all()
    if not requests:
        await message.answer("Архив пуст", reply_markup=get_manager_main_keyboard())
        return
    def _icon(s: str) -> str:
        return {"Выполнена": "✅", "Подтверждена": "⭐", "Отменена": "❌", "Принято": "✅"}.get(s, "")
    # Каждую заявку отправляем отдельным сообщением
    for r in requests:
        addr = r.address[:60] + ("…" if len(r.address) > 60 else "")
        text = (
            f"{_icon(r.status)} #{r.request_number} • {r.category} • {r.status}\n"
            f"Адрес: {addr}\n"
            f"Создана: {r.created_at.strftime('%d.%m.%Y %H:%M')}"
        )
        if r.notes and r.notes.strip():
            if r.status == "Отменена":
                text += f"\n💬 Причина отказа: {r.notes.strip()}"
            else:
                text += f"\n💬 Заметки: {r.notes.strip()}"
        await message.answer(text)
    await message.answer("📦 Конец списка архива", reply_markup=get_manager_main_keyboard())

@router.message(F.text == "💰 Закуп")
async def list_procurement_requests(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Показать заявки в статусе закупа"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("errors.permission_denied", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Получаем заявки в статусе "Закуп"
    q = (
        db.query(Request)
        .filter(Request.status == "Закуп")
        .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
    )
    requests = q.limit(10).all()
    
    if not requests:
        await message.answer("💰 Заявок в статусе 'Закуп' не найдено", reply_markup=get_manager_main_keyboard())
        return
    
    # Каждую заявку отправляем отдельным сообщением
    for r in requests:
        addr = r.address[:60] + ("…" if len(r.address) > 60 else "")
        text = (
            f"💰 #{r.request_number} • {r.category} • {r.status}\n"
            f"Адрес: {addr}\n"
            f"Создана: {r.created_at.strftime('%d.%m.%Y %H:%M')}"
        )
        # Показываем запрошенные материалы и комментарии менеджера
        if r.requested_materials:
            text += f"\n📋 Запрошено: {r.requested_materials}"
        if r.manager_materials_comment:
            text += f"\n💬 Менеджер: {r.manager_materials_comment}"
        # Для совместимости со старыми записями
        if not r.requested_materials and r.purchase_materials:
            text += f"\n💡 Материалы: {r.purchase_materials}"
        
        # Создаем инлайн клавиатуру для действий с заявкой
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Вернуть в работу", callback_data=f"return_to_work_{r.request_number}")],
            [InlineKeyboardButton(text="✏️ Комментарий менеджера", callback_data=f"edit_materials_{r.request_number}")]
        ])
        
        await message.answer(text, reply_markup=keyboard)
    
    await message.answer("💰 Конец списка заявок в статусе 'Закуп'", reply_markup=get_manager_main_keyboard())
    logger.info(f"Показаны заявки в статусе закуп менеджеру {message.from_user.id}")






# ===== ОБРАБОТЧИКИ СОЗДАНИЯ ПРИГЛАШЕНИЙ =====

@router.message(F.text == "📨 Создать приглашение")
async def start_invite_creation(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Начать процесс создания приглашения"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа (только менеджеры могут создавать приглашения)
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("invites.manager_only", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    await message.answer(
        get_text("invites.select_role", language=lang),
        reply_markup=get_invite_role_keyboard()
    )


@router.callback_query(F.data.startswith("invite_role_"))
async def handle_invite_role_selection(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработчик выбора роли для приглашения"""
    lang = callback.from_user.language_code or 'ru'
    
    # Извлекаем роль из callback_data
    role = callback.data.replace("invite_role_", "")
    
    if role not in ["applicant", "executor", "manager"]:
        await callback.answer("Неверная роль")
        return
    
    # Сохраняем роль в состоянии
    await state.update_data(role=role)
    
    # Если выбрана роль executor, нужно выбрать специализацию
    if role == "executor":
        await callback.message.edit_text(
            get_text("invites.select_specialization", language=lang),
            reply_markup=get_invite_specialization_keyboard()
        )
        await state.set_state(InviteCreationStates.waiting_for_specialization)
    else:
        # Для других ролей переходим к выбору срока действия
        await callback.message.edit_text(
            get_text("invites.select_expiry", language=lang),
            reply_markup=get_invite_expiry_keyboard()
        )
        await state.set_state(InviteCreationStates.waiting_for_expiry)
    
    await callback.answer()


@router.callback_query(F.data.startswith("invite_spec_"))
async def handle_invite_specialization_selection(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработчик выбора специализации для исполнителя"""
    lang = callback.from_user.language_code or 'ru'
    
    # Извлекаем специализацию из callback_data
    specialization = callback.data.replace("invite_spec_", "")
    
    # Сохраняем специализацию в состоянии
    await state.update_data(specialization=specialization)
    
    # Переходим к выбору срока действия
    await callback.message.edit_text(
        get_text("invites.select_expiry", language=lang),
        reply_markup=get_invite_expiry_keyboard()
    )
    await state.set_state(InviteCreationStates.waiting_for_expiry)
    
    await callback.answer()


@router.callback_query(F.data.startswith("invite_expiry_"))
async def handle_invite_expiry_selection(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработчик выбора срока действия приглашения"""
    lang = callback.from_user.language_code or 'ru'
    
    # Извлекаем срок действия из callback_data
    expiry = callback.data.replace("invite_expiry_", "")
    
    # Преобразуем в часы
    expiry_hours = {
        "1h": 1,
        "24h": 24,
        "7d": 168  # 7 дней * 24 часа
    }.get(expiry, 24)
    
    # Сохраняем срок действия в состоянии
    await state.update_data(expiry_hours=expiry_hours)
    
    # Получаем данные из состояния для подтверждения
    data = await state.get_data()
    role = data.get("role", "unknown")
    specialization = data.get("specialization", "")
    expiry_text = {
        1: "1 час",
        24: "24 часа",
        168: "7 дней"
    }.get(expiry_hours, "24 часа")
    
    # Формируем текст подтверждения
    role_name = get_text(f"roles.{role}", language=lang)
    confirmation_text = f"📋 Подтвердите создание приглашения:\n\n"
    confirmation_text += f"👤 Роль: {role_name}\n"
    
    if role == "executor" and specialization:
        spec_name = get_text(f"specializations.{specialization}", language=lang)
        confirmation_text += f"🛠️ Специализация: {spec_name}\n"
    
    confirmation_text += f"⏰ Срок действия: {expiry_text}\n\n"
    confirmation_text += "Нажмите 'Создать приглашение' для генерации токена."
    
    await callback.message.edit_text(
        confirmation_text,
        reply_markup=get_invite_confirmation_keyboard()
    )
    await state.set_state(InviteCreationStates.waiting_for_confirmation)
    
    await callback.answer()


@router.callback_query(F.data == "invite_confirm")
async def handle_invite_confirmation(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработчик подтверждения создания приглашения"""
    lang = callback.from_user.language_code or 'ru'
    
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        role = data.get("role")
        specialization = data.get("specialization", "")
        expiry_hours = data.get("expiry_hours", 24)
        
        if not role:
            await callback.answer("Ошибка: роль не выбрана")
            return
        
        # Создаем приглашение в виде ссылки
        invite_service = InviteService(db)
        invite_link = invite_service.generate_invite_link(
            role=role,
            created_by=callback.from_user.id,
            specialization=specialization if role == "executor" else None,
            hours=expiry_hours
        )
        
        # Генерируем токен отдельно для отображения
        token = invite_service.generate_invite(
            role=role,
            created_by=callback.from_user.id,
            specialization=specialization if role == "executor" else None,
            hours=expiry_hours
        )
        
        # Формируем текст с токеном
        role_name = get_text(f"roles.{role}", language=lang)
        expiry_text = {
            1: "1 час",
            24: "24 часа", 
            168: "7 дней"
        }.get(expiry_hours, "24 часа")
        
        success_text = f"✅ Приглашение создано!\n\n"
        success_text += f"👤 Роль: {role_name}\n"
        
        if role == "executor" and specialization:
            spec_name = get_text(f"specializations.{specialization}", language=lang)
            success_text += f"🛠️ Специализация: {spec_name}\n"
        
        success_text += f"⏰ Срок действия: {expiry_text}\n\n"
        success_text += f"🔗 Ссылка для регистрации:\n\n"
        success_text += f"`{invite_link}`\n\n"
        success_text += f"📋 Инструкция для кандидата:\n"
        success_text += f"1. Перейдите по ссылке\n"
        success_text += f"2. Нажмите кнопку «Начать»\n"
        success_text += f"3. Отправьте команду: `/join {token}`"
        
        await callback.message.edit_text(
            success_text
        )
        await callback.message.answer(
            "Вернуться в админ-панель:",
            reply_markup=get_manager_main_keyboard()
        )
        
        # Очищаем состояние
        await state.clear()
        
        logger.info(f"Пользователь {callback.from_user.id} создал приглашение для роли {role}")
        
    except Exception as e:
        logger.error(f"Ошибка создания приглашения: {e}")
        await callback.message.edit_text(
            get_text("errors.unknown_error", language=lang)
        )
        await callback.message.answer(
            "Вернуться в админ-панель:",
            reply_markup=get_manager_main_keyboard()
        )
        await state.clear()
    
    await callback.answer()


@router.callback_query(F.data == "invite_cancel")
async def handle_invite_cancel(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработчик отмены создания приглашения"""
    lang = callback.from_user.language_code or 'ru'
    
    await callback.message.edit_text(
        get_text("buttons.operation_cancelled", language=lang)
    )
    await callback.message.answer(
        "Вернуться в админ-панель:",
        reply_markup=get_manager_main_keyboard()
    )
    
    # Очищаем состояние
    await state.clear()
    
    await callback.answer()


# ===== ОБРАБОТЧИКИ ДЕЙСТВИЙ С ЗАЯВКАМИ ДЛЯ МЕНЕДЖЕРОВ =====

@router.callback_query(lambda c: c.data.startswith("accept_") and not c.data.startswith("accept_request_"))
async def handle_accept_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка принятия заявки менеджером - показ выбора типа назначения"""
    try:
        logger.info(f"Обработка принятия заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return

        request_number = callback.data.replace("accept_", "")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Обновляем статус на "В работе"
        request.status = "В работе"
        request.updated_at = datetime.now()
        db.commit()

        # Показываем выбор типа назначения
        await callback.message.edit_text(
            f"✅ <b>Заявка #{request_number} принята в работу</b>\n\n"
            f"📂 Категория: {request.category}\n"
            f"📍 Адрес: {request.address}\n\n"
            f"<b>Выберите способ назначения исполнителя:</b>",
            reply_markup=get_assignment_type_keyboard(request_number),
            parse_mode="HTML"
        )

        logger.info(f"Заявка {request_number} принята менеджером {callback.from_user.id}, ожидание выбора типа назначения")

    except Exception as e:
        logger.error(f"Ошибка обработки принятия заявки менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("deny_"))
async def handle_deny_request(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка отклонения заявки менеджером"""
    try:
        logger.info(f"Обработка отклонения заявки менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_number = callback.data.replace("deny_", "")
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Запрашиваем причину отклонения
        await callback.message.edit_text(
            f"❌ Отклонение заявки #{request_number}\n\n"
            f"📋 Заявка: {request.category}\n"
            f"📍 Адрес: {request.address}\n\n"
            f"💬 Введите причину отклонения:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_{request_number}")]
            ])
        )
        
        # Сохраняем номер заявки в состоянии для отклонения
        await state.update_data(deny_request_number=request_number)
        
        # Устанавливаем состояние ожидания причины отклонения
        await state.set_state(ManagerStates.cancel_reason)
        
        logger.info(f"Запрошена причина отклонения заявки {request_number} менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки отклонения заявки менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("clarify_"))
async def handle_clarify_request(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка запроса уточнения по заявке"""
    try:
        logger.info(f"Обработка запроса уточнения по заявке менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_number = callback.data.replace("clarify_", "")
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем, что заявка не отменена
        if request.status == "Отменена":
            await callback.answer("Нельзя задать уточнение по отмененной заявке", show_alert=True)
            return
        
        # Сохраняем номер заявки в состоянии
        await state.update_data(request_number=request_number)
        
        # Запрашиваем текст уточнения
        await callback.message.edit_text(
            f"❓ Введите текст уточнения для заявки #{request_number}:\n\n"
            f"📋 Заявка: {request.category}\n"
            f"📍 Адрес: {request.address}\n\n"
            f"💬 Введите ваш вопрос или уточнение:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_clarification")]
            ])
        )
        
        # Устанавливаем состояние ожидания текста уточнения
        await state.set_state(ManagerStates.waiting_for_clarification_text)
        
        logger.info(f"Запрошен текст уточнения для заявки {request_number} менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки запроса уточнения: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "cancel_clarification")
async def handle_cancel_clarification(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Отмена уточнения"""
    try:
        # Очищаем состояние
        await state.clear()
        
        # Возвращаемся к списку заявок
        await handle_manager_back_to_list(callback, db, roles, active_role, user)
        
        await callback.answer("❌ Уточнение отменено")
        
    except Exception as e:
        logger.error(f"Ошибка отмены уточнения: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("purchase_") and not c.data.startswith("purchase_materials_"))
async def handle_purchase_request(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка перевода заявки в статус 'Закуп' менеджером"""
    try:
        logger.info(f"Обработка перевода заявки в закуп менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_number = callback.data.replace("purchase_", "")
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Формируем текст с учетом истории закупок
        prompt_text = "💰 Переводим заявку в статус 'Закуп'\n\n"
        
        # Проверяем, есть ли история предыдущих закупок
        if request.purchase_history:
            prompt_text += "📚 Найдена история предыдущих закупок:\n"
            
            # Показываем последние данные из истории
            history_lines = request.purchase_history.split('\n')
            last_requested = None
            last_comment = None
            
            for i in range(len(history_lines) - 1, -1, -1):
                line = history_lines[i].strip()
                if line.startswith("Запрошенные материалы:") and not last_requested:
                    last_requested = line.replace("Запрошенные материалы:", "").strip()
                elif line.startswith("Комментарий менеджера:") and not last_comment:
                    last_comment = line.replace("Комментарий менеджера:", "").strip()
                
                if last_requested and last_comment:
                    break
            
            if last_requested and last_requested != "Не указано":
                prompt_text += f"📋 Последние запрошенные материалы: {last_requested}\n"
            if last_comment and last_comment != "Без комментариев":
                prompt_text += f"💬 Последний комментарий менеджера: {last_comment}\n"
            
            prompt_text += "\n"
        
        prompt_text += "📝 Введите список необходимых материалов для закупки:"
        
        # Запрашиваем список материалов
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        await callback.message.edit_text(
            prompt_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_{request_number}")]
            ])
        )
        
        # Сохраняем состояние
        from uk_management_bot.states.request_status import RequestStatusStates
        from aiogram.fsm.context import FSMContext
        
        # Получаем контекст состояния
        try:
            await state.update_data(
                request_number=request_number,
                action="purchase_materials_admin"
            )
            await state.set_state(RequestStatusStates.waiting_for_materials)
        except Exception as e:
            logger.error(f"Ошибка установки состояния: {e}")
            await callback.answer("Ошибка обработки запроса", show_alert=True)
        
        await callback.answer()
        
        logger.info(f"Заявка {request_number} переведена в закуп менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки перевода в закуп менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("complete_"))
async def handle_complete_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка завершения заявки менеджером"""
    try:
        logger.info(f"Обработка завершения заявки менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_number = callback.data.replace("complete_", "")
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Обновляем статус
        request.status = "Выполнена"
        request.completed_at = datetime.now()
        request.updated_at = datetime.now()
        db.commit()
        
        await callback.answer("✅ Заявка отмечена как выполненная")
        
        # Возвращаемся к списку заявок
        await handle_manager_back_to_list(callback, db, roles, active_role, user)
        
        logger.info(f"Заявка {request_number} отмечена как выполненная менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки завершения заявки менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(
    F.data.startswith("delete_") &
    ~F.data.startswith("delete_employee_")
)
async def handle_delete_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка удаления заявки менеджером"""
    try:
        logger.info(f"Обработка удаления заявки менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_number = callback.data.replace("delete_", "")
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Удаляем заявку
        db.delete(request)
        db.commit()
        
        await callback.answer("🗑️ Заявка удалена")
        
        # Возвращаемся к списку заявок
        await handle_manager_back_to_list(callback, db, roles, active_role, user)
        
        logger.info(f"Заявка {request_number} удалена менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки удаления заявки менеджером: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.message(ManagerStates.waiting_for_clarification_text)
async def handle_clarification_text(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка текста уточнения от менеджера"""
    try:
        logger.info(f"Получен текст уточнения от менеджера {message.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await message.answer("Нет прав для выполнения действий")
            await state.clear()
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        
        if not request_number:
            await message.answer("Ошибка: не найдена заявка")
            await state.clear()
            return
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await message.answer("Заявка не найдена")
            await state.clear()
            return
        
        # Получаем текст уточнения
        clarification_text = message.text.strip()
        
        if not clarification_text:
            await message.answer("Текст уточнения не может быть пустым. Попробуйте еще раз или нажмите 'Отмена'.")
            return
        
        # Формируем имя менеджера
        manager_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not manager_name:
            manager_name = f"Менеджер {user.telegram_id}"
        
        # Добавляем уточнение в примечания заявки
        timestamp = datetime.now().strftime('%d.%m.%Y %H:%M')
        new_note = f"--- УТОЧНЕНИЕ {timestamp} ---\n"
        new_note += f"👨‍💼 {manager_name}:\n"
        new_note += f"{clarification_text}"
        
        # Обновляем примечания
        if request.notes and request.notes.strip():
            request.notes = request.notes.strip() + "\n\n" + new_note
        else:
            request.notes = new_note
        
        # Обновляем статус на "Уточнение" если он еще не такой
        if request.status != "Уточнение":
            request.status = "Уточнение"
        
        request.updated_at = datetime.now()
        db.commit()
        
        # Отправляем уведомление заявителю
        try:
            from uk_management_bot.services.notification_service import send_to_user
            from uk_management_bot.database.models.user import User as UserModel
            
            # Получаем telegram_id пользователя
            user_obj = db.query(UserModel).filter(UserModel.id == request.user_id).first()
            if user_obj and user_obj.telegram_id:
                notification_text = f"❓ По вашей заявке #{request.request_number} появилось уточнение:\n\n"
                notification_text += f"📋 Заявка: {request.category}\n"
                notification_text += f"📍 Адрес: {request.address}\n\n"
                notification_text += f"💬 Вопрос от менеджера:\n{clarification_text}\n\n"
                notification_text += f"💬 Для ответа используйте команду /reply_{request.request_number}"
                
                # Получаем bot из состояния
                bot = message.bot
                await send_to_user(bot, user_obj.telegram_id, notification_text)
            
            logger.info(f"Уведомление об уточнении отправлено пользователю {request.user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об уточнении: {e}")
        
        # Подтверждаем менеджеру
        await message.answer(
            f"✅ Уточнение отправлено!\n\n"
            f"📋 Заявка #{request.request_number}\n"
            f"💬 Текст: {clarification_text[:100]}{'...' if len(clarification_text) > 100 else ''}\n\n"
            f"📱 Заявитель получил уведомление и сможет ответить."
        )
        
        # Очищаем состояние
        await state.clear()
        
        logger.info(f"Уточнение по заявке {request_number} добавлено менеджером {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки текста уточнения: {e}")
        await message.answer("Произошла ошибка при отправке уточнения")
        await state.clear()


@router.message(ManagerStates.cancel_reason)
async def handle_cancel_reason_text(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка причины отклонения заявки"""
    try:
        logger.info(f"Получена причина отклонения от менеджера {message.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await message.answer("Нет прав для выполнения действий")
            await state.clear()
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("deny_request_number")
        
        if not request_number:
            await message.answer("Ошибка: не найдена заявка")
            await state.clear()
            return
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await message.answer("Заявка не найдена")
            await state.clear()
            return
        
        # Получаем причину отклонения
        cancel_reason = message.text.strip()
        
        if not cancel_reason:
            await message.answer("Причина отклонения не может быть пустой. Попробуйте еще раз.")
            return
        
        # Формируем имя менеджера
        manager_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not manager_name:
            manager_name = f"Менеджер {user.telegram_id}"
        
        # Обновляем статус и добавляем примечание
        request.status = "Отменена"
        cancel_note = f"Отклонена менеджером {manager_name} {datetime.now().strftime('%d.%m.%Y %H:%M')}\nПричина: {cancel_reason}"
        
        if request.notes and request.notes.strip():
            request.notes = request.notes.strip() + "\n\n" + cancel_note
        else:
            request.notes = cancel_note
        request.updated_at = datetime.now()
        db.commit()
        
        await message.answer(
            f"❌ Заявка #{request_number} отклонена\n\n"
            f"💬 Причина: {cancel_reason}",
            reply_markup=get_manager_main_keyboard()
        )
        
        # Очищаем состояние
        await state.clear()
        
        logger.info(f"Заявка {request_number} отклонена менеджером {message.from_user.id} с причиной: {cancel_reason}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки причины отклонения: {e}")
        await message.answer("Произошла ошибка при отклонении заявки")
        await state.clear()


@router.message(F.text == "👥 Смены")
async def handle_admin_shifts_button(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработчик кнопки 'Смены' в админ панели"""
    lang = message.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not has_admin_access(roles=roles, user=user):
        await message.answer(
            get_text("auth.no_access", language=lang),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )
        return
    
    # Прямой вызов интерфейса управления сменами без декоратора
    try:
        from uk_management_bot.keyboards.shift_management import get_main_shift_menu
        from uk_management_bot.states.shift_management import ShiftManagementStates
        from uk_management_bot.utils.helpers import get_user_language
        
        language = get_user_language(message.from_user.id, db)
        
        await message.answer(
            "🔧 <b>Управление сменами</b>\n\n"
            "Выберите действие:",
            reply_markup=get_main_shift_menu(language),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.main_menu)
        
    except Exception as e:
        logger.error(f"Ошибка при открытии управления сменами: {e}")
        await message.answer(
            "🔧 <b>Управление сменами</b>\n\n"
            "Временно недоступно. Попробуйте команду /shifts",
            parse_mode="HTML",
            reply_markup=get_manager_main_keyboard()
        )


@router.callback_query(F.data.startswith("return_to_work_"))
async def handle_return_to_work(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка возврата заявки из закупа в работу"""
    try:
        logger.info(f"Возврат заявки из закупа в работу менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_number = callback.data.replace("return_to_work_", "")
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем, что заявка в статусе "Закуп"
        if request.status != "Закуп":
            await callback.answer("Заявка не в статусе закуп", show_alert=True)
            return
        
        # Добавляем разделитель закупки к списку материалов
        if request.requested_materials:
            current_date = datetime.now().strftime('%d.%m.%Y %H:%M')
            procurement_separator = f"--закуплено {current_date}--"
            
            # Добавляем разделитель к существующим материалам
            request.requested_materials += f"\n{procurement_separator}\n"
            
            # Сохраняем информацию в историю для отчетности
            if request.manager_materials_comment:
                manager_comment = request.manager_materials_comment
            else:
                manager_comment = "Без комментариев"
            
            history_entry = (
                f"ЗАКУП ЗАВЕРШЕН:\n"
                f"Материалы: {request.requested_materials.split(f'{procurement_separator}')[0].strip()}\n"
                f"Комментарий менеджера: {manager_comment}\n"
                f"Дата завершения: {current_date}"
            )
            
            if request.purchase_history:
                request.purchase_history += f"\n\n===\n\n{history_entry}"
            else:
                request.purchase_history = history_entry
        
        # Обновляем статус на "В работе"
        request.status = "В работе"
        request.updated_at = datetime.now()
        db.commit()
        
        await callback.answer("✅ Заявка возвращена в работу")
        
        # Загружаем обновленный список заявок в закупе
        q = (
            db.query(Request)
            .filter(Request.status == "Закуп")
            .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
        )
        requests = q.limit(10).all()
        
        if not requests:
            await callback.message.edit_text("💰 Заявок в статусе 'Закуп' не найдено", reply_markup=get_manager_main_keyboard())
            return
        
        # Показываем обновленный список заявок в закупе
        text = "💰 Заявки в статусе 'Закуп' (обновлено):\n\n"
        for i, r in enumerate(requests, 1):
            addr = r.address[:40] + ("…" if len(r.address) > 40 else "")
            text += f"{i}. #{r.request_number} - {r.category}\n"
            text += f"   📍 {addr}\n\n"
        
        await callback.message.edit_text(text, reply_markup=get_manager_main_keyboard())
        
        logger.info(f"Заявка {request_number} возвращена в работу менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка возврата заявки из закупа в работу: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("edit_materials_"))
async def handle_edit_materials(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, active_role: str = None, user: User = None):
    """Обработка редактирования списка материалов для закупа"""
    try:
        logger.info(f"Редактирование списка материалов менеджером {callback.from_user.id}")
        
        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer("Нет прав для выполнения действий", show_alert=True)
            return
        
        request_number = callback.data.replace("edit_materials_", "")
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем, что заявка в статусе "Закуп"
        if request.status != "Закуп":
            await callback.answer("Заявка не в статусе закуп", show_alert=True)
            return
        
        # Сохраняем номер заявки в состоянии
        await state.update_data(edit_materials_request_number=request_number)
        await state.set_state(ManagerStates.waiting_for_materials_edit)
        
        # Показываем запрошенные материалы от исполнителя и текущий комментарий менеджера
        requested = request.requested_materials or "Не указано"
        manager_comment = request.manager_materials_comment or ""
        
        text = (
            f"📝 Редактирование комментариев к материалам для заявки #{request_number}\n\n"
            f"📋 Запрошенные материалы (от исполнителя):\n{requested}\n\n"
        )
        
        if manager_comment:
            text += f"💬 Текущий комментарий менеджера:\n{manager_comment}\n\n"
        
        text += "Введите комментарии менеджера к списку материалов:"
        
        await callback.message.answer(text)
        
        await callback.answer()
        
        logger.info(f"Начато редактирование материалов для заявки {request_number} менеджером {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка редактирования списка материалов: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.message(ManagerStates.waiting_for_materials_edit)
async def handle_materials_edit_text(message: Message, state: FSMContext, db: Session, user: User = None):
    """Обработка нового текста списка материалов"""
    try:
        data = await state.get_data()
        request_number = data.get("edit_materials_request_number")
        
        if not request_number:
            await message.answer("Ошибка: не найден номер заявки")
            await state.clear()
            return
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await message.answer("Заявка не найдена")
            await state.clear()
            return
        
        # Обновляем комментарий менеджера к материалам (запрошенные материалы НЕ изменяем)
        old_comment = request.manager_materials_comment
        new_comment = message.text.strip()
        request.manager_materials_comment = new_comment
        request.updated_at = datetime.now()
        
        # Обновляем историю закупов для сохранения данных
        requested_materials = request.requested_materials or "Не указано"
        purchase_history_entry = (
            f"Запрошенные материалы: {requested_materials}\n"
            f"Комментарий менеджера: {new_comment}\n"
            f"Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        if request.purchase_history:
            request.purchase_history += f"\n\n---\n\n{purchase_history_entry}"
        else:
            request.purchase_history = purchase_history_entry
            
        db.commit()
        
        await message.answer(f"✅ Комментарии к материалам для заявки #{request_number} обновлены", reply_markup=get_manager_main_keyboard())
        
        # Добавляем комментарий об изменении
        if user:
            try:
                from uk_management_bot.services.comment_service import CommentService
                comment_service = CommentService(db)
                comment_text = f"Комментарии к материалам изменены менеджером:\n\nБыло: {old_comment or 'Комментарий отсутствовал'}\n\nСтало: {new_comment}"
                comment_service.add_status_change_comment(
                    request_id=request_number,
                    user_id=user.id,
                    old_status="Закуп",
                    new_status="Закуп", 
                    comment=comment_text
                )
            except Exception as e:
                logger.error(f"Ошибка добавления комментария: {e}")
                # Не критично, продолжаем
        
        await state.clear()

        logger.info(f"Список материалов для заявки {request_number} обновлен менеджером {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обновления списка материалов: {e}")
        await message.answer("Произошла ошибка при обновлении списка")
        await state.clear()


# ===== ОБРАБОТЧИКИ НАЗНАЧЕНИЯ ИСПОЛНИТЕЛЕЙ =====

@router.callback_query(F.data.startswith("assign_duty_"))
async def handle_assign_duty_executor_admin(callback: CallbackQuery, db: Session, user: User = None):
    """Назначение дежурного специалиста (автоматическое по сменам)"""
    try:
        request_number = callback.data.replace("assign_duty_", "")
        logger.info(f"Назначение дежурного специалиста для заявки {request_number}")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Используем существующую логику auto_assign
        await auto_assign_request_by_category(request, db, user)

        await callback.message.edit_text(
            f"✅ <b>Заявка #{request_number} назначена дежурному специалисту</b>\n\n"
            f"Назначение выполнено автоматически на основе:\n"
            f"• Текущих смен\n"
            f"• Специализации исполнителей\n"
            f"• Загруженности\n\n"
            f"Исполнитель получит уведомление.",
            parse_mode="HTML"
        )

        logger.info(f"Заявка {request_number} назначена дежурному специалисту")

    except Exception as e:
        logger.error(f"Ошибка назначения дежурного специалиста: {e}")
        await callback.answer("Произошла ошибка при назначении", show_alert=True)


@router.callback_query(F.data.startswith("assign_specific_"))
async def handle_assign_specific_executor_admin(callback: CallbackQuery, db: Session):
    """Показать список исполнителей для ручного выбора"""
    try:
        request_number = callback.data.replace("assign_specific_", "")
        logger.info(f"Выбор конкретного исполнителя для заявки {request_number}")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Получаем исполнителей с нужной специализацией
        category_to_spec = {
            "Электрика": "electrician",
            "Сантехника": "plumber",
            "Охрана": "security",
            "Уборка": "cleaner",
        }

        spec = category_to_spec.get(request.category, "other")

        # Получаем всех исполнителей с данной специализацией
        import json

        executors = db.query(User).filter(
            User.roles.contains('"executor"'),
            User.status == "approved"
        ).all()

        # Фильтруем по специализации
        filtered_executors = []
        for ex in executors:
            if ex.specialization:
                try:
                    specializations = json.loads(ex.specialization) if isinstance(ex.specialization, str) else ex.specialization
                    if spec in specializations or "other" in specializations:
                        filtered_executors.append(ex)
                except:
                    pass

        executors_text = f"Найдено исполнителей: {len(filtered_executors)}" if filtered_executors else "Нет доступных исполнителей"

        await callback.message.edit_text(
            f"👤 <b>Выбор исполнителя</b>\n\n"
            f"📋 Заявка: #{request_number}\n"
            f"📂 Категория: {request.category}\n"
            f"🔧 Специализация: {spec}\n\n"
            f"{executors_text}\n\n"
            f"🟢 - На смене\n"
            f"⚪ - Не на смене",
            reply_markup=get_executors_by_category_keyboard(request_number, request.category, filtered_executors),
            parse_mode="HTML"
        )

        logger.info(f"Показан список из {len(filtered_executors)} исполнителей для заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка показа списка исполнителей: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("assign_executor_"))
async def handle_final_executor_assignment_admin(callback: CallbackQuery, db: Session):
    """Финальное назначение конкретного исполнителя"""
    try:
        # Парсим данные: assign_executor_251013-001_123
        parts = callback.data.replace("assign_executor_", "").split("_")
        request_number = parts[0]
        executor_id = int(parts[1])

        logger.info(f"Финальное назначение исполнителя {executor_id} на заявку {request_number}")

        # Получаем заявку и исполнителя
        request = db.query(Request).filter(Request.request_number == request_number).first()
        executor = db.query(User).filter(User.id == executor_id).first()

        if not request or not executor:
            await callback.answer("Заявка или исполнитель не найдены", show_alert=True)
            return

        # Назначаем исполнителя
        request.executor_id = executor_id
        request.assignment_type = "manual"
        db.commit()

        executor_name = f"{executor.first_name or ''} {executor.last_name or ''}".strip()
        if not executor_name:
            executor_name = f"@{executor.username}" if executor.username else f"ID{executor.id}"

        await callback.message.edit_text(
            f"✅ <b>Заявка #{request_number} назначена исполнителю</b>\n\n"
            f"👤 Исполнитель: {executor_name}\n"
            f"📂 Категория: {request.category}\n"
            f"📍 Адрес: {request.address}\n\n"
            f"Исполнитель получит уведомление о назначении.",
            parse_mode="HTML"
        )

        # Отправляем уведомление исполнителю
        try:
            from aiogram import Bot
            bot = Bot.get_current()

            notification_text = (
                f"📋 <b>Вам назначена новая заявка!</b>\n\n"
                f"№ заявки: #{request.format_number_for_display()}\n"
                f"📂 Категория: {request.category}\n"
                f"📍 Адрес: {request.address}\n"
                f"📝 Описание: {request.description}\n\n"
                f"Пожалуйста, приступите к выполнению."
            )

            await bot.send_message(executor.telegram_id, notification_text, parse_mode="HTML")
            logger.info(f"Уведомление о назначении отправлено исполнителю {executor.telegram_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления исполнителю: {e}")

        logger.info(f"Заявка {request_number} назначена исполнителю {executor_id}")

    except Exception as e:
        logger.error(f"Ошибка финального назначения исполнителя: {e}")
        await callback.answer("Произошла ошибка при назначении", show_alert=True)


@router.callback_query(F.data.startswith("back_to_assignment_type_"))
async def handle_back_to_assignment_type_admin(callback: CallbackQuery, db: Session):
    """Возврат к выбору типа назначения"""
    try:
        request_number = callback.data.replace("back_to_assignment_type_", "")

        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        await callback.message.edit_text(
            f"✅ <b>Заявка #{request_number} принята в работу</b>\n\n"
            f"📂 Категория: {request.category}\n"
            f"📍 Адрес: {request.address}\n\n"
            f"<b>Выберите способ назначения исполнителя:</b>",
            reply_markup=get_assignment_type_keyboard(request_number),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к выбору типа назначения: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

