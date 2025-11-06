# TASK 17: requests.py Critical Architectural Issues

**Date**: 5 November 2025
**Status**: 🔴 CRITICAL - Blocks Uzbek users from creating requests
**Priority**: HIGHEST

---

## 🚨 Problem Overview

The requests.py file was refactored for localization in Sessions 24-35, but **critical architectural issues** remain that completely break the request creation flow for Uzbek users.

---

## 🐛 Issues Identified

### Issue #1: Entry Handler Matches Hard-Coded Russian Text (Line 380)

**Location**: `requests.py:380`

```python
@router.message(F.text == "📝 Создать заявку")
async def start_request_creation(message: Message, state: FSMContext, user_status: Optional[str] = None):
```

**Problem:**
- Handler only triggers when message text exactly matches "📝 Создать заявку" (Russian)
- When main keyboard is localized, Uzbek users click "📝 Ariza yaratish"
- Message text doesn't match → handler never triggers → flow never starts

**Impact**: **COMPLETE BLOCKER** - Uzbek users cannot create requests at all

**Solution Required:**
- Cannot use F.text filter with hard-coded strings
- Options:
  1. Use callback_data instead of text buttons
  2. Check both Russian AND Uzbek text in filter
  3. Use a command/state-based approach
  4. Store button text keys in constants and compare dynamically

---

### Issue #2: Category Handling Uses Russian-Only List (Line 422)

**Location**: `requests.py:422`

```python
@router.message(RequestStates.category, F.text.in_(REQUEST_CATEGORIES))
async def process_category(message: Message, state: FSMContext):
```

**Where REQUEST_CATEGORIES is:**
```python
# constants.py
REQUEST_CATEGORIES = [
    "Электрика",
    "Сантехника",
    "Отопление",
    "Лифт",
    "Уборка",
    "Благоустройство",
    "Безопасность",
    "Интернет/ТВ"
]
```

**Problem:**
- FSM filter checks if message text is in REQUEST_CATEGORIES
- Category keyboard sends localized text (e.g., "Elektr" for Uzbek)
- Uzbek text not in Russian list → filter rejects → handler never triggers
- User stuck in RequestStates.category state forever

**Impact**: **COMPLETE BLOCKER** - Category selection broken for Uzbek users

**Solution Required:**
- Create bilingual category mapping
- Use callback_data with category IDs instead of text
- OR: Check against both Russian and Uzbek category lists
- Store canonical category names (English IDs) and map to display names

---

### Issue #3: smart_address_validation Builds Russian Suggestions (Lines 323-353)

**Location**: `requests.py:323-353`

```python
def smart_address_validation(address: str, lang: str = "ru") -> Dict:
    # ... validation logic ...
    if not building_match:
        suggestions.append(f"Возможно, вы имели в виду: {closest_building}")

    if closest_street and distance <= 3:
        suggestions.append(f"Возможно, улица: {closest_street}")

    return {
        "valid": is_valid,
        "suggestions": suggestions,  # ← Russian strings
        "message": " ".join(suggestions) if suggestions else None
    }
```

**Problem:**
- Function builds suggestion strings in Russian ("Возможно, вы имели в виду...")
- These strings are embedded directly, cannot be translated
- Uzbek users get Russian error messages even when UI is Uzbek

**Impact**: **HIGH** - Mixed-language UX, confusing for Uzbek users

**Solution Required:**
- Move suggestion templates to locale files
- Use get_text() with placeholders: `get_text("address.suggestion_building", language=lang).format(building=closest_building)`
- Return suggestion data (not strings), let caller format with get_text()

---

### Issue #4: Request Details View Has Inline Russian Strings (Lines 1473-1545)

**Location**: `requests.py:1473-1545`

