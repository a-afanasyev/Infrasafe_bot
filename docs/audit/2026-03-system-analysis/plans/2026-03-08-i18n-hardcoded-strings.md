# i18n: Замена хардкод-строк на русском языке

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Заменить все хардкод-строки на русском языке на вызовы `get_text()` с ключами локализации, чтобы бот корректно работал на всех поддерживаемых языках (ru, uz).

**Architecture:** Каждая user-facing строка заменяется на `get_text("section.key", language=language)`. Новые ключи добавляются в `ru.json` и `uz.json`. Keyboard-функции получают параметр `language`. Handlers используют middleware-injected `language` параметр.

**Tech Stack:** Python 3.11, aiogram 3.x, JSON locale files, `get_text()` из `utils/helpers.py`

---

## Масштаб

| Слой | Файлов | Хардкод-строк |
|------|--------|---------------|
| Keyboards | 16 | ~625 |
| Handlers | 22 | ~497 |
| Utils | 1 | ~17 |
| **Итого** | **39** | **~1139** |

## Правила выполнения

### Паттерн замены в handler

```python
# БЫЛО:
await callback.answer("Заявка не найдена", show_alert=True)

# СТАЛО:
await callback.answer(get_text("errors.request_not_found", language=language), show_alert=True)
```

### Паттерн замены в keyboard

```python
# БЫЛО:
def get_manager_main_keyboard() -> ReplyKeyboardMarkup:
    builder.add(KeyboardButton(text="🆕 Новые заявки"))

# СТАЛО:
def get_manager_main_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    builder.add(KeyboardButton(text=get_text("admin.keyboards.new_requests", language=language)))
```

### Паттерн замены f-строки

```python
# БЫЛО:
text = f"📋 Заявка #{request.request_number}\n📂 Категория: {request.category}"

# СТАЛО:
text = get_text("requests.detail_header", language=language).format(
    request_number=request.request_number,
    category=request.category
)
```

### Получение языка в handler

```python
# Правильно — middleware injection (параметр language уже в сигнатуре):
async def my_handler(callback: CallbackQuery, db: Session, language: str):
    text = get_text("my.key", language=language)

# Если middleware не доступен (rare) — из user в БД:
from uk_management_bot.utils.helpers import get_language_from_event
lang = get_language_from_event(callback, db)
```

### Именование ключей локализации

Используем существующую структуру `ru.json`:
- `admin.*` — менеджерский интерфейс
- `requests.*` — работа с заявками
- `shifts.*` / `my_shifts.*` — смены
- `errors.*` — ошибки
- `buttons.*` — тексты кнопок
- `keyboards.*` — inline-клавиатуры (новая секция)

Для каждого нового ключа необходимо добавить перевод в ОБА файла:
- `uk_management_bot/config/locales/ru.json`
- `uk_management_bot/config/locales/uz.json`

### Формат ключей в JSON

```json
{
  "section": {
    "subsection_key": "Текст с {параметром}"
  }
}
```

### Верификация каждого файла

После изменения каждого файла:
```bash
python3 -c "import ast; ast.parse(open('uk_management_bot/path/to/file.py').read())"
```

---

## Фаза 0: Инфраструктура

### Task 0.1: Создать утилиту отображения статусов

**Files:**
- Create: `uk_management_bot/utils/status_display.py`
- Modify: `uk_management_bot/config/locales/ru.json`
- Modify: `uk_management_bot/config/locales/uz.json`

**Зачем:** Статусы заявок хранятся в БД как русские строки (`"Новая"`, `"В работе"` и т.д.) — это значения БД, их нельзя менять. Но при отображении пользователю статус должен быть на его языке.

**Step 1: Создать файл `status_display.py`**

