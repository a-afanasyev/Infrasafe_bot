# TWA Phase 1: Backend Preparation — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подготовить API для TWA — data isolation, executor actions, shift endpoints, role switch, auth flow.

**Architecture:** Расширение существующего FastAPI API новыми dependencies (access check, shift-gate), executor shift router, role switch endpoint. Без breaking changes для дашборда — manager endpoints остаются без изменений.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 async, PostgreSQL 15

**Source spec:** `docs/superpowers/specs/2026-03-29-twa-redesign-design.md` (sections 6.1—6.7)

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `uk_management_bot/api/dependencies_access.py` | `check_request_access()`, `filter_requests_by_role()`, `require_active_shift()` |
| Create | `uk_management_bot/api/shifts/executor_router.py` | Executor shift endpoints: `/me`, `/current`, `/start`, `/{id}/end` |
| Create | `uk_management_bot/tests/test_api_access.py` | Unit tests for access check dependencies |
| Modify | `uk_management_bot/api/requests/router.py` | Add access checks, executor PATCH support |
| Modify | `uk_management_bot/api/profile/router.py` | Add `PATCH /role` endpoint |
| Modify | `uk_management_bot/api/main.py` | Register executor_shifts_router |

---

### Task 1: Access check dependencies

**Files:**
- Create: `uk_management_bot/api/dependencies_access.py`
- Create: `uk_management_bot/tests/test_api_access.py`

**Spec ref:** 6.1 (data isolation), 6.6 (shift-gate)

- [ ] **Step 1: Create dependencies_access.py with check_request_access()**

```python
"""Access control dependencies for TWA-safe API endpoints."""
import json
import logging
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from uk_management_bot.api.dependencies import get_db, get_current_user, _parse_user_roles
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.shift import Shift

logger = logging.getLogger(__name__)


async def check_request_access(
    request_number: str,
    db: AsyncSession,
    user: User,
) -> Request:
    """Check user has access to a specific request. Returns request or raises 403.

    Access rules:
    - Owner (request.user_id == user.id): always
    - Apartment resident: only if request.status == 'Исполнено' (acceptance flow)
    - Executor (via RequestAssignment OR request.executor_id): always
    - Manager: always
    """
    result = await db.execute(
        select(Request).where(Request.request_number == request_number)
    )
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    roles = _parse_user_roles(user)

    # Manager — full access
    if "manager" in roles:
        return request

    # Owner — full access
    if request.user_id == user.id:
        return request

    # Executor — via RequestAssignment or executor_id
    if "executor" in roles:
        if request.executor_id == user.id:
            return request
        assignment = await db.execute(
            select(RequestAssignment).where(
                RequestAssignment.request_number == request_number,
                RequestAssignment.executor_id == user.id,
                RequestAssignment.status == "active",
            )
        )
        if assignment.scalar_one_or_none():
            return request

    # Apartment resident — only for acceptance (status == Исполнено)
    if request.apartment_id and request.status == "Исполнено":
        resident = await db.execute(
            select(UserApartment).where(
                UserApartment.user_id == user.id,
                UserApartment.apartment_id == request.apartment_id,
                UserApartment.status == "approved",
            )
        )
        if resident.scalar_one_or_none():
            return request

    raise HTTPException(status_code=403, detail="Access denied")


async def require_active_shift(
    db: AsyncSession,
    user: User,
) -> Shift:
    """Require executor to have an active shift. Returns shift or raises 403.

    Used as shift-gate for executor actions (status changes, group assignments).
    """
    result = await db.execute(
        select(Shift).where(
            Shift.user_id == user.id,
            Shift.status == "active",
        )
    )
    shift = result.scalar_one_or_none()
    if not shift:
        raise HTTPException(
            status_code=403,
            detail="Active shift required. Start a shift first.",
        )
    return shift


def is_assigned_executor(request: Request, user: User, assignments: list) -> bool:
    """Check if user is assigned executor (via RequestAssignment OR executor_id fallback)."""
    if request.executor_id == user.id:
        return True
    return any(
        a.executor_id == user.id and a.status == "active"
        for a in assignments
    )
```

- [ ] **Step 2: Verify file syntax**

Run: `docker exec uk-management-api python -c "from uk_management_bot.api.dependencies_access import check_request_access, require_active_shift; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add uk_management_bot/api/dependencies_access.py
git commit -m "feat(api): add access control dependencies for TWA (check_request_access, require_active_shift)"
```

---

### Task 2: Wire access checks into request endpoints

**Files:**
- Modify: `uk_management_bot/api/requests/router.py`

**Spec ref:** 6.1 (data isolation), 6.2 (executor actions)

- [ ] **Step 1: Add access check to GET /requests/{request_number}**

In `get_request()`, replace direct query with `check_request_access()`:

```python
from uk_management_bot.api.dependencies_access import check_request_access

# BEFORE (around line 112):
# result = await db.execute(select(Request).where(...))
# request = result.scalar_one_or_none()

# AFTER:
request = await check_request_access(request_number, db, user)
```

