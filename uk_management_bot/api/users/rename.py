"""HTTP-обвязка исправления ФИО — общая для «Жителей» и «Сотрудников».

Точки входа две (`/residents/{id}/name` и `/shifts/employees/{id}/name`), и
разъехаться они не должны: право, валидация и коды ответов заданы здесь один
раз. Новый префикс `/api/v2/users` намеренно НЕ заводится — публичный edge
InfraSafe пропускает `/uk/api/*` по allowlist'у префиксов, и неизвестный дал бы
404 на проде до правки на их стороне.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from uk_management_bot.database.models.user import User
from uk_management_bot.services.users.rename import (
    RenameForbidden,
    RenamePlan,
    apply_rename,
    ensure_renamable,
    plan_rename,
)
from uk_management_bot.utils.person_name import MAX_FULL_NAME_LEN, InvalidFullName

#: Повод отказа → текст для менеджера. Ключи — `InvalidFullName.code`;
#: неизвестный код превратился бы в KeyError-500, поэтому есть фолбэк.
_INVALID_MESSAGES = {
    "empty": "ФИО не может быть пустым",
    "no_letters": "ФИО должно содержать хотя бы одну букву",
    "too_long": f"ФИО не длиннее {MAX_FULL_NAME_LEN} символов",
}


class FullNameIn(BaseModel):
    """Новое ФИО одной строкой."""

    # Грубый предел ДО сервиса: нормализация схлопывает пробельное, поэтому
    # исходная строка законно длиннее итоговой — но не в разы.
    full_name: str = Field(..., max_length=MAX_FULL_NAME_LEN * 4)


class FullNameOut(BaseModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: str


async def lock_user_for_rename(db, user_id: int) -> Optional[User]:
    """Строка `users` под `FOR UPDATE` с перечиткой, либо None.

    Лок нужен не ради самой записи (UPDATE двух колонок атомарен), а ради
    строки аудита: без него `old_full_name` берётся из состояния, которое
    параллельный менеджер мог уже заменить, и журнал покажет замену того, чего
    в тот момент уже не было. `populate_existing` обязателен — при уже
    загруженном в identity map объекте иначе вернутся старые атрибуты.
    """
    return (await db.execute(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()


async def rename_user_http(db, target, raw_full_name: str, *, actor_id: int) -> FullNameOut:
    """Guard → валидация → запись → commit, с маппингом отказов в HTTP.

    Идемпотентно: то же ФИО = 200 без записи и без строки аудита (решение
    принимает `apply_rename`).
    """
    try:
        ensure_renamable(target)
    except RenameForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    try:
        plan: RenamePlan = plan_rename(target, raw_full_name)
    except InvalidFullName as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_INVALID_MESSAGES.get(exc.code, "Некорректное ФИО"),
        ) from exc

    # id снимается ДО записи: ответ не должен зависеть от того, истекают ли
    # атрибуты на commit (`expire_on_commit` задан в другом модуле, и его смена
    # превратила бы чтение `target.id` здесь в отложенный запрос из async-кода).
    target_id = target.id

    if apply_rename(db, target, plan, actor_id=actor_id):
        await db.commit()

    return FullNameOut(
        id=target_id,
        first_name=plan.first_name,
        last_name=plan.last_name,
        full_name=plan.new_full_name,
    )
