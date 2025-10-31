# TASK 17 - Phase 2: Handler Migration Strategy

**Date**: 30 October 2025
**Status**: 🚀 In Progress
**Current Todo**: Migrate 6,590 hardcoded strings from handlers/

---

## 📊 Current State Analysis

### Scan Results (30 Oct 2025)
```
Total hardcoded strings in handlers/: 6,590

Top 10 Files by String Count:
  1. requests.py            - 1,083 strings (16.4%)
  2. admin.py               - 957 strings (14.5%)
  3. shift_management.py    - 923 strings (14.0%)
  4. user_management.py     - 343 strings (5.2%)
  5. address_apartments.py  - 327 strings (5.0%)
  6. employee_management.py - 210 strings (3.2%)
  7. quarterly_planning.py  - 199 strings (3.0%)
  8. request_acceptance.py  - 181 strings (2.7%)
  9. user_apartments.py     - 176 strings (2.7%)
 10. my_shifts.py           - 164 strings (2.5%)

Total in top 10: 4,563 strings (69.2% of total)
```

### Current Locale File Status
- **ru.json**: ~5,700 keys (+839% growth from initial 607)
- **uz.json**: ~5,700 keys (+839% growth from initial 607)
- **Key parity**: 99.9% (1 extra key in UZ - minor issue)
- **Translation status**: 100% (no [TRANSLATE] markers, no Russian strings)
- **Validation issues**: 8 format mismatches, 1 extra key

### Already Migrated Files (0 hardcoded strings)
✅ Files with proper `get_text()` usage:
- **NONE** - All 30 handler files need migration

---

## 🎯 Phase 2 Migration Strategy

### Approach: Batch Migration with Automated Tools

We have **6,590 strings** to migrate. Manual migration is impractical. Strategy:

1. **Automated Key Extraction** (Day 1-2)
   - Use `generate_locale_keys.py` in **auto mode**
   - Generate all keys programmatically
   - Add to ru.json with original Russian text
   - Add to uz.json with `[TRANSLATE]` placeholders

2. **Code Refactoring** (Day 3-5)
   - Semi-automated search & replace
   - Update each file to use `get_text()`
   - Add language parameter to all functions
   - Update imports

3. **Batch Translation** (Day 6-7)
   - Use Google Translate API for initial UZ translations
   - Manual review of critical user-facing strings
   - Update uz.json

4. **Testing & Validation** (Day 8-9)
   - Run `validate_translations.py`
   - Test bilingual flows
   - Fix any issues

---

## 📝 Detailed Action Plan

### Day 1: Automated Key Generation (Top 3 Files)

#### Step 1.1: Generate Keys for requests.py (1,083 strings)
```bash
# Scan to JSON
python3 scripts/scan_hardcoded_strings.py \
  --path uk_management_bot/handlers/requests.py \
  --format json \
  --output scans/requests_scan.json

# Generate keys (auto mode)
python3 scripts/generate_locale_keys.py \
  --input scans/requests_scan.json \
  --mode auto \
  --ru-locale uk_management_bot/config/locales/ru.json \
  --uz-locale uk_management_bot/config/locales/uz.json \
  --output-mapping mappings/requests_mapping.json
```

**Expected Output**:
- ru.json: +1,083 keys (607 → 1,690)
- uz.json: +1,083 keys with `[TRANSLATE]` markers
- Mapping file for code refactoring

#### Step 1.2: Generate Keys for admin.py (957 strings)
```bash
python3 scripts/scan_hardcoded_strings.py \
  --path uk_management_bot/handlers/admin.py \
  --format json \
  --output scans/admin_scan.json

python3 scripts/generate_locale_keys.py \
  --input scans/admin_scan.json \
  --mode auto \
  --ru-locale uk_management_bot/config/locales/ru.json \
  --uz-locale uk_management_bot/config/locales/uz.json \
  --output-mapping mappings/admin_mapping.json
```

**Expected Output**:
- ru.json: +957 keys (1,690 → 2,647)
- uz.json: +957 keys with `[TRANSLATE]` markers

