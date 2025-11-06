# TASK 17: Comprehensive Localization Migration (RU/UZ)

**Created**: 29.10.2025
**Status**: 🚀 Planning Complete
**Priority**: P0 (Critical for UX)
**Timeline**: 17-26 days (6 phases)
**Owner**: Development Team

---

## 📊 EXECUTIVE SUMMARY

### Current State Analysis

**Existing Infrastructure:**
- ✅ Locale files: `ru.json` (659 lines), `uz.json` (660 lines)
- ✅ Helper functions: `load_locale()`, `get_text()` in `utils/helpers.py`
- ✅ Nested key support: `"auth.pending"` format
- ✅ Fallback mechanism: auto-fallback to Russian
- ✅ Parameter substitution: `{param}` support
- ✅ Database field: `User.language` (default: "ru")

**Problems Identified:**

1. **12,030 hardcoded Russian/Uzbek strings** across entire codebase (updated from initial estimate of 167)
   - Handlers: 6,590 strings (30 files)
   - Services: 3,549 strings (38 files)
   - Keyboards: 1,015 strings (20 files)
   - Utils: 487 strings (12 files)
   - Other: 2,389 strings (55+ files)
2. **~1787 user-facing message calls** (`answer()`, `send_message()`, `edit_text()`)
3. **322 f-strings with Russian text** in 24 files
4. **16 files** use `get_user_locale` / `get_locale` inconsistently
5. **Partial coverage**: some texts use locales, others are hardcoded

**Scope:**
- 30 handler files
- 38 service files
- 20 keyboard files
- ~12,500 lines of code total

---

## 🎯 MIGRATION OBJECTIVES

### Primary Goals

1. **100% Localization Coverage**
   - Zero hardcoded Russian/Uzbek strings in code
   - All user-facing messages via `get_text()` system

2. **Language Synchronization**
   - Full parity between `ru.json` and `uz.json`
   - Automated validation of translation completeness

3. **Dynamic Language Detection**
   - Auto-detect from Telegram user settings
   - Fallback to database `User.language` field
   - No hardcoded `lang = "ru"` anywhere

4. **Developer Experience**
   - Easy-to-use translation system
   - Clear naming conventions for keys
   - Automated tools for finding missing translations

### Success Metrics

- ✅ **0 hardcoded strings** (currently: 12,030 → target: 0)
- ⏳ **100% translation coverage** for all user messages (in progress)
- ⚠️ **ru.json ↔ uz.json synchronization** (99.9% parity, 1 extra key)
- ⏳ **All tests pass** in both RU and UZ languages (pending)
- ⏳ **Dynamic language detection** working in all handlers (pending)
- ⏳ **ASCII-only runtime strings**: все рабочие строки (условия `F.text`, названия кнопок, значения по умолчанию, ответы бота) берутся из локалей или ASCII-констант; кириллица разрешена только в комментариях и документации

---

## 🏗️ ARCHITECTURE & INFRASTRUCTURE

### Current System

```python
# utils/helpers.py

def load_locale(language: str = "ru") -> Dict[str, Any]:
    """Load locale file with fallback to RU"""
    locale_file = f"config/locales/{language}.json"
    if not os.path.exists(locale_file):
        locale_file = "config/locales/ru.json"  # Fallback
    return json.load(open(locale_file, "r", encoding="utf-8"))

def get_text(key: str, language: str = "ru", **kwargs) -> str:
    """Get translated text by key with parameter substitution"""
    locale = load_locale(language)

    # Support nested keys: "auth.pending"
    keys = key.split(".")
    value = locale
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            # Fallback to RU if not found
            return get_text_from_ru(key)

    # Replace {param} with actual values
    if isinstance(value, str) and kwargs:
        for param, replacement in kwargs.items():
            value = value.replace(f"{{{param}}}", str(replacement))

    return value if isinstance(value, str) else key
```

### Locale File Structure

```json
{
  "auth": {
    "pending": "⏳ Ваша заявка на рассмотрении",
    "approved": "✅ Вы одобрены",
    "blocked": "❌ Доступ заблокирован"
  },
  "profile": {
    "title": "👤 Профиль пользователя",
    "edit": "✏️ Редактировать профиль",
    "enter_phone": "📱 Введите ваш номер телефона:"
  },
  "requests": {
    "title": "📋 Мои заявки",
    "create": "➕ Создать заявку",
    "details": "Детали заявки",
    "category": "Категория",
    "status": "Статус"
  }
}
```

### Enhanced Infrastructure (Phase 1)

**New Tools to Create:**

1. **Hardcoded String Scanner** (`scripts/scan_hardcoded_strings.py`)
   - Scan all `.py` files for hardcoded Russian/Uzbek strings
   - Generate report with file:line:string
   - Support ignore patterns for comments/docstrings

2. **Locale Key Generator** (`scripts/generate_locale_keys.py`)
   - Auto-generate locale keys from hardcoded strings
   - Suggest key names based on context (file name, function name)
   - Update both ru.json and uz.json

3. **Translation Validator** (`scripts/validate_translations.py`)
   - Check ru.json ↔ uz.json key parity
   - Find missing translations
   - Validate parameter placeholders match

4. **Dynamic Language Helper** (`utils/language_helpers.py`)
   - `get_language_from_message(message)` - extract from Telegram
   - `get_language_from_callback(callback)` - extract from callback
   - `get_language_from_user(user_id, db)` - get from database

---

## 🎯 WEEKLY MILESTONES & CHECKPOINTS