- [ ] **Step 2: Add access check to GET/POST comments**

In `get_comments()` and `add_comment()`, add access check before fetching comments.

- [ ] **Step 3: Expand PATCH /requests/{number} for executor role**

In `update_request()`, after the manager check, add executor path:

```python
roles = _parse_user_roles(user)
if "executor" in roles and "manager" not in roles:
    # Executor: check assignment (RequestAssignment OR executor_id)
    from uk_management_bot.api.dependencies_access import is_assigned_executor, require_active_shift
    assignments_result = await db.execute(
        select(RequestAssignment).where(
            RequestAssignment.request_number == request_number,
        )
    )
    assignments = assignments_result.scalars().all()
    if not is_assigned_executor(request, user, assignments):
        raise HTTPException(status_code=403, detail="Not assigned to this request")
    # Require active shift for status changes
    if body.status:
        await require_active_shift(db, user)
        # Executor allowed transitions
        executor_transitions = {
            "Новая": {"В работе"},
            "В работе": {"Закуп", "Уточнение", "Выполнена"},
            "Закуп": {"В работе"},
            "Уточнение": {"В работе"},
        }
        allowed = executor_transitions.get(request.status, set())
        if body.status not in allowed:
            raise HTTPException(status_code=422, detail=f"Executor cannot transition from '{request.status}' to '{body.status}'")
    # Executor can update: status, completion_report, requested_materials
    allowed_fields = {"status", "completion_report", "requested_materials", "notes"}
    update_data = body.model_dump(exclude_unset=True)
    for field in list(update_data.keys()):
        if field not in allowed_fields:
            del update_data[field]
```

- [ ] **Step 4: Add GET /requests/acceptance endpoint**

New endpoint for applicant acceptance (own + apartment neighbors, status Исполнено only):

```python
@router.get("/acceptance", response_model=list[RequestCard])
async def get_acceptance_requests(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Requests pending acceptance: own + apartment neighbors, status=Исполнено."""
    # Get user's apartment IDs
    from uk_management_bot.database.models.user_apartment import UserApartment
    apt_result = await db.execute(
        select(UserApartment.apartment_id).where(
            UserApartment.user_id == user.id,
            UserApartment.status == "approved",
        )
    )
    apt_ids = [row[0] for row in apt_result.all()]

    conditions = [Request.user_id == user.id]
    if apt_ids:
        conditions.append(Request.apartment_id.in_(apt_ids))

    result = await db.execute(
        select(Request).where(
            or_(*conditions),
            Request.status == "Исполнено",
        ).order_by(Request.updated_at.desc()).limit(20)
    )
    requests = result.scalars().all()
    return [_request_to_card(r) for r in requests]
```

- [ ] **Step 5: Rebuild, run tests, verify**

Run: `docker compose build api && docker compose up -d api`
Run: `docker exec uk-management-api python -m pytest uk_management_bot/tests/ -q`

- [ ] **Step 6: Commit**

```bash
git add uk_management_bot/api/requests/router.py
git commit -m "feat(api): add data isolation + executor PATCH + acceptance endpoint"
```

---

### Task 3: Executor shift endpoints

**Files:**
- Create: `uk_management_bot/api/shifts/executor_router.py`
- Modify: `uk_management_bot/api/main.py`

**Spec ref:** 6.5 (executor shift API)

- [ ] **Step 1: Create executor_router.py**

```python
"""Executor-scoped shift endpoints for TWA."""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from uk_management_bot.api.dependencies import get_db, get_current_user, require_roles
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()


class ShiftOut(BaseModel):
    id: int
    user_id: int
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    status: str
    notes: Optional[str] = None
    specialization_focus: Optional[list[str]] = None
    model_config = {"from_attributes": True}

    @classmethod
    def from_shift(cls, s: Shift) -> "ShiftOut":
        return cls(
            id=s.id, user_id=s.user_id,
            start_time=s.start_time.isoformat() if s.start_time else None,
            end_time=s.end_time.isoformat() if s.end_time else None,
            status=s.status, notes=s.notes,
            specialization_focus=s.specialization_focus if isinstance(s.specialization_focus, list) else None,
        )


class StartShiftBody(BaseModel):
    notes: Optional[str] = None


@router.get("/current", response_model=Optional[ShiftOut])
async def get_current_shift(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("executor")),
):
    result = await db.execute(
        select(Shift).where(Shift.user_id == user.id, Shift.status == "active")
    )
    shift = result.scalar_one_or_none()
    return ShiftOut.from_shift(shift) if shift else None


@router.get("/me", response_model=list[ShiftOut])
async def get_my_shifts(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("executor")),
):
    result = await db.execute(
        select(Shift).where(Shift.user_id == user.id)
        .order_by(Shift.start_time.desc()).limit(limit)
    )
    return [ShiftOut.from_shift(s) for s in result.scalars().all()]


@router.post("/start", response_model=ShiftOut, status_code=201)
async def start_shift(
    body: StartShiftBody = StartShiftBody(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("executor")),
):
    shift = Shift(
        user_id=user.id,
        start_time=datetime.now(timezone.utc),
        status="active",
        notes=body.notes,
    )
    db.add(shift)
    await db.commit()
    await db.refresh(shift)
    logger.info("Executor %d started shift %d", user.id, shift.id)
    return ShiftOut.from_shift(shift)


@router.post("/{shift_id}/end", response_model=ShiftOut)
async def end_shift(
    shift_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("executor")),
):
    result = await db.execute(
        select(Shift).where(Shift.id == shift_id, Shift.user_id == user.id)
    )
    shift = result.scalar_one_or_none()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    if shift.status != "active":
        raise HTTPException(status_code=422, detail="Shift is not active")

    shift.end_time = datetime.now(timezone.utc)
    shift.status = "completed"
    await db.commit()
    await db.refresh(shift)
    logger.info("Executor %d ended shift %d", user.id, shift.id)
    return ShiftOut.from_shift(shift)
```

- [ ] **Step 2: Register in main.py**

Add to `uk_management_bot/api/main.py`:

```python
from uk_management_bot.api.shifts.executor_router import router as executor_shifts_router
app.include_router(executor_shifts_router, prefix="/api/v2/executor/shifts", tags=["executor-shifts"])
```

- [ ] **Step 3: Rebuild and verify**

Run: `docker compose build api && docker compose up -d api`
Run: `curl -s http://localhost:8085/api/v2/executor/shifts/current -H "Authorization: Bearer $TOKEN"` (should return null or shift)

- [ ] **Step 4: Commit**

```bash
git add uk_management_bot/api/shifts/executor_router.py uk_management_bot/api/main.py
git commit -m "feat(api): add executor shift endpoints (start, end, current, me)"
```

---

### Task 4: Profile role switch endpoint

**Files:**
- Modify: `uk_management_bot/api/profile/router.py`

**Spec ref:** 6.3 (active_role switch)

- [ ] **Step 1: Add PATCH /role endpoint**

```python
class RoleSwitchBody(BaseModel):
    active_role: str

class RoleSwitchOut(BaseModel):
    active_role: str
    roles: list[str]

@router.patch("/role", response_model=RoleSwitchOut)
async def switch_role(
    body: RoleSwitchBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    roles = _parse_user_roles(user)
    if body.active_role not in roles:
        raise HTTPException(
            status_code=422,
            detail=f"Role '{body.active_role}' not in user roles: {roles}",
        )
    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.active_role = body.active_role
    await db.commit()
    return RoleSwitchOut(active_role=body.active_role, roles=roles)
```

- [ ] **Step 2: Add GET /apartments endpoint**

```python
@router.get("/apartments")
async def get_my_apartments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uk_management_bot.database.models.user_apartment import UserApartment
    from uk_management_bot.database.models.apartment import Apartment
    from uk_management_bot.database.models.building import Building
    from uk_management_bot.database.models.yard import Yard

    result = await db.execute(
        select(Apartment, Building.address, Yard.name)
        .join(UserApartment, UserApartment.apartment_id == Apartment.id)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(UserApartment.user_id == user.id, UserApartment.status == "approved")
    )
    rows = result.all()
    return [
        {
            "apartment_id": apt.id,
            "apartment_number": apt.apartment_number,
            "building_address": bld_addr,
            "yard_name": yard_name,
            "full_address": f"Квартира {apt.apartment_number}, {bld_addr}, ({yard_name})",
        }
        for apt, bld_addr, yard_name in rows
    ]
```

- [ ] **Step 3: Rebuild and verify**

Run: `docker compose build api && docker compose up -d api`

- [ ] **Step 4: Commit**

```bash
git add uk_management_bot/api/profile/router.py
git commit -m "feat(api): add PATCH /profile/role + GET /profile/apartments for TWA"
```

---

### Task 5: Build, test, verify all together

- [ ] **Step 1: Rebuild all**

Run: `docker compose build api && docker compose up -d api`

- [ ] **Step 2: Run all tests**

Run: `docker exec uk-management-api python -m pytest uk_management_bot/tests/ -v`

- [ ] **Step 3: Manual smoke test — acceptance endpoint**

```bash
TOKEN=$(curl -s -X POST http://localhost:8085/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Acceptance requests
curl -s http://localhost:8085/api/v2/requests/acceptance \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Profile apartments
curl -s http://localhost:8085/api/v2/profile/apartments \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Role switch
curl -s -X PATCH http://localhost:8085/api/v2/profile/role \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"active_role":"executor"}' | python3 -m json.tool

# Executor current shift
curl -s http://localhost:8085/api/v2/executor/shifts/current \
  -H "Authorization: Bearer $TOKEN"
```

- [ ] **Step 4: Commit all remaining**

```bash
git add -A
git commit -m "feat(api): TWA Phase 1 backend complete — access control, executor shifts, role switch"
```
