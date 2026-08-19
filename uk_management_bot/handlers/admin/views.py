"""Менеджер: просмотр заявок, медиа, подтверждение, пагинация."""
from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.services.admin_handler_service import AdminHandlerService
# AUD6-P1-6: адресные уведомления — той же матрицей интентов, что API-путь
# (одни получатели, один текст); канальная лента — отдельным хелпером.
from uk_management_bot.services.workflow_notifications import (
    dispatch_notify_intents_sync,
    notify_channel_status_changed,
)
from uk_management_bot.utils.workflow_predicates import (
    is_awaiting_applicant,
    is_awaiting_manager,
)

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.status_display import get_status_display
from uk_management_bot.keyboards.requests import (
    get_category_display,
    get_discussion_rows,
    get_urgency_display,
    resolve_category_key,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.services.completion_media import get_completion_media_file_ids
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.utils.user_names import display_name
from uk_management_bot.states.request_acceptance import ManagerAcceptanceStates

from ._router import router

logger = logging.getLogger(__name__)


# ===== ОБРАБОТЧИКИ ПРОСМОТРА ЗАЯВОК ДЛЯ МЕНЕДЖЕРОВ =====

@router.callback_query(F.data.startswith("mview_"))
async def handle_manager_view_request(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка просмотра деталей заявки для менеджеров"""
    try:
        lang = language
        logger.info(f"Обработка просмотра заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_requests", language=lang), show_alert=True)
            return
        
        request_number = callback.data.replace("mview_", "")

        svc = AdminHandlerService(db)
        # Получаем заявку из базы данных
        request = svc.get_request_by_number(request_number)

        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Получаем информацию о пользователе, создавшем заявку
        request_user = svc.get_user_by_id(request.user_id)
        if request_user:
            # Формируем полное имя из first_name и last_name
            full_name_parts = []
            if request_user.first_name:
                full_name_parts.append(request_user.first_name)
            if request_user.last_name:
                full_name_parts.append(request_user.last_name)
            user_info = " ".join(full_name_parts) if full_name_parts else get_text("admin.handlers.user_by_id", language=lang).format(telegram_id=request_user.telegram_id)
        else:
            user_info = get_text("admin.handlers.unknown_user", language=lang)
        
        # Формируем детальную информацию о заявке
        message_text = get_text("admin.handlers.request_detail_header", language=lang).format(request_number=request.request_number) + "\n\n"
        message_text += get_text("admin.handlers.request_detail_applicant", language=lang).format(user_info=user_info) + "\n"
        message_text += get_text("admin.handlers.request_detail_telegram_id", language=lang).format(telegram_id=request_user.telegram_id if request_user else 'N/A') + "\n"
        category_display = get_category_display(resolve_category_key(request.category), language=lang)
        urgency_display = get_urgency_display(request.urgency, language=lang) if request.urgency else ""
        message_text += get_text("admin.handlers.request_detail_category", language=lang).format(category=category_display) + "\n"
        message_text += get_text("admin.handlers.request_detail_status", language=lang).format(status=get_status_display(request.status, language=lang)) + "\n"
        message_text += get_text("admin.handlers.request_detail_address", language=lang).format(address=request.address) + "\n"
        message_text += get_text("admin.handlers.request_detail_description", language=lang).format(description=request.description) + "\n"
        message_text += get_text("admin.handlers.request_detail_urgency", language=lang).format(urgency=urgency_display) + "\n"
        if request.apartment:
            message_text += get_text("admin.handlers.request_detail_apartment", language=lang).format(apartment=request.apartment) + "\n"
        message_text += get_text("admin.handlers.request_detail_created", language=lang).format(created_at=request.created_at.strftime('%d.%m.%Y %H:%M')) + "\n"
        if request.updated_at:
            message_text += get_text("admin.handlers.request_detail_updated", language=lang).format(updated_at=request.updated_at.strftime('%d.%m.%Y %H:%M')) + "\n"

        # Добавляем информацию о назначении
        active_assignment = svc.get_active_assignment(request.request_number)

        if active_assignment:
            if active_assignment.assignment_type == "group":
                # Групповое назначение (дежурному специалисту)
                spec_name = get_text(f"specializations.{active_assignment.group_specialization}", language=lang) if active_assignment.group_specialization else active_assignment.group_specialization
                message_text += get_text("admin.handlers.assigned_duty_specialist", language=lang).format(spec_name=spec_name) + "\n"
            elif active_assignment.assignment_type == "individual" and active_assignment.executor_id:
                # Индивидуальное назначение конкретному исполнителю
                assigned_executor = svc.get_user_by_id(active_assignment.executor_id)
                if assigned_executor:
                    executor_name = display_name(assigned_executor)
                    message_text += get_text("admin.handlers.assigned_executor", language=lang).format(executor_name=executor_name) + "\n"

        if request.notes:
            message_text += get_text("admin.handlers.request_detail_notes", language=lang).format(notes=request.notes) + "\n"

        # Проверяем наличие медиафайлов. Фотоотчёт: SSOT — media-service
        # (дашборд/TWA грузят туда, минуя legacy-поле), фолбэк — completion_media.
        media_files = request.media_files if request.media_files else []
        completion_media = await get_completion_media_file_ids(
            request.request_number, request.completion_media
        )
        has_media = len(media_files) > 0 or len(completion_media) > 0

        # Создаем клавиатуру действий для менеджера
        from uk_management_bot.keyboards.admin import (
            get_manager_request_actions_keyboard,
            get_manager_completed_request_actions_keyboard,
            get_reassign_button_row,
            get_unaccepted_request_actions_keyboard
        )

        # Для исполненных, но непринятых заявок (ожидают приёмки заявителем) - специальная клавиатура
        if is_awaiting_applicant(request):
            # Добавляем информацию о времени ожидания принятия
            from datetime import datetime, timezone
            completed_at = request.completed_at if request.completed_at else request.updated_at
            if completed_at:
                if completed_at.tzinfo is None:
                    from datetime import timezone as dt_tz
                    completed_at = completed_at.replace(tzinfo=dt_tz.utc)
                now = datetime.now(timezone.utc)
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

                message_text += "\n" + get_text("admin.handlers.waiting_acceptance", language=lang).format(time_str=time_str) + "\n"

            actions_kb = get_unaccepted_request_actions_keyboard(request.request_number)

            # Добавляем кнопку медиа если есть
            rows = list(actions_kb.inline_keyboard)
            if has_media:
                # Вставляем кнопку медиа перед кнопкой "Назад к списку"
                rows.insert(-1, [InlineKeyboardButton(text=get_text("admin.handlers.btn_media", language=lang), callback_data=f"media_{request.request_number}")])
            rows.extend(get_discussion_rows(
                request.request_number,
                has_report=bool(request.completion_report),
                language=lang,
            ))
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        # Для заявок, ожидающих подтверждения менеджером - специальная клавиатура
        elif is_awaiting_manager(request):
            actions_kb = get_manager_completed_request_actions_keyboard(request.request_number, is_returned=request.is_returned)

            # Добавляем кнопку медиа если есть
            rows = list(actions_kb.inline_keyboard)
            if has_media:
                rows.append([InlineKeyboardButton(text=get_text("admin.handlers.btn_media", language=lang), callback_data=f"media_{request.request_number}")])
            rows.extend(get_discussion_rows(
                request.request_number,
                has_report=bool(request.completion_report),
                language=lang,
            ))
            rows.append([InlineKeyboardButton(text=get_text("admin.handlers.btn_back_to_list", language=lang), callback_data=f"mreq_back_{request.request_number}")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        else:
            # Для обычных заявок - стандартная клавиатура
            actions_kb = get_manager_request_actions_keyboard(request.request_number, has_media=has_media)

            # Добавляем кнопку "Назад к списку"
            rows = list(actions_kb.inline_keyboard)
            # Переназначение — только при активном назначении и подходящем
            # статусе. active_assignment уже прочитан выше для ТЕКСТА карточки,
            # второй запрос не нужен.
            reassign_row = get_reassign_button_row(
                request.request_number,
                assignment_type=(active_assignment.assignment_type
                                 if active_assignment else None),
                status=request.status,
                roles=roles,
                language=lang,
            )
            if reassign_row:
                rows.append(reassign_row)
            rows.extend(get_discussion_rows(
                request.request_number,
                has_report=bool(request.completion_report),
                language=lang,
            ))
            rows.append([InlineKeyboardButton(text=get_text("admin.handlers.btn_back_to_list", language=lang), callback_data=f"mreq_back_{request.request_number}")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
        logger.info(f"Показаны детали заявки {request.request_number} менеджеру {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки просмотра заявки менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("media_"))
async def handle_view_request_media(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка просмотра медиафайлов заявки"""
    try:
        from aiogram.types import InputMediaPhoto, InputMediaDocument
        lang = language

        logger.info(f"Просмотр медиафайлов заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_media", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("media_", "")

        # Получаем заявку из базы данных
        request = AdminHandlerService(db).get_request_by_number(request_number)

        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем наличие медиафайлов и парсим JSON
        import json

        media_files = []
        if request.media_files:
            try:
                media_files = json.loads(request.media_files) if isinstance(request.media_files, str) else request.media_files
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Ошибка парсинга media_files для заявки {request.request_number}: {e}")

        # Фотоотчёт: SSOT — media-service, фолбэк — legacy-поле (парсинг
        # JSON-строки/dict'ов внутри сервиса). Элементы — telegram file_id,
        # цикл отправки ниже работает и со строками, и с legacy-dict'ами.
        completion_media = await get_completion_media_file_ids(
            request.request_number, request.completion_media
        )

        if not media_files and not completion_media:
            await callback.answer(get_text("admin.handlers.no_media_attached", language=lang), show_alert=True)
            return

        # Отправляем медиафайлы при создании заявки
        if media_files:
            await callback.message.answer(
                get_text("admin.handlers.media_creation_header", language=lang).format(request_number=request.request_number),
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
                            media_group.append(InputMediaPhoto(media=file_id, caption=get_text("admin.handlers.photo_counter", language=lang).format(current=idx+1, total=len(media_files))))
                        else:
                            media_group.append(InputMediaPhoto(media=file_id))
                    except Exception:
                        # Если не получилось как фото, пробуем как документ
                        if idx == 0:
                            media_group.append(InputMediaDocument(media=file_id, caption=get_text("admin.handlers.file_counter", language=lang).format(current=idx+1, total=len(media_files))))
                        else:
                            media_group.append(InputMediaDocument(media=file_id))

                if media_group:
                    await callback.message.answer_media_group(media=media_group)
            else:
                # Один файл - отправляем отдельно
                file_id = media_files[0].get("file_id") if isinstance(media_files[0], dict) else media_files[0]
                try:
                    await callback.message.answer_photo(photo=file_id)
                except Exception:
                    try:
                        await callback.message.answer_document(document=file_id)
                    except Exception as e:
                        logger.error(f"Ошибка отправки медиафайла: {e}")
                        await callback.message.answer(get_text("admin.handlers.media_send_failed", language=lang))

        # Отправляем медиафайлы при завершении заявки
        if completion_media:
            await callback.message.answer(
                get_text("admin.handlers.media_completion_header", language=lang).format(request_number=request.request_number),
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
                            media_group.append(InputMediaPhoto(media=file_id, caption=get_text("admin.handlers.photo_counter", language=lang).format(current=idx+1, total=len(completion_media))))
                        else:
                            media_group.append(InputMediaPhoto(media=file_id))
                    except Exception:
                        # Если не получилось как фото, пробуем как документ
                        if idx == 0:
                            media_group.append(InputMediaDocument(media=file_id, caption=get_text("admin.handlers.file_counter", language=lang).format(current=idx+1, total=len(completion_media))))
                        else:
                            media_group.append(InputMediaDocument(media=file_id))

                if media_group:
                    await callback.message.answer_media_group(media=media_group)
            else:
                # Один файл - отправляем отдельно
                file_id = completion_media[0].get("file_id") if isinstance(completion_media[0], dict) else completion_media[0]
                try:
                    await callback.message.answer_photo(photo=file_id)
                except Exception:
                    try:
                        await callback.message.answer_document(document=file_id)
                    except Exception as e:
                        logger.error(f"Ошибка отправки медиафайла при завершении: {e}")
                        await callback.message.answer(get_text("admin.handlers.media_send_failed", language=lang))

        await callback.answer(get_text("admin.handlers.media_sent", language=lang))
        logger.info(f"Отправлены медиафайлы заявки {request.request_number} менеджеру {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка просмотра медиафайлов заявки: {e}")
        await callback.answer(get_text("admin.handlers.error_loading_media", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("confirm_completed_"))
async def handle_manager_confirm_completed(callback: CallbackQuery, db: Session, roles: list = None, user: User = None, language: str = "ru"):
    """Менеджер подтверждает выполнение заявки"""
    try:
        lang = language

        logger.info(f"Подтверждение выполнения заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_confirm", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("confirm_completed_", "")

        # Канонический переход через единый layer (PR2a): run_command владеет
        # своей транзакцией (свежая сессия + FOR UPDATE + ActorContext из БД +
        # patch/audit/outbox в одной tx). Пишет СРАЗУ канон: Выполнена→Исполнено.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        try:
            outcome = run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                ActionCommand(callback.id, Action.MANAGER_CONFIRM, {}),
            )
        except RequestNotFound:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return
        except WorkflowError as e:
            logger.info(f"MANAGER_CONFIRM отклонён для {request_number}: {e}")
            await callback.answer(get_text("admin.handlers.error_confirming", language=lang), show_alert=True)
            return

        # Best-effort post-commit (потеря допустима, PR0 Р7): уведомления + правка.
        # run_command работал в своей сессии → перечитываем заявку свежей.
        request = AdminHandlerService(db).get_request_by_number(request_number)

        # Адресно — по матрице интентов (не бросает); в канал — хелпером.
        await dispatch_notify_intents_sync(
            db, request_number, outcome.post_commit_intents, bot=callback.bot)
        await notify_channel_status_changed(
            callback.bot, request, outcome.old_status, outcome.public_status)

        # Дополнительное уведомление заявителю с инструкцией
        applicant = request.user if request else None
        if applicant and applicant.telegram_id:
            try:
                bot = callback.bot

                notification_text = get_text("admin.handlers.notify_applicant_completed", language=lang).format(
                    request_number=request.format_number_for_display()
                )

                await bot.send_message(applicant.telegram_id, notification_text)
                logger.info(f"✅ Уведомление о подтверждении заявки {request_number} отправлено заявителю {applicant.telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления заявителю: {e}")

        await callback.message.edit_text(
            get_text("admin.handlers.request_confirmed", language=lang).format(request_number=request_number)
        )

        logger.info(f"Заявка {request_number} подтверждена менеджером {user.id} (canon)")

    except Exception as e:
        logger.error(f"Ошибка подтверждения выполнения заявки: {e}")
        if db:
            AdminHandlerService(db).rollback()
        await callback.answer(get_text("admin.handlers.error_confirming", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("reconfirm_completed_"))
async def handle_manager_reconfirm_completed(callback: CallbackQuery, db: Session, roles: list = None, user: User = None, language: str = "ru"):
    """Менеджер повторно подтверждает выполнение возвратной заявки"""
    try:
        lang = language

        logger.info(f"Повторное подтверждение возвратной заявки менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_confirm", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("reconfirm_completed_", "")

        # PR2a-2: под каноном (модель A) у статуса «Возвращена» нет ребра
        # обратно в «Исполнено». Кнопка reconfirm = MANAGER_FORCE_ACCEPT
        # (продуктовое решение 2026-06-10): менеджер отклоняет возврат →
        # заявка принимается терминально (Возвращена→Принято), повторной
        # приёмки заявителем больше нет.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        try:
            outcome = run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                ActionCommand(callback.id, Action.MANAGER_FORCE_ACCEPT, {}),
            )
        except RequestNotFound:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return
        except WorkflowError as e:
            logger.info(f"MANAGER_FORCE_ACCEPT (reconfirm) отклонён для {request_number}: {e}")
            await callback.answer(get_text("admin.handlers.error_confirming", language=lang), show_alert=True)
            return

        # Best-effort post-commit (PR0 Р7): уведомления + правка сообщения.
        request = AdminHandlerService(db).get_request_by_number(request_number)

        # Адресно — по матрице интентов (не бросает); в канал — хелпером.
        await dispatch_notify_intents_sync(
            db, request_number, outcome.post_commit_intents, bot=callback.bot)
        await notify_channel_status_changed(
            callback.bot, request, outcome.old_status, outcome.public_status)

        # Дополнительное уведомление заявителю: возврат рассмотрен, заявка принята
        applicant = request.user if request else None
        if applicant and applicant.telegram_id:
            try:
                bot = callback.bot

                notification_text = get_text("admin.handlers.notify_applicant_reconfirmed", language=lang).format(
                    request_number=request.format_number_for_display()
                )

                await bot.send_message(applicant.telegram_id, notification_text)
                logger.info(f"✅ Уведомление о принятии возвратной заявки {request_number} отправлено заявителю {applicant.telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления заявителю: {e}")

        await callback.message.edit_text(
            get_text("admin.handlers.request_reconfirmed", language=lang).format(request_number=request_number)
        )

        logger.info(f"Возврат по заявке {request_number} отклонён, принято менеджером {user.id} (canon force-accept)")

    except Exception as e:
        logger.error(f"Ошибка повторного подтверждения заявки: {e}")
        if db:
            AdminHandlerService(db).rollback()
        await callback.answer(get_text("admin.handlers.error_confirming", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("return_to_work_"))
async def handle_manager_return_to_work(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None, user: User = None, language: str = "ru"):
    """Менеджер возвращает заявку в работу — шаг 1: спрашиваем причину.

    Сам переход исполняет `handle_return_to_work_reason`: возврат без причины
    бесполезен исполнителю, поэтому она обязательна (ядро отклонит пустой
    payload). Оживляет уже объявленное состояние `awaiting_return_to_work_reason`.
    """
    try:
        lang = language
        logger.info(f"Возврат заявки в работу менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_change_status", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("return_to_work_", "")

        await callback.message.edit_text(
            get_text("admin.handlers.return_to_work_prompt", language=lang).format(
                request_number=request_number),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=get_text("admin.handlers.btn_cancel", language=lang),
                    # СВОЙ callback, а не общий `view_`: тот не снимает FSM, и
                    # состояние «жду причину» пережило бы отмену. Тогда любое
                    # следующее сообщение менеджера — заметка, ответ в другом
                    # диалоге — было бы съедено как причина и молча вернуло бы
                    # заявку в работу.
                    callback_data=f"rtw_cancel_{request_number}")
            ]]),
        )

        await state.update_data(return_to_work_number=request_number)
        await state.set_state(ManagerAcceptanceStates.awaiting_return_to_work_reason)

        logger.info(f"Запрошена причина возврата в работу по заявке {request_number}")

    except Exception as e:
        logger.error(f"Ошибка запроса причины возврата в работу: {e}")
        await callback.answer(get_text("admin.handlers.error_changing_status", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("rtw_cancel_"))
async def handle_return_to_work_cancel(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена сбора причины: снимаем состояние, иначе следующее сообщение
    менеджера будет принято за причину и вернёт заявку в работу."""
    await state.clear()
    request_number = callback.data.replace("rtw_cancel_", "")
    await callback.message.edit_text(
        get_text("admin.handlers.return_to_work_cancelled", language=language).format(
            request_number=request_number)
    )


@router.message(ManagerAcceptanceStates.awaiting_return_to_work_reason)
async def handle_return_to_work_reason(message: Message, state: FSMContext, db: Session, roles: list = None, user: User = None, language: str = "ru"):
    """Шаг 2: причина получена — исполняем канонический переход."""
    lang = language
    try:
        if not has_admin_access(roles=roles, user=user):
            await message.answer(get_text("admin.handlers.no_access_change_status", language=lang))
            await state.clear()
            return

        reason = (message.text or "").strip()
        if not reason:
            # Не отправляем пустое в движок — он всё равно отклонит, а менеджер
            # получил бы невнятную ошибку вместо понятной просьбы.
            await message.answer(get_text("admin.handlers.return_to_work_reason_empty", language=lang))
            return

        data = await state.get_data()
        request_number = data.get("return_to_work_number")
        if not request_number:
            await message.answer(get_text("admin.handlers.request_not_found", language=lang))
            await state.clear()
            return

        # Канонический переход (PR2a-2): Выполнена/Возвращена → В работе.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        try:
            outcome = run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                ActionCommand(f"rtw:{request_number}:{message.message_id}",
                              Action.MANAGER_RETURN_TO_WORK, {"reason": reason}),
            )
        except RequestNotFound:
            await message.answer(get_text("admin.handlers.request_not_found", language=lang))
            await state.clear()
            return
        except WorkflowError as e:
            logger.info(f"MANAGER_RETURN_TO_WORK отклонён для {request_number}: {e}")
            await message.answer(get_text("admin.handlers.error_changing_status", language=lang))
            await state.clear()
            return

        # Best-effort post-commit (PR0 Р7): уведомление + подтверждение менеджеру.
        request = AdminHandlerService(db).get_request_by_number(request_number)
        await dispatch_notify_intents_sync(
            db, request_number, outcome.post_commit_intents, bot=message.bot)
        await notify_channel_status_changed(
            message.bot, request, outcome.old_status, outcome.public_status)

        await message.answer(
            get_text("admin.handlers.request_returned_to_work", language=lang).format(
                request_number=request_number)
        )
        await state.clear()

        logger.info(f"Заявка {request_number} возвращена в работу менеджером {user.id} (canon)")

    except Exception as e:
        logger.error(f"Ошибка возврата заявки в работу: {e}")
        if db:
            AdminHandlerService(db).rollback()
        await message.answer(get_text("admin.handlers.error_changing_status", language=lang))
        await state.clear()


@router.callback_query(F.data.startswith("mreq_page_"))
async def handle_manager_request_pagination(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработка пагинации списков заявок для менеджеров"""
    try:
        lang = language
        logger.info(f"Обработка пагинации заявок менеджером {callback.from_user.id}")

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_view_requests", language=lang), show_alert=True)
            return

        # Парсим данные пагинации
        page_data = callback.data.replace("mreq_page_", "")

        if page_data == "curr":
            await callback.answer(get_text("admin.handlers.current_page", language=lang))
            return
        
        current_page = int(page_data)

        # Определяем тип списка заявок (новые, активные, архив)
        # Пока что показываем активные заявки
        svc = AdminHandlerService(db)

        # Вычисляем общее количество страниц
        total_requests = svc.count_active_requests()
        requests_per_page = 10
        total_pages = max(1, (total_requests + requests_per_page - 1) // requests_per_page)

        if current_page < 1 or current_page > total_pages:
            await callback.answer(get_text("admin.handlers.page_not_found", language=lang), show_alert=True)
            return

        # Получаем заявки для текущей страницы
        requests = svc.page_active_requests(
            (current_page - 1) * requests_per_page, requests_per_page
        )

        if not requests:
            await callback.answer(get_text("admin.handlers.no_requests_on_page", language=lang), show_alert=True)
            return
        
        items = [{"request_number": r.request_number, "category": get_category_display(resolve_category_key(r.category), language=lang), "address": r.address, "status": r.status} for r in requests]
        
        # Обновляем сообщение с новой страницей
        from uk_management_bot.keyboards.admin import get_manager_request_list_kb
        new_keyboard = get_manager_request_list_kb(items, current_page, total_pages)
        
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        
        logger.info(f"Показана страница {current_page} заявок менеджеру {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки пагинации заявок менеджером: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


