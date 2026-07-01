import logging

from aiogram import F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from uk_management_bot.services.shift_management_service import ShiftManagementService
from uk_management_bot.services.template_manager import TemplateManager
from uk_management_bot.keyboards.shift_management import (
    get_template_management_keyboard,
)
from uk_management_bot.states.shift_management import ShiftManagementStates, TemplateManagementStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language, get_text

from ._router import router
from .shared import _db_scope

logger = logging.getLogger(__name__)


@router.callback_query(F.data == "template_management")
@require_role(['admin', 'manager'])
async def handle_template_management(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Управление шаблонами смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            await callback.message.edit_text(
                get_text("shift_management.template_management_title", language=lang),
                reply_markup=get_template_management_keyboard(lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.template_menu)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка управления шаблонами: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.template_error", language=lang), show_alert=True)


@router.callback_query(F.data == "create_new_template")
@require_role(['admin', 'manager'])
async def handle_create_new_template(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Создание нового шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            await callback.message.edit_text(
                get_text("shift_management.create_template_title", language=lang),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                        callback_data="template_management")]
                ]),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.template_name_input)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка создания шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.template_error", language=lang), show_alert=True)


@router.callback_query(F.data == "templates_view_all")
@require_role(['admin', 'manager'])
async def handle_view_all_templates(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Просмотр всех шаблонов"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            template_manager = TemplateManager(db)
        
            # Получаем все шаблоны
            templates = template_manager.get_templates(active_only=False)
        
            if not templates:
                await callback.message.edit_text(
                    get_text("shift_management.no_templates_found", language=lang),
                    reply_markup=get_template_management_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer(get_text("shift_management.no_templates_alert", language=lang))
                return
        
            # Формируем текст со списком шаблонов
            templates_text = get_text("shift_management.templates_list_title", language=lang)
        
            for i, template in enumerate(templates, 1):
                status_emoji = "✅" if template.is_active else "❌"
                time_info = f"{template.start_hour:02d}:{template.start_minute or 0:02d}"
                duration_info = f"{template.duration_hours}ч"
            
                specialization_info = ""
                if template.required_specializations:
                    from uk_management_bot.utils.constants import SPECIALIZATIONS
                    spec_names = [SPECIALIZATIONS.get(spec, spec) for spec in template.required_specializations[:2]]
                    specialization_info = f" • {', '.join(spec_names)}"
                    if len(template.required_specializations) > 2:
                        specialization_info += f" (+{len(template.required_specializations)-2})"
            
                description = template.description or get_text("shift_management.no_description", language=lang)
                templates_text += (
                    f"{i}. {status_emoji} <b>{template.name}</b>\n"
                    f"   🕒 {time_info} ({duration_info}){specialization_info}\n"
                    f"   📝 {description}\n\n"
                )
        
            await callback.message.edit_text(
                templates_text,
                reply_markup=get_template_management_keyboard(lang),
                parse_mode="HTML"
            )
        
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка просмотра шаблонов: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.template_error", language=lang), show_alert=True)


@router.message(StateFilter(ShiftManagementStates.template_name_input))
async def handle_template_name_input(message: Message, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка ввода названия шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(message.from_user.id, db)
        
            template_name = message.text.strip()
        
            # Проверяем длину названия
            if len(template_name) < 3:
                await message.answer(
                    get_text("shift_management.name_too_short", language=lang),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                            callback_data="template_management")]
                    ])
                )
                return
        
            if len(template_name) > 50:
                await message.answer(
                    get_text("shift_management.name_too_long", language=lang),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                            callback_data="template_management")]
                    ])
                )
                return
        
            # Сохраняем название в состоянии
            await state.update_data(template_name=template_name)
        
            # Переходим к вводу времени начала
            await message.answer(
                get_text("shift_management.name_saved_enter_time", language=lang, name=template_name),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                        callback_data="template_management")]
                ]),
                parse_mode="HTML"
            )
        
            await state.set_state(ShiftManagementStates.template_time_input)
        
    except Exception as e:
        logger.error(f"Ошибка ввода названия шаблона: {e}")
        lang = get_user_language(message.from_user.id, db) if db else "ru"
        await message.answer(get_text("shift_management.template_name_error", language=lang))


@router.message(StateFilter(ShiftManagementStates.template_time_input))
async def handle_template_time_input(message: Message, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка ввода времени начала шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(message.from_user.id, db)
        
            time_text = message.text.strip()
        
            # Парсим время
            try:
                if ":" not in time_text:
                    raise ValueError("Неверный формат")
            
                hour_str, minute_str = time_text.split(":")
                hour = int(hour_str)
                minute = int(minute_str)
            
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    raise ValueError("Неверное время")
                
            except (ValueError, IndexError):
                await message.answer(
                    get_text("shift_management.invalid_time_format", language=lang),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                            callback_data="template_management")]
                    ])
                )
                return
        
            # Сохраняем время в состоянии
            await state.update_data(start_hour=hour, start_minute=minute)
        
            # Переходим к вводу продолжительности
            await message.answer(
                get_text("shift_management.time_saved_enter_duration", language=lang, hour=hour, minute=minute),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                        callback_data="template_management")]
                ]),
                parse_mode="HTML"
            )
        
            await state.set_state(ShiftManagementStates.template_duration_input)
        
    except Exception as e:
        logger.error(f"Ошибка ввода времени шаблона: {e}")
        lang = get_user_language(message.from_user.id, db) if db else "ru"
        await message.answer(get_text("shift_management.template_time_error", language=lang))


