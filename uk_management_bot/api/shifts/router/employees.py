"""AUD5-ARCH-3 волна 8 (block-move из api/shifts/router.py): /employees-маршруты.

Тела перенесены байт-в-байт; порядок регистрации 1:1 с исходником
(`/employees/pending` — до динамического `/employees/{user_id}`).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.shifts import service
from uk_management_bot.api.users.rename import (
    FullNameIn,
    FullNameOut,
    lock_user_for_rename,
    rename_user_http,
)
from uk_management_bot.api.shifts.schemas import (
    EmployeeBrief, EmployeeDetail,
    DeleteEmployeeRequest, ActiveRequestsCount,
    CreateInviteRequest, CreateInviteResponse,
    MeterEntryToggleRequest,
)
from uk_management_bot.database.models.user import User

from ._helpers import _ensure_not_privileged, _resolve_bot_username, _shift_brief
from ._router import router


logger = logging.getLogger(__name__)


class _InviteInputError(Exception):
    """Валидация ввода внутри генерации инвайта — отделена от сбоев конфигурации.

    Нужна, чтобы 422 получал только тот ValueError, который бросила проверка
    входных данных в `InviteService.generate_invite`, а не, скажем, отсутствие
    `INVITE_SECRET` (это 500).
    """


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

@router.get("/employees", response_model=list[EmployeeBrief])
async def list_employees(
    specialization: Optional[str] = Query(None),
    has_active_shift: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    verification_status: Optional[str] = Query(None),
    for_category: Optional[str] = Query(
        None,
        description="Категория заявки: оставить только исполнителей, чья "
                    "специализация её покрывает (джокер universal проходит).",
    ),
    for_specializations: Optional[str] = Query(
        None,
        description="CSV специализаций шаблона смены: оставить только "
                    "исполнителей, покрывающих хотя бы одну (universal — "
                    "джокер; нерезолвимое требование не пропускает никого).",
    ),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    users, active_shifts = await service.list_employees(
        db,
        specialization=specialization,
        has_active_shift=has_active_shift,
        search=search,
        role=role,
        verification_status=verification_status,
        for_category=for_category,
        for_specializations=for_specializations,
        limit=limit,
        offset=offset,
    )

    briefs = []
    for u in users:
        # Inject active_shift_id into the object so model_validator can see it
        u.__dict__['active_shift_id'] = active_shifts.get(u.id)
        briefs.append(EmployeeBrief.model_validate(u))
    return briefs


@router.get("/employees/pending", response_model=list[EmployeeBrief])
async def list_pending_staff(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    """Сотрудники (manager/executor/inspector), ожидающие активации аккаунта.

    Объявлен ВЫШЕ динамического `GET /employees/{user_id}`, иначе `pending`
    захватился бы как `{user_id}` и упал на парсинге int.
    """
    users = await service.list_pending_staff(db)
    briefs = []
    for u in users:
        u.__dict__['active_shift_id'] = None
        briefs.append(EmployeeBrief.model_validate(u))
    return briefs


@router.post("/employees/invite", response_model=CreateInviteResponse, status_code=201)
async def create_invite(
    body: CreateInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("manager")),
):
    """Generate an invite token for a new employee to join via the Telegram bot."""
    import asyncio
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.services.invite_service import InviteService, requires_specialization
    from datetime import timedelta

    spec_str = ",".join(body.specializations) if body.specializations else None

    # Ошибка ВВОДА, а не сбой: без этого гварда пустой список специализаций у
    # executor'а долетал до InviteService, тот бросал ValueError, и менеджер
    # получал голый 500 без текста («не работает выдача приглашений», profk
    # 2026-08-17). Проверяем ДО getMe() и БД — незачем ходить в сеть за
    # заведомо невалидный запрос. Условие берём предикатом из сервиса, а не
    # переписываем: два экземпляра правила разъехались бы при его смене.
    if requires_specialization(body.role) and not body.specializations:
        raise HTTPException(
            status_code=422,
            detail="Specialization is required for executor role",
        )

    # Resolve the bot username up front: if it can't be determined we must not
    # generate a token only to hand back a broken https://t.me/None link.
    bot_username = await _resolve_bot_username()
    if not bot_username:
        raise HTTPException(
            status_code=503,
            detail="Bot username unavailable — set BOT_USERNAME in the API environment.",
        )

    def _generate():
        sync_db = SessionLocal()
        try:
            # Конструктор бросает ValueError при незаданном INVITE_SECRET — это
            # сбой конфигурации, а НЕ ошибка ввода: он должен остаться 500 и не
            # уехать клиенту вместе с именем переменной окружения. Поэтому в
            # 422 переводится только валидация самой генерации (ниже).
            svc = InviteService(sync_db)
            try:
                return svc.generate_invite(
                    role=body.role,
                    created_by=current_user.telegram_id,
                    specialization=spec_str,
                    hours=body.hours,
                )
            except ValueError as exc:
                raise _InviteInputError(str(exc)) from exc
        finally:
            sync_db.close()

    loop = asyncio.get_running_loop()
    try:
        token = await loop.run_in_executor(None, _generate)
    except _InviteInputError as exc:
        # Валидация сервиса — 422, а не 500: иначе любая будущая проверка в
        # InviteService снова обернётся для менеджера «упало без причины».
        # Текст исключения НЕ пересылаем клиенту: это generic-перехват, и
        # будущая проверка может положить в сообщение внутреннее состояние.
        # Внятная формулировка есть у известного случая — в гварде выше.
        logger.warning("Инвайт отклонён валидацией сервиса: %s", exc)
        raise HTTPException(status_code=422, detail="Invalid invite parameters") from exc

    expires_at = datetime.now(timezone.utc) + timedelta(hours=body.hours)

    return CreateInviteResponse(
        token=token,
        bot_link=f"https://t.me/{bot_username}",
        expires_at=expires_at,
    )


@router.patch("/employees/{user_id}/approve", dependencies=[Depends(require_roles("manager"))])
async def approve_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Approve a pending user (set verification_status = 'verified')"""
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_not_privileged(user, action="Cannot modify status of a manager or admin user")
    if user.verification_status == "verified":
        raise HTTPException(status_code=409, detail="User is already verified")
    if user.verification_status == "rejected":
        raise HTTPException(status_code=409, detail="User was rejected and cannot be re-approved this way")
    await service.set_user_verification(db, user, "verified")
    return {"id": user.id, "verification_status": user.verification_status}


