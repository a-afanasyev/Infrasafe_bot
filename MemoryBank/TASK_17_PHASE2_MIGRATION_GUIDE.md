# TASK 17 - Phase 2 Migration Guide

**Date**: 29 October 2025
**Status**: 📋 Ready to Start
**Phase**: 2 of 6 - Handler Migration
**Target**: 6,639 strings in 30 handler files

---

## 📋 Overview

Phase 2 focuses on migrating all handler files to use the unified localization system. This is the most critical phase as handlers contain user-facing text that directly impacts UX.

**Timeline**: 5-7 days
**Priority**: P0 (Critical)

---

## 🎯 Migration Workflow (Per File)

### Step-by-Step Process

For each handler file, follow this workflow:

#### 1. **Identify Hardcoded Strings** (15-30 min)

```bash
# Manual inspection of file
# Look for:
# - answer() calls with Russian text
# - send_message() with Russian text
# - edit_text() with Russian text
# - F-strings with Cyrillic
# - Inline keyboard button text
# - Error messages
```

#### 2. **Create Locale Keys** (30-45 min)

```python
# For auth.py example:
{
  "auth": {
    "login_button": "🔑 Войти",
    "already_authorized": "Вы уже авторизованы.",
    "login_success": "✅ Авторизация выполнена. Вы вошли как заявитель.",
    ...
  }
}
```

**Key Naming Convention**:
- Section: `auth`, `requests`, `shifts`, etc.
- Action: `login_success`, `create_error`, `update_confirm`
- Descriptive: clear purpose from name

#### 3. **Update ru.json** (15 min)

```bash
# Open uk_management_bot/config/locales/ru.json
# Add new keys to appropriate section
# Save and validate JSON syntax
```

#### 4. **Update uz.json** (15 min)

```bash
# Open uk_management_bot/config/locales/uz.json
# Add same keys with Uzbek translations
# Use [TRANSLATE] placeholder if translation not ready
# Maintain 100% key parity with ru.json
```

#### 5. **Migrate Handler Code** (1-3 hours depending on file size)

**Before**:
```python
await message.answer("Вы уже авторизованы.")
```

**After**:
```python
from uk_management_bot.utils.language_helpers import get_language_for_user

# Get user language
language = await get_language_for_user(message.from_user.id, db, message)

# Use localized text
await message.answer(get_text("auth.already_authorized", language=language))
```

**Best Practices**:
- Import `get_text` and language helpers at top of file
- Get user language once per handler function
- Pass `language` parameter to all `get_text()` calls
- Use format parameters for dynamic values: `get_text("key", language=lang, param=value)`

#### 6. **Test in Docker** (30 min)

```bash
# Copy updated files to container
docker cp uk_management_bot/handlers/auth.py uk-management-bot-dev:/app/uk_management_bot/handlers/
docker cp uk_management_bot/config/locales/ru.json uk-management-bot-dev:/app/uk_management_bot/config/locales/
docker cp uk_management_bot/config/locales/uz.json uk-management-bot-dev:/app/uk_management_bot/config/locales/

# Restart bot
docker restart uk-management-bot-dev

# Test both languages
# 1. Set user language to RU and test flows
# 2. Set user language to UZ and test flows
# 3. Check logs for errors
```

#### 7. **Validate** (15 min)

```bash
# Run validator
python scripts/validate_translations.py

# Verify:
# - No format string mismatches
# - All keys exist in both files
# - No [TRANSLATE] placeholders remaining (or documented)
```

#### 8. **Commit Changes** (5 min)

```bash
git add uk_management_bot/handlers/auth.py
git add uk_management_bot/config/locales/ru.json
git add uk_management_bot/config/locales/uz.json
git commit -m "feat: Migrate auth.py to unified localization (TASK 17 Phase 2)

- Added 26 locale keys for auth flows
- Replaced all hardcoded strings with get_text()
- Tested in RU/UZ languages
- Part of TASK 17 Phase 2: Handler Migration"
```

**Total Time Per File**: 3-5 hours (average)

---

## 📊 Phase 2 Roadmap

### Priority P0 - Critical Handlers (Days 1-2)

#### File 1: **auth.py** (111 strings, ~4 hours)

**Hardcoded Strings Identified**: 26 unique messages