### Milestone 1: Infrastructure Complete ✅ **ACHIEVED** (Day 0 - 29 Oct 2025)
**Target**: Phase 1 завершена
**Success Criteria**:
- ✅ Все scanning tools работают - **DONE** (3 scripts created)
- ✅ Language helpers созданы - **DONE** (13 functions)
- ✅ Enhanced get_text() с plural support - **DONE** (RU + UZ rules)
- ✅ Full codebase scanned - **DONE** (12,030 strings found)

### Milestone 2: Critical Handlers Complete (Day 7)
**Target**: Phase 2 P0 handlers завершены
**Success Criteria**:
- ✅ auth.py, onboarding.py, requests.py мигрированы
- ✅ Все P0 handlers используют get_text()
- ✅ Тесты для P0 handlers проходят в RU/UZ
- ✅ 50+ hardcoded strings устранены

### Milestone 3: All Handlers Complete (Day 11)
**Target**: Phase 2 завершена полностью
**Success Criteria**:
- ✅ Все 30 handler файлов мигрированы
- ✅ 0 hardcoded strings в handlers/
- ✅ Все handler тесты проходят в RU/UZ
- ✅ 150+ hardcoded strings устранены

### Milestone 4: Core Services Complete (Day 16)
**Target**: Phase 3 P0+P1 services завершены
**Success Criteria**:
- ✅ notification_service.py, request_service.py, auth_service.py мигрированы
- ✅ shift_service.py, assignment_service.py, profile_service.py мигрированы
- ✅ Multi-user scenarios работают корректно
- ✅ 200+ hardcoded strings устранены

### Milestone 5: All Services Complete (Day 19)
**Target**: Phase 3 завершена полностью
**Success Criteria**:
- ✅ Все 38 service файлов мигрированы
- ✅ 0 hardcoded strings в services/
- ✅ AI services error messages локализованы
- ✅ 250+ hardcoded strings устранены

### Milestone 6: Keyboards Complete (Day 22)
**Target**: Phase 4 завершена
**Success Criteria**:
- ✅ Все 20 keyboard файлов мигрированы
- ✅ Все keyboard функции принимают language parameter
- ✅ Все handlers передают language в keyboards
- ✅ 300+ hardcoded strings устранены

### Milestone 7: Testing Complete (Day 26)
**Target**: Phase 5 завершена
**Success Criteria**:
- ✅ 0 hardcoded strings подтверждено scanner'ом
- ✅ 100% translation parity (ru.json ↔ uz.json)
- ✅ Все integration тесты проходят в RU/UZ
- ✅ Manual testing завершен
- ✅ Edge case testing пройден

### Milestone 8: Production Ready (Day 26+)
**Target**: Phase 6 завершена (опционально)
**Success Criteria**:
- ✅ English language support добавлен
- ✅ Translation management UI создан
- ✅ CI/CD validation настроен
- ✅ Pre-commit hooks установлены

---

## 📅 PHASE-BY-PHASE PLAN

### **PHASE 1: Infrastructure & Preparation** ✅ **COMPLETED** (29 Oct 2025)

**Status**: ✅ **100% COMPLETE** - All deliverables ready
**Duration**: 2 hours (Target: 3-4 days)
**Completion Report**: `MemoryBank/TASK_17_PHASE1_COMPLETION_REPORT.md`

**Key Results**:
- ✅ Scanner detected **12,030 hardcoded strings** (vs estimated 167)
- ✅ All 5 tools created and tested in Docker
- ✅ Enhanced `get_text()` with plural support (RU + UZ)
- ✅ 13 language helper functions operational
- ✅ Translation validator: 582 keys validated, 0 errors

#### 1.1 Create Scanning Tools (Day 1) ✅ COMPLETED

**Task**: Build `scripts/scan_hardcoded_strings.py`

**Features:**
- Regex patterns for Russian/Uzbek strings: `[А-Яа-яЁё]`, `[ЎўҚқҒғҲҳ]`
- Filter out comments, docstrings, logger messages
- Generate report: `hardcoded_strings_report.txt`

**Example Output:**
```
uk_management_bot/handlers/requests.py:234: "⏳ Ваша заявка на рассмотрении"
uk_management_bot/handlers/auth.py:67: "❌ Доступ запрещен"
uk_management_bot/services/notification_service.py:123: "✅ Заявка создана"
...
Total: 167 hardcoded strings found
```

#### 1.2 Create Key Generator (Day 2)

**Task**: Build `scripts/generate_locale_keys.py`

**Features:**
- Auto-suggest key names from context
- Interactive mode: review and confirm keys
- Auto-update ru.json and uz.json

**Example:**
```bash
$ python scripts/generate_locale_keys.py

Found: "⏳ Ваша заявка на рассмотрении" in handlers/auth.py:234
Suggested key: "auth.pending_review"
Confirm? [Y/n]: Y

✅ Added to ru.json: auth.pending_review = "⏳ Ваша заявка на рассмотрении"
⚠️  uz.json needs translation for: auth.pending_review
```

#### 1.3 Translation Validator (Day 2)

**Task**: Build `scripts/validate_translations.py`

**Features:**
- Compare ru.json and uz.json keys
- Find missing translations
- Validate parameter placeholders

**Example Output:**
```
✅ ru.json: 542 keys
⚠️  uz.json: 538 keys (4 missing)

Missing in uz.json:
  - auth.pending_review
  - requests.media_upload_error
  - shifts.transfer_approved
  - profile.verification_pending

❌ Parameter mismatch:
  - requests.assigned_to: RU has {executor}, UZ has {исполнитель}
```

#### 1.4 Language Detection Helpers (Day 3)

**Task**: Create `utils/language_helpers.py`

