"""Шаблоны смен: специализации, удаление, правка полей (часть B).

AUD3-07/AUD5-ARCH-1 (A2-хвост, волна 7): DB-фаза каждого хендлера — sync
unit-of-work под ``run_db``. Прежний ``with _db_scope(db) as db:`` держал
сессию открытой ЧЕРЕЗ ``await``'ы (FSM-хранилище, edit_text в Telegram) прямо
на event loop; теперь БД живёт только внутри юнита, а рендер клавиатур,
FSM-операции и Telegram-IO происходят вне сессии на примитивах.
``@require_role``-хендлеры объявляют ``roles``/``user`` (DI декоратора), но
НЕ ``db``.

Кросс-модульные вызовы в templates_a (handle_edit_templates /
handle_edit_template_details) идут теперь с ``db=None`` — их собственный
``_db_scope(None)`` откроет свежую сессию; оба хендлера только читают и
рендерят список/карточку шаблона (templates_a в этой волне не конвертируется).

Инвентарь живости: все 10 хендлеров живые. Корни цепочки — templates_a:
267 (template_create_spec_), 271 (template_create_no_specs),
407 (template_edit_specializations_), 411 (template_delete_),
493-494 (состояние editing_field); template_create_finish,
template_spec_toggle_/template_spec_save_ и template_delete_confirm_/
template_force_delete_ рождают клавиатуры этого же файла. Мёртвых нет.
"""
import logging

from aiogram import F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.services.shift_management_service import ShiftManagementService
from uk_management_bot.services.template_manager import TemplateManager
from uk_management_bot.states.shift_management import TemplateManagementStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language, get_text

from ._router import router
from .templates_a import handle_edit_templates, handle_edit_template_details

logger = logging.getLogger(__name__)


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# Наружу — только примитивы: клавиатуры собираются в async-слое.
# ==========================================================================


def _lang(db, telegram_id: int) -> str:
    """Язык пользователя из БД (тот же helper, что и раньше)."""
    return get_user_language(telegram_id, db)


def _apply_create_template(db, template_name, start_hour, start_minute, duration,
                           description: str, selected_specs):
    """Создаёт шаблон. -> (name, start_hour, start_minute, duration_hours) | None."""
    template_manager = TemplateManager(db)

    # Создаем шаблон в базе данных
    template = template_manager.create_template(
        name=template_name,
        start_hour=start_hour,
        start_minute=start_minute,
        duration_hours=duration,
        description=description,
        required_specializations=selected_specs if selected_specs else None,
        is_active=True,
        auto_create=True,
        days_of_week=[1, 2, 3, 4, 5, 6, 7],  # Все дни недели
        advance_days=1  # Создавать смены за 1 день
    )

    if not template:
        return None

    return template.name, template.start_hour, template.start_minute, template.duration_hours


def _load_template_specs(db, template_id: int):
    """-> (name, required_specializations) | None (шаблона нет)."""
    template = ShiftManagementService(db).get_template(template_id)

    if not template:
        return None

    return template.name, list(template.required_specializations or [])


def _apply_toggle_specialization(db, template_id: int, specialization: str):
    """Переключает специализацию шаблона. -> (name, новый список) | None."""
    template = ShiftManagementService(db).get_template(template_id)

    if not template:
        return None

    current_specs = template.required_specializations or []

    # Переключаем специализацию
    if specialization in current_specs:
        current_specs.remove(specialization)
    else:
        current_specs.append(specialization)

    # Принудительно устанавливаем новое значение и помечаем поле как измененное
    ShiftManagementService(db).set_template_specializations(template_id, current_specs)

    return template.name, list(current_specs)


def _load_template_name(db, template_id: int):
    """-> name | None (шаблона нет)."""
    template = ShiftManagementService(db).get_template(template_id)

    if not template:
        return None

    return template.name


def _apply_delete_template(db, template_id: int, force: bool):
    """Удаляет шаблон. -> (name, success) | None (шаблона нет)."""
    template_manager = TemplateManager(db)

    template = ShiftManagementService(db).get_template(template_id)

    if not template:
        return None

    template_name = template.name

    return template_name, template_manager.delete_template(template_id, force=force)


