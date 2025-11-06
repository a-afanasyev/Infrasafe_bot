# TASK 17: requests.py Manual Refactoring Plan

**File**: `uk_management_bot/handlers/requests.py`
**Date**: 1 November 2025
**Status**: 🎯 Ready to Execute

---

## 📊 File Analysis

**Statistics:**
- **Total lines**: 3,031
- **Hardcoded strings**: 1,083
- **Functions**: 28+ handlers
- **Current get_text() usage**: Minimal (only in helper functions)

**Key Functions:**
```python
_deny_if_pending_message()           # Line 66  - ✅ Already uses get_text
_deny_if_pending_callback()          # Line 81  - ✅ Already uses get_text
get_contextual_help()                # Line 96  - ❌ Hardcoded strings
graceful_fallback()                  # Line 113 - ❌ Hardcoded strings
start_request_creation()             # Line 324 - ❌ Hardcoded strings (CRITICAL)
process_category()                   # Line 356 - ❌ Hardcoded strings
process_address()                    # Line 408 - ❌ Hardcoded strings
process_description()                # Line 627 - ❌ Hardcoded strings
process_urgency()                    # Line 651 - ❌ Hardcoded strings
process_media()                      # Line 681 - ❌ Hardcoded strings
show_confirmation()                  # Line 731 - ❌ Hardcoded strings
save_request()                       # Line 805 - ❌ Hardcoded strings
handle_category_selection()          # Line 882 - ❌ Hardcoded strings
... and 15 more handlers
```

---

## 🎯 Refactoring Strategy

### Phase 1: Setup & Imports (30 min)
✅ Add centralized imports at top of file
✅ Create language helper utility
✅ Update existing imports

### Phase 2: Helper Functions (1h)
- `get_contextual_help()` - add language parameter
- `graceful_fallback()` - add language parameter
- `smart_address_validation()` - review for hardcoded strings

### Phase 3: Create Request Flow (4h) - PRIORITY
Main user journey:
1. `start_request_creation()` - entry point
2. `process_category()` / `handle_category_selection()`
3. `process_address()` / `process_address_manual()`
4. `process_description()`
5. `process_urgency()` / `handle_urgency_selection()`
6. `process_media()`
7. `show_confirmation()` / `handle_confirmation()`
8. `save_request()`

### Phase 4: View Request Flow (2h)
- `handle_pagination()`
- `handle_view_request()`
- `handle_back_to_list()`

### Phase 5: Request Actions (1h)
- `handle_edit_request()`
- `handle_delete_request()`
- `handle_accept_request()`

---

## 📝 Step-by-Step Execution Plan

### Step 1: Add Centralized Imports ✅

**Location**: After line 52 (after existing imports)

**Add:**
```python
# Localization imports
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.language_helpers import (
    get_language_for_user,
    get_language_from_message,
    get_language_from_callback
)
```

**Verification:**
```bash
# Check imports added
grep -n "from uk_management_bot.utils.helpers import get_text" uk_management_bot/handlers/requests.py

# Should show single import near top (not scattered in functions)
```

---

### Step 2: Create Language Helper Wrapper

**Location**: After imports, before first function (~line 64)

**Add:**
```python
# Language detection helper for this module
async def _get_user_language(message: Message = None, callback: CallbackQuery = None, user_id: int = None) -> str:
    """Get user language from message, callback, or user_id"""
    try:
        if message:
            return await get_language_from_message(message)
        elif callback:
            return await get_language_from_callback(callback)
        elif user_id:
            db = next(get_db())
            try:
                return await get_language_for_user(user_id, db)
            finally:
                db.close()
    except Exception as e:
        logger.warning(f"Failed to get user language: {e}")
    return "ru"  # Fallback
```

**Why**: Централизует логику определения языка, упрощает код

---

### Step 3: Refactor `get_contextual_help()` (Line 96)

**Current:**
```python
def get_contextual_help(address_type: str) -> str:
    """Получить контекстную помощь в зависимости от типа адреса"""
    if address_type == "yard":
        return "💡 Двор — это территория, обслуживаемая вашей УК..."
    elif address_type == "building":
        return "💡 Здание — это отдельный дом..."
    # ... more hardcoded strings
```

**Refactored:**
```python
def get_contextual_help(address_type: str, language: str = "ru") -> str:
    """Получить контекстную помощь в зависимости от типа адреса"""
    if address_type == "yard":
        return get_text("requests.help_yard", language=language)
    elif address_type == "building":
        return get_text("requests.help_building", language=language)
    elif address_type == "apartment":
        return get_text("requests.help_apartment", language=language)
    else:
        return get_text("requests.help_default", language=language)
```

**Locale keys needed in ru.json:**
```json
{
  "requests": {
    "help_yard": "💡 Двор — это территория, обслуживаемая вашей УК...",
    "help_building": "💡 Здание — это отдельный дом...",
    "help_apartment": "💡 Квартира — это отдельная единица жилья...",
    "help_default": "💡 Укажите адрес заявки"
  }
}
```

**Verification:**
```bash
# Check function signature updated
grep -A 5 "def get_contextual_help" uk_management_bot/handlers/requests.py | grep "language"

# Check no hardcoded Russian in function
grep -A 20 "def get_contextual_help" uk_management_bot/handlers/requests.py | grep "💡"
# Should return EMPTY (all moved to get_text)
```

---

### Step 4: Refactor `graceful_fallback()` (Line 113)

**Current:**
```python
async def graceful_fallback(message: Message, error_type: str):
    """Обработка ошибок с контекстными сообщениями"""
    error_message = ERROR_MESSAGES.get(error_type, "❌ Произошла ошибка")
    await message.answer(error_message, reply_markup=get_cancel_keyboard())
```

**Refactored:**
```python
async def graceful_fallback(message: Message, error_type: str, language: str = "ru"):
    """Обработка ошибок с контекстными сообщениями"""
    # Use localized error messages
    error_key = f"errors.{error_type}"
    error_message = get_text(error_key, language=language)

    await message.answer(
        error_message,
        reply_markup=get_cancel_keyboard(language=language)
    )
```

**Note**: Requires `get_cancel_keyboard()` to accept language parameter (update in keyboards/requests.py)

---

### Step 5: Refactor `start_request_creation()` (Line 324) 🎯 CRITICAL

**Current (lines 324-352):**
```python
@router.message(F.text == "📝 Создать заявку")
async def start_request_creation(message: Message, state: FSMContext, user_status: Optional[str] = None):
    # ... phone check ...

    logger.info(f"Пользователь {message.from_user.id} нажал '📝 Создать заявку'")
    await state.set_state(RequestStates.category)
    await message.answer("Начинаем создание заявки…", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите категорию заявки:", reply_markup=get_categories_inline_keyboard_with_cancel())
    logger.info(f"Пользователь {message.from_user.id} начал создание заявки")
```

**Problem**:
1. `F.text == "📝 Создать заявку"` - hardcoded Russian
2. "Начинаем создание заявки…" - hardcoded
3. "Выберите категорию заявки:" - hardcoded
4. `get_categories_inline_keyboard_with_cancel()` doesn't accept language

**Refactored:**
```python
@router.message(F.text.in_([
    get_text("buttons.create_request", language="ru"),
    get_text("buttons.create_request", language="uz")
]))
async def start_request_creation(message: Message, state: FSMContext, user_status: Optional[str] = None):
    """Начало создания заявки"""

    # Get user language
    lang = await _get_user_language(message=message)

    # Check pending status
    if await _deny_if_pending_message(message, user_status):
        return

    # Check phone number
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or not user.phone:
            await message.answer(get_text("requests.phone_required", language=lang))
            return
    except Exception as e:
        logger.error(f"Error checking user phone: {e}")
    finally:
        db.close()

    logger.info(f"User {message.from_user.id} pressed '{get_text('buttons.create_request', language=lang)}'")

    await state.set_state(RequestStates.category)

    # Start request creation
    await message.answer(
        get_text("requests.create_start", language=lang),
        reply_markup=ReplyKeyboardRemove()
    )

    await message.answer(
        get_text("requests.select_category", language=lang),
        reply_markup=get_categories_inline_keyboard_with_cancel(language=lang)
    )

    logger.info(f"User {message.from_user.id} started request creation")
```

**Locale keys:**
```json
{
  "buttons": {
    "create_request": "📝 Создать заявку"
  },
  "requests": {
    "phone_required": "📱 Пожалуйста, сначала укажите номер телефона в профиле",
    "create_start": "Начинаем создание заявки…",
    "select_category": "Выберите категорию заявки:"
  }
}
```