**Code:**
```python
from typing import Optional
from aiogram.types import Message, CallbackQuery
from uk_management_bot.database.models.user import User

def get_language_from_message(message: Message, db=None) -> str:
    """Extract language from Telegram message with fallback"""
    # 1. Try Telegram language_code
    if message.from_user and message.from_user.language_code:
        lang = message.from_user.language_code[:2].lower()
        if lang in ["ru", "uz"]:
            return lang

    # 2. Fallback to database
    if db and message.from_user:
        user = db.query(User).filter(
            User.telegram_id == message.from_user.id
        ).first()
        if user and user.language:
            return user.language

    # 3. Default fallback
    return "ru"

def get_language_from_callback(callback: CallbackQuery, db=None) -> str:
    """Extract language from callback query with fallback"""
    if callback.from_user and callback.from_user.language_code:
        lang = callback.from_user.language_code[:2].lower()
        if lang in ["ru", "uz"]:
            return lang

    if db and callback.from_user:
        user = db.query(User).filter(
            User.telegram_id == callback.from_user.id
        ).first()
        if user and user.language:
            return user.language

    return "ru"

def get_language_from_user_id(user_id: int, db) -> str:
    """Get language from database by user ID"""
    user = db.query(User).filter(User.telegram_id == user_id).first()
    return user.language if user and user.language else "ru"
```

#### 1.5 Enhanced `get_text()` (Day 4)

**Task**: Extend `utils/helpers.py` with plural support

**New Features:**
- Plural forms: `get_text("requests.count", n=5)` → "5 заявок"
- Gender forms (optional): `get_text("profile.created", gender="m")`

**Example:**
```python
def get_text_plural(key: str, count: int, language: str = "ru") -> str:
    """Get text with plural forms"""
    locale = load_locale(language)

    # Russian plural rules: 1, 2-4, 5+
    # Uzbek is simpler: same form for all

    keys = key.split(".")
    value = locale
    for k in keys:
        value = value.get(k, key)

    if isinstance(value, dict) and "plural" in value:
        plural_rules = value["plural"]
        if language == "ru":
            if count % 10 == 1 and count % 100 != 11:
                return plural_rules.get("one", "").replace("{count}", str(count))
            elif count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]:
                return plural_rules.get("few", "").replace("{count}", str(count))
            else:
                return plural_rules.get("many", "").replace("{count}", str(count))
        else:
            return plural_rules.get("other", "").replace("{count}", str(count))

    return value
```

**Locale Example:**
```json
{
  "requests": {
    "count": {
      "plural": {
        "one": "{count} заявка",
        "few": "{count} заявки",
        "many": "{count} заявок"
      }
    }
  }
}
```

#### Phase 1 Deliverables

✅ `scripts/scan_hardcoded_strings.py` - working scanner
✅ `scripts/generate_locale_keys.py` - key generator
✅ `scripts/validate_translations.py` - validator
✅ `utils/language_helpers.py` - language detection helpers
✅ Enhanced `get_text()` with plural support
✅ Documentation: `docs/LOCALIZATION_GUIDE.md`

---

### **PHASE 2: Handlers Migration** (5-7 days)

**Target**: 30 handler files, ~1787 message calls

#### Priority Groups

**P0 - Critical User Flows (Days 1-2)**
1. `auth.py` - authorization/registration
2. `onboarding.py` - first-time user experience
3. `requests.py` - request creation (most used feature)

**P1 - Core Features (Days 3-4)**
4. `base.py` - main menu and basic commands
5. `admin.py` - admin panel
6. `my_shifts.py` - shift viewing
7. `shifts.py` - shift management

**P2 - Secondary Features (Days 5-7)**
8. All remaining 23 handler files

#### Migration Process (Per File)

**Step 1: Scan for Hardcoded Strings**
```bash
$ python scripts/scan_hardcoded_strings.py uk_management_bot/handlers/requests.py

Found 29 hardcoded strings in requests.py:
  Line 67: "📋 Создать заявку"
  Line 134: "Выберите категорию"
  Line 245: "✅ Заявка создана"
  ...
```

**Step 2: Generate Locale Keys**
```bash
$ python scripts/generate_locale_keys.py uk_management_bot/handlers/requests.py

Generating keys for requests.py...
✅ Created 29 keys under "requests.*" namespace
⚠️  uz.json needs 29 translations
```

**Step 3: Update Handler Code**
- Заменяем все кириллические литералы, участвующие в логике, на локализованные строки: условия `F.text`, значения кнопок, ответы бота, значения по умолчанию берём через `get_text()` либо ASCII-константы

**Before:**
```python
@router.message(Command("create_request"))
async def create_request_start(message: Message, state: FSMContext):
    await message.answer(
        "📋 Создать заявку\n\nВыберите категорию:",
        reply_markup=get_categories_keyboard()
    )
```

**After:**
```python
from uk_management_bot.utils.language_helpers import get_language_from_message
from uk_management_bot.utils.helpers import get_text

@router.message(Command("create_request"))
async def create_request_start(message: Message, state: FSMContext, db: Session):
    lang = get_language_from_message(message, db)

    await message.answer(
        get_text("requests.create_prompt", language=lang),
        reply_markup=get_categories_keyboard(lang)
    )
```

**Step 4: Update Tests**
```python
@pytest.mark.asyncio
async def test_create_request_start_ru(mock_message, mock_db):
    """Test request creation in Russian"""
    mock_message.from_user.language_code = "ru"
    await create_request_start(mock_message, FSMContext(), mock_db)

    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args[0][0]
    assert "📋 Создать заявку" in call_args

@pytest.mark.asyncio
async def test_create_request_start_uz(mock_message, mock_db):
    """Test request creation in Uzbek"""
    mock_message.from_user.language_code = "uz"
    await create_request_start(mock_message, FSMContext(), mock_db)

    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args[0][0]
    assert "📋 So'rov yaratish" in call_args  # Uzbek translation
```