def _apply_template_field(db, template_id: int, field: str, new_value):
    """Применяет новое значение поля шаблона и коммитит. -> True | None (шаблона нет).

    Валидация значения остаётся в async-слое (она чистая и завязана на ранние
    ответы пользователю); сюда приходит уже приведённое значение.
    """
    service = ShiftManagementService(db)
    template = service.get_template(template_id)

    if not template:
        return None

    setattr(template, field, new_value)

    # Сохраняем изменения
    service.commit()
    return True


@router.callback_query(F.data.startswith("template_create_spec_"))
async def handle_template_create_specialization_toggle(callback: CallbackQuery, state: FSMContext, roles: list = None, user=None, *, _db=None):
    """Переключение специализации при создании шаблона"""
    lang = "ru"  # A6-P3-21 (как в PR #334): except не ходит в БД — сессия закрыта/aborted
    try:
        lang = await run_db(lambda s: _lang(s, callback.from_user.id), db=_db)

        specialization = callback.data.replace("template_create_spec_", "")

        # Получаем текущие выбранные специализации из состояния
        data = await state.get_data()
        selected_specs = data.get('selected_specializations', [])

        # Переключаем специализацию
        if specialization in selected_specs:
            selected_specs.remove(specialization)
        else:
            selected_specs.append(specialization)

        # Сохраняем в состоянии
        await state.update_data(selected_specializations=selected_specs)

        # Обновляем клавиатуру
        from uk_management_bot.utils.constants import SPECIALIZATIONS
        keyboard = []

        for spec_key, spec_name in SPECIALIZATIONS.items():
            is_selected = spec_key in selected_specs
            text = f"{'✅' if is_selected else '⭕'} {spec_name}"
            keyboard.append([InlineKeyboardButton(
                text=text,
                callback_data=f"template_create_spec_{spec_key}"
            )])

        keyboard.append([InlineKeyboardButton(text=get_text("shift_management.create_finish_button", language=lang), callback_data="template_create_finish")])
        keyboard.append([InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang), callback_data="template_management")])

        selected_text = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in selected_specs]) if selected_specs else get_text("shift_management.specs_not_selected", language=lang)

        try:
            await callback.message.edit_text(
                get_text("shift_management.select_specs_for_template", language=lang, selected=selected_text),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )
        except Exception as edit_error:
            if "message is not modified" not in str(edit_error):
                raise edit_error

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка переключения специализации при создании: {e}")
        await callback.answer(get_text("shift_management.spec_toggle_error", language=lang), show_alert=True)


@router.callback_query(F.data == "template_create_finish")
async def handle_template_create_finish(callback: CallbackQuery, state: FSMContext, roles: list = None, user=None, *, _db=None):
    """Завершение создания шаблона с выбранными специализациями"""
    lang = "ru"  # A6-P3-21 (как в PR #334): except не ходит в БД — сессия закрыта/aborted
    try:
        lang = await run_db(lambda s: _lang(s, callback.from_user.id), db=_db)

        # Получаем все данные из состояния
        data = await state.get_data()
        template_name = data.get('template_name')
        start_hour = data.get('start_hour')
        start_minute = data.get('start_minute', 0)
        duration = data.get('duration')
        selected_specs = data.get('selected_specializations', [])

        logger.info(f"Создание шаблона: name={template_name}, start_hour={start_hour}, start_minute={start_minute}, duration={duration}, specs={selected_specs}")

        description = get_text("shift_management.template_default_description", language=lang).format(name=template_name)
        template = await run_db(
            lambda s: _apply_create_template(
                s, template_name, start_hour, start_minute, duration, description, selected_specs
            ),
            db=_db,
        )

        if template:
            created_name, created_hour, created_minute, created_duration = template
            from uk_management_bot.utils.constants import SPECIALIZATIONS
            selected_text = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in selected_specs]) if selected_specs else get_text("shift_management.specializations_not_specified", language=lang)
            status_text = get_text("shift_management.template_status_active", language=lang)

            await callback.message.edit_text(
                get_text("shift_management.template_created_success", language=lang,
                        name=created_name,
                        time=f"{created_hour:02d}:{(created_minute or 0):02d}",
                        duration=created_duration,
                        specializations=selected_text,
                        status=status_text),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.back_to_templates_button", language=lang), callback_data="template_management")]
                ]),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                get_text("shift_management.template_creation_failed", language=lang),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang), callback_data="template_management")]
                ])
            )

        await state.clear()
        success_msg = get_text("shift_management.template_created_popup", language=lang) if template else get_text("shift_management.template_creation_failed_popup", language=lang)
        await callback.answer(success_msg)

    except Exception as e:
        logger.error(f"Ошибка завершения создания шаблона: {e}")
        await callback.answer(get_text("shift_management.template_finish_error", language=lang), show_alert=True)