```python
async def get_request_details(request_number: str, db: Session, user: User = None, show_actions: bool = True, lang: str = "ru") -> tuple:
    """Get formatted request details with action buttons"""
    # ... lots of inline Russian strings ...

    text = f"📋 **Заявка #{request.request_number}**\n\n"
    text += f"**Категория:** {request.category}\n"
    text += f"**Адрес:** {request.address}\n"
    text += f"**Статус:** {request_status_emoji} {request.status}\n"
    # ... more hard-coded labels ...

    buttons = []
    if can_change_status:
        buttons.append([InlineKeyboardButton(text="✅ Выполнена", callback_data=f"complete_{request_number}")])
    # ... more hard-coded button text ...
```

**Problem:**
- All labels ("Категория", "Адрес", "Статус") hard-coded in Russian
- Button text ("✅ Выполнена", "💬 Ответить") hard-coded in Russian
- Function has `lang` parameter but doesn't use it!
- Entire details screen shows Russian regardless of user language

**Impact**: **CRITICAL** - Request details screen completely ignores locale

**Solution Required:**
- Replace ALL inline strings with get_text() calls
- Use locale keys like "requests.label_category", "requests.label_address", etc.
- Localize ALL button text
- Actually use the `lang` parameter!

---

### Issue #5: Listing Page Has Hard-Coded Russian Labels (Lines 1720-1788)

**Location**: `requests.py:1720-1788`

```python
@router.callback_query(F.data.startswith("requests_page_"))
async def handle_requests_pagination(callback: CallbackQuery, db: Session, user: User = None):
    # ... pagination logic ...

    text = "📋 **Назначенные заявки**\n\n"  # ← Hard-coded
    if not requests:
        text += "Пока нет заявок для отображения."  # ← Hard-coded
    # ... more hard-coded strings ...

    filter_text = "**Фильтры:**\n"  # ← Hard-coded
    if filters.get('status'):
        filter_text += f"Статус: {filters['status']}\n"  # ← Hard-coded
    # ... more hard-coded filter labels ...

    buttons = []
    buttons.append([InlineKeyboardButton(text="Активные", callback_data="filter_status_active")])  # ← Hard-coded
```

**Problem:**
- Page title, empty state, filter labels all hard-coded in Russian
- Pagination buttons, filter buttons all Russian
- No use of get_text() anywhere in listing logic
- Uzbek users see entirely Russian listings screen

**Impact**: **CRITICAL** - Entire requests listing UI is Russian-only

**Solution Required:**
- Localize ALL page titles, headers, empty states
- Localize ALL filter labels and button text
- Move all strings to locale files
- Use get_text() throughout listing logic

---

## 🎯 Root Cause Analysis

The fundamental issue is **mixing data and presentation**:

1. **Button text as data**: Using button text strings for flow control (F.text filters)
2. **Russian constants as filters**: REQUEST_CATEGORIES used both as data and UI
3. **Inline string building**: Functions that build UI strings inline instead of using templates
4. **Ignored language parameters**: Functions have `lang` params but don't use them

**Correct Architecture:**
- **Data layer**: Use language-independent IDs (e.g., "category_plumbing", "status_active")
- **Presentation layer**: Map IDs to localized strings via get_text()
- **Flow control**: Use callback_data or commands, NOT display text
- **Templates**: All UI strings in locale files, NO inline Russian

---

## 🔧 Proposed Solutions

### Solution Strategy A: Callback Data (RECOMMENDED)

**Principle**: Use language-independent callback_data for ALL buttons

**Changes:**
1. Replace text button "📝 Создать заявку" with inline button + callback "create_request"
2. Use category IDs in callback_data: "category_plumbing", "category_electric", etc.
3. Store canonical category names, map to display text
4. All handlers match callback_data, NOT text

**Pros:**
- Clean separation of data and presentation
- No language-dependent filters
- Future-proof for more languages

**Cons:**
- Requires changing from ReplyKeyboard to InlineKeyboard in some places
- More refactoring needed

---

### Solution Strategy B: Bilingual Text Matching (QUICK FIX)

**Principle**: Check against BOTH Russian and Uzbek text in filters