**Step 5: Translate to Uzbek**

Work with translator or use Google Translate API for initial draft:
```json
// uz.json
{
  "requests": {
    "create_prompt": "📋 So'rov yaratish\n\nToifani tanlang:",
    "category_selected": "✅ Toifa tanlandi: {category}",
    "created_success": "✅ So'rov yaratildi: {request_number}"
  }
}
```

#### Phase 2 Milestones

**Day 2**: P0 handlers complete (auth, onboarding, requests)
**Day 4**: P1 handlers complete (base, admin, shifts)
**Day 7**: All 30 handlers migrated, tests passing

#### Phase 2 Deliverables

✅ 30 handler files migrated to `get_text()`
✅ 0 hardcoded strings in handlers/
✅ Все условия и кнопки в handlers используют локальные ключи/ASCII-значения (скан `rg "[\\u0400-\\u04FF]" handlers/` возвращает только комментарии)
✅ Updated tests for bilingual support
✅ ru.json and uz.json updated with all handler texts

---

### **PHASE 3: Services Migration** (4-5 days)

**Target**: 38 service files

#### Priority Groups

**P0 - User-Facing Services (Days 1-2)**
1. `notification_service.py` - all notifications
2. `request_service.py` + `async_request_service.py` - request operations
3. `auth_service.py` - authentication messages

**P1 - Core Business Logic (Days 3-4)**
4. `shift_service.py` + `async_shift_service.py` - shift management
5. `assignment_service.py` + `async_assignment_service.py` - assignment logic
6. `profile_service.py` - user profile operations

**P2 - AI & Advanced Services (Day 5)**
7. `smart_dispatcher.py`, `async_smart_dispatcher.py` - error messages only
8. `assignment_optimizer.py`, `async_assignment_optimizer.py` - logs/errors
9. `geo_optimizer.py`, `async_geo_optimizer.py` - logs/errors
10. `workload_predictor.py`, `async_workload_predictor.py` - logs/errors

**P3 - Infrastructure Services (Optional)**
11. Remaining 25+ service files

#### Service Migration Patterns

**Pattern 1: Notification Service**

**Before:**
```python
class NotificationService:
    async def notify_request_created(self, request: Request, user: User):
        message = f"✅ Заявка {request.request_number} создана"
        await self.bot.send_message(user.telegram_id, message)
```

**After:**
```python
from uk_management_bot.utils.helpers import get_text

class NotificationService:
    async def notify_request_created(self, request: Request, user: User):
        message = get_text(
            "notifications.request_created",
            language=user.language,
            request_number=request.request_number
        )
        await self.bot.send_message(user.telegram_id, message)
```

**Pattern 2: Service with Multiple User References**

**Before:**
```python
class RequestService:
    def assign_executor(self, request: Request, executor: User, manager: User):
        # Notify executor
        executor_msg = f"✅ Вам назначена заявка {request.request_number}"

        # Notify manager
        manager_msg = f"✅ Заявка {request.request_number} назначена на {executor.first_name}"
```

**After:**
```python
class RequestService:
    def assign_executor(self, request: Request, executor: User, manager: User):
        # Notify executor in their language
        executor_msg = get_text(
            "requests.assigned_to_you",
            language=executor.language,
            request_number=request.request_number
        )

        # Notify manager in their language
        manager_msg = get_text(
            "requests.assigned_to_executor",
            language=manager.language,
            request_number=request.request_number,
            executor_name=executor.first_name
        )
```

#### Phase 3 Deliverables

✅ 38 service files migrated
✅ All user-facing messages via `get_text()`
✅ Общие утилиты и сервисы не содержат кириллических литералов в логике (fallback-строки вынесены в локали/ASCII)
✅ Multi-user scenarios handled (different languages per user)
✅ Tests updated for services

#### Shared Utility Cleanup (Phase 3.b)

- `uk_management_bot/utils/helpers.py`: все значения по умолчанию и форматируемые подписи берём из локалей (никаких "Детали заявки" и т.п. непосредственно в коде)
- `uk_management_bot/utils/language_helpers.py`: словари названий языков переводим на ASCII либо выносим в локали (`get_text("languages.ru")` и т.п.)
- Общие ASCII-константы (например, fallback "UNKNOWN") документируем отдельно, чтобы не использовать кириллицу для плейсхолдеров
- Проверяем вспомогательные CLI-скрипты и сервисные модули: вывод и параметры по возможности делаем на английском; кириллица допустима только в help/README, но не в рабочих строках

---

### **PHASE 4: Keyboards Migration** (2-3 days)

**Target**: 20 keyboard files

#### Keyboard Migration Strategy

**Before:**
```python
# keyboards/requests.py
def get_categories_keyboard() -> InlineKeyboardMarkup:
    categories = [
        ("🔧 Сантехника", "plumbing"),
        ("⚡ Электрика", "electrical"),
        ("🚪 Столярка", "carpentry")
    ]

    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"cat_{code}")]
        for name, code in categories
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

**After:**
```python
# keyboards/requests.py
from uk_management_bot.utils.helpers import get_text

