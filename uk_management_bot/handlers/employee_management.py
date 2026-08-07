"""
Обработчики для управления сотрудниками

Содержит обработчики для:
- Панели управления сотрудниками
- Списков и поиска сотрудников
- Действий модерации
- Управления ролями и специализациями

AUD3-37 (вариант (б), волна B4): DB-фаза каждого хендлера — цельный sync
unit-of-work (`_load_*`/`_update_*`/`_apply_*`/`_moderate_*` ниже), исполняемый
в worker-потоке через ``run_db``. Сессия живёт только внутри юнита; наружу
выходят DTO (``_EmployeeRow``) — рендеринг и клавиатуры работают по ним
duck-typed. Хендлеры НЕ объявляют параметр ``db``: иначе aiogram DI снова
инъецировал бы middleware-сессию, и запрос исполнялся бы на event loop
(гейт: tests/services/test_aud337_async_handlers_gate.py). Тестовый seam —
keyword-only ``_db`` (aiogram это имя не инъецирует: ключа "_db" в data нет),
с ним юнит исполняется синхронно на переданной сессии.
"""

import logging

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.database.session import run_db

from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.specialization_service import SpecializationService
from uk_management_bot.states.employee_management import EmployeeManagementStates
from uk_management_bot.keyboards.employee_management import (
    get_employee_management_main_keyboard,
    get_employee_list_keyboard,
    get_employee_actions_keyboard,
    get_employee_deleted_keyboard,
    get_cancel_keyboard,
    get_employee_edit_keyboard,
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access, sync_legacy_role, parse_roles_safe
from uk_management_bot.utils.specializations import parse_specializations
from uk_management_bot.utils.user_names import display_name
from uk_management_bot.database.models.user import User
import json
from uk_management_bot.utils.datetime_utils import utc_now

def _format_employee_name(employee) -> str:
    """Подпись сотрудника — общий канон имён (REFACTOR-133), сведено в AUD5-CODE-8."""
    return display_name(employee)


# ==========================================================================
# DTO + sync-юниты (AUD3-37, волна B4).
# Имена полей DTO совпадают с ORM-атрибутами User — display_name и клавиатуры
# (get_employee_list_keyboard, get_employee_actions_keyboard) работают по ним
# duck-typed, их код не менялся. Юниты берут сессию первым аргументом, commit
# делают сами (или он живёт в сервисе) — через границу потока ORM не выходит.
# ==========================================================================

@dataclass(frozen=True)
class _EmployeeRow:
    id: int
    telegram_id: Optional[int]
    first_name: Optional[str]
    last_name: Optional[str]
    username: Optional[str]
    phone: Optional[str]
    roles: Optional[str]
    status: Optional[str]
    specialization: Optional[str]
    created_at: Optional[datetime]


def _employee_row(user: User) -> _EmployeeRow:
    return _EmployeeRow(
        id=user.id,
        telegram_id=user.telegram_id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        phone=user.phone,
        roles=user.roles,
        status=user.status,
        specialization=user.specialization,
        created_at=user.created_at,
    )


def _load_employee_stats(db: Session) -> dict:
    return UserManagementService(db).get_employee_stats()


def _load_employees_page(db: Session, list_type: str, page: int) -> dict:
    data = UserManagementService(db).get_employees_list(list_type, page)
    return {**data, 'employees': [_employee_row(e) for e in data.get('employees', [])]}


def _load_employee(db: Session, employee_id: int) -> Optional[_EmployeeRow]:
    employee = UserManagementService(db).get_user_by_id(employee_id)
    return _employee_row(employee) if employee else None


def _moderate_employee(db: Session, actor_tg_id: int, employee_id: int,
                       method_name: str, comment: str) -> str:
    """Модерация через AuthService (approve_user/block_user/delete_user).

    Возвращает "no_actor" (оператор не найден в БД), "ok" или "fail".
    Commit — внутри AuthService.
    """
    current_user = db.query(User).filter(User.telegram_id == actor_tg_id).first()
    if not current_user:
        return "no_actor"
    success = getattr(AuthService(db), method_name)(employee_id, current_user.id, comment)
    return "ok" if success else "fail"


def _search_employees(db: Session, raw_query: str) -> List[_EmployeeRow]:
    from uk_management_bot.utils.sql_search import (
        ci_contains_any, escape_like, is_postgres,
    )
    pattern = f"%{escape_like(raw_query)}%"
    employees = (
        db.query(User)
        .filter(
            ci_contains_any(
                (User.first_name, User.last_name, User.username, User.phone),
                pattern,
                is_postgres=is_postgres(db),
            )
        )
        .limit(20)
        .all()
    )
    return [_employee_row(e) for e in employees]


def _load_detailed_spec_stats(db: Session) -> dict:
    detailed = SpecializationService(db).get_detailed_specialization_stats()
    return {
        spec: {
            'count': spec_data['count'],
            'employees': [_employee_row(e) for e in spec_data['employees']],
        }
        for spec, spec_data in detailed.items()
    }


def _update_employee_name(db: Session, target_employee_id: int, new_name: str) -> bool:
    user = db.query(User).filter(User.id == target_employee_id).first()
    if not user:
        return False
    # Разделяем ФИО на имя и фамилию
    name_parts = new_name.split()
    if len(name_parts) >= 2:
        user.first_name = name_parts[0]
        user.last_name = ' '.join(name_parts[1:])
    else:
        user.first_name = new_name
        user.last_name = None
    db.commit()
    return True


def _update_employee_phone(db: Session, target_employee_id: int, new_phone: str) -> bool:
    user = db.query(User).filter(User.id == target_employee_id).first()
    if not user:
        return False
    user.phone = new_phone
    db.commit()
    return True


def _apply_role_change(db: Session, actor_tg_id: int, target_employee_id: int,
                       current_roles: list, comment: str) -> str:
    """Смена набора ролей + best-effort аудит. "no_actor" | "no_target" | "ok"."""
    current_user = db.query(User).filter(User.telegram_id == actor_tg_id).first()
    if not current_user:
        return "no_actor"

    # with_for_update: два менеджера правят набор ролей одного сотрудника —
    # без блокировки last-write-wins тихо терял бы правку и рассинхронизировал
    # аудит с фактическим состоянием (как в B1 для _start_shift; sqlite — no-op).
    user = (
        db.query(User)
        .filter(User.id == target_employee_id)
        .with_for_update()
        .first()
    )
    if not user:
        return "no_target"

    logger.debug(f" Найден пользователь для обновления ролей: {user.id}")
    old_roles = parse_roles_safe(user.roles)  # COD-01: JSON+CSV
    logger.debug(f" Старые роли: {old_roles}, новые роли: {current_roles}")

    user.roles = json.dumps(current_roles)
    if current_roles:
        sync_legacy_role(user, current_roles[0])  # Первая роль как основная
        # Инвариант: active_role всегда ∈ roles. Если активная роль
        # больше не входит в набор (или не задана) — переводим на первую.
        if not user.active_role or user.active_role not in current_roles:
            user.active_role = current_roles[0]

    # Создаем запись в аудит логе
    try:
        from uk_management_bot.database.models.audit import AuditLog
        audit = AuditLog(
            action="role_change",
            user_id=current_user.id,  # ID пользователя, который вносит изменения
            telegram_user_id=user.telegram_id,  # Telegram ID пользователя, у которого изменяются роли
            details=json.dumps({
                "target_user_id": target_employee_id,
                "old_roles": old_roles,
                "new_roles": current_roles,
                "comment": comment,
                "timestamp": utc_now().isoformat()
            })
        )
        db.add(audit)
        logger.debug(" AuditLog создан успешно")
    except Exception as audit_error:
        logger.error(f"Failed to create AuditLog: {audit_error}")
        # Продолжаем выполнение даже если аудит не удался

    db.commit()
    return "ok"


def _apply_specialization_change(db: Session, actor_tg_id: int, target_employee_id: int,
                                 current_specializations: list, comment: str) -> str:
    """Смена специализаций + best-effort аудит. "no_actor" | "no_target" | "ok"."""
    current_user = db.query(User).filter(User.telegram_id == actor_tg_id).first()
    if not current_user:
        return "no_actor"

    # Сохраняем специализации напрямую в базу (обходя проверки сервиса).
    # with_for_update — та же TOCTOU-защита, что в _apply_role_change.
    user = (
        db.query(User)
        .filter(User.id == target_employee_id)
        .with_for_update()
        .first()
    )
    if not user:
        return "no_target"

    # AUD5-CODE-8: единый парсер вместо копии (json.loads без гейта —
    # JSON-скаляр попадал в аудит числом, элементы не стрипались)
    old_specializations = sorted(parse_specializations(user))

    # Сохраняем специализации как JSON строку
    user.specialization = json.dumps(current_specializations)

    # Создаем запись в аудит логе
    try:
        from uk_management_bot.database.models.audit import AuditLog
        audit = AuditLog(
            action="specialization_change",
            user_id=current_user.id,  # ID пользователя, который вносит изменения
            telegram_user_id=user.telegram_id,  # Telegram ID пользователя, у которого изменяются специализации
            details=json.dumps({
                "target_user_id": target_employee_id,
                "old_specializations": old_specializations,
                "new_specializations": current_specializations,
                "comment": comment,
                "timestamp": utc_now().isoformat()
            })
        )
        db.add(audit)
    except Exception as audit_error:
        logger.error(f"Ошибка создания AuditLog: {audit_error}")
        # Продолжаем выполнение даже если аудит не удался

    db.commit()
    return "ok"


async def _return_to_employee_info(callback: CallbackQuery, employee_id: int,
                                   language: str = "ru", *, _db=None) -> bool:
    """MGR-05: render-only карточка сотрудника по employee_id.

    НЕ проверяет права и НЕ вызывает callback.answer() ни на одном пути — это
    ответственность caller'а (он отвечает ровно один раз). Возвращает True при
    успешном рендере, False если сотрудник не найден. Может бросить исключение —
    caller оборачивает.

    Локализует роли/статус/специализацию через employee_display (BUG-BOT-023/
    MGR-06) и читает employee.roles (не deprecated employee.role).
    """
    lang = language
    from uk_management_bot.utils.employee_display import (
        format_user_status,
        format_roles,
        format_specializations,
    )

    employee = await run_db(lambda s: _load_employee(s, employee_id), db=_db)
    if not employee:
        return False

    employee_info = f"👤 {get_text('employee_management.employee_info', language=lang)}\n\n"

    # AUD5-CODE-8: имя через канон вместо инлайн-копии той же логики
    full_name = _format_employee_name(employee)

    not_specified = get_text('employee_mgmt.handlers.not_specified', language=lang)
    employee_info += f"📝 {get_text('employee_management.full_name', language=lang)}: {full_name}\n"
    employee_info += f"📱 {get_text('employee_management.phone', language=lang)}: {employee.phone or not_specified}\n"
    employee_info += f"🎯 {get_text('employee_management.role', language=lang)}: {format_roles(employee.roles, lang)}\n"
    employee_info += f"📊 {get_text('employee_management.status', language=lang)}: {format_user_status(employee.status, lang)}\n"

    if employee.specialization:
        employee_info += f"🛠️ {get_text('employee_management.specialization', language=lang)}: {format_specializations(employee.specialization, lang)}\n"

    employee_info += f"📅 {get_text('employee_management.created_at', language=lang)}: {employee.created_at.strftime('%d.%m.%Y %H:%M')}\n"

    await callback.message.edit_text(
        employee_info,
        reply_markup=get_employee_actions_keyboard(employee_id, employee.status, lang)
    )
    return True

logger = logging.getLogger(__name__)
router = Router()


# ═══ ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ СОТРУДНИКАМИ ═══

@router.callback_query(F.data == "employee_management_panel")
async def show_employee_management_panel(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Показать панель управления сотрудниками"""
    logger.debug(f"Employee management panel called: callback_data={callback.data}")
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    logger.debug(f" has_access = {has_access}, roles = {roles}, user = {user}")
    
    if not has_access:
        logger.debug(f"Access denied for user {callback.from_user.id}")
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        logger.debug(" Начинаем получение статистики сотрудников")
        # Получаем статистику сотрудников
        stats = await run_db(_load_employee_stats, db=_db)
        logger.debug(f" Статистика получена: {stats}")
        
        # Показываем главное меню
        try:
            title = get_text('employee_management.main_title', language=lang)
            keyboard = get_employee_management_main_keyboard(stats, lang)
            logger.debug(f" Заголовок: {title}")
            logger.debug(" Клавиатура создана успешно")
            
            await callback.message.edit_text(
                title,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"❌ Ошибка создания клавиатуры: {e}")
            raise
        
        await callback.answer()
        logger.debug(" Панель управления сотрудниками успешно отображена")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отображения панели управления сотрудниками: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "employee_mgmt_main")
async def back_to_main_panel(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Вернуться к главному меню панели управления"""
    await show_employee_management_panel(callback, roles, active_role, user, _db=_db)


@router.callback_query(F.data == "employee_mgmt_stats")
async def show_employee_stats(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Показать статистику сотрудников"""
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
        stats = await run_db(_load_employee_stats, db=_db)

        # Формируем текст статистики
        stats_text = f"📊 {get_text('employee_management.stats_title', language=lang)}\n\n"
        stats_text += f"📝 {get_text('employee_management.pending_employees', language=lang)}: {stats.get('pending', 0)}\n"
        stats_text += f"✅ {get_text('employee_management.active_employees', language=lang)}: {stats.get('active', 0)}\n"
        stats_text += f"🚫 {get_text('employee_management.blocked_employees', language=lang)}: {stats.get('blocked', 0)}\n"
        stats_text += f"🛠️ {get_text('employee_management.executors', language=lang)}: {stats.get('executors', 0)}\n"
        stats_text += f"👨‍💼 {get_text('employee_management.managers', language=lang)}: {stats.get('managers', 0)}\n"
        
        await callback.message.edit_text(
            stats_text,
            reply_markup=get_employee_management_main_keyboard(stats, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения статистики сотрудников: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ СПИСКИ СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("employee_mgmt_list_"))
async def show_employee_list(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Показать список сотрудников"""
    logger.debug(f" show_employee_list вызвана с callback_data: {callback.data}")
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    logger.debug(f" has_access = {has_access}, roles = {roles}, user = {user}")
    
    if not has_access:
        logger.debug(f"Access denied for user {callback.from_user.id}")
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        # Парсим callback data
        parts = callback.data.split('_')
        list_type = parts[3]  # pending, active, blocked, executors, managers
        page = int(parts[4]) if len(parts) > 4 else 1
        
        logger.debug(f" Запрос списка сотрудников: тип={list_type}, страница={page}")

        employees_data = await run_db(lambda s: _load_employees_page(s, list_type, page), db=_db)

        logger.debug(f" Получены данные сотрудников: {len(employees_data.get('employees', []))} сотрудников")
        
        # Формируем заголовок
        title_map = {
            'pending': get_text('employee_management.pending_employees', language=lang),
            'active': get_text('employee_management.active_employees', language=lang),
            'blocked': get_text('employee_management.blocked_employees', language=lang),
            'executors': get_text('employee_management.executors', language=lang),
            'managers': get_text('employee_management.managers', language=lang)
        }
        
        title = f"👥 {title_map.get(list_type, list_type)}"
        
        await callback.message.edit_text(
            title,
            reply_markup=get_employee_list_keyboard(employees_data, list_type, lang)
        )
        
        await callback.answer()
        logger.debug(" Список сотрудников успешно отображен")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отображения списка сотрудников: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ДЕЙСТВИЯ С СОТРУДНИКАМИ ═══

@router.callback_query(F.data.startswith("employee_mgmt_employee_"))
async def show_employee_actions(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Показать действия с сотрудником"""
    logger.debug(f" show_employee_actions вызвана с callback_data: {callback.data}")
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    logger.debug(f" has_access = {has_access}, roles = {roles}, user = {user}")
    
    if not has_access:
        logger.debug(f"Access denied for user {callback.from_user.id}")
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        # Получаем ID сотрудника
        employee_id = int(callback.data.split('_')[3])
        logger.debug(f" Запрошен сотрудник с ID: {employee_id}")

        # AUD5-CODE-8: карточка рендерится единственным хелпером
        # _return_to_employee_info — раньше здесь была вторая копия того же
        # текста. Вместе с копией ушёл fallback на deprecated employee.role:
        # роли живут в employee.roles (см. CLAUDE.md, «Роли в БД»).
        rendered = await _return_to_employee_info(callback, employee_id, lang, _db=_db)
        if rendered:
            await callback.answer()
        else:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка отображения действий с сотрудником: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


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


# ═══ РЕДАКТИРОВАНИЕ СОТРУДНИКОВ ═══

@router.callback_query(F.data.regexp(r"^edit_employee_\d+$"))
async def edit_employee_entry(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """MGR-03: вход в редактирование сотрудника (кнопка `edit_employee_<id>`).

    Раньше кнопка была no-op — листовые `edit_employee_name_`/`edit_employee_phone_`
    есть, а входного хендлера не было. Строгий regex `^edit_employee_\\d+$` не
    перехватывает листовые (после id у них идёт `_name_`/`_phone_`).
    """
    lang = language

    # Проверяем права доступа (как в листовых хендлерах)
    if not has_admin_access(roles=roles, user=user):
        await callback.answer(get_text('errors.permission_denied', language=lang), show_alert=True)
        return

    try:
        employee_id = int(callback.data.split('_')[2])

        employee = await run_db(lambda s: _load_employee(s, employee_id), db=_db)
        if not employee:
            await callback.answer(get_text('errors.user_not_found', language=lang), show_alert=True)
            return

        await callback.message.edit_text(
            get_text("employee_mgmt.handlers.edit_menu", language=lang).format(
                employee_name=_format_employee_name(employee)
            ),
            reply_markup=get_employee_edit_keyboard(employee_id, lang),
            parse_mode="HTML",
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка открытия меню редактирования сотрудника: {e}")
        await callback.answer(get_text('errors.unknown_error', language=lang), show_alert=True)


@router.callback_query(F.data.startswith("edit_employee_name_"))
async def edit_employee_name(callback: CallbackQuery, state: FSMContext, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Редактировать ФИО сотрудника"""
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
        employee_id = int(callback.data.split('_')[3])

        # Получаем сотрудника
        employee = await run_db(lambda s: _load_employee(s, employee_id), db=_db)

        if not employee:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return

        # Сохраняем данные в FSM
        await state.update_data({
            'target_employee_id': employee_id,
            'action': 'edit_name'
        })
        
        await state.set_state(EmployeeManagementStates.editing_full_name)
        
        # Запрашиваем новое ФИО
        await callback.message.edit_text(
            get_text("employee_mgmt.handlers.enter_new_name", language=lang).format(
                employee_name=_format_employee_name(employee),
                current_name=f"{employee.first_name or ''} {employee.last_name or ''}"
            ),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования ФИО сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("edit_employee_phone_"))
async def edit_employee_phone(callback: CallbackQuery, state: FSMContext, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Редактировать телефон сотрудника"""
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
        employee_id = int(callback.data.split('_')[3])

        # Получаем сотрудника
        employee = await run_db(lambda s: _load_employee(s, employee_id), db=_db)

        if not employee:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return

        # Сохраняем данные в FSM
        await state.update_data({
            'target_employee_id': employee_id,
            'action': 'edit_phone'
        })
        
        await state.set_state(EmployeeManagementStates.editing_phone)
        
        # Запрашиваем новый телефон
        await callback.message.edit_text(
            get_text("employee_mgmt.handlers.enter_new_phone", language=lang).format(
                employee_name=_format_employee_name(employee),
                current_phone=employee.phone or get_text("employee_mgmt.handlers.not_specified", language=lang)
            ),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования телефона сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.message(EmployeeManagementStates.editing_full_name)
async def process_employee_name_edit(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработать изменение ФИО сотрудника"""
    try:
        new_name = message.text.strip()
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')

        if not new_name:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.name_cannot_be_empty", language=lang))
            return

        # Обновляем ФИО
        updated = await run_db(lambda s: _update_employee_name(s, target_employee_id, new_name), db=_db)
        if updated:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.name_updated", language=lang).format(name=new_name))
        else:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.employee_not_found", language=lang))

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка обработки изменения ФИО: {e}")
        lang = language
        await message.answer(get_text("employee_mgmt.handlers.error_updating_name", language=lang))
        await state.clear()


@router.message(EmployeeManagementStates.editing_phone)
async def process_employee_phone_edit(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработать изменение телефона сотрудника"""
    try:
        new_phone = message.text.strip()
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')

        if not new_phone:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.phone_cannot_be_empty", language=lang))
            return

        # Обновляем телефон
        updated = await run_db(lambda s: _update_employee_phone(s, target_employee_id, new_phone), db=_db)
        if updated:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.phone_updated", language=lang).format(phone=new_phone))
        else:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.employee_not_found", language=lang))

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка обработки изменения телефона: {e}")
        lang = language
        await message.answer(get_text("employee_mgmt.handlers.error_updating_phone", language=lang))
        await state.clear()


@router.callback_query(F.data.startswith("change_employee_role_"))
async def change_employee_role(callback: CallbackQuery, state: FSMContext, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Изменить роль сотрудника"""
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
        employee_id = int(callback.data.split('_')[3])

        # Получаем сотрудника
        employee = await run_db(lambda s: _load_employee(s, employee_id), db=_db)

        if not employee:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return

        # Получаем текущие роли (COD-01: канонический парсер, JSON+CSV)
        user_roles = parse_roles_safe(employee.roles)
        
        # Сохраняем данные в FSM
        await state.update_data({
            'target_employee_id': employee_id,
            'original_roles': user_roles.copy(),
            'current_roles': user_roles.copy()
        })
        
        await state.set_state(EmployeeManagementStates.selecting_roles)
        
        # Формируем сообщение
        user_name = _format_employee_name(employee)
        message_text = f"🎯 {get_text('employee_management.change_role', language=lang)}: {user_name}\n\n"
        no_roles_text = get_text("employee_mgmt.handlers.no_roles", language=lang)
        # MGR-06: локализуем роли через канон-helper (roles.* namespace) вместо
        # сырых DB-значений ('executor' → 'Исполнитель').
        from uk_management_bot.utils.employee_display import format_roles
        message_text += get_text("employee_mgmt.handlers.current_roles", language=lang).format(
            roles=format_roles(user_roles, lang) if user_roles else no_roles_text
        )
        
        # Показываем меню выбора ролей
        from uk_management_bot.keyboards.employee_management import get_roles_management_keyboard
        
        await callback.message.edit_text(
            message_text,
            reply_markup=get_roles_management_keyboard(user_roles, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка изменения роли сотрудника: {e}")
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


# ═══ СПЕЦИАЛИЗАЦИИ СОТРУДНИКОВ ═══

@router.callback_query(F.data.startswith("change_employee_specialization_"))
async def change_employee_specialization(callback: CallbackQuery, state: FSMContext, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Изменить специализацию сотрудника"""
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
        employee_id = int(callback.data.split('_')[3])

        # Получаем сотрудника
        employee = await run_db(lambda s: _load_employee(s, employee_id), db=_db)

        if not employee:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return

        # AUD5-CODE-8: единый парсер вместо локальной копии — та делала
        # json.loads без гейта startswith('['), поэтому JSON-скаляр ('123')
        # превращался в int и ронял хендлер на .copy(), а элементы
        # JSON-списка не чистились от пробелов/пустых значений.
        user_specializations = sorted(parse_specializations(employee))
        
        # Сохраняем данные в FSM
        await state.update_data({
            'target_employee_id': employee_id,
            'original_specializations': user_specializations.copy(),
            'current_specializations': user_specializations.copy()
        })
        
        await state.set_state(EmployeeManagementStates.selecting_specializations)
        
        # Формируем сообщение
        user_name = _format_employee_name(employee)
        message_text = f"🛠️ {get_text('employee_management.specialization', language=lang)}: {user_name}\n\n"
        message_text += f"{get_text('specializations.current_specializations', language=lang)}: "
        
        # Форматируем специализации
        if user_specializations:
            spec_names = []
            for spec in user_specializations:
                spec_text = get_text(f'specializations.{spec}', language=lang, default=spec)
                spec_names.append(spec_text)
            message_text += ", ".join(spec_names)
        else:
            message_text += get_text("employee_mgmt.handlers.no_specializations", language=lang)
        
        # Показываем меню выбора специализаций
        from uk_management_bot.keyboards.employee_management import get_specializations_selection_keyboard
        
        await callback.message.edit_text(
            message_text,
            reply_markup=get_specializations_selection_keyboard(user_specializations, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка изменения специализации сотрудника: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ПОИСК СОТРУДНИКОВ ═══

@router.callback_query(F.data == "employee_mgmt_search")
async def start_employee_search(callback: CallbackQuery, state: FSMContext, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Начать поиск сотрудников"""
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
        await callback.message.edit_text(
            get_text('employee_management.search_instructions', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )

        # BUG-BOT-025: переводим пользователя в FSM-состояние ожидания запроса,
        # иначе message-handler ниже не сработает.
        await state.set_state(EmployeeManagementStates.waiting_for_search_query)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала поиска сотрудников: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.message(EmployeeManagementStates.waiting_for_search_query)
async def handle_employee_search_query(message: Message, state: FSMContext, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """BUG-BOT-025: обработка введённого запроса поиска сотрудников.

    Ищем по first_name / last_name / username / phone (ILIKE %query%).
    На пусто-результат возвращаем дружелюбное сообщение, иначе — inline-клавиатуру
    с кнопками-сотрудниками.
    """
    lang = language

    # Проверяем права доступа (тот же check, что и на старте)
    if not has_admin_access(roles=roles, user=user):
        await message.answer(get_text('errors.permission_denied', language=lang))
        await state.clear()
        return

    raw_query = (message.text or "").strip()
    if not raw_query:
        await message.answer(get_text('employee_management.search_empty_query', language=lang))
        return

    try:
        employees = await run_db(lambda s: _search_employees(s, raw_query), db=_db)

        if not employees:
            await message.answer(
                get_text('employee_management.search_not_found', language=lang),
                reply_markup=get_cancel_keyboard(lang)
            )
            await state.clear()
            return

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        rows = []
        for emp in employees:
            label = _format_employee_name(emp)
            rows.append([
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"employee_view_{emp.id}"
                )
            ])
        rows.append([
            InlineKeyboardButton(
                text=get_text('buttons.cancel', language=lang),
                callback_data="employee_management_panel"
            )
        ])

        await message.answer(
            get_text('employee_management.search_results_header', language=lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка поиска сотрудников: {e}")
        await message.answer(get_text('errors.unknown_error', language=lang))
        await state.clear()


# ═══ УПРАВЛЕНИЕ СПЕЦИАЛИЗАЦИЯМИ ═══

@router.callback_query(F.data == "employee_mgmt_specializations")
async def show_employee_specializations_management(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Показать управление специализациями сотрудников"""
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
        # Получаем детальную статистику по специализациям
        detailed_stats = await run_db(_load_detailed_spec_stats, db=_db)

        # Формируем сообщение со статистикой и списком сотрудников
        message_text = get_text("employee_mgmt.handlers.specialization_stats_title", language=lang) + "\n\n"
        
        if detailed_stats:
            for spec_key, spec_data in detailed_stats.items():
                # Переводим название специализации
                spec_name = get_text(f'specializations.{spec_key}', language=lang)
                count = spec_data['count']
                employees = spec_data['employees']
                
                message_text += get_text("employee_mgmt.handlers.spec_employee_count", language=lang).format(spec_name=spec_name, count=count) + "\n"
                
                # Добавляем список сотрудников
                if employees:
                    for employee in employees:
                        # AUD5-CODE-8: имя через канон вместо инлайн-копии
                        message_text += f"  - {_format_employee_name(employee)}\n"
                else:
                    message_text += f"  - {get_text('employee_mgmt.handlers.no_employees', language=lang)}\n"
                
                message_text += "\n"
        else:
            message_text += get_text("employee_mgmt.handlers.no_specialization_data", language=lang) + "\n"
        
        message_text += get_text("employee_mgmt.handlers.specialization_management_hint", language=lang)
        
        # Кнопка "Назад"
        from uk_management_bot.keyboards.employee_management import get_cancel_keyboard
        await callback.message.edit_text(
            message_text,
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения управления специализациями: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ВЫБОР РОЛЕЙ И СПЕЦИАЛИЗАЦИЙ ═══

@router.callback_query(F.data.startswith("role_toggle_"), EmployeeManagementStates.selecting_roles)
async def toggle_role(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Переключить роль"""
    try:
        role = callback.data.split('_')[-1]
        data = await state.get_data()
        current_roles = data.get('current_roles', [])
        
        if role in current_roles:
            current_roles.remove(role)
        else:
            current_roles.append(role)
        
        await state.update_data(current_roles=current_roles)
        
        # Обновляем клавиатуру
        from uk_management_bot.keyboards.employee_management import get_roles_management_keyboard
        lang = language
        
        await callback.message.edit_reply_markup(
            reply_markup=get_roles_management_keyboard(current_roles, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка переключения роли: {e}")
        lang = language
        await callback.answer(get_text("employee_mgmt.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "role_save", EmployeeManagementStates.selecting_roles)
async def save_employee_roles(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Сохранить роли сотрудника"""
    try:
        data = await state.get_data()
        original_roles = data.get('original_roles', [])
        current_roles = data.get('current_roles', [])
        
        # Проверяем, изменились ли роли
        if set(original_roles) == set(current_roles):
            lang = language
            await callback.answer(get_text("employee_mgmt.handlers.roles_not_changed", language=lang), show_alert=True)
            await state.clear()
            return
        
        # Запрашиваем комментарий
        await state.update_data({'action': 'roles_change'})
        await state.set_state(EmployeeManagementStates.waiting_for_role_comment)
        
        lang = language
        await callback.message.edit_text(
            get_text('moderation.enter_role_change_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения ролей: {e}")
        lang = language
        await callback.answer(get_text("employee_mgmt.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "role_cancel", EmployeeManagementStates.selecting_roles)
async def cancel_roles_editing(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Отменить редактирование ролей"""
    try:
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')

        await state.clear()

        # Возвращаемся к информации о сотруднике (render-only helper не отвечает
        # на callback — отвечаем здесь ровно один раз).
        rendered = await _return_to_employee_info(callback, target_employee_id, language, _db=_db)
        if rendered:
            await callback.answer()
        else:
            await callback.answer(get_text('errors.user_not_found', language=language), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка отмены редактирования ролей: {e}")
        lang = language
        await callback.answer(get_text("employee_mgmt.handlers.error_occurred", language=lang), show_alert=True)


@router.message(EmployeeManagementStates.waiting_for_role_comment)
async def process_role_change_comment(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработать комментарий для изменения ролей"""
    try:
        comment = message.text
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')
        current_roles = data.get('current_roles', [])

        # Запрет снятия последней роли (паритет с AuthService.remove_role):
        # roles=[] недопустимо — у пользователя всегда должна быть хотя бы одна роль.
        if not current_roles:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.cannot_remove_last_role", language=lang))
            await state.clear()
            return

        logger.debug(f" Обработка комментария ролей. target_employee_id={target_employee_id}, current_roles={current_roles}")

        outcome = await run_db(
            lambda s: _apply_role_change(
                s, message.from_user.id, target_employee_id, current_roles, comment),
            db=_db)
        if outcome == "no_actor":
            logger.error(f"User not found: telegram_id={message.from_user.id}")
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.user_not_found_error", language=lang))
            await state.clear()
            return
        if outcome == "no_target":
            logger.error(f"Employee not found: ID {target_employee_id}")
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.employee_not_found", language=lang))
            await state.clear()
            return

        logger.debug(" Роли успешно обновлены и сохранены")
        await state.clear()

        lang = language
        no_roles_text = get_text("employee_mgmt.handlers.no_roles", language=lang)
        await message.answer(
            get_text("employee_mgmt.handlers.roles_updated", language=lang).format(
                roles=', '.join(current_roles) if current_roles else no_roles_text
            )
        )

    except Exception as e:
        logger.error(f"Error processing role change comment: {e}")
        lang = language
        await message.answer(get_text("employee_mgmt.handlers.error_updating_roles", language=lang))
        await state.clear()


@router.callback_query(F.data.startswith("spec_toggle_"), EmployeeManagementStates.selecting_specializations)
async def toggle_specialization(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Переключить специализацию"""
    try:
        specialization = callback.data.split('_')[-1]
        data = await state.get_data()
        current_specializations = data.get('current_specializations', [])
        
        if specialization in current_specializations:
            current_specializations.remove(specialization)
        else:
            current_specializations.append(specialization)
        
        await state.update_data(current_specializations=current_specializations)
        
        # Обновляем клавиатуру
        from uk_management_bot.keyboards.employee_management import get_specializations_selection_keyboard
        lang = language
        
        await callback.message.edit_reply_markup(
            reply_markup=get_specializations_selection_keyboard(current_specializations, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка переключения специализации: {e}")
        lang = language
        await callback.answer(get_text("employee_mgmt.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "spec_save", EmployeeManagementStates.selecting_specializations)
async def save_employee_specializations(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Сохранить специализации сотрудника"""
    try:
        data = await state.get_data()
        original_specializations = data.get('original_specializations', [])
        current_specializations = data.get('current_specializations', [])
        
        # Проверяем, изменились ли специализации
        if set(original_specializations) == set(current_specializations):
            lang = language
            await callback.answer(get_text("employee_mgmt.handlers.specializations_not_changed", language=lang), show_alert=True)
            await state.clear()
            return
        
        # Запрашиваем комментарий
        await state.update_data({'action': 'specializations_change'})
        await state.set_state(EmployeeManagementStates.waiting_for_specialization_comment)
        
        lang = language
        await callback.message.edit_text(
            get_text('moderation.enter_specialization_change_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения специализаций: {e}")
        lang = language
        await callback.answer(get_text("employee_mgmt.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data == "spec_cancel", EmployeeManagementStates.selecting_specializations)
async def cancel_specializations_editing(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Отменить редактирование специализаций"""
    try:
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')

        await state.clear()

        # Возвращаемся к информации о сотруднике (render-only helper не отвечает
        # на callback — отвечаем здесь ровно один раз).
        rendered = await _return_to_employee_info(callback, target_employee_id, language, _db=_db)
        if rendered:
            await callback.answer()
        else:
            await callback.answer(get_text('errors.user_not_found', language=language), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка отмены редактирования специализаций: {e}")
        lang = language
        await callback.answer(get_text("employee_mgmt.handlers.error_occurred", language=lang), show_alert=True)


@router.message(EmployeeManagementStates.waiting_for_specialization_comment)
async def process_specialization_change_comment(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработать комментарий для изменения специализаций"""
    try:
        comment = message.text
        data = await state.get_data()
        target_employee_id = data.get('target_employee_id')
        current_specializations = data.get('current_specializations', [])

        outcome = await run_db(
            lambda s: _apply_specialization_change(
                s, message.from_user.id, target_employee_id, current_specializations, comment),
            db=_db)
        if outcome == "no_actor":
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.user_not_found_error", language=lang))
            await state.clear()
            return

        await state.clear()

        if outcome == "ok":
            lang = language
            no_specs_text = get_text("employee_mgmt.handlers.no_specializations", language=lang)
            await message.answer(
                get_text("employee_mgmt.handlers.specializations_updated", language=lang).format(
                    specializations=', '.join(current_specializations) if current_specializations else no_specs_text
                )
            )
        else:
            lang = language
            await message.answer(get_text("employee_mgmt.handlers.error_saving_specializations", language=lang))

    except Exception as e:
        logger.error(f"Ошибка обработки комментария специализаций: {e}")
        lang = language
        await message.answer(get_text("employee_mgmt.handlers.error_updating_specializations", language=lang))
        await state.clear()


# ═══ НАВИГАЦИЯ ═══

@router.callback_query(F.data == "no_action")
async def no_action_handler(callback: CallbackQuery, language: str = "ru"):
    """Обработчик для кнопок без действия"""
    await callback.answer()


@router.callback_query(F.data == "admin_panel")
async def back_to_admin_panel(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Вернуться к админ панели"""
    lang = language
    
    try:
        from uk_management_bot.keyboards.admin import get_manager_main_keyboard
        
        await callback.message.edit_text(
            get_text('admin.panel_title', language=lang),
            reply_markup=get_manager_main_keyboard(language=lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к админ панели: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )
