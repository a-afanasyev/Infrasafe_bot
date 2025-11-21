# ОТЧЕТ ПО АУДИТУ ЛОКАЛИЗАЦИИ

**Дата:** 2025-01-27  
**Задача:** Проверка применения локализации во всем коде  
**Статус:** Обнаружены проблемы

## 📊 РЕЗЮМЕ

Проведен анализ кодовой базы на предмет использования функции `get_text()` для локализации строк и кнопок. Обнаружены следующие категории проблем:

1. **Клавиатуры с хардкодными строками** - 7 функций
2. **Сообщения в обработчиках** - несколько случаев
3. **Валидаторы** - множество хардкодных сообщений об ошибках
4. **Константы** - сообщения об ошибках и успехе

---

## 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ

### 1. Клавиатуры в `uk_management_bot/keyboards/requests.py`

#### ❌ `get_edit_request_keyboard()` (строки 383-394)
**Проблема:** Полностью хардкодные строки, нет параметра `language`

```python
def get_edit_request_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для редактирования заявки"""
    keyboard = [
        ["🏷️ Изменить категорию"],
        ["📍 Изменить адрес"],
        ["📝 Изменить описание"],
        ["⚡ Изменить срочность"],
        ["🏠 Изменить квартиру"],
        ["📸 Изменить файлы"],
        ["❌ Отмена"]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
```

**Исправление:** Добавить параметр `language` и использовать `get_text()`:
- `buttons.edit_category`
- `buttons.edit_address`
- `buttons.edit_description`
- `buttons.edit_urgency`
- `buttons.edit_apartment`
- `buttons.edit_files`
- `buttons.cancel`

---

#### ❌ `get_request_status_keyboard()` (строки 396-407)
**Проблема:** Хардкодные статусы на русском языке

```python
def get_request_status_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для изменения статуса заявки"""
    keyboard = [
        ["🔧 В работу"],
        ["🔄 В работе"],
        ["💰 Закуп"],
        ["❓ Уточнение"],
        ["✅ Выполнена"],
        ["❌ Отменить"],
        ["🔙 Назад"]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
```

**Исправление:** Использовать локализованные статусы через `get_status_display()`:
- Статусы через `get_status_display(status, language)`
- `buttons.cancel`
- `buttons.back`

---

#### ❌ `get_requests_filter_keyboard()` (строки 409-420)
**Проблема:** Хардкодные тексты фильтров

```python
def get_requests_filter_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для фильтрации заявок"""
    keyboard = [
        ["📋 Все заявки"],
        ["🆕 Новые"],
        ["🔄 В работе"],
        ["💰 Закуп"],
        ["✅ Выполненные"],
        ["❌ Отмененные"],
        ["🔙 Назад"]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
```

**Исправление:** Использовать `get_text()`:
- `requests.all_requests`
- `requests.status_new`
- `requests.status_in_progress`
- `requests.status_purchase`
- `requests.status_executed` (для выполненных)
- `requests.status_cancelled`
- `buttons.back`

---

#### ❌ `get_yard_selection_keyboard()` (строки 522-559)
**Проблема:** Хардкодная строка "❌ Отмена"

**Места:**
- Строка 547: `KeyboardButton(text="❌ Отмена")`
- Строка 557: `KeyboardButton(text="❌ Отмена")`

**Исправление:** Добавить параметр `language` и использовать `get_text("buttons.cancel", language=language)`

---

#### ❌ `get_building_selection_keyboard()` (строки 562-601)
**Проблема:** Хардкодные строки "⬅️ Назад" и "❌ Отмена"

**Места:**
- Строка 588: `KeyboardButton(text="⬅️ Назад")`
- Строка 589: `KeyboardButton(text="❌ Отмена")`
- Строка 599: `KeyboardButton(text="❌ Отмена")`

**Исправление:** Добавить параметр `language` и использовать:
- `get_text("buttons.back", language=language)`
- `get_text("buttons.cancel", language=language)`

---

#### ❌ `get_apartment_selection_keyboard()` (строки 604-643)
**Проблема:** Хардкодные строки и шаблон с префиксом "🏠 Квартира"

**Места:**
- Строка 627: `f"🏠 Квартира {apartment.apartment_number}"`
- Строка 630: `KeyboardButton(text="⬅️ Назад")`
- Строка 631: `KeyboardButton(text="❌ Отмена")`
- Строка 641: `KeyboardButton(text="❌ Отмена")`

**Исправление:** 
- Использовать `get_text("requests.apartment_prefix", language=language, number=apartment.apartment_number)`
- `get_text("buttons.back", language=language)`
- `get_text("buttons.cancel", language=language)`

---

#### ❌ `get_address_selection_keyboard()` (строки 650-725)
**Проблема:** Хардкодная строка "❌ Отмена" в fallback (строка 722)

**Исправление:** Использовать `get_text("buttons.cancel", language=language)`

---

### 2. Обработчики в `uk_management_bot/handlers/requests.py`

#### ❌ Строка 2483
**Проблема:** Хардкодное сообщение "Пока нет заявок..."

```python
if not page_requests:
    message_text += "Пока нет заявок. Нажмите 'Создать заявку' в главном меню."
```

**Исправление:** Использовать `get_text("requests.no_requests_on_page", language=lang)` или существующий ключ `requests.no_requests`

---

### 3. Валидаторы в `uk_management_bot/utils/validators.py`

#### ❌ Класс `Validator` - множественные хардкодные сообщения

**Проблемные методы:**

1. **`validate_phone()`** (строки 13-32):
   - `"Номер телефона не может быть пустым"`
   - `"Номер телефона корректен"`
   - `"Неверный формат номера телефона"`

2. **`validate_description()`** (строки 35-46):
   - `"Описание не может быть пустым"`
   - `"Описание должно содержать минимум 10 символов"`
   - `"Описание слишком длинное (максимум {MAX_DESCRIPTION_LENGTH} символов)"`
   - `"Описание корректно"`

3. **`validate_apartment()`** (строки 49-61):
   - `"Номер квартиры необязателен"`
   - `"Номер квартиры слишком длинный (максимум {MAX_APARTMENT_LENGTH} символов)"`
   - `"Номер квартиры может содержать только цифры, буквы и дефис"`
   - `"Номер квартиры корректен"`

4. **`validate_category()`** (строки 64-130):
   - ✅ **УЖЕ ИСПОЛЬЗУЕТ локализацию** (частично)
   - ❌ Но есть fallback на строках 88, 105, 128:
     - `"Категория не может быть пустой"`
     - `"Неверная категория. Доступные категории: {categories_list}"`
     - `"Категория корректна"`

5. **`validate_status()`** (строки 133-141):
   - `"Статус не может быть пустым"`
   - `"Неверный статус. Доступные статусы: {', '.join(REQUEST_STATUSES)}"`
   - `"Статус корректен"`

6. **`validate_role()`** (строки 144-152):
   - `"Роль не может быть пустой"`
   - `"Неверная роль. Доступные роли: {', '.join(USER_ROLES)}"`
   - `"Роль корректна"`

7. **`validate_urgency()`** (строки 155-165):
   - `valid_urgencies = ["Обычная", "Средняя", "Срочная", "Критическая"]` - хардкод
   - `"Срочность не может быть пустой"`
   - `"Неверная срочность. Доступные варианты: {', '.join(valid_urgencies)}"`
   - `"Срочность корректна"`

8. **`validate_file_size()`** (строки 168-182):
   - `"Файл слишком большой. Максимальный размер: {size_mb} MB"`
   - `"Размер файла корректен"`

9. **`validate_rating()`** (строки 185-193):
   - `"Оценка должна быть числом"`
   - `"Оценка должна быть от 1 до 5"`
   - `"Оценка корректна"`

10. **`validate_media_files_count()`** (строки 196-203):
    - `"Слишком много файлов. Максимум: {MAX_MEDIA_FILES_PER_REQUEST}"`
    - `"Количество файлов корректно"`

11. **`validate_request_data()`** (строки 227-263):
    - `f"Поле '{field}' обязательно для заполнения"` - строка 233
    - `"Адрес не может быть пустым"` - строка 244
    - `"Все данные корректны"` - строка 263

**Исправление:** Добавить параметр `language` во все методы и использовать `get_text()` для всех сообщений.

**Рекомендуемые ключи локализации:**
```
validation.phone_empty
validation.phone_valid
validation.phone_invalid_format
validation.description_empty
validation.description_too_short
validation.description_too_long
validation.description_valid
validation.apartment_optional
validation.apartment_too_long
validation.apartment_invalid_chars
validation.apartment_valid
validation.category_empty (уже есть fallback)
validation.category_valid (уже есть fallback)
validation.status_empty
validation.status_invalid
validation.status_valid
validation.role_empty
validation.role_invalid
validation.role_valid
validation.urgency_empty
validation.urgency_invalid
validation.urgency_valid
validation.file_too_large
validation.file_size_valid
validation.rating_not_number
validation.rating_out_of_range
validation.rating_valid
validation.too_many_files
validation.files_count_valid
validation.field_required
validation.address_empty
validation.all_data_valid
```

---

### 4. Константы в `uk_management_bot/utils/constants.py`

#### ❌ `ERROR_MESSAGES` (строки 168-179)
**Проблема:** Хардкодные сообщения об ошибках на русском

```python
ERROR_MESSAGES = {
    "permission_denied": "У вас нет прав для выполнения этого действия",
    "not_in_shift": "Вы не в смене. Смена необходима для выполнения этого действия",
    "invalid_data": "Неверные данные",
    "file_too_large": "Файл слишком большой",
    "unknown_error": "Произошла ошибка. Попробуйте позже",
    "request_not_found": "Заявка не найдена",
    "user_not_found": "Пользователь не найден",
    "shift_not_found": "Смена не найдена",
    "already_in_shift": "Вы уже в смене",
    "not_in_shift": "Вы не в смене"
}
```

**Исправление:** Создать функцию-обертку:
```python
def get_error_message(key: str, language: str = "ru") -> str:
    """Получить локализованное сообщение об ошибке"""
    return get_text(f"errors.{key}", language=language)
```

---

#### ❌ `SUCCESS_MESSAGES` (строки 182-190)
**Проблема:** Хардкодные сообщения об успехе на русском

```python
SUCCESS_MESSAGES = {
    "request_created": "Заявка успешно создана!",
    "request_updated": "Заявка обновлена!",
    "user_approved": "Пользователь одобрен!",
    "user_blocked": "Пользователь заблокирован!",
    "shift_started": "Смена принята!",
    "shift_ended": "Смена сдана!",
    "rating_submitted": "Оценка отправлена!"
}
```

**Исправление:** Создать функцию-обертку:
```python
def get_success_message(key: str, language: str = "ru") -> str:
    """Получить локализованное сообщение об успехе"""
    return get_text(f"success.{key}", language=language)
```

---

#### ⚠️ `SPECIALIZATION_DISPLAY` и `SPECIALIZATIONS` (строки 237-257)
**Статус:** Это отображаемые названия специализаций. Они могут храниться в БД на русском, но для UI нужна локализация.

**Рекомендация:** Создать функцию `get_specialization_display(specialization_key: str, language: str = "ru")` аналогично `get_category_display()`.

---

## ✅ ПОЛОЖИТЕЛЬНЫЕ МОМЕНТЫ

1. ✅ Большинство обработчиков в `handlers/requests.py` уже используют `get_text()`
2. ✅ Клавиатуры категорий, срочности, пагинации уже локализованы
3. ✅ `get_request_actions_keyboard()` использует локализацию
4. ✅ `format_request_details()` и `format_request_list_item()` используют локализацию
5. ✅ `Validator.validate_category()` частично использует локализацию

---

## 📋 ПЛАН ИСПРАВЛЕНИЙ

### Приоритет 1: Критические клавиатуры
1. Исправить `get_edit_request_keyboard()` - добавить локализацию
2. Исправить `get_request_status_keyboard()` - использовать `get_status_display()`
3. Исправить `get_requests_filter_keyboard()` - добавить локализацию
4. Исправить функции выбора адреса - добавить параметр `language`

### Приоритет 2: Обработчики
1. Исправить хардкодное сообщение в строке 2483 `handlers/requests.py`

### Приоритет 3: Валидаторы
1. Добавить параметр `language` во все методы `Validator`
2. Заменить все хардкодные сообщения на `get_text()`
3. Добавить недостающие ключи в локализацию

### Приоритет 4: Константы
1. Создать функции-обертки для `ERROR_MESSAGES` и `SUCCESS_MESSAGES`
2. Обновить все места использования на новые функции

---

## 🔍 ДОПОЛНИТЕЛЬНЫЕ ЗАМЕЧАНИЯ

### Другие файлы (требуют отдельной проверки):
- `handlers/admin.py` - есть хардкодные строки в клавиатурах (строки 8-18)
- `handlers/onboarding.py` - есть хардкодные кнопки
- `keyboards/admin.py` - хардкодные кнопки
- `keyboards/onboarding.py` - хардкодные кнопки
- `keyboards/address_management.py` - есть хардкодные кнопки

---

## 📊 СТАТИСТИКА

- **Всего найдено проблемных мест:** ~50+
- **Клавиатуры без локализации:** 7 функций
- **Валидаторы без локализации:** 11 методов
- **Константы без локализации:** 2 словаря
- **Хардкодные строки в обработчиках:** 1+ случаев

---

## 🎯 РЕКОМЕНДАЦИИ

1. **Создать helper-функции** для часто используемых паттернов:
   - `get_localized_keyboard(text_key: str, language: str)` - для простых кнопок
   - `get_error_message(key: str, language: str)` - для ошибок
   - `get_success_message(key: str, language: str)` - для успешных сообщений

2. **Добавить проверку в CI/CD** на наличие хардкодных русских строк в коде

3. **Создать линтер-правило** для автоматического обнаружения хардкодных строк

4. **Добавить unit-тесты** для проверки локализации всех UI-элементов

---

**Следующий шаг:** Создать задачи на исправление каждого приоритета.