@router.patch("/employees/{user_id}/reject", dependencies=[Depends(require_roles("manager"))])
async def reject_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Reject a pending user (set verification_status = 'rejected')"""
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_not_privileged(user, action="Cannot modify status of a manager or admin user")
    if user.verification_status == "rejected":
        raise HTTPException(status_code=409, detail="User is already rejected")
    await service.set_user_verification(db, user, "rejected")
    return {"id": user.id, "verification_status": user.verification_status}


@router.patch("/employees/{user_id}/block", dependencies=[Depends(require_roles("manager"))])
async def block_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Block an employee — sets status='blocked', preventing system access."""
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_not_privileged(user, action="Cannot modify status of a manager or admin user")
    if user.status == "blocked":
        raise HTTPException(status_code=409, detail="User is already blocked")
    await service.set_user_status(db, user, "blocked")
    return {"message": "blocked"}


@router.patch("/employees/{user_id}/unblock", dependencies=[Depends(require_roles("manager"))])
async def unblock_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Unblock an employee — sets status back to 'approved'."""
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_not_privileged(user, action="Cannot modify status of a manager or admin user")
    if user.status != "blocked":
        raise HTTPException(status_code=409, detail="User is not blocked")
    await service.set_user_status(db, user, "approved")
    return {"message": "unblocked"}


@router.patch("/employees/{user_id}/activate", dependencies=[Depends(require_roles("manager"))])
async def activate_staff(user_id: int, db: AsyncSession = Depends(get_db)):
    """Активировать pending-СТАФФ аккаунт (status='approved'). Допускает менеджеров.

    Отличается от `/approve` (тот ставит verification_status и запрещает
    менеджеров): здесь активируется account-гейт, который проверяет бот.
    Ограничено стафф-ролями в статусе pending — жителей и уже активных
    менеджеров не трогает (НЕ применяем `_ensure_not_privileged` намеренно).
    """
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not service._is_staff(user):
        raise HTTPException(status_code=422, detail="Not a staff account (manager/executor/inspector)")
    if user.status != "pending":
        raise HTTPException(status_code=409, detail="User is not pending activation")
    await service.activate_employee(db, user)
    return {"id": user.id, "status": user.status, "active_role": user.active_role}


@router.patch("/employees/{user_id}/decline", dependencies=[Depends(require_roles("manager"))])
async def decline_staff(user_id: int, db: AsyncSession = Depends(get_db)):
    """Отклонить pending-СТАФФ заявку (status='blocked'). Те же guard'ы, что activate."""
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not service._is_staff(user):
        raise HTTPException(status_code=422, detail="Not a staff account (manager/executor/inspector)")
    if user.status != "pending":
        raise HTTPException(status_code=409, detail="User is not pending")
    await service.decline_employee(db, user)
    return {"id": user.id, "status": user.status}