def get_categories_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Get categories keyboard in specified language"""
    categories = [
        (get_text("categories.plumbing", language=language), "plumbing"),
        (get_text("categories.electrical", language=language), "electrical"),
        (get_text("categories.carpentry", language=language), "carpentry")
    ]

    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"cat_{code}")]
        for name, code in categories
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

**Locale Files:**
```json
// ru.json
{
  "categories": {
    "plumbing": "🔧 Сантехника",
    "electrical": "⚡ Электрика",
    "carpentry": "🚪 Столярка"
  }
}

// uz.json
{
  "categories": {
    "plumbing": "🔧 Santexnika",
    "electrical": "⚡ Elektrika",
    "carpentry": "🚪 Duradgorlik"
  }
}
```

#### Handler Update Pattern

**Before:**
```python
@router.message(Command("categories"))
async def show_categories(message: Message):
    await message.answer(
        "Выберите категорию:",
        reply_markup=get_categories_keyboard()
    )
```

**After:**
```python
from uk_management_bot.utils.language_helpers import get_language_from_message

@router.message(Command("categories"))
async def show_categories(message: Message, db: Session):
    lang = get_language_from_message(message, db)

    await message.answer(
        get_text("requests.select_category", language=lang),
        reply_markup=get_categories_keyboard(lang)
    )
```

#### Priority List

**P1 - High-Traffic Keyboards (Day 1)**
1. `base.py` - main menu
2. `requests.py` - request categories, urgency, status
3. `admin.py` - admin actions

**P2 - Feature Keyboards (Day 2)**
4. `my_shifts.py` - shift actions
5. `shift_management.py` - shift planning
6. `profile.py` - profile editing

**P3 - Remaining Keyboards (Day 3)**
7. All other 14 keyboard files

#### Phase 4 Deliverables

✅ 20 keyboard files migrated
✅ All button texts via `get_text()`
✅ Keyboard functions accept `language` parameter
✅ All handlers updated to pass language to keyboards
✅ Строковые литералы в keyboards (callback data, сравнения) не содержат кириллицу; для пользовательского текста используем только локали

---

### **PHASE 5: Validation & Testing** (3-4 days)

#### 5.1 Automated Validation (Day 1)

**Run All Validators:**
```bash
# 1. Scan for hardcoded strings - should return 0
$ python scripts/scan_hardcoded_strings.py
✅ Scanned 88 files
✅ Found 0 hardcoded strings

# 1a. Дополнительная ASCII-проверка рантайм-кода
$ rg "[\u0400-\u04FF]" uk_management_bot/handlers uk_management_bot/services uk_management_bot/keyboards uk_management_bot/utils | grep -v "#"
# Результат должен быть пустым (допускаются только комментарии и docstring'и)

# 2. Validate translations completeness
$ python scripts/validate_translations.py
✅ ru.json: 847 keys
✅ uz.json: 847 keys
✅ 100% translation parity
✅ All parameter placeholders match

# 3. Check for missed files
$ grep -r "await.*answer(" uk_management_bot/handlers/ | grep -v "get_text"
# Should return nothing
```

#### 5.2 Integration Testing (Day 2)

**Test Matrix:**
| Module | RU Tests | UZ Tests | Status |
|--------|----------|----------|--------|
| auth.py | 12/12 ✅ | 12/12 ✅ | PASS |
| requests.py | 34/34 ✅ | 34/34 ✅ | PASS |
| my_shifts.py | 18/18 ✅ | 18/18 ✅ | PASS |
| ... | ... | ... | ... |

**Test Example:**
```python
@pytest.mark.parametrize("language", ["ru", "uz"])
@pytest.mark.asyncio
async def test_request_creation_multilang(language, mock_db, mock_bot):
    """Test request creation in both languages"""
    user = create_test_user(language=language)
    mock_db.add(user)

    result = await RequestService.create_request(
        user_id=user.telegram_id,
        category="plumbing",
        description="Test request",
        db=mock_db
    )

    # Check notification message language
    assert result.success
    notification = mock_bot.sent_messages[-1]

    if language == "ru":
        assert "✅ Заявка создана" in notification.text
    else:
        assert "✅ So'rov yaratildi" in notification.text
```

#### 5.3 Manual Testing (Day 3)

**Test Scenarios:**

1. **User Registration Flow (RU)**
   - Start bot → Select RU → Register → Verify all messages in Russian

2. **User Registration Flow (UZ)**
   - Start bot → Select UZ → Register → Verify all messages in Uzbek

3. **Request Creation (RU)**
   - Create request → Select category → Add details → Submit
   - Verify all prompts, keyboards, notifications in Russian

4. **Request Creation (UZ)**
   - Same flow in Uzbek

5. **Language Switching**
   - Register in RU → Change language to UZ → Verify UI updates

6. **Multi-User Scenarios**
   - User A (RU) creates request
   - User B (UZ) is assigned as executor
   - Verify each user gets notifications in their language

#### 5.4 Edge Case Testing (Day 4)

**Test Cases:**

1. **Missing Translation Key**
   ```python
   # Should fallback to key name, not crash
   text = get_text("nonexistent.key", language="uz")
   assert text == "nonexistent.key"
   ```

2. **Invalid Language Code**
   ```python
   # Should fallback to Russian
   text = get_text("auth.pending", language="invalid")
   assert text == "⏳ Ваша заявка на рассмотрении"
   ```

3. **Parameter Substitution**
   ```python
   text = get_text(
       "requests.created",
       language="uz",
       request_number="251029-001"
   )
   assert "251029-001" in text
   ```

4. **Plural Forms**
   ```python
   # Russian plurals
   assert "1 заявка" in get_text_plural("requests.count", 1, "ru")
   assert "2 заявки" in get_text_plural("requests.count", 2, "ru")
   assert "5 заявок" in get_text_plural("requests.count", 5, "ru")
   ```

#### 5.5 User Acceptance Testing (Day 4)

**Real User Testing Scenarios:**

1. **Native Russian Speaker Testing**
   - Test complete user journey in Russian
   - Verify cultural appropriateness of translations
   - Check for any awkward phrasing or terminology
   - Validate business context accuracy

2. **Native Uzbek Speaker Testing**
   - Test complete user journey in Uzbek
   - Verify translation quality and naturalness
   - Check cultural context appropriateness
   - Validate technical terminology accuracy

3. **Language Switching Testing**
   - Test seamless language switching mid-conversation
   - Verify UI updates immediately
   - Check for mixed-language displays
   - Test language persistence across sessions

4. **Multi-User Interaction Testing**
   - User A (RU) creates request
   - User B (UZ) gets assigned as executor
   - Verify each user receives notifications in their language
   - Test manager (RU) and executor (UZ) communication

5. **Accessibility Testing**
   - Test with screen readers in both languages
   - Verify emoji and special characters display correctly
   - Check text length doesn't break UI layouts
   - Test keyboard navigation in both languages

#### 5.6 Translation Quality Assessment (Day 4)

**Quality Metrics:**

1. **Consistency Check**
   ```python
   # scripts/translation_consistency_check.py
   def check_translation_consistency():
       """Check for consistent terminology across all translations"""
       # Same Russian term should map to same Uzbek term
       # Check for duplicate translations
       # Validate parameter placeholder consistency
   ```

2. **Cultural Appropriateness**
   - Review translations with native speakers
   - Check for cultural context accuracy
   - Validate business terminology
   - Ensure respectful language usage

3. **Technical Accuracy**
   - Verify technical terms are correctly translated
   - Check parameter placeholders work correctly
   - Validate plural forms are grammatically correct
   - Ensure emoji usage is appropriate

4. **Length and Layout Validation**
   ```python
   # scripts/layout_validation.py
   def validate_text_lengths():
       """Check that translations don't break UI layouts"""
       # Compare text lengths between RU and UZ
       # Check for overflow in buttons/keyboards
       # Validate line breaks and formatting
   ```

#### 5.7 Performance Impact Assessment (Day 4)

**Performance Metrics:**

1. **Locale Loading Performance**
   ```python
   # scripts/performance_benchmark.py
   def benchmark_locale_loading():
       """Measure locale loading performance impact"""
       # Time to load ru.json vs uz.json
       # Memory usage comparison
       # Cache efficiency validation
   ```

2. **Response Time Impact**
   - Measure bot response time before/after migration
   - Check for any noticeable delays
   - Validate async performance maintained
   - Test under load conditions

3. **Memory Usage Analysis**
   - Compare memory usage before/after
   - Check for memory leaks in locale loading
   - Validate garbage collection efficiency
   - Monitor long-running performance

#### 5.8 Cross-Platform Testing (Day 4)

**Platform Coverage:**

1. **Telegram Client Testing**
   - Test on different Telegram clients (Mobile, Desktop, Web)
   - Verify message formatting consistency
   - Check emoji display across platforms
   - Test keyboard rendering

2. **Browser Testing (Web App)**
   - Test FastAPI web interface in both languages
   - Verify form labels and buttons
   - Check error messages and validation
   - Test responsive design with longer text

3. **Database Testing**
   - Verify language field storage correctly
   - Test language switching persistence
   - Check query performance with language filters
   - Validate data integrity

#### Phase 5 Deliverables

✅ 0 hardcoded strings confirmed by scanner
✅ 100% translation parity (ru.json ↔ uz.json)
✅ All integration tests pass in both languages
✅ Manual testing completed for all flows
✅ Edge case testing passed
✅ User acceptance testing completed with native speakers
✅ Translation quality assessment completed
✅ Performance impact assessment completed
✅ Cross-platform testing completed
✅ Documentation: `docs/LOCALIZATION_TESTING.md`

---

### **PHASE 6: Improvements (Optional)** (2-3 days)

#### 6.1 Third Language Support (Day 1)

**Add English for Admin Panel:**

```json
// en.json
{
  "auth": {
    "pending": "⏳ Your registration is under review",
    "approved": "✅ You are approved",
    "blocked": "❌ Access blocked"
  },
  "admin": {
    "panel": "👨‍💼 Admin Panel",
    "users": "👥 User Management",
    "requests": "📋 Request Management"
  }
}
```

**Update Language Detection:**
```python
SUPPORTED_LANGUAGES = ["ru", "uz", "en"]