**Keys to Add** (ru.json + uz.json):
```json
{
  "auth": {
    "login_button": "🔑 Войти",
    "already_authorized": "Вы уже авторизованы.",
    "login_success": "✅ Авторизация выполнена. Вы вошли как заявитель.",
    "login_failed": "Не удалось выполнить авторизацию. Попробуйте позже или обратитесь к менеджеру.",
    "registration_pending": "📋 Ваша регистрация уже на рассмотрении. Пожалуйста, дождитесь решения администратора.",
    "enter_full_name": "📝 Пожалуйста, введите ваше полное имя (ФИО):",
    "full_name_invalid": "❌ Пожалуйста, введите полное имя (Фамилия Имя Отчество):",
    "confirm_position_prompt": "📝 Подтвердите, что вы согласны с указанной ролью и специализацией:",
    "confirm_button": "✅ Подтвердить",
    "cancel_button": "❌ Отменить",
    "error_try_again": "❌ Произошла ошибка. Попробуйте еще раз.",
    "enter_phone_label": "Введите ваш номер телефона:",
    "phone_invalid": "❌ Пожалуйста, введите корректный номер телефона (например: +7 999 123-45-67):",
    "phone_too_short": "❌ Номер телефона слишком короткий. Пожалуйста, введите полный номер:",
    "confirm_data_prompt": "📝 Подтвердите, что все данные указаны верно:",
    "new_registration_admin_title": "📝 Новая заявка на регистрацию:",
    "user_field": "👤 Пользователь:",
    "phone_field": "📱 Телефон:",
    "telegram_id_field": "🆔 Telegram ID:",
    "role_field": "🎯 Роль:",
    "specialization_field": "🛠️ Специализация:",
    "date_field": "📅 Дата:",
    "registration_complete_title": "✅ Регистрация завершена!",
    "full_name_field": "👤 ФИО:",
    "registration_submitted_message": "📋 Ваша заявка отправлена администратору на рассмотрение.\nВы получите уведомление, когда заявка будет рассмотрена.",
    "registration_cancelled": "❌ Регистрация отменена."
  }
}
```

**Code Changes**:
- Add language detection at start of each handler
- Replace 26 hardcoded strings with `get_text()` calls
- Update inline keyboard buttons with localized text
- Test registration flow in both languages

**Testing Checklist**:
- [  ] Login button works in RU/UZ
- [  ] Registration flow completes in RU
- [  ] Registration flow completes in UZ
- [  ] Admin notifications show correct language
- [  ] Error messages display correctly
- [  ] Keyboard buttons are localized

---

#### File 2: **onboarding.py** (114 strings, ~4 hours)

**Estimated Keys**: ~30 unique messages
**Focus Areas**:
- Welcome messages
- Onboarding steps
- Tutorial text
- Completion messages

**Status**: Not started

---

#### File 3: **requests.py** (1,083 strings, ~12-16 hours)

**Estimated Keys**: ~150-200 unique messages
**Focus Areas**:
- Request creation flow
- Request viewing/listing
- Status updates
- Assignment messages
- Comments and updates

**Special Considerations**:
- Largest file in codebase for migration
- Most critical user-facing flow
- Requires extensive testing
- Consider breaking into multiple sessions

**Recommendation**: Split into 3 sub-tasks:
1. Request creation (300 strings, 4 hours)
2. Request management (400 strings, 6 hours)
3. Request status/comments (383 strings, 4 hours)

**Status**: Not started

---

### Priority P1 - High Priority Handlers (Days 3-4)

#### File 4: **base.py** (92 strings, ~3 hours)
- Base handler functionality
- Common messages
- Navigation

#### File 5: **admin.py** (957 strings, ~10-12 hours)
- Admin panel messages
- User management
- System settings
- Statistics displays

#### File 6: **shifts.py** (126 strings, ~4 hours)
- Shift management
- Shift assignment
- Shift notifications

#### File 7: **my_shifts.py** (164 strings, ~5 hours)
- Personal shift view
- Shift calendar
- Shift details

**Total P1 Time**: 22-24 hours (Days 3-4)

---

### Priority P2 - Medium Priority Handlers (Days 5-7)

Remaining 23 handler files (~3,000 strings)

**Batch 1 (Day 5)**: 8 files, ~1,000 strings
- address_apartments.py (327)
- user_management.py (343)
- employee_management.py (210)
- quarterly_planning.py (199)
- request_acceptance.py (181)
- user_apartments.py (176)
- address_buildings.py (164)
- address_yards.py (159)

**Batch 2 (Day 6)**: 8 files, ~1,000 strings
- user_verification.py (124)
- address_moderation.py (123)
- user_apartment_selection.py (117)
- unaccepted_requests.py (112)
- request_reports.py (107)
- request_assignment.py (106)
- request_status_management.py (150)
- profile_editing.py (141)

**Batch 3 (Day 7)**: 7 files, ~800 strings
- request_comments.py (90)
- shift_transfer.py (89)
- user_yards_management.py (59)
- clarification_replies.py (58)
- health.py (33)
- __init__.py (1)
- others

---

## 🛠️ Tools & Helpers

### Quick Commands

**Copy file to container:**
```bash
docker cp uk_management_bot/handlers/FILE.py uk-management-bot-dev:/app/uk_management_bot/handlers/
```

**Copy locales to container:**
```bash
docker cp uk_management_bot/config/locales/ru.json uk-management-bot-dev:/app/uk_management_bot/config/locales/
docker cp uk_management_bot/config/locales/uz.json uk-management-bot-dev:/app/uk_management_bot/config/locales/
```

**Restart bot:**
```bash
docker restart uk-management-bot-dev
```

**Check logs:**
```bash
docker logs uk-management-bot-dev --tail 50 --follow
```

**Validate translations:**
```bash
python scripts/validate_translations.py
```

### Code Templates

**Handler with language detection:**
```python
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.language_helpers import get_language_for_user

@router.message(Command("example"))
async def example_handler(message: Message, db: Session):
    # Get user language
    language = await get_language_for_user(
        message.from_user.id,
        db,
        message
    )

    # Use localized text
    await message.answer(
        get_text("section.key", language=language)
    )

    # With parameters
    await message.answer(
        get_text("section.key_with_param", language=language, name=message.from_user.first_name)
    )
```

**Inline keyboard with localization:**
```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(
        text=get_text("buttons.confirm", language=language),
        callback_data="confirm"
    )],
    [InlineKeyboardButton(
        text=get_text("buttons.cancel", language=language),
        callback_data="cancel"
    )]
])
```

---

## 📝 Translation Notes

### Uzbek Translation Guidelines

For strings marked with `[TRANSLATE]`:

1. **Keep emojis**: 🔑, ✅, ❌, 📝, etc.
2. **Maintain formatting**: Line breaks, bold, etc.
3. **Preserve placeholders**: `{name}`, `{count}`, etc.
4. **Consider context**: Professional tone for admin, friendly for users
5. **Test character length**: Some Uzbek phrases are longer

### Common Translations (Reference)

| Russian | Uzbek | English |
|---------|-------|---------|
| Войти | Kirish | Login |
| Отменить | Bekor qilish | Cancel |
| Подтвердить | Tasdiqlash | Confirm |
| Сохранить | Saqlash | Save |
| Удалить | O'chirish | Delete |
| Назад | Orqaga | Back |
| Далее | Keyingi | Next |
| Готово | Tayyor | Done |
| Ошибка | Xato | Error |
| Успешно | Muvaffaqiyatli | Success |

---

## ✅ Daily Checklist

### Day 1-2: P0 Handlers
- [  ] auth.py migrated and tested
- [  ] onboarding.py migrated and tested
- [ ] requests.py part 1/3 migrated
- [  ] All P0 tests pass in RU/UZ
- [  ] Commit and push changes

### Day 3-4: P1 Handlers
- [  ] base.py migrated
- [  ] admin.py migrated (largest after requests.py)
- [  ] shifts.py migrated
- [  ] my_shifts.py migrated
- [  ] All P1 tests pass in RU/UZ

### Day 5-7: P2 Handlers
- [  ] Batch 1 (8 files) migrated
- [  ] Batch 2 (8 files) migrated
- [  ] Batch 3 (7 files) migrated
- [  ] All handlers tested
- [  ] Zero hardcoded strings in handlers/ verified

---

## 🚨 Common Issues & Solutions

### Issue 1: Language not detected

**Symptom**: Always shows Russian text
**Solution**: Check language detection logic, ensure `get_language_for_user()` is called

### Issue 2: Format string mismatch

**Symptom**: `KeyError` when using `{param}`
**Solution**: Ensure same placeholders in RU and UZ strings

### Issue 3: Missing translation key

**Symptom**: Text shows as key name (e.g., "auth.login_success")
**Solution**: Check key exists in both ru.json and uz.json

### Issue 4: Unicode encoding errors

**Symptom**: Broken Cyrillic characters
**Solution**: Ensure all files use UTF-8 encoding

---

## 📊 Progress Tracking

**Phase 2 Progress**: 0% (0/30 files)

| Priority | Files | Strings | Completed | Remaining |
|----------|-------|---------|-----------|-----------|
| P0 | 3 | 1,308 | 0 | 3 |
| P1 | 4 | 1,339 | 0 | 4 |
| P2 | 23 | 3,992 | 0 | 23 |
| **Total** | **30** | **6,639** | **0** | **30** |

---

## 🎯 Success Criteria

Phase 2 is complete when:

- ✅ All 30 handler files migrated
- ✅ 0 hardcoded Russian/Uzbek strings in handlers/
- ✅ 100% key parity between ru.json and uz.json
- ✅ All handler flows work in both RU and UZ
- ✅ Integration tests pass in both languages
- ✅ Manual testing complete for critical flows

---

## 📚 Resources

- **Main Plan**: `MemoryBank/TASK_17_LOCALIZATION_MIGRATION.md`
- **Phase 1 Report**: `MemoryBank/TASK_17_PHASE1_COMPLETION_REPORT.md`
- **Tools**:
  - `scripts/scan_hardcoded_strings.py`
  - `scripts/generate_locale_keys.py`
  - `scripts/validate_translations.py`
- **Helpers**: `uk_management_bot/utils/language_helpers.py`

---

**Document Version**: 1.0
**Last Updated**: 29 October 2025
**Status**: Ready for implementation