@router.patch("/employees/{user_id}/name", response_model=FullNameOut)
async def rename_employee(
    user_id: int,
    body: FullNameIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("manager")),
):
    """Исправить ФИО сотрудника."""
    # Однострочно намеренно — докстринг попадает в публичный OpenAPI.
    #
    # `_ensure_not_privileged` здесь не вызывается напрямую: тот же запрет на
    # менеджеров и админов живёт в `services/users/rename.py` — иначе его
    # пришлось бы дублировать во второй точке входа (карточка жителя), и они бы
    # разошлись.
    user = await lock_user_for_rename(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await rename_user_http(db, user, body.full_name, actor_id=actor.id)


@router.patch("/employees/{user_id}/meter-entry", dependencies=[Depends(require_roles("manager"))])
async def toggle_meter_entry(
    user_id: int,
    body: MeterEntryToggleRequest,
    db: AsyncSession = Depends(get_db),
):
    """Выдать/снять роль контролёра показаний (resource_meter_entry) сотруднику.

    Капабилити для Mini App «Ввод показаний» — даёт доступ к вводу показаний в
    «Учёт ресурсов». Идемпотентна; НЕ трогает active_role.
    """
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await service.set_meter_entry_role(db, user, body.enabled)
    return {"id": user.id, "meter_entry": body.enabled}


@router.get("/employees/{user_id}/active-requests-count", response_model=ActiveRequestsCount)
async def get_active_requests_count(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    """Return number of active requests assigned to this employee."""
    count = await service.count_active_requests(db, user_id)
    return ActiveRequestsCount(count=count)


@router.patch("/employees/{user_id}/delete")
async def delete_employee(
    user_id: int,
    body: DeleteEmployeeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("manager")),
):
    """Soft-delete an employee, optionally reassigning their active requests."""
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _ensure_not_privileged(user, action="Cannot delete a manager or admin user")

    if user.deleted_at is not None:
        raise HTTPException(status_code=409, detail="User is already deleted")

    active_count = await service.count_active_requests(db, user_id)

    if active_count > 0 and body.reassign_to is None:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Employee has active requests that must be reassigned",
                "active_requests_count": active_count,
            },
        )

    if body.reassign_to is not None and active_count > 0:
        target_user = await service.get_user(db, body.reassign_to)
        if not target_user:
            raise HTTPException(status_code=404, detail="Target employee not found")
        if target_user.deleted_at is not None:
            raise HTTPException(status_code=422, detail="Cannot reassign to a deleted employee")

    await service.soft_delete_employee(
        db,
        user=user,
        reassign_to=body.reassign_to,
        reason=body.reason,
        deleted_by_id=current_user.id,
        active_count=active_count,
    )
    return {"message": "deleted", "reassigned_requests": active_count if body.reassign_to else 0}


@router.get("/employees/{user_id}", response_model=EmployeeDetail)
async def get_employee(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    data = await service.get_employee_with_stats(db, user_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp, active_shift_obj, total_shifts, total_completed, rating = data

    active_shift_brief = _shift_brief(active_shift_obj) if active_shift_obj else None

    emp.__dict__['active_shift_id'] = active_shift_obj.id if active_shift_obj else None
    brief = EmployeeBrief.model_validate(emp)

    return EmployeeDetail(
        **brief.model_dump(),
        active_shift=active_shift_brief,
        rating=rating,
        total_shifts=total_shifts,
        total_completed=total_completed,
    )