**Changes:**
1. Create `get_create_request_text(lang)` helper returning "📝 Создать заявку" or "📝 Ariza yaratish"
2. Filter: `F.text.in_([get_text("buttons.create_request", "ru"), get_text("buttons.create_request", "uz")])`
3. Create CATEGORIES_RU + CATEGORIES_UZ lists, filter checks both
4. In handler, detect which language was sent, use for response

**Pros:**
- Faster to implement
- Works with existing ReplyKeyboard approach

**Cons:**
- Doesn't scale to 3+ languages
- Still couples data and presentation
- Harder to maintain

---

### Solution Strategy C: State-Based Entry (ALTERNATIVE)

**Principle**: Don't match text at all, use FSM states

**Changes:**
1. Set state after /start or menu navigation
2. When in "main_menu" state, ANY message with category keywords triggers flow
3. Or use commands: /create_request instead of button

**Pros:**
- No text matching needed
- Language-independent

**Cons:**
- Changes UX significantly
- Requires rethinking navigation flow

---

## 📋 Implementation Plan

### Phase 1: Critical Blockers (IMMEDIATE)

**Priority**: Fix category flow so Uzbek users can create requests

1. **Fix category handling** (Issue #2):
   - Create category ID constants: `CATEGORY_PLUMBING = "plumbing"`, etc.
   - Add mapping in locale files: `"categories.plumbing": "Сантехника" / "Santexnika"`
   - Change category keyboard to use callback_data with IDs
   - Update handler to match callback_data, not text
   - Map ID back to display name for storage

2. **Fix entry handler** (Issue #1):
   - Option A: Change to inline button with callback "create_request"
   - Option B: Check both Russian and Uzbek text
   - Recommended: Option A (callback-based)

**Estimated time**: 30-45 minutes
**Result**: Request creation flow works for both languages

---

### Phase 2: UI Strings (HIGH PRIORITY)

**Priority**: Fix user-facing screens to show correct language

3. **Fix request details** (Issue #4):
   - Extract all labels to locale keys
   - Replace inline strings with get_text() calls
   - Localize all button text
   - Actually use the `lang` parameter

4. **Fix listing page** (Issue #5):
   - Move all page titles, headers to locale files
   - Localize filter labels and buttons
   - Use get_text() for empty states
   - Fix pagination button text

**Estimated time**: 45-60 minutes
**Result**: All request screens show correct language

---

### Phase 3: Address Validation (MEDIUM PRIORITY)

**Priority**: Clean up mixed-language error messages

5. **Fix address validation** (Issue #3):
   - Move suggestion templates to locale files
   - Refactor to return data, not formatted strings
   - Let caller format suggestions with get_text()

**Estimated time**: 20-30 minutes
**Result**: Address errors in user's language

---

## 🎯 Recommended Approach

**START WITH**: Phase 1 - Fix critical blockers (Issues #1 and #2)

**THEN**: Phase 2 - Fix UI strings (Issues #4 and #5)

**FINALLY**: Phase 3 - Fix address validation (Issue #3)

**Total estimated time**: 2-2.5 hours for complete fix

---

## ✅ Success Criteria

After fixes, the following must work:

1. ✅ Uzbek user clicks "📝 Ariza yaratish" → request creation starts
2. ✅ Uzbek user selects "Elektr" category → category accepted and saved
3. ✅ Request details screen shows Uzbek labels for Uzbek users
4. ✅ Listings page shows Uzbek labels and filters for Uzbek users
5. ✅ Address validation errors show in Uzbek for Uzbek users
6. ✅ Russian users still see everything in Russian (regression test)

---

## 📝 Next Steps

1. **Decide on strategy**: Callback-based (A) vs Bilingual matching (B)
2. **Start Phase 1**: Fix critical blockers first
3. **Test with both languages**: Verify flow works
4. **Continue Phase 2**: Fix UI strings
5. **Update SESSION summaries**: Document the architectural fixes

---

**Status**: 🔴 Analysis complete, awaiting implementation decision
**Blocking**: All Uzbek users from creating/viewing requests
**Impact**: HIGH - Core functionality broken for 50% of users