```python
"""Локализованное отображение статусов заявок.

Значения REQUEST_STATUS_* — это ключи БД (русские строки), они НЕ меняются.
Эта утилита маппит их на локализованные display-строки.
"""
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_EXECUTED, REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_APPROVED, REQUEST_STATUS_CANCELLED,
)

STATUS_DISPLAY_KEYS = {
    REQUEST_STATUS_NEW: "statuses.new",
    REQUEST_STATUS_IN_PROGRESS: "statuses.in_progress",
    REQUEST_STATUS_PURCHASE: "statuses.purchase",
    REQUEST_STATUS_CLARIFICATION: "statuses.clarification",
    REQUEST_STATUS_EXECUTED: "statuses.executed",
    REQUEST_STATUS_COMPLETED: "statuses.completed",
    REQUEST_STATUS_APPROVED: "statuses.approved",
    REQUEST_STATUS_CANCELLED: "statuses.cancelled",
}

STATUS_EMOJI = {
    REQUEST_STATUS_NEW: "🆕",
    REQUEST_STATUS_IN_PROGRESS: "🛠️",
    REQUEST_STATUS_PURCHASE: "💰",
    REQUEST_STATUS_CLARIFICATION: "❓",
    REQUEST_STATUS_EXECUTED: "✅",
    REQUEST_STATUS_COMPLETED: "⭐",
    REQUEST_STATUS_APPROVED: "✔️",
    REQUEST_STATUS_CANCELLED: "❌",
}


def get_status_display(status: str, language: str = "ru") -> str:
    """Получить локализованное название статуса."""
    key = STATUS_DISPLAY_KEYS.get(status)
    if key:
        return get_text(key, language=language)
    return status


def get_status_with_emoji(status: str, language: str = "ru") -> str:
    """Получить статус с эмодзи."""
    emoji = STATUS_EMOJI.get(status, "📋")
    display = get_status_display(status, language)
    return f"{emoji} {display}"
```

**Step 2: Добавить ключи в locale файлы**

В `ru.json` добавить секцию `"statuses"`:
```json
{
  "statuses": {
    "new": "Новая",
    "in_progress": "В работе",
    "purchase": "Закуп",
    "clarification": "Уточнение",
    "executed": "Выполнена",
    "completed": "Исполнено",
    "approved": "Принято",
    "cancelled": "Отменена"
  }
}
```

В `uz.json` добавить секцию `"statuses"`:
```json
{
  "statuses": {
    "new": "Yangi",
    "in_progress": "Ishda",
    "purchase": "Xarid",
    "clarification": "Aniqlashtirish",
    "executed": "Bajarildi",
    "completed": "Ijro etildi",
    "approved": "Qabul qilindi",
    "cancelled": "Bekor qilindi"
  }
}
```

**Step 3: Верификация**

```bash
python3 -c "import ast; ast.parse(open('uk_management_bot/utils/status_display.py').read())"
python3 -c "import json; json.load(open('uk_management_bot/config/locales/ru.json')); json.load(open('uk_management_bot/config/locales/uz.json')); print('OK')"
```

**Step 4: Commit**
```bash
git add uk_management_bot/utils/status_display.py uk_management_bot/config/locales/ru.json uk_management_bot/config/locales/uz.json
git commit -m "feat(i18n): add status display utility for localized status names"
```

---

## Фаза 1: Клавиатуры (keyboards)

Клавиатуры обрабатываются ПЕРВЫМИ, т.к. handlers зависят от них. После изменения каждой клавиатуры нужно обновить все вызовы в соответствующих handlers (добавить `language=language`).

### Task 1.1: keyboards/admin.py (~60 строк)

**Files:**
- Modify: `uk_management_bot/keyboards/admin.py`
- Modify: `uk_management_bot/config/locales/ru.json` (секция `admin.keyboards`)
- Modify: `uk_management_bot/config/locales/uz.json` (секция `admin.keyboards`)

**Ключевые функции для локализации:**
- `get_manager_main_keyboard()` — 11 кнопок ReplyKeyboard
- `get_completed_requests_submenu()` — 4 кнопки
- `_status_icon()` — маппинг статусов → emoji (заменить на `STATUS_EMOJI` из `status_display.py`)
- `get_manager_request_detail_kb()` — inline кнопки действий
- `get_manager_request_list_kb()` — кнопки списка заявок
- Все остальные функции с хардкод текстами

**Паттерн:**
1. Добавить `from uk_management_bot.utils.helpers import get_text` в импорты
2. Добавить параметр `language: str = "ru"` в каждую функцию
3. Заменить `KeyboardButton(text="🆕 Новые заявки")` → `KeyboardButton(text=get_text("admin.keyboards.new_requests", language=language))`
4. Заменить `_status_icon()` на использование `STATUS_EMOJI` из `status_display.py`