@router.message(StateFilter(ShiftManagementStates.template_duration_input))
async def handle_template_duration_input(message: Message, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка ввода продолжительности шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(message.from_user.id, db)

            duration_text = message.text.strip()
        
            # Парсим продолжительность
            try:
                duration = int(duration_text)
                if duration < 1 or duration > 24:
                    raise ValueError("Неверная продолжительность")
            except ValueError:
                await message.answer(
                    get_text("shift_management.invalid_duration", language=lang),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                            callback_data="template_management")]
                    ])
                )
                return
        
            # Сохраняем продолжительность в состоянии и переходим к выбору специализаций
            await state.update_data(duration=duration)
        
            from uk_management_bot.utils.constants import SPECIALIZATIONS
            keyboard = []
        
            for spec_key, spec_name in SPECIALIZATIONS.items():
                keyboard.append([InlineKeyboardButton(
                    text=f"⭕ {spec_name}",
                    callback_data=f"template_create_spec_{spec_key}"
                )])
        
            keyboard.append([InlineKeyboardButton(text=get_text("shift_management.next_no_specs", language=lang),
                                                callback_data="template_create_no_specs")])
            keyboard.append([InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                                callback_data="template_management")])

            await message.answer(
                get_text("shift_management.duration_saved_select_specs", language=lang, duration=duration),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )
        
            await state.set_state(ShiftManagementStates.template_specialization_selection)
        
    except Exception as e:
        logger.error(f"Ошибка создания шаблона: {e}")
        lang = get_user_language(message.from_user.id, db) if db else "ru"
        await message.answer(
            get_text("shift_management.template_creation_error", language=lang),
            reply_markup=get_template_management_keyboard(lang)
        )


@router.callback_query(F.data == "templates_edit")
@require_role(['admin', 'manager'])
async def handle_edit_templates(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Редактирование шаблонов смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            template_manager = TemplateManager(db)
        
            logger.debug(f"Начинаем редактирование шаблонов для пользователя {callback.from_user.id}")
        
            # Получаем все шаблоны для редактирования
            templates = template_manager.get_templates(active_only=False)
        
            logger.debug(f"Найдено шаблонов: {len(templates)}")
        
            if not templates:
                await callback.message.edit_text(
                    get_text("shift_management.edit_no_templates", language=lang),
                    reply_markup=get_template_management_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer(get_text("shift_management.no_templates_alert", language=lang))
                return
        
            # Формируем клавиатуру со списком шаблонов для редактирования
            keyboard = []
            for template in templates:
                status_emoji = "✅" if template.is_active else "❌"
                time_info = f"{template.start_hour:02d}:{template.start_minute or 0:02d}"
            
                button_text = f"{status_emoji} {template.name} ({time_info})"
                keyboard.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"template_edit_{template.id}"
                    )
                ])
        
            # Добавляем кнопки управления
            keyboard.extend([
                [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                    callback_data="template_management")]
            ])

            logger.debug("Отправляем сообщение со списком шаблонов")

            await callback.message.edit_text(
                get_text("shift_management.edit_templates_title", language=lang),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )
        
            logger.debug("Устанавливаем состояние")
            await state.set_state(TemplateManagementStates.editing_template)
        
            logger.debug("Отвечаем на callback")
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования шаблонов: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.edit_templates_error", language=lang), show_alert=True)