@router.callback_query(F.data == "template_create_no_specs")
async def handle_template_create_no_specs(callback: CallbackQuery, state: FSMContext, roles: list = None, user=None, *, _db=None):
    """Создание шаблона без специализаций (совместимость со старым кодом)"""
    await handle_template_create_finish(callback, state, roles, user, _db=_db)


@router.callback_query(F.data.startswith("template_edit_specializations_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_specializations(callback: CallbackQuery, state: FSMContext, roles: list = None, user=None, *, _db=None):
    """Изменение специализаций шаблона"""
    lang = "ru"  # A6-P3-21 (как в PR #334): except не ходит в БД — сессия закрыта/aborted
    try:
        lang = await run_db(lambda s: _lang(s, callback.from_user.id), db=_db)

        template_id = int(callback.data.replace("template_edit_specializations_", ""))
        template = await run_db(lambda s: _load_template_specs(s, template_id), db=_db)

        if not template:
            await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
            return

        template_name, current_specializations = template
        from uk_management_bot.utils.constants import SPECIALIZATIONS
        not_specified = get_text("shift_management.not_specified", language=lang)
        specializations_text = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in current_specializations]) if current_specializations else not_specified

        # Создаем клавиатуру с доступными специализациями
        from uk_management_bot.utils.constants import SPECIALIZATIONS
        keyboard = []

        for spec_key, spec_name in SPECIALIZATIONS.items():
            is_selected = spec_key in current_specializations
            text = f"{'✅' if is_selected else '⭕'} {spec_name}"
            keyboard.append([InlineKeyboardButton(
                text=text,
                callback_data=f"template_spec_toggle_{template_id}_{spec_key}"
            )])

        keyboard.append([InlineKeyboardButton(text=get_text("shift_management.save_button", language=lang), callback_data=f"template_spec_save_{template_id}")])
        keyboard.append([InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang), callback_data=f"template_edit_{template_id}")])

        await callback.message.edit_text(
            get_text("shift_management.edit_specializations_title", language=lang,
                    template_name=template_name,
                    current_specs=specializations_text),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="HTML"
        )

        await state.update_data(editing_template_id=template_id)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка редактирования специализаций шаблона: {e}")
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_spec_toggle_"))
@require_role(['admin', 'manager'])
async def handle_toggle_template_specialization(callback: CallbackQuery, state: FSMContext, roles: list = None, user=None, *, _db=None):
    """Переключение специализации шаблона"""
    lang = "ru"  # A6-P3-21 (как в PR #334): except не ходит в БД — сессия закрыта/aborted
    try:
        lang = await run_db(lambda s: _lang(s, callback.from_user.id), db=_db)

        # Парсим callback data: template_spec_toggle_{template_id}_{specialization}
        parts = callback.data.replace("template_spec_toggle_", "").split("_", 1)
        template_id = int(parts[0])
        specialization = parts[1]

        toggled = await run_db(
            lambda s: _apply_toggle_specialization(s, template_id, specialization), db=_db
        )

        if not toggled:
            await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
            return

        template_name, current_specs = toggled

        # Обновляем клавиатуру
        from uk_management_bot.utils.constants import SPECIALIZATIONS
        keyboard = []

        for spec_key, spec_name in SPECIALIZATIONS.items():
            is_selected = spec_key in current_specs
            text = f"{'✅' if is_selected else '⭕'} {spec_name}"
            keyboard.append([InlineKeyboardButton(
                text=text,
                callback_data=f"template_spec_toggle_{template_id}_{spec_key}"
            )])

        keyboard.append([InlineKeyboardButton(text=get_text("shift_management.save_button", language=lang), callback_data=f"template_spec_save_{template_id}")])
        keyboard.append([InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang), callback_data=f"template_edit_{template_id}")])

        not_specified = get_text("shift_management.not_specified", language=lang)
        specializations_text = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in current_specs]) if current_specs else not_specified

        try:
            await callback.message.edit_text(
                get_text("shift_management.edit_specializations_title", language=lang,
                        template_name=template_name,
                        current_specs=specializations_text),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )
        except Exception as edit_error:
            # Если сообщение не изменилось, просто игнорируем ошибку
            if "message is not modified" not in str(edit_error):
                raise edit_error

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка переключения специализации: {e}")
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_spec_save_"))
@require_role(['admin', 'manager'])
async def handle_save_template_specializations(callback: CallbackQuery, state: FSMContext, roles: list = None, user=None, *, _db=None):
    """Сохранение специализаций шаблона"""
    lang = "ru"  # A6-P3-21 (как в PR #334): except не ходит в БД — сессия закрыта/aborted
    try:
        lang = await run_db(lambda s: _lang(s, callback.from_user.id), db=_db)

        template_id = int(callback.data.replace("template_spec_save_", ""))

        await callback.answer(get_text("shift_management.specializations_saved", language=lang))

        # Создаем новый callback объект для возврата к редактированию
        from aiogram.types import CallbackQuery
        new_callback = CallbackQuery(
            id=callback.id,
            from_user=callback.from_user,
            message=callback.message,
            data=f"template_edit_{template_id}",
            chat_instance=callback.chat_instance
        )

        # Возвращаемся к редактированию шаблона (templates_a не конвертирован —
        # его _db_scope(None) откроет собственную сессию на чтение карточки)
        await handle_edit_template_details(new_callback, state, _db, roles, user)

    except Exception as e:
        logger.error(f"Ошибка сохранения специализаций: {e}")
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(lambda c: c.data.startswith("template_delete_") and not c.data.startswith("template_delete_confirm_") and c.data.replace("template_delete_", "").isdigit())
@require_role(['admin', 'manager'])
async def handle_delete_template(callback: CallbackQuery, state: FSMContext, roles: list = None, user=None, *, _db=None):
    """Удаление шаблона"""
    lang = "ru"  # A6-P3-21 (как в PR #334): except не ходит в БД — сессия закрыта/aborted
    try:
        lang = await run_db(lambda s: _lang(s, callback.from_user.id), db=_db)

        template_id = int(callback.data.replace("template_delete_", ""))
        template_name = await run_db(lambda s: _load_template_name(s, template_id), db=_db)

        if not template_name:
            await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
            return

        # Показываем подтверждение удаления
        await callback.message.edit_text(
            get_text("shift_management.delete_template_confirm", language=lang, name=template_name),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text=get_text("shift_management.delete_yes_button", language=lang),
                                       callback_data=f"template_delete_confirm_{template_id}"),
                    InlineKeyboardButton(text=get_text("shift_management.delete_cancel_button", language=lang),
                                       callback_data=f"template_edit_{template_id}")
                ]
            ]),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка удаления шаблона: {e}")
        await callback.answer(get_text("shift_management.template_delete_error", language=lang), show_alert=True)