def get_language_from_message(message: Message, db=None) -> str:
    lang = message.from_user.language_code[:2].lower()
    return lang if lang in SUPPORTED_LANGUAGES else "ru"
```

#### 6.2 Translation Management UI (Day 2)

**Create Web Interface for Translators:**

```python
# web/translation_manager.py
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="web/templates")

@app.get("/translations")
async def translation_manager(request: Request):
    """Web UI for managing translations"""
    ru_locale = load_locale("ru")
    uz_locale = load_locale("uz")

    # Find missing translations
    missing_uz = find_missing_keys(ru_locale, uz_locale)

    return templates.TemplateResponse("translations.html", {
        "request": request,
        "ru_locale": ru_locale,
        "uz_locale": uz_locale,
        "missing": missing_uz
    })

@app.post("/translations/update")
async def update_translation(key: str, language: str, value: str):
    """Update a translation"""
    locale = load_locale(language)

    # Update nested key
    keys = key.split(".")
    nested = locale
    for k in keys[:-1]:
        nested = nested.setdefault(k, {})
    nested[keys[-1]] = value

    # Save back to file
    save_locale(language, locale)

    return {"success": True}
```

**Template:**
```html
<!-- web/templates/translations.html -->
<h1>Translation Manager</h1>

<table>
  <tr>
    <th>Key</th>
    <th>Russian</th>
    <th>Uzbek</th>
    <th>Status</th>
  </tr>
  {% for key, ru_text in ru_locale.items() %}
  <tr>
    <td>{{ key }}</td>
    <td>{{ ru_text }}</td>
    <td>
      <input type="text" value="{{ uz_locale.get(key, '') }}"
             data-key="{{ key }}" data-lang="uz">
    </td>
    <td>
      {% if key in uz_locale %}
        ✅ Translated
      {% else %}
        ❌ Missing
      {% endif %}
    </td>
  </tr>
  {% endfor %}