**Critical Issue**: `F.text.in_([...])` with dynamic values may not work. Need alternative approach.

**Alternative Approach:**
```python
# Create constant mapping at module level
BUTTON_TEXTS = {
    "create_request": ["📝 Создать заявку", "📝 So'rov yaratish"]  # RU, UZ
}

@router.message(F.text.in_(BUTTON_TEXTS["create_request"]))
async def start_request_creation(message: Message, state: FSMContext, user_status: Optional[str] = None):
    # ... rest of function
```

**Better**: Update this in Phase 2 after testing basic localization works

---

### Step 6: Refactor `process_category()` (Line 356)

**Current:**
```python
@router.message(RequestStates.category, F.text.in_(REQUEST_CATEGORIES))
async def process_category(message: Message, state: FSMContext):
    """Обработка выбора категории с улучшенной интеграцией"""
    # ... lots of hardcoded strings
```

**Challenge**: `F.text.in_(REQUEST_CATEGORIES)` where REQUEST_CATEGORIES is hardcoded list

**Solution**: Will handle in Phase 3 - need to refactor keyboards first

---

## 🔧 Execution Order

### TODAY (4 hours):

1. ✅ **Step 1**: Add centralized imports (5 min)
2. ✅ **Step 2**: Add `_get_user_language()` helper (10 min)
3. ✅ **Step 3**: Refactor `get_contextual_help()` (30 min)
4. ✅ **Step 4**: Refactor `graceful_fallback()` (20 min)
5. 🧪 **Test**: Verify no import errors, file loads (5 min)
6. ✅ **Step 5a**: Refactor `start_request_creation()` - messages only (45 min)
7. 🧪 **Test**: Create request flow still works (30 min)
8. 📝 **Commit**: "TASK 17: requests.py Phase 1 - Helper functions and start_request_creation"

### NEXT SESSION (4 hours):

9. Refactor `handle_category_selection()` callback
10. Refactor `process_address()`
11. Refactor `process_description()`
12. Test address flow
13. Commit progress

---

## 🧪 Testing Strategy

After each function refactored:

```bash
# 1. Check syntax
python3 -m py_compile uk_management_bot/handlers/requests.py

# 2. Check imports
python3 -c "from uk_management_bot.handlers import requests; print('OK')"

# 3. Check for remaining hardcoded strings in refactored function
grep -A 30 "async def start_request_creation" uk_management_bot/handlers/requests.py | grep '"[А-Яа-я]'
# Should return EMPTY if fully refactored

# 4. Manual test in bot
# - Change language to UZ in profile
# - Click "Создать заявку" / "So'rov yaratish"
# - Verify messages appear in Uzbek
```

---

## 📊 Progress Tracking

| Function | Lines | Strings | Status | Time |
|----------|-------|---------|--------|------|
| Imports | 52 | 0 | ⏳ Pending | 5 min |
| `_get_user_language()` | +15 | 0 | ⏳ Pending | 10 min |
| `get_contextual_help()` | 96-112 | ~5 | ⏳ Pending | 30 min |
| `graceful_fallback()` | 113-130 | ~3 | ⏳ Pending | 20 min |
| `start_request_creation()` | 324-352 | ~8 | ⏳ Pending | 60 min |
| **Phase 1 Total** | - | **~16** | ⏳ **0%** | **2h** |

---

## 🎯 Success Criteria for Today

- ✅ Centralized imports added
- ✅ `_get_user_language()` helper works
- ✅ `get_contextual_help()` refactored and tested
- ✅ `graceful_fallback()` refactored and tested
- ✅ `start_request_creation()` shows localized messages
- ✅ No syntax errors
- ✅ Bot still works in Russian
- ✅ Bot shows Uzbek messages when language=uz
- ✅ Code committed with clear message

---

## 📝 Notes

**Key Challenges:**
1. `F.text` filters with dynamic localized values
2. Keyboard functions need language parameter
3. Constants like REQUEST_CATEGORIES need localization
4. Logger messages - keep in Russian or localize?

**Decisions:**
- Logger messages: Keep in Russian/English (not user-facing)
- F.text filters: Handle in Phase 2 with button text mapping
- Focus on user-facing messages first
- Test incrementally after each function

---

**Ready to start?** Begin with Step 1: Add centralized imports.

**Document Version**: 1.0
**Last Updated**: 1 November 2025
**Status**: 🎯 Ready to Execute
