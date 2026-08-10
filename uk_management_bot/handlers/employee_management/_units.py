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

AUD5-ARCH-3 (волна 1): файл — часть пакета ``employee_management`` (разбит
god-файл); здесь живут DTO, sync-юниты и render-хелпер
``_return_to_employee_info``, хендлеры — в соседних под-модулях.
"""

import logging

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from aiogram.types import CallbackQuery
from sqlalchemy.orm import Session

from uk_management_bot.database.session import run_db

from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.specialization_service import SpecializationService
from uk_management_bot.keyboards.employee_management import (
    get_employee_actions_keyboard,
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import sync_legacy_role, parse_roles_safe
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
