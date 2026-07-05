"""Списание материалов исполнителем на заявку (складской учёт).

Сценарий (FSM MaterialIssueStates): кнопка «📦 Материалы» в карточке заявки
«В работе» → выбор материала (инлайн-список с остатками, пагинация) → ввод
количества → подтверждение → списание + RequestComment (type='material')
одной транзакцией (``material_service.issue_material_with_comment``).

Guard жёсткий (кнопка — не защита, callback можно вызвать напрямую): заявка
существует; статус «В работе»; ``request.executor_id == user.id``; материал
активен; остаток > 0. Статус/исполнитель перепроверяются на финальном
подтверждении, количество жёстко валидируется внутри лока сервиса.

ARCH-01: хендлер — тонкий FSM/UI-слой, весь ORM в services/material_service.py.
"""
import logging
import re
from decimal import Decimal

from aiogram import F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from uk_management_bot.keyboards.materials import (
    get_material_confirm_keyboard,
    get_material_list_keyboard,
    unit_label,
)
from uk_management_bot.services.material_service import (
    InsufficientStockError,
    MaterialServiceError,
    MaterialValidationError,
    get_material_stock_sync,
    guard_executor_issue,
    issue_material_with_comment,
    list_materials_with_stock,
    parse_qty,
)
from uk_management_bot.services.request_number_service import REQUEST_NUMBER_CORE
from uk_management_bot.states.material_issue import MaterialIssueStates
from uk_management_bot.utils.helpers import get_text

from ._router import router
from .shared import _db_scope, _get_user_language

logger = logging.getLogger(__name__)

_MATISSUE_START_RE = rf"^matissue_start_{REQUEST_NUMBER_CORE}$"
_MATPICK_RE = re.compile(r"^matpick_(\d+)$")
_MATPAGE_RE = re.compile(r"^matpage_(\d+)$")


def _fmt_qty(qty: Decimal) -> str:
    return f"{qty.normalize():f}"


@router.callback_query(F.data.regexp(_MATISSUE_START_RE))
async def start_material_issue(callback: CallbackQuery, state: FSMContext):
    """Вход: кнопка «📦 Материалы» в карточке заявки «В работе»."""
    request_number = callback.data.removeprefix("matissue_start_")
    try:
        with _db_scope(None) as db:
            lang = await _get_user_language(callback=callback)
            _, _, err = guard_executor_issue(
                db, request_number=request_number,
                telegram_id=callback.from_user.id)
            if err:
                await callback.answer(get_text(err, language=lang), show_alert=True)
                return
            materials = list_materials_with_stock(db)
            if not materials:
                await callback.answer(
                    get_text("materials.issue.no_materials", language=lang),
                    show_alert=True,
                )
                return
            await state.set_state(MaterialIssueStates.selecting_material)
            await state.update_data(mat_request_number=request_number, mat_page=1)
            await callback.message.answer(
                get_text("materials.issue.select_material", language=lang)
                .format(request_number=request_number),
                reply_markup=get_material_list_keyboard(materials, page=1, language=lang),
            )
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка старта списания материалов ({request_number}): {e}")
        await callback.answer(get_text("materials.issue.error", language="ru"), show_alert=True)


@router.callback_query(MaterialIssueStates.selecting_material, F.data.regexp(_MATPAGE_RE))
async def paginate_materials(callback: CallbackQuery, state: FSMContext):
    page = int(_MATPAGE_RE.match(callback.data).group(1))
    try:
        with _db_scope(None) as db:
            lang = await _get_user_language(callback=callback)
            materials = list_materials_with_stock(db)
            await state.update_data(mat_page=page)
            await callback.message.edit_reply_markup(
                reply_markup=get_material_list_keyboard(materials, page=page, language=lang)
            )
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка пагинации материалов: {e}")
        await callback.answer()


@router.callback_query(MaterialIssueStates.selecting_material, F.data == "matpage_current")
async def paginate_materials_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(MaterialIssueStates.selecting_material, F.data.regexp(_MATPICK_RE))
async def pick_material(callback: CallbackQuery, state: FSMContext):
    material_id = int(_MATPICK_RE.match(callback.data).group(1))
    try:
        with _db_scope(None) as db:
            lang = await _get_user_language(callback=callback)
            materials = {m["id"]: m for m in list_materials_with_stock(db)}
            material = materials.get(material_id)
            if material is None:  # деактивирован/обнулился между экранами
                await callback.answer(
                    get_text("materials.issue.material_unavailable", language=lang),
                    show_alert=True,
                )
                return
            await state.set_state(MaterialIssueStates.entering_quantity)
            await state.update_data(
                mat_material_id=material_id,
                mat_material_name=material["name"],
                mat_material_unit=material["unit"],
            )
            await callback.message.edit_text(
                get_text("materials.issue.enter_quantity", language=lang).format(
                    name=material["name"],
                    stock=_fmt_qty(material["stock"]),
                    unit=unit_label(material["unit"], lang),
                )
            )
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка выбора материала {material_id}: {e}")
        await callback.answer(get_text("materials.issue.error", language="ru"), show_alert=True)