#### Step 1.3: Generate Keys for shift_management.py (923 strings)
```bash
python3 scripts/scan_hardcoded_strings.py \
  --path uk_management_bot/handlers/shift_management.py \
  --format json \
  --output scans/shift_management_scan.json

python3 scripts/generate_locale_keys.py \
  --input scans/shift_management_scan.json \
  --mode auto \
  --ru-locale uk_management_bot/config/locales/ru.json \
  --uz-locale uk_management_bot/config/locales/uz.json \
  --output-mapping mappings/shift_management_mapping.json
```

**Expected Output**:
- ru.json: +923 keys (2,647 → 3,570)
- uz.json: +923 keys with `[TRANSLATE]` markers

### Day 1 Target
- **ru.json**: 607 → 3,570 keys (+2,963 keys, 45% of total work)
- **uz.json**: 607 → 3,570 keys (+2,963 `[TRANSLATE]` placeholders)
- **3 mapping files** created for code refactoring

---

### Day 2: Code Refactoring (Top 3 Files)

#### Refactoring Pattern

**Before** (requests.py:349):
```python
await message.answer("Начинаем создание заявки…", reply_markup=ReplyKeyboardRemove())
```

**After**:
```python
from uk_management_bot.utils.language_helpers import get_language_for_user
from uk_management_bot.utils.helpers import get_text

lang = await get_language_for_user(message.from_user.id, db, message)
await message.answer(
    get_text("requests.create_start", language=lang),
    reply_markup=ReplyKeyboardRemove()
)
```

#### Semi-Automated Approach

Use mapping file from `generate_locale_keys.py`:
```json
{
  "Начинаем создание заявки…": {
    "key": "requests.create_start",
    "file": "uk_management_bot/handlers/requests.py",
    "line": 349
  }
}
```

Create a **refactoring script** (`scripts/refactor_handler.py`):
```python
#!/usr/bin/env python3
"""
Semi-automated code refactoring for localization migration
"""
import json
import re
from pathlib import Path

def refactor_handler(file_path: str, mapping_file: str):
    """Replace hardcoded strings with get_text() calls"""

    with open(mapping_file) as f:
        mappings = json.load(f)

    with open(file_path) as f:
        code = f.read()

    # Add imports if not present
    if "from uk_management_bot.utils.helpers import get_text" not in code:
        # Find first import block and add
        code = add_imports(code)

    # Replace each string
    for original_string, info in mappings.items():
        key = info["key"]

        # Escape special regex characters
        escaped = re.escape(original_string)

        # Pattern: "string" → get_text("key", language=lang)
        pattern = f'"{escaped}"'
        replacement = f'get_text("{key}", language=lang)'

        code = code.replace(pattern, replacement)

        # Pattern: f"string" → get_text("key", language=lang)
        pattern = f'f"{escaped}"'
        code = code.replace(pattern, replacement)

    # Write back
    with open(file_path, 'w') as f:
        f.write(code)

    print(f"✅ Refactored {file_path}")
```

**Usage**:
```bash
python3 scripts/refactor_handler.py \
  --file uk_management_bot/handlers/requests.py \
  --mapping mappings/requests_mapping.json
```

#### Day 2 Targets
- ✅ requests.py refactored
- ✅ admin.py refactored
- ✅ shift_management.py refactored
- ✅ All handlers use `get_text()`
- ✅ Language parameter added to all functions

---

### Day 3-4: Batch Translation to Uzbek

#### Google Translate API Integration

Create `scripts/batch_translate.py`:
```python
#!/usr/bin/env python3
"""
Batch translate Russian locale keys to Uzbek using Google Translate API
"""
from googletrans import Translator
import json
import time

def batch_translate_uz(ru_locale_path, uz_locale_path):
    """Translate all [TRANSLATE] placeholders in uz.json"""

    with open(ru_locale_path) as f:
        ru_locale = json.load(f)

    with open(uz_locale_path) as f:
        uz_locale = json.load(f)

    translator = Translator()

    # Flatten dicts
    ru_flat = flatten_dict(ru_locale)
    uz_flat = flatten_dict(uz_locale)

    to_translate = []
    for key, value in uz_flat.items():
        if value == "[TRANSLATE]":
            ru_text = ru_flat.get(key)
            if ru_text:
                to_translate.append((key, ru_text))

    print(f"Found {len(to_translate)} strings to translate")

    # Translate in batches of 100
    for i in range(0, len(to_translate), 100):
        batch = to_translate[i:i+100]

        for key, ru_text in batch:
            try:
                # Translate Russian → Uzbek
                result = translator.translate(ru_text, src='ru', dest='uz')
                uz_flat[key] = result.text

                print(f"✅ {key}: {ru_text[:50]}... → {result.text[:50]}...")

                # Rate limiting
                time.sleep(0.1)
            except Exception as e:
                print(f"❌ Failed to translate {key}: {e}")
                uz_flat[key] = f"[TRANSLATE: {ru_text}]"

    # Unflatten and save
    uz_locale = unflatten_dict(uz_flat)

    with open(uz_locale_path, 'w', encoding='utf-8') as f:
        json.dump(uz_locale, f, ensure_ascii=False, indent=2)

    print(f"✅ Translated {len(to_translate)} strings to Uzbek")
```

**Usage**:
```bash
python3 scripts/batch_translate.py \
  --ru-locale uk_management_bot/config/locales/ru.json \
  --uz-locale uk_management_bot/config/locales/uz.json
```

#### Manual Review (Critical Strings Only)

Focus on:
- User-facing notifications
- Error messages
- Button labels
- Status messages

**Estimated time**: 4-6 hours for top 200 critical strings

---

### Day 5: Remaining Handlers (Batch Processing)

Use the same workflow for remaining 27 handlers:

```bash
# Generate all remaining keys
for file in uk_management_bot/handlers/*.py; do
  python3 scripts/scan_hardcoded_strings.py \
    --path "$file" \
    --format json \
    --output "scans/$(basename $file .py)_scan.json"

  python3 scripts/generate_locale_keys.py \
    --input "scans/$(basename $file .py)_scan.json" \
    --mode auto \
    --ru-locale uk_management_bot/config/locales/ru.json \
    --uz-locale uk_management_bot/config/locales/uz.json \
    --output-mapping "mappings/$(basename $file .py)_mapping.json"
done

# Refactor all files
for file in uk_management_bot/handlers/*.py; do
  python3 scripts/refactor_handler.py \
    --file "$file" \
    --mapping "mappings/$(basename $file .py)_mapping.json"
done

# Batch translate all [TRANSLATE] markers
python3 scripts/batch_translate.py \
  --ru-locale uk_management_bot/config/locales/ru.json \
  --uz-locale uk_management_bot/config/locales/uz.json
```

---

## 📊 Success Metrics

### Phase 2 Completion Criteria
- ✅ **0 hardcoded strings** in all 30 handler files
- ✅ **6,590+ keys** added to ru.json and uz.json
- ✅ **100% translation parity** (ru.json ↔ uz.json)
- ✅ **All handlers use `get_text()`** with language parameter
- ✅ **Scanner reports 0 findings** in handlers/
- ✅ **Validator passes with 0 errors**

### Expected Final State
```
ru.json: 607 → 7,197 keys (+6,590 keys)
uz.json: 607 → 7,197 keys (+6,590 translations)
```

---

## 🚧 Potential Challenges

### Challenge 1: F-strings with Variables
**Problem**: `f"Заявка {request_number} создана"`

**Solution**: Use parameter substitution in `get_text()`
```python
# ru.json
"requests.created": "Заявка {request_number} создана"

# Code
get_text("requests.created", language=lang, request_number=request_number)
```

### Challenge 2: Multi-line Strings
**Problem**: Long notification messages

**Solution**: Use triple-quoted strings in JSON
```json
{
  "requests.notification_long": "Заявка создана\n\nНомер: {request_number}\nКатегория: {category}\nАдрес: {address}"
}
```

### Challenge 3: Context-Dependent Translations
**Problem**: Same Russian word, different UZ translations

**Solution**: Create separate keys with context
```json
{
  "requests.status_field": "Статус:",
  "profile.status_field": "Статус:",
  "admin.status_action": "Изменить статус"
}
```

---

## 🎯 Next Steps

1. ✅ Create strategy document (this file)
2. ⏳ Create directories for scans and mappings
3. ⏳ Run Day 1 key generation for top 3 files
4. ⏳ Create refactoring script
5. ⏳ Test refactoring on requests.py
6. ⏳ Create batch translation script
7. ⏳ Full migration of all handlers

---

**Document Version**: 1.0
**Last Updated**: 30 October 2025
**Status**: 🚀 Ready to Execute
