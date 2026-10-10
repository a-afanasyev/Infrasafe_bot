"""Админка ролей: роли, их права и роли сотрудников.

Кто что может здесь:

* смотреть — действие `rbac.view` (по умолчанию менеджер) и суперадмин;
* менять — только суперадмин (`rbac.manage`, telegram_id в ADMIN_USER_IDS).

Адрес — `/api/v2/shifts/employees/...`, а не отдельный `/api/v2/rbac`: публичный
edge обеих площадок пропускает в API только заявленные префиксы, и этот уже
открыт (там же живёт раздел «Сотрудники»). Новый префикс требовал бы заявки
владельцу edge до выкатки. Роутер подключается в `api/main.py` ДО роутера
смен — иначе `/employees/rbac/...` перехватил бы маршрут `/employees/{user_id}`.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.rbac import service as svc
from uk_management_bot.api.rbac.schemas import (
    ActionOut, RoleCreate, RoleOut, RolesOut, RoleUpdate, UserRolesOut, UserRolesUpdate,
)
from uk_management_bot.authz import ACTIONS, is_superadmin
from uk_management_bot.authz.catalog import SYSTEM_ROLES
from uk_management_bot.database.models.rbac import RbacRole
from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

#: Чтение доступно и менеджерам — ограничиваем перебор сотрудников.
READ_LIMIT = "120/minute"


@router.get("/employees/rbac/catalog", response_model=list[ActionOut])
@limiter.limit(READ_LIMIT)
async def get_catalog(request: Request, user: User = Depends(require_action("rbac.view"))):
    """Все действия системы: что можно разрешить роли."""
    return [
        ActionOut(key=key, title=a.title, area=svc.area_of(key), approved_only=a.approved_only,
                  superadmin_only=a.superadmin_only, default_roles=sorted(a.default_roles))
        for key, a in ACTIONS.items()
    ]


@router.get("/employees/rbac/roles", response_model=RolesOut)
@limiter.limit(READ_LIMIT)
async def list_roles(request: Request, db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_action("rbac.view"))):
    """Роли с их текущими правами и числом сотрудников."""
    snapshot = await svc.read_snapshot(db)
    roles = (await db.execute(RbacRole.__table__.select().order_by(
        RbacRole.is_system.desc(), RbacRole.key))).mappings().all()
    counts = await svc.users_count_by_role(db, [row["key"] for row in roles])
    out = []
    for row in roles:
        actions = svc.role_actions(row["key"], snapshot)
        customized = sorted(actions ^ svc.default_actions(row["key"])) if row["is_system"] else []
        out.append(RoleOut(key=row["key"], title=row["title"], description=row["description"],
                           is_system=row["is_system"], actions=sorted(actions), customized=customized,
                           users_count=counts.get(row["key"], 0)))
    return RolesOut(roles=out, can_edit=is_superadmin(user))


@router.post("/employees/rbac/roles", response_model=RoleOut, status_code=201)
@limiter.limit("30/minute")
async def create_role(request: Request, body: RoleCreate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_action("rbac.manage"))):
    """Создать свою роль с набором прав."""
    actions = svc.validate_actions(body.actions)
    await svc.begin_change(db)
    if body.key in SYSTEM_ROLES or await db.get(RbacRole, body.key) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Роль с таким ключом уже есть")
    db.add(RbacRole(key=body.key, title=body.title, description=body.description,
                    is_system=False, updated_by=user.id))
    await db.flush()
    await svc.write_permissions(db, body.key, actions)
    svc.audit(db, user, "rbac.role.created", {"role": body.key, "actions": sorted(actions)})
    await svc.commit_change(db)
    logger.info("RBAC: роль %s создана суперадмином %s", body.key, user.id)
    return RoleOut(key=body.key, title=body.title, description=body.description, is_system=False,
                   actions=sorted(actions))


@router.put("/employees/rbac/roles/{key}", response_model=RoleOut)
@limiter.limit("30/minute")
async def update_role(request: Request, key: str, body: RoleUpdate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_action("rbac.manage"))):
    """Изменить название, описание и/или права роли (системной тоже)."""
    actions = svc.validate_actions(body.actions) if body.actions is not None else None
    await svc.begin_change(db)
    role = await svc.get_role(db, key)
    details: dict = {"role": key}
    if body.title is not None:
        role.title = body.title
    if body.description is not None:
        role.description = body.description
    role.updated_by = user.id
    if actions is not None:
        before = svc.role_actions(key, await svc.read_snapshot(db))
        await svc.write_permissions(db, key, actions)
        details.update(added=sorted(actions - before), removed=sorted(before - actions))
    svc.audit(db, user, "rbac.role.updated", details)
    await svc.commit_change(db)
    snapshot = await svc.read_snapshot(db)
    actions_now = svc.role_actions(key, snapshot)
    return RoleOut(key=key, title=role.title, description=role.description, is_system=role.is_system,
                   actions=sorted(actions_now),
                   customized=sorted(actions_now ^ svc.default_actions(key)) if role.is_system else [])


@router.post("/employees/rbac/roles/{key}/reset", response_model=RoleOut)
@limiter.limit("30/minute")
async def reset_role(request: Request, key: str, db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_action("rbac.manage"))):
    """Вернуть системной роли права «из коробки» (удалить её переопределения)."""
    await svc.begin_change(db)
    role = await svc.get_role(db, key)
    if not role.is_system:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Сбросить можно только системную роль")
    await svc.drop_permissions(db, key)
    svc.audit(db, user, "rbac.role.reset", {"role": key})
    await svc.commit_change(db)
    return RoleOut(key=key, title=role.title, description=role.description, is_system=True,
                   actions=sorted(svc.default_actions(key)))


@router.delete("/employees/rbac/roles/{key}", status_code=204)
@limiter.limit("30/minute")
async def delete_role(request: Request, key: str, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_action("rbac.manage"))):
    """Удалить свою роль. Системные не удаляются; роль с сотрудниками — тоже."""
    await svc.begin_change(db)
    role = await svc.get_role(db, key)
    if role.is_system:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Системную роль удалить нельзя")
    holders = (await svc.users_count_by_role(db, [key]))[key]
    if holders:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Роль выдана сотрудникам: {holders}. Сначала снимите её")
    await svc.drop_permissions(db, key)
    await db.delete(role)
    svc.audit(db, user, "rbac.role.deleted", {"role": key})
    await svc.commit_change(db)


@router.get("/employees/{user_id}/roles", response_model=UserRolesOut)
@limiter.limit(READ_LIMIT)
async def get_user_roles_view(request: Request, user_id: int, db: AsyncSession = Depends(get_db),
                              user: User = Depends(require_action("rbac.view"))):
    """Роли сотрудника. Кто суперадмин — видно только суперадмину."""
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    viewer_is_superadmin = is_superadmin(user)
    return UserRolesOut(user_id=target.id, roles=svc.user_roles_list(target), active_role=target.active_role,
                        is_superadmin=viewer_is_superadmin and is_superadmin(target),
                        can_edit=viewer_is_superadmin)


@router.put("/employees/{user_id}/roles", response_model=UserRolesOut)
@limiter.limit("30/minute")
async def set_user_roles(request: Request, user_id: int, body: UserRolesUpdate,
                         db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_action("rbac.manage"))):
    """Назначить сотруднику роли (полный набор)."""
    # Под блокировкой строки: роли пишут и другие эндпоинты (капабилити
    # контролёра в карточке) — без неё одна правка молча затёрла бы другую.
    target = await db.get(User, user_id, with_for_update=True, populate_existing=True)
    if target is None or target.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    unknown = set(body.roles) - await svc.known_role_keys(db)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Неизвестные роли: {sorted(unknown)}")
    if not set(body.roles) & SYSTEM_ROLES:
        # Меню бота и режимы строятся по системным ролям; одна своя роль
        # оставила бы человека без меню.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Нужна хотя бы одна системная роль (своя роль выдаётся вместе с ней)")
    before = svc.user_roles_list(target)
    active = svc.apply_user_roles(target, body.roles)
    svc.audit(db, user, "rbac.user_roles.changed",
              {"target_user_id": target.id, "before": before, "after": list(dict.fromkeys(body.roles))})
    await db.commit()
    logger.info("RBAC: роли пользователя %s изменены суперадмином %s", target.id, user.id)
    return UserRolesOut(user_id=target.id, roles=svc.user_roles_list(target), active_role=active,
                        is_superadmin=is_superadmin(target), can_edit=True)