@router.message(MaterialIssueStates.entering_quantity)
async def enter_quantity(message: Message, state: FSMContext):
    try:
        with _db_scope(None) as db:
            lang = await _get_user_language(message=message)
            data = await state.get_data()
            material_id = data["mat_material_id"]
            unit = unit_label(data["mat_material_unit"], lang)
            try:
                qty = parse_qty((message.text or "").replace(",", ".").strip())
            except MaterialValidationError:
                await message.answer(
                    get_text("materials.issue.invalid_quantity", language=lang))
                return
            # мягкая проверка остатка до транзакции (жёсткая — в локе сервиса)
            stock = get_material_stock_sync(db, material_id)
            if qty > stock:
                await message.answer(
                    get_text("materials.issue.not_enough", language=lang)
                    .format(stock=_fmt_qty(stock), unit=unit))
                return
            await state.set_state(MaterialIssueStates.confirming)
            await state.update_data(mat_qty=str(qty))
            await message.answer(
                get_text("materials.issue.confirm", language=lang).format(
                    request_number=data["mat_request_number"],
                    name=data["mat_material_name"],
                    qty=_fmt_qty(qty),
                    unit=unit,
                ),
                reply_markup=get_material_confirm_keyboard(lang),
            )
    except Exception as e:
        logger.error(f"Ошибка ввода количества материала: {e}")
        await message.answer(get_text("materials.issue.error", language="ru"))


@router.callback_query(MaterialIssueStates.confirming, F.data == "matconfirm")
async def confirm_material_issue(callback: CallbackQuery, state: FSMContext):
    """Финал: перепроверка guard'ов → списание + комментарий одной транзакцией."""
    try:
        data = await state.get_data()
        request_number = data["mat_request_number"]
        with _db_scope(None) as db:
            lang = await _get_user_language(callback=callback)
            _, user, err = guard_executor_issue(
                db, request_number=request_number,
                telegram_id=callback.from_user.id)
            if err:
                await state.clear()
                await callback.answer(get_text(err, language=lang), show_alert=True)
                return
            unit = unit_label(data["mat_material_unit"], lang)
            qty = Decimal(data["mat_qty"])
            # Текст журнала — по-русски (единый язык учётных записей)
            comment_text = get_text("materials.issue.comment", language="ru").format(
                name=data["mat_material_name"],
                qty=_fmt_qty(qty),
                unit=unit_label(data["mat_material_unit"], "ru"),
            )
            try:
                issue = issue_material_with_comment(
                    db,
                    material_id=data["mat_material_id"],
                    qty=data["mat_qty"],
                    created_by=user.id,
                    request_number=request_number,
                    comment_text=comment_text,
                )
            except InsufficientStockError as exc:
                await state.clear()
                await callback.answer(
                    get_text("materials.issue.not_enough", language=lang)
                    .format(stock=_fmt_qty(exc.available), unit=unit),
                    show_alert=True,
                )
                return
            except MaterialServiceError as exc:
                await state.clear()
                logger.warning(f"Списание отклонено ({request_number}): {exc}")
                await callback.answer(
                    get_text("materials.issue.error", language=lang), show_alert=True)
                return

            await state.clear()
            await callback.message.edit_text(
                get_text("materials.issue.success", language=lang).format(
                    name=issue.material_name,
                    qty=_fmt_qty(Decimal(str(issue.qty))),
                    unit=unit,
                    request_number=request_number,
                )
            )
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка подтверждения списания: {e}")
        await state.clear()
        await callback.answer(get_text("materials.issue.error", language="ru"), show_alert=True)


@router.callback_query(StateFilter(MaterialIssueStates), F.data == "matcancel")
async def cancel_material_issue(callback: CallbackQuery, state: FSMContext):
    lang = await _get_user_language(callback=callback)
    await state.clear()
    await callback.message.edit_text(
        get_text("materials.issue.cancelled", language=lang))
    await callback.answer()