</table>
```

#### 6.3 Google Sheets Integration (Day 3)

**Sync Translations with Google Sheets:**

```python
# scripts/sync_translations_sheets.py
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def sync_to_sheets():
    """Upload translations to Google Sheets for collaborative editing"""
    # Authenticate
    scope = ['https://spreadsheets.google.com/feeds']
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        'google_credentials.json', scope
    )
    client = gspread.authorize(creds)

    # Open sheet
    sheet = client.open("UK Bot Translations").sheet1

    # Load locales
    ru_locale = load_locale("ru")
    uz_locale = load_locale("uz")

    # Flatten nested dicts
    ru_flat = flatten_dict(ru_locale)
    uz_flat = flatten_dict(uz_locale)

    # Write to sheets
    rows = [["Key", "Russian", "Uzbek", "Status"]]
    for key in sorted(ru_flat.keys()):
        ru_text = ru_flat[key]
        uz_text = uz_flat.get(key, "")
        status = "✅" if uz_text else "❌ NEEDS TRANSLATION"
        rows.append([key, ru_text, uz_text, status])

    sheet.update("A1", rows)
    print(f"✅ Uploaded {len(rows)-1} translations to Google Sheets")

def sync_from_sheets():
    """Download translations from Google Sheets back to locale files"""
    # ... reverse operation
```

**Run Sync:**
```bash
# Upload current state to sheets
$ python scripts/sync_translations_sheets.py --mode upload

# Translators edit in Google Sheets...

# Download updated translations
$ python scripts/sync_translations_sheets.py --mode download
```

#### 6.4 CI/CD Integration (Day 3)

**GitHub Actions Workflow:**

```yaml
# .github/workflows/localization_check.yml
name: Localization Check

on: [push, pull_request]

jobs:
  validate-translations:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Scan for hardcoded strings
        run: |
          python scripts/scan_hardcoded_strings.py
          if [ $? -ne 0 ]; then
            echo "❌ Found hardcoded strings!"
            exit 1
          fi

      - name: Validate translation completeness
        run: |
          python scripts/validate_translations.py
          if [ $? -ne 0 ]; then
            echo "❌ Translation validation failed!"
            exit 1
          fi

      - name: Run bilingual tests
        run: |
          pytest tests/ -k "test_*_multilang" -v
```

**Pre-commit Hook:**
```bash
# .git/hooks/pre-commit
#!/bin/bash

echo "🔍 Checking for hardcoded strings..."
python scripts/scan_hardcoded_strings.py

if [ $? -ne 0 ]; then
    echo "❌ Commit blocked: Found hardcoded strings"
    echo "Please use get_text() for all user-facing messages"
    exit 1
fi