@router.callback_query(lambda c: c.data.startswith("template_edit_") and c.data.replace("template_edit_", "").isdigit())
@require_role(['admin', 'manager'])
async def handle_edit_template_details(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Редактирование конкретного шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            # Извлекаем ID шаблона из callback_data
            template_id = int(callback.data.replace("template_edit_", ""))
        
            # Получаем шаблон из базы данных
            template = ShiftManagementService(db).get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            # Формируем информацию о шаблоне
            status_text = get_text("shift_management.template_status_active", language=lang) if template.is_active else get_text("shift_management.template_status_inactive", language=lang)
            time_info = f"{template.start_hour:02d}:{template.start_minute or 0:02d}"

            specialization_info = get_text("shift_management.specializations_not_specified", language=lang)
            if template.required_specializations:
                from uk_management_bot.utils.constants import SPECIALIZATIONS
                specialization_info = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in template.required_specializations])

            description = template.description or get_text("shift_management.description_not_specified", language=lang)

            template_info = get_text("shift_management.edit_template_details", language=lang,
                                    name=template.name,
                                    description=description,
                                    time=time_info,
                                    duration=template.duration_hours,
                                    specializations=specialization_info,
                                    status=status_text)
        
            # Клавиатура редактирования
            toggle_text = get_text("shift_management.activate_button", language=lang) if not template.is_active else get_text("shift_management.deactivate_button", language=lang)

            keyboard = [
                [InlineKeyboardButton(text=get_text("shift_management.edit_name_button", language=lang),
                                    callback_data=f"template_edit_name_{template_id}")],
                [InlineKeyboardButton(text=get_text("shift_management.edit_description_button", language=lang),
                                    callback_data=f"template_edit_description_{template_id}")],
                [InlineKeyboardButton(text=get_text("shift_management.edit_time_button", language=lang),
                                    callback_data=f"template_edit_time_{template_id}")],
                [InlineKeyboardButton(text=get_text("shift_management.edit_duration_button", language=lang),
                                    callback_data=f"template_edit_duration_{template_id}")],
                [InlineKeyboardButton(text=get_text("shift_management.edit_specializations_button", language=lang),
                                    callback_data=f"template_edit_specializations_{template_id}")],
                [InlineKeyboardButton(text=toggle_text,
                                    callback_data=f"template_toggle_active_{template_id}")],
                [InlineKeyboardButton(text=get_text("shift_management.delete_template_button", language=lang),
                                    callback_data=f"template_delete_{template_id}")],
                [InlineKeyboardButton(text=get_text("shift_management.back_to_list_button", language=lang),
                                    callback_data="templates_edit")]
            ]
        
            await callback.message.edit_text(
                template_info,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )
        
            # Сохраняем ID шаблона в состоянии для дальнейшего использования
            await state.update_data(editing_template_id=template_id)
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.edit_templates_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_toggle_active_"))
@require_role(['admin', 'manager'])
async def handle_toggle_template_active(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Переключение активности шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            # Извлекаем ID шаблона
            template_id = int(callback.data.replace("template_toggle_active_", ""))

            service = ShiftManagementService(db)
            # Получаем шаблон
            template = service.get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            # Переключаем активность
            new_status = not template.is_active
            success = service.set_template_active(template_id, new_status)

            if success:
                status_key = "shift_management.template_activated" if new_status else "shift_management.template_deactivated"
                await callback.answer(get_text(status_key, language=lang))

                # Обновляем отображение
                await handle_edit_template_details(callback, state, db, roles, user)
            else:
                await callback.answer(get_text("shift_management.template_status_change_failed", language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка переключения активности шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.template_toggle_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_edit_name_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_name(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение названия шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            template_id = int(callback.data.replace("template_edit_name_", ""))
            template = ShiftManagementService(db).get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            await callback.message.edit_text(
                get_text("shift_management.edit_name_prompt", language=lang, current_name=template.name),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.cancel_button", language=lang), callback_data=f"template_edit_{template_id}")]
                ]),
                parse_mode="HTML"
            )

            await state.update_data(editing_template_id=template_id, editing_field="name")
            await state.set_state(TemplateManagementStates.editing_field)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка изменения названия шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.edit_name_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_edit_description_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_description(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение описания шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            template_id = int(callback.data.replace("template_edit_description_", ""))
            template = ShiftManagementService(db).get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            current_desc = template.description or get_text("shift_management.description_not_specified", language=lang)
            await callback.message.edit_text(
                get_text("shift_management.edit_description_prompt", language=lang, current_description=current_desc),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.cancel_button", language=lang), callback_data=f"template_edit_{template_id}")]
                ]),
                parse_mode="HTML"
            )

            await state.update_data(editing_template_id=template_id, editing_field="description")
            await state.set_state(TemplateManagementStates.editing_field)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка изменения описания шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.edit_description_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_edit_time_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_time(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение времени начала шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            template_id = int(callback.data.replace("template_edit_time_", ""))
            template = ShiftManagementService(db).get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            await callback.message.edit_text(
                get_text("shift_management.edit_time_prompt", language=lang, current_time=f"{template.start_hour:02d}:00"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.cancel_button", language=lang), callback_data=f"template_edit_{template_id}")]
                ]),
                parse_mode="HTML"
            )

            await state.update_data(editing_template_id=template_id, editing_field="start_hour")
            await state.set_state(TemplateManagementStates.editing_field)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка изменения времени шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.edit_time_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_edit_duration_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_duration(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение продолжительности шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            template_id = int(callback.data.replace("template_edit_duration_", ""))
            template = ShiftManagementService(db).get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            await callback.message.edit_text(
                get_text("shift_management.edit_duration_prompt", language=lang, current_duration=template.duration_hours),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.cancel_button", language=lang), callback_data=f"template_edit_{template_id}")]
                ]),
                parse_mode="HTML"
            )

            await state.update_data(editing_template_id=template_id, editing_field="duration_hours")
            await state.set_state(TemplateManagementStates.editing_field)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка изменения продолжительности шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.edit_duration_error", language=lang), show_alert=True)