@router.callback_query(lambda c: c.data.startswith("template_delete_confirm_") and c.data.replace("template_delete_confirm_", "").isdigit())
@require_role(['admin', 'manager'])
async def handle_delete_template_confirm(callback: CallbackQuery, state: FSMContext, roles: list = None, user=None, *, _db=None):
    """Подтверждение удаления шаблона"""
    lang = "ru"  # A6-P3-21 (как в PR #334): except не ходит в БД — сессия закрыта/aborted
    try:
        lang = await run_db(lambda s: _lang(s, callback.from_user.id), db=_db)

        template_id = int(callback.data.replace("template_delete_confirm_", ""))
        deleted = await run_db(
            lambda s: _apply_delete_template(s, template_id, False), db=_db
        )

        if not deleted:
            await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
            return

        template_name, success = deleted

        if success:
            await callback.answer(get_text("shift_management.template_deleted", language=lang, name=template_name))
            # Возвращаемся к списку шаблонов
            await handle_edit_templates(callback, state, _db, roles, user)
        else:
            # Показываем опцию принудительного удаления
            await callback.message.edit_text(
                get_text("shift_management.template_delete_failed", language=lang, name=template_name),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.force_delete_button", language=lang),
                                        callback_data=f"template_force_delete_{template_id}")],
                    [InlineKeyboardButton(text=get_text("shift_management.delete_cancel_button", language=lang),
                                        callback_data=f"template_edit_{template_id}")]
                ]),
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Ошибка подтверждения удаления шаблона: {e}")
        await callback.answer(get_text("shift_management.template_delete_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_force_delete_"))