**Locale keys для `ru.json`** (пример, точный список — из файла):
```json
{
  "admin": {
    "keyboards": {
      "new_requests": "🆕 Новые заявки",
      "active_requests": "🔄 Активные заявки",
      "completed_requests": "✅ Исполненные заявки",
      "purchase": "💰 Закуп",
      "archive": "📦 Архив",
      "shifts": "👥 Смены",
      "address_directory": "📍 Справочник адресов",
      "user_management": "👥 Управление пользователями",
      "employee_management": "👷 Управление сотрудниками",
      "create_invite": "📨 Создать приглашение",
      "back": "🔙 Назад",
      "awaiting_check": "📋 Ожидают проверки",
      "returned": "🔄 Возвращённые",
      "not_accepted": "⏳ Не принятые",
      "back_to_menu": "🔙 Назад в меню"
    }
  }
}
```

**ВАЖНО:** После изменения keyboard, найти все вызовы `get_manager_main_keyboard()`, `get_completed_requests_submenu()` и т.д. в handlers и добавить `language=language`.

**Step 1:** Прочитать файл, определить полный список строк
**Step 2:** Добавить locale ключи в ru.json и uz.json
**Step 3:** Модифицировать keyboard functions — добавить `language` параметр, заменить хардкод на `get_text()`
**Step 4:** Grep все вызовы этих функций в handlers и обновить передачу `language`
**Step 5:** Верификация синтаксиса
**Step 6:** Commit

---

### Task 1.2: keyboards/quarterly_planning.py (~65 строк)

**Files:**
- Modify: `uk_management_bot/keyboards/quarterly_planning.py`
- Modify: `uk_management_bot/config/locales/ru.json` (секция `quarterly.keyboards`)
- Modify: `uk_management_bot/config/locales/uz.json`

**Ключевые функции:** `get_quarterly_planning_menu()`, `get_quarter_selection_keyboard()`, и другие. Все кнопки хардкод: "📅 Создать план на квартал", "📊 Текущие планы", "I квартал", "(текущий)" и т.д.

**Шаги аналогичны Task 1.1.**

---

### Task 1.3: keyboards/address_management.py (~82 строки)

**Files:**
- Modify: `uk_management_bot/keyboards/address_management.py`
- Modify: locale файлы (секция `address.keyboards`)

**Самый большой keyboard-файл.** Кнопки управления адресами, дворами, зданиями, квартирами. Все тексты хардкод.

---

### Task 1.4: keyboards/my_shifts.py (~60 строк)

**Files:**
- Modify: `uk_management_bot/keyboards/my_shifts.py`
- Modify: locale файлы (секция `my_shifts.keyboards`)

---

### Task 1.5: keyboards/shift_management.py (~57 строк)

**Files:**
- Modify: `uk_management_bot/keyboards/shift_management.py`
- Modify: locale файлы (секция `shift_management.keyboards`)

---

### Task 1.6: keyboards/request_status.py (~32 строки)

**Files:**
- Modify: `uk_management_bot/keyboards/request_status.py`
- Modify: locale файлы

---

### Task 1.7: keyboards/request_assignment.py (~18 строк)

**Files:**
- Modify: `uk_management_bot/keyboards/request_assignment.py`
- Modify: locale файлы

---

### Task 1.8: keyboards/onboarding.py (~19 строк)

**Files:**
- Modify: `uk_management_bot/keyboards/onboarding.py`
- Modify: locale файлы

---

### Task 1.9: keyboards/request_comments.py (~14 строк)

**Files:**
- Modify: `uk_management_bot/keyboards/request_comments.py`
- Modify: locale файлы

---

### Task 1.10: keyboards/request_reports.py (~12 строк)

**Files:**
- Modify: `uk_management_bot/keyboards/request_reports.py`
- Modify: locale файлы

---

### Task 1.11: keyboards/requests.py (~10 строк)

**Files:**
- Modify: `uk_management_bot/keyboards/requests.py`
- Modify: locale файлы

---

### Task 1.12: keyboards/shifts.py (~9 строк)

**Files:**
- Modify: `uk_management_bot/keyboards/shifts.py`
- Modify: locale файлы

---

### Task 1.13: keyboards/profile.py (~7 строк)

**Files:**
- Modify: `uk_management_bot/keyboards/profile.py`
- Modify: locale файлы

---

### Task 1.14: keyboards/user_management.py (~5 строк) + keyboards/user_verification.py (~2 строки)

**Files:**
- Modify: `uk_management_bot/keyboards/user_management.py`
- Modify: `uk_management_bot/keyboards/user_verification.py`
- Modify: locale файлы

---

### Task 1.15: keyboards/base.py (~1 строка)

**Files:**
- Modify: `uk_management_bot/keyboards/base.py`
- Modify: locale файлы

**Step (для всей Фазы 1):** Commit

```bash
git add uk_management_bot/keyboards/ uk_management_bot/config/locales/
git commit -m "feat(i18n): localize all keyboard button texts"
```

---

## Фаза 2: Handlers

Каждый handler-файл — отдельная задача. Паттерн одинаковый:

1. Добавить `language: str` в сигнатуру handler (middleware injection)
2. Добавить `from uk_management_bot.utils.helpers import get_text`
3. Заменить хардкод-строки на `get_text()` вызовы
4. Если handler уже использует `get_language_from_event()` — заменить на `language` параметр
5. Для f-строк — создать locale key с `{параметрами}` и использовать `.format()`
6. Добавить locale ключи в ru.json и uz.json
7. Верифицировать синтаксис

### Task 2.1: handlers/admin.py (~109 строк) — САМЫЙ БОЛЬШОЙ

**Files:**
- Modify: `uk_management_bot/handlers/admin.py`
- Modify: locale файлы (секция `admin`)

**Категории хардкод-строк:**
- Ошибки доступа: "Нет прав", "Заявка не найдена" (~15 строк)
- Уведомления менеджера: "Заявка подтверждена", "Возвращена в работу" (~20 строк)
- Уведомления исполнителю: "Вам назначена заявка", "Заявка возвращена" (~15 строк)
- Формирование деталей заявки: f-строки с полями заявки (~30 строк)
- Статусные сообщения: "Нет новых заявок", "Список заявок" (~15 строк)
- Управление: "Пользователь заблокирован", invite flow (~15 строк)

**ВАЖНО:** Файл ~2500 строк. Разбить работу на подбатчи по функциональным блокам. Не менять логику — только строки.

**Locale key namespace:** `admin.*` (уже существует 726 ключей — сверять с существующими перед добавлением!)

**Step 1:** Прочитать файл полностью, составить список всех хардкод-строк
**Step 2:** Проверить какие ключи уже есть в `admin.*` секции locale — не дублировать
**Step 3:** Добавить недостающие ключи
**Step 4:** Последовательно заменять строки (сначала простые `callback.answer()`, потом f-строки)
**Step 5:** Обновить все keyboard-вызовы — передать `language=language`
**Step 6:** Верификация
**Step 7:** Commit

---

### Task 2.2: handlers/user_apartments.py (~35 строк)

**Files:**
- Modify: `uk_management_bot/handlers/user_apartments.py`
- Modify: locale файлы (секция `apartment`)

---

### Task 2.3: handlers/user_management.py (~35 строк)

**Files:**
- Modify: `uk_management_bot/handlers/user_management.py`
- Modify: locale файлы (секция `user_management`)

---

### Task 2.4: handlers/request_status_management.py (~30 строк)

**Files:**
- Modify: `uk_management_bot/handlers/request_status_management.py`
- Modify: locale файлы (секция `request_status`)

---

### Task 2.5: handlers/quarterly_planning.py (~28 строк)

**Files:**
- Modify: `uk_management_bot/handlers/quarterly_planning.py`
- Modify: locale файлы (секция `quarterly`)

---

### Task 2.6: handlers/address_apartments.py (~26 строк)

**Files:**
- Modify: `uk_management_bot/handlers/address_apartments.py`
- Modify: locale файлы (секция `address`)

---

### Task 2.7: handlers/request_reports.py (~24 строк)

**Files:**
- Modify: `uk_management_bot/handlers/request_reports.py`
- Modify: locale файлы (секция `reports`)

---

### Task 2.8: handlers/employee_management.py (~22 строк)

**Files:**
- Modify: `uk_management_bot/handlers/employee_management.py`
- Modify: locale файлы (секция `employee_management`)

---

### Task 2.9: handlers/request_acceptance.py (~20 строк)

**Files:**
- Modify: `uk_management_bot/handlers/request_acceptance.py`
- Modify: locale файлы (секция `requests.acceptance`)

---

### Task 2.10: handlers/shifts.py (~19 строк)

**Files:**
- Modify: `uk_management_bot/handlers/shifts.py`
- Modify: locale файлы (секция `shifts`)

---

### Task 2.11: handlers/unaccepted_requests.py (~18 строк)

**Files:**
- Modify: `uk_management_bot/handlers/unaccepted_requests.py`
- Modify: locale файлы

---

### Task 2.12: handlers/my_shifts.py (~15 строк)

**Files:**
- Modify: `uk_management_bot/handlers/my_shifts.py`
- Modify: locale файлы (секция `my_shifts`)

---

### Task 2.13: handlers/address_buildings.py (~14 строк)

**Files:**
- Modify: `uk_management_bot/handlers/address_buildings.py`
- Modify: locale файлы

---

### Task 2.14: handlers/address_yards.py (~13 строк)

**Files:**
- Modify: `uk_management_bot/handlers/address_yards.py`
- Modify: locale файлы

---

### Task 2.15: handlers/user_apartment_selection.py (~11 строк)

**Files:**
- Modify: `uk_management_bot/handlers/user_apartment_selection.py`
- Modify: locale файлы

---

### Task 2.16: handlers/profile_editing.py (~10 строк)

**Files:**
- Modify: `uk_management_bot/handlers/profile_editing.py`
- Modify: locale файлы (секция `profile`)

---

### Task 2.17: handlers/requests.py (~6 строк)

**Files:**
- Modify: `uk_management_bot/handlers/requests.py`
- Modify: locale файлы

---

### Task 2.18: handlers/address_moderation.py (~5 строк)

**Files:**
- Modify: `uk_management_bot/handlers/address_moderation.py`
- Modify: locale файлы

---

### Task 2.19: handlers/user_verification.py (~5 строк)

**Files:**
- Modify: `uk_management_bot/handlers/user_verification.py`
- Modify: locale файлы (секция `verification`)

---

### Task 2.20: handlers/auth.py + handlers/base.py + handlers/onboarding.py (~11 строк)

**Files:**
- Modify: `uk_management_bot/handlers/auth.py`
- Modify: `uk_management_bot/handlers/base.py`
- Modify: `uk_management_bot/handlers/onboarding.py`
- Modify: locale файлы

---

### Task 2.21: handlers/shift_transfer.py (~4 строки)

**Files:**
- Modify: `uk_management_bot/handlers/shift_transfer.py`
- Modify: locale файлы

---

**Step (для всей Фазы 2):** Commit после каждых 3-5 handlers

```bash
git commit -m "feat(i18n): localize handler_name.py strings"
```

---

## Фаза 3: Статусное отображение

### Task 3.1: Заменить хардкод-статусы на `get_status_display()`

**Files:**
- Modify: `uk_management_bot/handlers/admin.py` — emoji mapping, status display в деталях заявки
- Modify: `uk_management_bot/handlers/request_status_management.py` — status labels
- Modify: `uk_management_bot/handlers/requests.py` — my_requests list
- Modify: `uk_management_bot/keyboards/admin.py` — `_status_icon()` function
- Modify: `uk_management_bot/keyboards/request_status.py` — status buttons

**Паттерн:**
```python
# БЫЛО:
status_text = request.status  # "Выполнена" — всегда по-русски

# СТАЛО:
from uk_management_bot.utils.status_display import get_status_display
status_text = get_status_display(request.status, language=language)
```

**ВАЖНО:** НЕ менять значения `REQUEST_STATUS_*` констант и БД-поле `request.status` — менять только ОТОБРАЖЕНИЕ.

---

## Фаза 4: Инфраструктурная очистка

### Task 4.1: Унификация получения языка

**Files:**
- Modify: все handlers, которые используют `get_language_from_event()` — заменить на middleware `language`
- Modify: все handlers, которые используют `callback.from_user.language_code` — заменить на middleware `language`

**Текущая ситуация:**
- 6 handlers используют middleware `language` ✅
- 13 handlers используют `get_language_from_event(event, db)` — ЗАМЕНИТЬ
- 3 handlers используют `from_user.language_code` — ЗАМЕНИТЬ

**Паттерн:**
```python
# БЫЛО:
async def my_handler(callback: CallbackQuery, db: Session):
    lang = get_language_from_event(callback, db)

# СТАЛО:
async def my_handler(callback: CallbackQuery, db: Session, language: str):
    # language уже инжектирован middleware
    lang = language
```

**Step 1:** Grep для `get_language_from_event` во всех handlers
**Step 2:** Для каждого — добавить `language: str` в сигнатуру, убрать вызов `get_language_from_event()`
**Step 3:** Grep для `from_user.language_code` — аналогично
**Step 4:** Верификация

---

### Task 4.2: Добавить недостающие ключи в uz.json

**Files:**
- Modify: `uk_management_bot/config/locales/uz.json`

7 ключей `status_transitions.*` отсутствуют:
```
status_transitions.new_to_in_progress
status_transitions.in_progress_to_executed
status_transitions.executed_to_approved
status_transitions.executed_to_completed
status_transitions.completed_to_executed
status_transitions.in_progress_to_clarification
status_transitions.purchase_to_in_progress
```

**Step 1:** Найти эти ключи в `ru.json`, получить русские значения
**Step 2:** Добавить узбекские переводы в `uz.json`
**Step 3:** Верификация JSON

---

### Task 4.3: Обновить button_texts.py fallback

**Files:**
- Modify: `uk_management_bot/utils/button_texts.py`

Fallback-тексты в `_init_button_texts()` — хардкод на русском (строки 99-182). Заменить fallback на английские нейтральные значения или убрать (get_text уже делает fallback на ru.json).

**Низкий приоритет** — fallback срабатывает только если locale-файл не загрузился.

---

## Финальная верификация

### Проверка синтаксиса всех изменённых файлов

```bash
cd uk_management_bot
for f in $(find . -name "*.py" -newer ../docs/plans/2026-03-08-i18n-hardcoded-strings.md); do
  python3 -c "import ast; ast.parse(open('$f').read())" && echo "OK: $f" || echo "FAIL: $f"
done
```

### Проверка JSON locale файлов

```bash
python3 -c "
import json
for f in ['uk_management_bot/config/locales/ru.json', 'uk_management_bot/config/locales/uz.json']:
    data = json.load(open(f))
    print(f'{f}: {sum(1 for _ in str(data))} chars, valid JSON')
"
```

### Grep на оставшийся хардкод

```bash
# Ищем типичные паттерны хардкод-строк в handlers и keyboards
grep -rn 'await callback.answer("' uk_management_bot/handlers/ | grep -v 'get_text' | head -20
grep -rn 'await message.answer("' uk_management_bot/handlers/ | grep -v 'get_text' | head -20
grep -rn 'KeyboardButton(text="' uk_management_bot/keyboards/ | grep -v 'get_text' | head -20
grep -rn 'InlineKeyboardButton(text="' uk_management_bot/keyboards/ | grep -v 'get_text' | head -20
```

### Проверка что все keyboard-функции принимают language

```bash
grep -rn 'def get_.*keyboard\|def get_.*kb\|def get_.*menu' uk_management_bot/keyboards/ | grep -v 'language'
```

---

## Порядок выполнения (батчи)

| Батч | Tasks | Описание | ~Строк |
|------|-------|----------|--------|
| 1 | 0.1 | Инфраструктура: status_display.py | ~10 |
| 2 | 1.1–1.5 | Крупные keyboards (admin, quarterly, address, shifts) | ~264 |
| 3 | 1.6–1.15 | Остальные keyboards | ~107 |
| 4 | 2.1 | handlers/admin.py (самый большой) | ~109 |
| 5 | 2.2–2.6 | Крупные handlers (users, status, quarterly, address) | ~154 |
| 6 | 2.7–2.12 | Средние handlers (reports, employee, acceptance, shifts) | ~114 |
| 7 | 2.13–2.21 | Мелкие handlers (address, profile, auth, etc.) | ~70 |
| 8 | 3.1 | Замена status display | ~40 |
| 9 | 4.1–4.3 | Инфраструктурная очистка | ~30 |

**Каждый батч завершается:**
1. Syntax verification всех изменённых файлов
2. JSON validation locale файлов
3. Commit
4. Отчёт и ожидание feedback
