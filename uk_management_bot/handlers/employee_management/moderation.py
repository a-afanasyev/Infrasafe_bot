"""Модерация сотрудников: одобрение/отклонение, блокировка, удаление.

AUD5-ARCH-3 (волна 1): перенос 1:1 из handlers/employee_management.py.
"""

import logging


from aiogram import F
from aiogram.types import CallbackQuery

from uk_management_bot.database.session import run_db

from uk_management_bot.keyboards.employee_management import (
    get_employee_deleted_keyboard,
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User

from ._router import router
from ._units import _moderate_employee, _return_to_employee_info

logger = logging.getLogger(__name__)


# ═══ ОДОБРЕНИЕ/ОТКЛОНЕНИЕ СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("approve_employee_"))
async def approve_employee(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Одобрить сотрудника"""
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        employee_id = int(callback.data.split('_')[2])

        outcome = await run_db(
            lambda s: _moderate_employee(
                s, callback.from_user.id, employee_id,
                "approve_user", "Одобрен через панель управления сотрудниками"),
            db=_db)
        if outcome == "no_actor":
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return

        if outcome == "ok":
            await callback.answer(
                get_text('employee_management.employee_approved', language=lang),
                show_alert=True
            )

            # CODE-1 (как MGR-05 block/unblock): ре-рендер карточки на месте
            # (виден новый статус) вместо show_employee_list(callback), который
            # парсил `approve_employee_<id>` как список и падал IndexError.
            # callback уже отвечен — ошибка рендера только логируется.
            try:
                await _return_to_employee_info(callback, employee_id, lang, _db=_db)
            except Exception as render_err:
                logger.error(f"Ошибка ре-рендера карточки после одобрения {employee_id}: {render_err}")
        else:
            await callback.answer(
                get_text('errors.unknown_error', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка одобрения сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("reject_employee_"))
async def reject_employee(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Отклонить сотрудника"""
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        employee_id = int(callback.data.split('_')[2])

        outcome = await run_db(
            lambda s: _moderate_employee(
                s, callback.from_user.id, employee_id,
                "block_user", "Отклонен через панель управления сотрудниками"),
            db=_db)
        if outcome == "no_actor":
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return

        if outcome == "ok":
            await callback.answer(
                get_text('employee_management.employee_rejected', language=lang),
                show_alert=True
            )

            # CODE-1 (как MGR-05 block/unblock): ре-рендер карточки на месте
            # вместо show_employee_list(callback) (IndexError на разборе callback).
            # callback уже отвечен — ошибка рендера только логируется.
            try:
                await _return_to_employee_info(callback, employee_id, lang, _db=_db)
            except Exception as render_err:
                logger.error(f"Ошибка ре-рендера карточки после отклонения {employee_id}: {render_err}")
        else:
            await callback.answer(
                get_text('errors.unknown_error', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка отклонения сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ БЛОКИРОВКА/РАЗБЛОКИРОВКА СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("block_employee_"))
async def block_employee(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Заблокировать сотрудника"""
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        employee_id = int(callback.data.split('_')[2])

        outcome = await run_db(
            lambda s: _moderate_employee(
                s, callback.from_user.id, employee_id,
                "block_user", "Заблокирован через панель управления сотрудниками"),
            db=_db)
        if outcome == "no_actor":
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return

        if outcome == "ok":
            await callback.answer(
                get_text('employee_management.employee_blocked', language=lang),
                show_alert=True
            )

            # MGR-05: ре-рендер карточки на месте (актуальный статус «Заблокирован»
            # + кнопка «Разблокировать») вместо ухода в список. callback уже отвечен
            # выше — ошибка рендера только логируется, без повторного answer.
            try:
                await _return_to_employee_info(callback, employee_id, lang, _db=_db)
            except Exception as render_err:
                logger.error(f"Ошибка ре-рендера карточки после блокировки {employee_id}: {render_err}")
        else:
            await callback.answer(
                get_text('errors.unknown_error', language=lang),
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Ошибка блокировки сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("unblock_employee_"))
async def unblock_employee(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Разблокировать сотрудника"""
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        employee_id = int(callback.data.split('_')[2])

        outcome = await run_db(
            lambda s: _moderate_employee(
                s, callback.from_user.id, employee_id,
                "approve_user", "Разблокирован через панель управления сотрудниками"),
            db=_db)
        if outcome == "no_actor":
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return

        if outcome == "ok":
            await callback.answer(
                get_text('employee_management.employee_unblocked', language=lang),
                show_alert=True
            )

            # MGR-05 (тот же фикс, что для block): ре-рендер карточки на месте
            # вместо show_employee_list(callback), который парсил callback.data
            # `unblock_employee_<id>` как `employee_mgmt_list_<type>_<page>` и падал
            # с IndexError. callback уже отвечен — ошибка рендера только логируется.
            try:
                await _return_to_employee_info(callback, employee_id, lang, _db=_db)
            except Exception as render_err:
                logger.error(f"Ошибка ре-рендера карточки после разблокировки {employee_id}: {render_err}")
        else:
            await callback.answer(
                get_text('errors.unknown_error', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка разблокировки сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ УДАЛЕНИЕ СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("delete_employee_"))
async def delete_employee(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Удалить сотрудника"""
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        employee_id = int(callback.data.split('_')[2])

        outcome = await run_db(
            lambda s: _moderate_employee(
                s, callback.from_user.id, employee_id,
                "delete_user", "Удален через панель управления сотрудниками"),
            db=_db)
        if outcome == "no_actor":
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return

        if outcome == "ok":
            await callback.answer(
                get_text('employee_management.employee_deleted', language=lang),
                show_alert=True
            )

            # CODE-1: карточку удалённого сотрудника рендерить нельзя (объекта нет),
            # а show_employee_list(callback) падал IndexError на разборе callback.
            # Показываем нейтральный экран с кнопкой возврата в список pending.
            # callback уже отвечен — ошибка рендера только логируется.
            try:
                await callback.message.edit_text(
                    get_text('employee_management.employee_deleted', language=lang),
                    reply_markup=get_employee_deleted_keyboard(lang),
                )
            except Exception as render_err:
                logger.error(f"Ошибка рендера экрана после удаления {employee_id}: {render_err}")
        else:
            await callback.answer(
                get_text('errors.unknown_error', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка удаления сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )
