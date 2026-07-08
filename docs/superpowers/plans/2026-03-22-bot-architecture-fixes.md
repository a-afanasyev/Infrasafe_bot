# Bot Architecture Fixes — Implementation Plan

> _Последнее редактирование: 2026-03-23_

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 8 architectural issues discovered during E2E Layer 2 audit and navigation map analysis — from duplicated mappings and missing FSM resets to dead callback handlers.

**Architecture:** Bottom-up — fix foundational issues first (constants, decorator), then higher-level concerns (FSM reset, navigation). Each task is independent and produces a working commit.

**Tech Stack:** Python 3.11, aiogram 3, SQLAlchemy, PostgreSQL, Docker Compose

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `uk_management_bot/constants/categories.py` | Single source of truth for category→specialization mapping |
| Modify | `uk_management_bot/middlewares/auth.py:135-231` | Defensive hardening: add `__signature__` to `require_role` wrapper |
| Modify | `uk_management_bot/handlers/admin.py:118-138, 2628-2652` | Remove inline `category_to_spec` dicts, import from constants |
| Modify | `uk_management_bot/handlers/requests.py:229-249, 2709-2714` | Remove inline `category_to_specialization` dicts, import from constants |
| Modify | `uk_management_bot/handlers/base.py:56` | Add global FSM clear in `/start` handler |
| Modify | `uk_management_bot/handlers/admin.py:422,430` | Encode request_number in `mreq_back` callback_data |
| Create | `tests/test_require_role.py` | Tests for decorator signature preservation |
| Create | `tests/test_category_mapping.py` | Tests for unified mapping |
| Create | `tests/test_start_fsm_reset.py` | Tests for /start FSM reset |

---

## Task 1: Unified Category-to-Specialization Mapping (P1)

**Problem:** `category_to_spec` / `category_to_specialization` dict is copy-pasted in 4 places (admin.py x2, requests.py x2) with different values. BUG-6 required fixing all 4 independently. **Live bug:** `requests.py:2713` maps `"Уборка"` → `"cleaner"` while all other copies map it to `"cleaning"`, causing executor matching failures for cleaning requests via that code path.

**Files:**
- Create: `uk_management_bot/constants/__init__.py`
- Create: `uk_management_bot/constants/categories.py`
- Modify: `uk_management_bot/handlers/admin.py:118-138` (function `auto_assign_request_by_category`)
- Modify: `uk_management_bot/handlers/admin.py:2628-2652` (handler for specific executor assignment)
- Modify: `uk_management_bot/handlers/requests.py:229-249` (function `auto_assign_request_by_category`)
- Modify: `uk_management_bot/handlers/requests.py:2709-2714` (handler `handle_assign_specific_executor`)
- Create: `tests/test_category_mapping.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_category_mapping.py
"""Tests for unified category-to-specialization mapping."""

from uk_management_bot.constants.categories import (
    CATEGORY_TO_SPECIALIZATION,
    get_specialization_for_category,
)


def test_all_internal_keys_present():
    """All 9 internal category keys must map to a specialization."""
    required_keys = [
        "plumbing", "electricity", "landscaping", "cleaning",
        "security", "hvac", "maintenance", "repair", "installation",
    ]
    for key in required_keys:
        assert key in CATEGORY_TO_SPECIALIZATION, f"Missing key: {key}"


def test_legacy_russian_keys_present():
    """Legacy Russian category names must also resolve."""
    legacy_keys = ["Сантехника", "Электрика", "Благоустройство", "Уборка", "Безопасность"]
    for key in legacy_keys:
        assert key in CATEGORY_TO_SPECIALIZATION, f"Missing legacy key: {key}"


def test_plumbing_maps_to_plumber():
    assert CATEGORY_TO_SPECIALIZATION["plumbing"] == "plumber"
    assert CATEGORY_TO_SPECIALIZATION["Сантехника"] == "plumber"


def test_electricity_maps_to_electrician():
    assert CATEGORY_TO_SPECIALIZATION["electricity"] == "electrician"
    assert CATEGORY_TO_SPECIALIZATION["Электрика"] == "electrician"


def test_get_specialization_fallback():
    """Unknown category returns 'other'."""
    assert get_specialization_for_category("unknown_cat") == "other"


def test_get_specialization_for_known():
    assert get_specialization_for_category("plumbing") == "plumber"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/andreyafanasyev/Code/UK && python -m pytest tests/test_category_mapping.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uk_management_bot.constants'`

- [ ] **Step 3: Create constants module**

```python
# uk_management_bot/constants/__init__.py
"""Shared constants for the UK Management Bot."""
```

```python
# uk_management_bot/constants/categories.py
"""
Single source of truth: category → specialization mapping.

Used by:
- admin.py: auto_assign_request_by_category, assign specific executor
- requests.py: auto_assign_request_by_category, assign specific executor
"""

CATEGORY_TO_SPECIALIZATION: dict[str, str] = {
    # Internal keys (new format)
    "plumbing": "plumber",
    "electricity": "electrician",
    "landscaping": "landscaping",
    "cleaning": "cleaning",
    "security": "security",
    "hvac": "hvac",
    "maintenance": "maintenance",
    "repair": "repair",
    "installation": "installation",
    # Legacy Russian names (backward compatibility)
    "Сантехника": "plumber",
    "Электрика": "electrician",
    "Благоустройство": "landscaping",
    "Уборка": "cleaning",
    "Безопасность": "security",
    "Охрана": "security",
    "Ремонт": "repair",
    "Установка": "installation",
    "Обслуживание": "maintenance",
    "HVAC": "hvac",
    "Отопление": "hvac",
    "Вентиляция": "hvac",
    "Лифт": "maintenance",
    "Интернет/ТВ": "electrician",
}


def get_specialization_for_category(category: str) -> str:
    """Return specialization for a category key, defaulting to 'other'."""
    return CATEGORY_TO_SPECIALIZATION.get(category, "other")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/andreyafanasyev/Code/UK && python -m pytest tests/test_category_mapping.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Replace inline dicts in admin.py**

In `uk_management_bot/handlers/admin.py`:

1. Add import at top:
   ```python
   from uk_management_bot.constants.categories import CATEGORY_TO_SPECIALIZATION, get_specialization_for_category
   ```

2. At line ~118 (`auto_assign_request_by_category` function): replace the entire `category_to_specialization = { ... }` dict with:
   ```python
   category_to_specialization = CATEGORY_TO_SPECIALIZATION
   ```

3. At line ~2628 (specific executor assignment handler): replace the entire `category_to_spec = { ... }` dict with:
   ```python
   category_to_spec = CATEGORY_TO_SPECIALIZATION
   ```

- [ ] **Step 6: Replace inline dicts in requests.py**

In `uk_management_bot/handlers/requests.py`:

1. Add import at top:
   ```python
   from uk_management_bot.constants.categories import CATEGORY_TO_SPECIALIZATION, get_specialization_for_category
   ```

2. At line ~229 (`auto_assign_request_by_category` function): replace the entire `category_to_specialization = { ... }` dict with:
   ```python
   category_to_specialization = CATEGORY_TO_SPECIALIZATION
   ```

3. At line ~2709 (`handle_assign_specific_executor` function): replace the entire `category_to_spec = { ... }` dict with:
   ```python
   category_to_spec = CATEGORY_TO_SPECIALIZATION
   ```

- [ ] **Step 7: Verify no regressions**

Run: `cd /Users/andreyafanasyev/Code/UK && python -m pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: No new failures

- [ ] **Step 8: Commit**

```bash
git add uk_management_bot/constants/ tests/test_category_mapping.py uk_management_bot/handlers/admin.py uk_management_bot/handlers/requests.py
git commit -m "refactor: unify category-to-specialization mapping into constants module

Eliminates 4 duplicate dicts across admin.py and requests.py.
Single source of truth prevents mapping drift (caused BUG-6)."
```

---

## Task 2: Harden `@require_role` Decorator Signature (P3 — defensive)

**Context:** BUG-5 was initially attributed to `@require_role` hiding parameter names from aiogram DI. Investigation shows `@wraps(func)` already sets `__wrapped__`, and aiogram 3.21 follows it for DI. The actual BUG-5 cause was likely a missing middleware or handler-specific issue. However, adding explicit `__signature__` is a defensive measure — it makes DI work even if aiogram changes its `__wrapped__` behavior.

**Note:** The signature test may already pass against the current code (aiogram resolves `__wrapped__`). If Step 2 passes, skip to Step 4 and commit as hardening.

**Files:**
- Modify: `uk_management_bot/middlewares/auth.py:135-231`
- Create: `tests/test_require_role.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_require_role.py
"""Tests for require_role decorator preserving function signature."""

import inspect
import asyncio
from unittest.mock import AsyncMock, MagicMock
from uk_management_bot.middlewares.auth import require_role


def test_decorator_preserves_parameter_names():
    """After decoration, aiogram must see the original parameter names."""

    @require_role(["executor"])
    async def my_handler(message, db, roles, user, language: str = "ru"):
        pass

    sig = inspect.signature(my_handler)
    param_names = list(sig.parameters.keys())
    assert "db" in param_names, f"'db' missing from {param_names}"
    assert "roles" in param_names, f"'roles' missing from {param_names}"
    assert "user" in param_names, f"'user' missing from {param_names}"
    assert "language" in param_names, f"'language' missing from {param_names}"


def test_decorator_preserves_defaults():
    """Default values must be preserved for DI."""

    @require_role(["manager"])
    async def my_handler(callback, db: "Session" = None, roles: list = None,
                         active_role: str = None, user=None, language: str = "ru"):
        pass

    sig = inspect.signature(my_handler)
    assert sig.parameters["language"].default == "ru"
    assert sig.parameters["roles"].default is None


def test_decorator_blocks_unauthorized():
    """Handler should not execute if user lacks required role."""
    executed = False

    @require_role(["admin"])
    async def my_handler(message, db=None, roles=None, user=None, language="ru"):
        nonlocal executed
        executed = True

    mock_msg = MagicMock()
    mock_msg.from_user = MagicMock(id=123)
    mock_msg.answer = AsyncMock()

    asyncio.get_event_loop().run_until_complete(
        my_handler(mock_msg, db=None, roles=["executor"], user=None, language="ru")
    )
    assert not executed, "Handler ran despite missing role"


def test_decorator_allows_authorized():
    """Handler should execute if user has required role."""
    executed = False

    @require_role(["executor"])
    async def my_handler(message, db=None, roles=None, user=None, language="ru"):
        nonlocal executed
        executed = True
        return "ok"

    mock_msg = MagicMock()
    mock_msg.from_user = MagicMock(id=123)

    result = asyncio.get_event_loop().run_until_complete(
        my_handler(mock_msg, db=None, roles=["executor"], user=None, language="ru")
    )
    assert executed
    assert result == "ok"
```

- [ ] **Step 2: Run test to check current behavior**

Run: `cd /Users/andreyafanasyev/Code/UK && python -m pytest tests/test_require_role.py::test_decorator_preserves_parameter_names -v`
Expected: May PASS (aiogram follows `__wrapped__`) or FAIL. If PASS — the fix is purely defensive hardening. Proceed to Step 3 regardless.

- [ ] **Step 3: Fix the decorator in auth.py**

Replace the `require_role` function in `uk_management_bot/middlewares/auth.py` (lines 135-231). The key change: use `makefun.wraps` or manually copy `__signature__` so aiogram sees the original parameter names.

Since we don't want to add a dependency, use `inspect.signature` + `functools.wraps`:

```python
def require_role(required_roles: List[str]):
    """Декоратор для проверки ролей пользователя перед выполнением хэндлера.

    Preserves the original function's signature so that aiogram 3 DI
    can inspect parameter names and inject db, roles, user, language.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Получаем event (первый позиционный аргумент)
            event = args[0] if args else None

            # Получаем роли из kwargs (injected by aiogram DI middleware)
            user_roles = kwargs.get("roles") or []
            language = kwargs.get("language", "ru")

            # Если роли не пришли через DI, пробуем из БД
            if not user_roles and event:
                db = kwargs.get("db")
                telegram_id = getattr(getattr(event, 'from_user', None), 'id', None)
                if telegram_id and db:
                    try:
                        from uk_management_bot.database.models.user import User as _User
                        from uk_management_bot.utils.auth_helpers import get_user_roles as _get_user_roles
                        user_obj = db.query(_User).filter(_User.telegram_id == telegram_id).first()
                        if user_obj:
                            user_roles = _get_user_roles(user_obj)
                    except Exception as e:
                        logger.warning(f"Ошибка получения ролей из БД: {e}")

            # Проверяем права
            has_access = any(role in user_roles for role in required_roles)

            if not has_access:
                text = get_text("auth.no_access", language=language)
                try:
                    if hasattr(event, 'answer'):
                        if isinstance(event, CallbackQuery):
                            await event.answer(text, show_alert=True)
                        else:
                            await event.answer(text)
                except Exception as e:
                    logger.warning(f"Не удалось отправить сообщение: {e}")
                return None

            return await func(*args, **kwargs)

        # CRITICAL: Copy the original signature so aiogram DI sees
        # the real parameter names (db, roles, user, language, etc.)
        import inspect
        wrapper.__signature__ = inspect.signature(func)

        return wrapper
    return decorator
```

The critical line is `wrapper.__signature__ = inspect.signature(func)` — this is what makes aiogram see `db`, `roles`, `user` instead of `*args, **kwargs`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/andreyafanasyev/Code/UK && python -m pytest tests/test_require_role.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Verify no regressions**

Run: `cd /Users/andreyafanasyev/Code/UK && python -m pytest tests/ -v --tb=short 2>&1 | tail -30`

- [ ] **Step 6: Commit**

```bash
git add uk_management_bot/middlewares/auth.py tests/test_require_role.py
git commit -m "fix: preserve function signature in @require_role for aiogram DI

Add explicit __signature__ to @require_role wrapper as defensive
hardening. Ensures aiogram DI works even without __wrapped__ support."
```

---

## Task 3: Global `/start` FSM Reset for All States (P0)

**Problem:** BUG-3 fix added `/start` handlers only for `RequestStates.*` (9 states). But there are 32 FSM state classes with 400+ states. If user sends `/start` while in any Manager/Shift/Address FSM, they get stuck.

**Strategy:** Instead of registering `/start` for each of 400+ states, add FSM clearing logic to the main `/start` handler in `base.py`. The key: `base_router` is registered last (fallback), so it only fires if no other router caught the command. Move FSM clear into a middleware or register `/start` with `StateFilter("*")` on a high-priority router.

**Files:**
- Modify: `uk_management_bot/handlers/base.py:56-140` (main `/start` handler)
- Modify: `uk_management_bot/handlers/requests.py:349-357` (remove individual state handlers — now redundant)
- Create: `tests/test_start_fsm_reset.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_start_fsm_reset.py
"""Tests for /start resetting FSM from any state."""

import inspect
from uk_management_bot.handlers.base import cmd_start, start_router


def test_start_handler_accepts_state_param():
    """cmd_start must accept 'state' for FSM clearing."""
    sig = inspect.signature(cmd_start)
    assert "state" in sig.parameters, f"'state' missing from {list(sig.parameters)}"


def test_start_router_exists():
    """start_router must exist as a separate router for priority registration."""
    assert start_router is not None
    assert start_router.name == "start"


def test_start_handler_registered_on_start_router():
    """cmd_start must be on start_router, not base router."""
    # Verify start_router has at least one message handler
    assert len(start_router.message.handlers) > 0, "start_router has no message handlers"
```

- [ ] **Step 2: Modify the main `/start` handler in base.py**

In `uk_management_bot/handlers/base.py`, the `cmd_start` handler at line 56 already accepts `state: FSMContext = None`. Ensure it calls `await state.clear()` **at the very beginning**, before any other logic:

```python
@router.message(Command("start"))
async def cmd_start(message: Message, db: Session, state: FSMContext = None,
                    roles: list = None, active_role: str = None,
                    user: User = None, language: str = "ru"):
    """Handle /start command — always clears FSM first."""
    # CRITICAL: Clear any active FSM state before processing
    if state:
        current_state = await state.get_state()
        if current_state is not None:
            logger.info(f"User {message.from_user.id}: /start clearing FSM state {current_state}")
            await state.clear()

    # ... rest of existing handler logic unchanged ...
```

- [ ] **Step 3: Move `base_router` registration BEFORE specific routers for `/start`**

The problem: `base_router` is registered last (line 304 in main.py), so other routers with FSM state filters catch `/start` first. Two options:

**Option A (recommended):** Create a dedicated `start_router` that handles `/start` and register it FIRST (before all others). This router has no FSM state filter, so it catches `/start` regardless of FSM state.

**IMPORTANT:** The `start_router` must contain the COMPLETE `cmd_start` handler — including invite token processing (`/start join_TOKEN`), user creation, onboarding, and main menu rendering. This is NOT just an FSM-clear stub; it is the full handler MOVED from `base_router` to `start_router`.

In `uk_management_bot/handlers/base.py`:

```python
from aiogram import Router

# This router is registered FIRST in main.py to catch /start from any FSM state
start_router = Router(name="start")

@start_router.message(Command("start"))
async def cmd_start(message: Message, db: Session, state: FSMContext = None,
                    roles: list = None, active_role: str = None,
                    user_status: str = None, language: str = "ru"):
    """Handle /start command — clears FSM first, then full start logic."""
    # CRITICAL: Clear any active FSM state before processing
    if state:
        current_state = await state.get_state()
        if current_state is not None:
            logger.info(f"User {message.from_user.id}: /start clearing FSM state {current_state}")
            await state.clear()

    # ... REST OF EXISTING cmd_start LOGIC (invite tokens, user creation, etc.) ...
    # Move the ENTIRE function body here from the old @router.message(Command("start"))
```

Remove the old `@router.message(Command("start"))` from `base_router` (it will never fire since `start_router` catches first).

Then in `main.py`, register `start_router` before all others:
```python
from uk_management_bot.handlers.base import start_router, router as base_router

dp.include_router(start_router)   # FIRST — catches /start from any state
# ... all other routers ...
dp.include_router(base_router)    # LAST — fallback
```

**Option B:** Keep single router, but register `/start` handler with `StateFilter("*")` — however aiogram 3 doesn't have this built-in.

**Go with Option A.**

- [ ] **Step 4: Remove redundant `/start` handlers from requests.py**

In `uk_management_bot/handlers/requests.py`, remove lines 349-370 (all the `@router.message(Command("start"), RequestStates.*)` handlers and the `handle_start_during_request_creation` function). They are now redundant — `start_router` catches `/start` before `requests_router`.

- [ ] **Step 5: Run tests**

Run: `cd /Users/andreyafanasyev/Code/UK && python -m pytest tests/test_start_fsm_reset.py tests/ -v --tb=short 2>&1 | tail -30`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add uk_management_bot/handlers/base.py uk_management_bot/handlers/requests.py uk_management_bot/main.py tests/test_start_fsm_reset.py
git commit -m "fix: /start now resets FSM from any state, not just RequestStates

Create dedicated start_router registered first in dispatcher.
Clears FSM state before processing, so user is never stuck.
Remove redundant per-state /start handlers from requests.py."
```

---

## Task 4: Fix Duplicate `admin_panel` Callback Handlers (P3→P0)

**Problem:** Two handlers respond to `callback_data == "admin_panel"`:
1. `employee_management.py:1419` — uses `edit_text` (correct for inline callback)
2. `user_management.py:2435` — uses `answer` (sends new message, wrong for callback)

Since `user_management_router` is registered BEFORE `employee_management_router` (line 300 vs 301 in main.py), the `user_management` handler wins (earlier = higher priority in aiogram 3). It sends a new message instead of editing, which leaves stale inline buttons.

**Files:**
- Modify: `uk_management_bot/handlers/user_management.py:2435-2455`
- Modify: `uk_management_bot/handlers/employee_management.py:1419-1439`

- [ ] **Step 1: Inspect both handlers**

Read both handlers to confirm the behavior difference.

- [ ] **Step 2: Remove duplicate from user_management.py**

Delete the `back_to_admin_panel` function from `uk_management_bot/handlers/user_management.py` (lines ~2435-2455). Keep the one in `employee_management.py` since it uses `edit_text` (correct behavior for inline callback navigation).

- [ ] **Step 3: Verify the remaining handler in employee_management.py uses edit_text**

Confirm `employee_management.py:1419` handler:
- Uses `callback.message.edit_text(...)` (not `callback.message.answer(...)`)
- Provides `get_manager_main_keyboard()` as reply_markup
- Handles language parameter

- [ ] **Step 4: Verify employee_management_router registration**

Confirm `employee_management_router` is included in `main.py` so the callback still gets handled.

- [ ] **Step 5: Commit**

```bash
git add uk_management_bot/handlers/user_management.py
git commit -m "fix: remove duplicate admin_panel callback handler

user_management.py had a duplicate that sent a new message
instead of editing. Keep the edit_text version in employee_management.py."
```

---

## Task 5: Fix `mreq_back_to_list` — Remove Regex Text Dependency (P3)

**Problem:** `admin.py:853-932` determines which list to return to by extracting the request number from message text using regex `r'Заявка #(\d{6}-\d{3})'`, then querying DB for request status. The regex part is fragile (depends on message language/format), but the status-based routing is sound.

**Files:**
- Modify: `uk_management_bot/handlers/admin.py:853-932`

- [ ] **Step 1: Analyze current approach**

The handler extracts request_number from message text, queries DB for status, then routes. The fragile part is only the regex extraction. Alternative: encode request_number in callback_data.

- [ ] **Step 2: Add request_number to callback_data**

Change callback_data from `mreq_back_to_list` to `mreq_back_{request_number}`. The callback buttons are constructed inline in `uk_management_bot/handlers/admin.py` at lines 422 and 430 (NOT in keyboards/admin.py). Change both to:
```python
InlineKeyboardButton(
    text=get_text("admin.handlers.btn_back_to_list", language=lang),
    callback_data=f"mreq_back_{request.request_number}"
)
```

- [ ] **Step 3: Update handler to parse from callback_data**

```python
@router.callback_query(F.data.startswith("mreq_back_"))
async def handle_manager_back_to_list(callback: CallbackQuery, db: Session, ...):
    request_number = callback.data.split("mreq_back_")[1]
    request = db.query(Request).filter(Request.request_number == request_number).first()
    # ... rest of status-based routing unchanged ...
```

- [ ] **Step 4: Verify no other handlers reference `mreq_back_to_list`**

Run: `grep -r "mreq_back_to_list" uk_management_bot/` — should find only the old references that need updating.

- [ ] **Step 5: Commit**

```bash
git add uk_management_bot/handlers/admin.py
git commit -m "fix: encode request_number in back-to-list callback data

Replace regex extraction from message text with direct parsing from
callback_data. Eliminates dependency on message format/language."
```

---

## Task 6: Unify Shift Interfaces Documentation (P2)

**Problem:** Executor has two shift menus: "🔄 Смена" (shifts.py — operational: start/stop) and "📋 Мои смены" (my_shifts.py — detailed: schedule/stats). They use different fields (`start_time` vs `planned_start_time`), creating potential data inconsistency.

**This is a design decision, not a code fix.** Full unification is a major refactor beyond the scope of these fixes. For now: document the intentional separation and add a cross-reference.

**Files:**
- Modify: `uk_management_bot/handlers/shifts.py` (add docstring at module level)
- Modify: `uk_management_bot/handlers/my_shifts.py` (add docstring at module level)

- [ ] **Step 1: Add module docstrings clarifying the split**

In `shifts.py`, add at top:
```python
"""
Operational shift menu ("🔄 Смена") — quick actions for shift start/stop.

Uses: Shift.start_time, Shift.end_time (actual times)
Related: my_shifts.py handles the detailed shift interface ("📋 Мои смены")
"""
```

In `my_shifts.py`, add at top:
```python
"""
Detailed shift interface ("📋 Мои смены") — schedule, stats, time tracking.

Uses: Shift.planned_start_time, Shift.planned_end_time (planned times)
Related: shifts.py handles the operational menu ("🔄 Смена")
"""
```

- [ ] **Step 2: Commit**

```bash
git add uk_management_bot/handlers/shifts.py uk_management_bot/handlers/my_shifts.py
git commit -m "docs: clarify dual shift interface design and field usage"
```

---

## Task 7: Synchronize /help Content Between RU and UZ (P3)

**Problem:** RU `/help` is brief, UZ `/help` is detailed. Users get different amounts of information depending on language.

**Files:**
- Identify: locale files containing `help` text keys
- Modify: the locale file with shorter content to match the longer one

- [ ] **Step 1: Find help text locations**

Run: `grep -r "help" uk_management_bot/config/locales/ --include="*.json" -l`

- [ ] **Step 2: Compare RU and UZ help texts**

Read both help text values and determine which is more complete.

- [ ] **Step 3: Update the shorter version to match the longer one's structure**

Translate the missing sections, keeping the same headings and structure.

- [ ] **Step 4: Commit**

```bash
git add uk_management_bot/config/locales/
git commit -m "fix: synchronize /help content between RU and UZ locales"
```

---

## Task 8: Document Manager-as-Applicant Behavior (P3)

**Problem:** Manager inherits all applicant buttons (create request, my requests, acceptance). Can create and accept own requests — potential conflict of interest, but may be intentional for small teams.

**Files:**
- Modify: `uk_management_bot/keyboards/base.py:91` (add comment)

- [ ] **Step 1: Add design decision comment**

In `get_main_keyboard_for_role()` in `keyboards/base.py`, add a comment at the manager section:

```python
# NOTE: Manager intentionally inherits applicant buttons (create request,
# my requests, acceptance) so managers in small teams can also submit
# maintenance requests. If role separation is needed later, remove these
# buttons from the manager keyboard and create a separate "submit as manager" flow.
```

- [ ] **Step 2: Commit**

```bash
git add uk_management_bot/keyboards/base.py
git commit -m "docs: document manager-as-applicant design decision"
```

---

## Build & Verify

After all tasks are committed:

- [ ] **Rebuild Docker container**

```bash
cd /Users/andreyafanasyev/Code/UK && docker compose up -d --build app
```

- [ ] **Wait for container to be healthy**

```bash
docker ps --filter name=uk-management-bot --format "{{.Status}}"
```
Expected: `Up ... (healthy)`

- [ ] **Smoke test via Telegram**

1. As executor: click "📋 Мои смены" → should work (require_role fix)
2. Send `/start` while in any FSM state → should return to main menu
3. As manager: open request → "В работу" → "Конкретному исполнителю" → should show executors (category mapping fix)

---

## Summary

| Task | Priority | Risk | Effort |
|------|----------|------|--------|
| 1. Unified category mapping | P0 (live bug: `cleaner` vs `cleaning`) | Low | 20 min |
| 2. Harden @require_role signature | P3 (defensive) | Low | 15 min |
| 3. Global /start FSM reset | P0 | Medium (router order) | 30 min |
| 4. Remove duplicate admin_panel | P1 | Low | 5 min |
| 5. Fix mreq_back_to_list | P3 | Low | 15 min |
| 6. Document shift interfaces | P3 | None | 5 min |
| 7. Sync /help RU/UZ | P3 | Low | 15 min |
| 8. Document manager-as-applicant | P3 | None | 5 min |

**Recommended execution order:** 1 → 3 → 4 → 5 → 2 → 6 → 7 → 8 → Build & Verify

Tasks 1, 3, 4 are P0/P1 and should be done first. All 8 tasks are independent and can be parallelized.