echo "✅ Localization check passed"
exit 0
```

#### Phase 6 Deliverables (Optional)

✅ English language support added (3rd language)
✅ Web UI for translation management
✅ Google Sheets integration for collaborative translation
✅ CI/CD validation for localization
✅ Pre-commit hooks to prevent hardcoded strings

---

## 📊 RESOURCE ESTIMATES

### Time Breakdown

| Phase | Duration | Effort (person-days) |
|-------|----------|---------------------|
| Phase 1: Infrastructure | 3-4 days | 4 days |
| Phase 2: Handlers | 5-7 days | 7 days |
| Phase 3: Services | 4-5 days | 5 days |
| Phase 4: Keyboards | 2-3 days | 3 days |
| Phase 5: Testing | 3-4 days | 4 days |
| **Total (Core)** | **17-23 days** | **23 days** |
| Phase 6: Improvements | 2-3 days | 3 days |
| **Total (Full)** | **19-26 days** | **26 days** |

### Files to Modify

- **Handlers**: 30 files (~1787 message calls)
- **Services**: 38 files (~500 message calls)
- **Keyboards**: 20 files (~300 button texts)
- **Tests**: 67+ files (add bilingual tests)
- **Total**: ~155 files

### Translations Required

- **Unique strings**: 500-800 (estimated)
- **Current coverage**: ~40% (ru.json: 542 keys)
- **New strings to translate**: 300-450

### Team Composition

**Ideal Team:**
- 1 Senior Developer (infrastructure, complex migrations)
- 1 Mid-Level Developer (handler/service migrations)
- 1 Translator (RU ↔ UZ translations)
- 1 QA Engineer (testing)

**Solo Developer:**
- Add +30% time for translation work
- Add +20% time for testing
- Total: ~30-35 days

---

## ✅ SUCCESS CRITERIA

### Technical Metrics

1. **Zero Hardcoded Strings**
   - `scan_hardcoded_strings.py` returns 0 results
   - All user-facing text via `get_text()`

2. **100% Translation Coverage**
   - ru.json and uz.json have identical keys
   - `validate_translations.py` passes with 0 errors

3. **All Tests Pass**
   - Existing tests pass in both RU and UZ
   - New bilingual tests added for critical flows
   - Test coverage ≥ 82% (current level maintained)

4. **Dynamic Language Detection**
   - No `lang = "ru"` hardcoded anywhere
   - Automatic detection from Telegram settings
   - Fallback to database User.language

5. **Performance**
   - No noticeable latency increase
   - Locale files cached efficiently
   - Lazy loading for large locale files

### User Experience Metrics

1. **Language Consistency**
   - All UI elements in selected language
   - Notifications in user's language
   - Keyboards in user's language

2. **Language Switching**
   - Users can change language in profile
   - UI updates immediately
   - No mixed-language displays

3. **Multi-User Scenarios**
   - User A (RU) and User B (UZ) interact correctly
   - Each gets messages in their language
   - No cross-language contamination

### Documentation

✅ `docs/LOCALIZATION_GUIDE.md` - developer guide
✅ `docs/LOCALIZATION_TESTING.md` - testing guide
✅ `docs/TRANSLATION_WORKFLOW.md` - translator guide
✅ Updated `README.md` with localization info

---

## 🚨 RISKS & MITIGATION

### Risk 1: Incomplete Translation Discovery

**Risk**: Missing some hardcoded strings during scanning

**Mitigation:**
- Run scanner multiple times at different phases
- Manual code review of critical modules
- Add pre-commit hook to catch new hardcoded strings

### Risk 2: Translation Quality

**Risk**: Google Translate produces poor UZ translations

**Mitigation:**
- Hire professional UZ translator for final review
- Get feedback from UZ-speaking users
- Iterate on translations based on feedback

### Risk 3: Test Breakage

**Risk**: Existing tests break during migration

**Mitigation:**
- Update tests incrementally per module
- Keep tests green after each handler/service migration
- Have rollback plan (git branches)

### Risk 4: Performance Degradation

**Risk**: Loading locale files on every request slows down bot

**Mitigation:**
- Cache loaded locale files in memory
- Use singleton pattern for locale loader
- Lazy load only used sections for large locales

### Risk 5: Timeline Overrun

**Risk**: Migration takes longer than 26 days

**Mitigation:**
- Start with P0/P1 modules (core features)
- Can deploy partially (P0/P1 only)
- P2/P3 modules can be done in later sprint

---

## 📋 CHECKLIST

### Phase 1: Infrastructure
- [ ] `scripts/scan_hardcoded_strings.py` created
- [ ] `scripts/generate_locale_keys.py` created
- [ ] `scripts/validate_translations.py` created
- [ ] `utils/language_helpers.py` created
- [ ] Enhanced `get_text()` with plural support
- [ ] `docs/LOCALIZATION_GUIDE.md` written

### Phase 2: Handlers
- [ ] P0 handlers migrated (auth, onboarding, requests)
- [ ] P1 handlers migrated (base, admin, shifts)
- [ ] P2 handlers migrated (remaining 23 files)
- [ ] All handler tests updated and passing
- [ ] No hardcoded strings in handlers/
- [ ] Кириллица отсутствует в рабочих строках handlers (проверка `rg "[\\u0400-\\u04FF]" uk_management_bot/handlers` без результатов)

### Phase 3: Services
- [ ] P0 services migrated (notification, request, auth)
- [ ] P1 services migrated (shift, assignment, profile)
- [ ] P2 services migrated (AI services - errors only)
- [ ] P3 services migrated (remaining infrastructure)
- [ ] All service tests updated and passing
- [ ] Утилиты/сервисы не содержат кириллицу во вводе/выводе (helpers, language_helpers и др.)

### Phase 4: Keyboards
- [ ] P1 keyboards migrated (base, requests, admin)
- [ ] P2 keyboards migrated (shifts, profile)
- [ ] P3 keyboards migrated (remaining 14 files)
- [ ] All keyboard functions accept `language` parameter
- [ ] All handlers pass language to keyboards
- [ ] Кнопки и callback data не содержат кириллицу (все тексты идут из локалей)

### Phase 5: Testing
- [ ] Scanner confirms 0 hardcoded strings
- [ ] Validator confirms 100% translation parity
- [ ] All integration tests pass (RU/UZ)
- [ ] Manual testing complete for all flows
- [ ] Edge case testing passed
- [ ] User acceptance testing with native speakers completed
- [ ] Translation quality assessment completed
- [ ] Performance impact assessment completed
- [ ] Cross-platform testing completed
- [ ] `docs/LOCALIZATION_TESTING.md` written
- [ ] ASCII-проверка runtime-кода (`rg "[\\u0400-\\u04FF]" ...`) зафиксирована в отчёте

### Phase 6: Improvements (Optional)
- [ ] English language support added
- [ ] Translation management web UI created
- [ ] Google Sheets integration working
- [ ] CI/CD validation added
- [ ] Pre-commit hooks installed

---

## 📚 REFERENCES

### Related Documentation
- `MemoryBank/tasks.md` - Main task tracking
- `CLAUDE.md` - Project overview and guidelines
- `uk_management_bot/config/locales/` - Locale files
- `uk_management_bot/utils/helpers.py` - Current locale system

### External Resources
- [Python i18n Best Practices](https://phrase.com/blog/posts/i18n-beginners-guide-python/)
- [Telegram Bot Localization](https://core.telegram.org/bots/api#formatting-options)
- [Russian Plural Rules](https://unicode-org.github.io/cldr-staging/charts/37/supplemental/language_plural_rules.html)
- [Uzbek Language Guide](https://en.wikipedia.org/wiki/Uzbek_language)

---

**Document Version**: 1.0
**Last Updated**: 29.10.2025
**Next Review**: After Phase 1 completion
**Status**: 🚀 Planning Complete - Ready for Phase 1 Kickoff