@require_role(['admin', 'manager'])
async def handle_force_delete_template(callback: CallbackQuery, state: FSMContext, roles: list = None, user=None, *, _db=None):
    """Принудительное удаление шаблона"""
    lang = "ru"  # A6-P3-21 (как в PR #334): except не ходит в БД — сессия закрыта/aborted
    try:
        lang = await run_db(lambda s: _lang(s, callback.from_user.id), db=_db)

        template_id = int(callback.data.replace("template_force_delete_", ""))
        deleted = await run_db(
            lambda s: _apply_delete_template(s, template_id, True), db=_db
        )

        if not deleted:
            await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
            return

        template_name, success = deleted

        if success:
            await callback.answer(get_text("shift_management.template_force_deleted", language=lang, name=template_name))
            # Возвращаемся к списку шаблонов
            await handle_edit_templates(callback, state, _db, roles, user)
        else:
            await callback.answer(get_text("shift_management.template_delete_failed", language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка принудительного удаления шаблона: {e}")
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.message(StateFilter(TemplateManagementStates.editing_field))
async def handle_template_field_input(message: Message, state: FSMContext, roles: list = None, user=None, *, _db=None):
    """Обработка ввода нового значения поля шаблона"""
    lang = "ru"  # A6-P3-21 (как в PR #334): except не ходит в БД — сессия закрыта/aborted
    try:
        lang = await run_db(lambda s: _lang(s, message.from_user.id), db=_db)

        data = await state.get_data()
        template_id = data.get('editing_template_id')
        field = data.get('editing_field')

        if not template_id or not field:
            await message.answer(get_text("shift_management.editing_data_not_found", language=lang))
            return

        template_name = await run_db(lambda s: _load_template_name(s, template_id), db=_db)

        if not template_name:
            await message.answer(get_text("shift_management.template_not_found", language=lang))
            return

        new_value = message.text.strip()

        # Валидация поля (чистая, без БД — ранние ответы пользователю остаются
        # на своих местах; в юнит уходит уже приведённое значение)
        if field == "name":
            if len(new_value) < 3:
                await message.answer(get_text("shift_management.name_min_length", language=lang))
                return
            field_value = new_value

        elif field == "description":
            field_value = new_value if new_value else None

        elif field == "start_hour":
            try:
                start_hour = int(new_value)
                if not (0 <= start_hour <= 23):
                    await message.answer(get_text("shift_management.hour_range_error", language=lang))
                    return
                field_value = start_hour
            except ValueError:
                await message.answer(get_text("shift_management.hour_number_error", language=lang))
                return

        elif field == "duration_hours":
            try:
                duration = int(new_value)
                if not (1 <= duration <= 24):
                    await message.answer(get_text("shift_management.duration_range_error", language=lang))
                    return
                field_value = duration
            except ValueError:
                await message.answer(get_text("shift_management.duration_number_error", language=lang))
                return
        else:
            await message.answer(get_text("shift_management.unknown_field_error", language=lang))
            return

        # Сохраняем изменения
        applied = await run_db(
            lambda s: _apply_template_field(s, template_id, field, field_value), db=_db
        )

        if not applied:
            await message.answer(get_text("shift_management.template_not_found", language=lang))
            return

        # Отображаем успешное сообщение с правильным текстом
        field_names = {
            "name": get_text("shift_management.field_name_label", language=lang),
            "description": get_text("shift_management.field_description_label", language=lang),
            "start_hour": get_text("shift_management.field_start_hour_label", language=lang),
            "duration_hours": get_text("shift_management.field_duration_label", language=lang)
        }

        field_display = field_names.get(field, field.capitalize())

        await message.answer(
            get_text("shift_management.field_updated_success", language=lang, field=field_display),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_text("shift_management.back_to_template_button", language=lang), callback_data=f"template_edit_{template_id}")]
            ])
        )

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка обновления поля шаблона: {e}")
        await message.answer(get_text("shift_management.save_error", language=lang))
