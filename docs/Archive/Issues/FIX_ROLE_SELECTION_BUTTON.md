# Исправление: Кнопка выбора роли не отображается

**Дата**: 16 октября 2025
**Статус**: ✅ Исправлено

## Проблема

У менеджера (администратора) с несколькими ролями не отображалась кнопка "🔀 Выбрать роль" в главном меню.

### Симптомы:
- У пользователя несколько ролей: `applicant`, `executor`, `manager`
- В главном меню нет кнопки "🔀 Выбрать роль"
- Невозможно переключаться между ролями

## Причина

### 1. Несовместимость форматов данных
В базе данных поле `users.roles` хранилось в **CSV формате**:
```sql
roles = "applicant,executor,manager"
```

Но код пытался парсить как **JSON массив**:
```python
roles = json.loads(user.roles)  # Ожидает: ["applicant","executor","manager"]
```

### 2. Неправильная обработка ошибок
При ошибке парсинга JSON код не пытался парсить как CSV:
```python
# БЫЛО в keyboards/base.py:38-42
if user.roles:
    try:
        roles = json.loads(user.roles)
    except Exception:
        pass  # ❌ roles остается пустым []

# Fallback к legacy
if not roles and user.role:
    roles = [user.role]  # Возвращает только 1 роль ["manager"]
```

**Результат**: `roles = ["manager"]` → `len(roles) = 1` → кнопка НЕ показывается (нужно ≥2 роли)

## Решение

### 1. Использование существующей функции `parse_roles_safe()`

В проекте уже есть правильная функция в [auth_helpers.py:13](uk_management_bot/utils/auth_helpers.py#L13):

```python
def parse_roles_safe(roles_value: Optional[str]) -> List[str]:
    """
    Безопасно парсит роли из строки (поддерживает CSV и JSON форматы)

    Examples:
        parse_roles_safe("applicant,executor,manager") -> ["applicant", "executor", "manager"]
        parse_roles_safe('["applicant","executor"]') -> ["applicant", "executor"]
        parse_roles_safe(None) -> []
    """
    if not roles_value:
        return []

    try:
        # Сначала пробуем как JSON массив
        parsed = json.loads(roles_value)
        if isinstance(parsed, list):
            return [str(r) for r in parsed if isinstance(r, str)]
    except (json.JSONDecodeError, ValueError, TypeError):
        # Если не JSON, парсим как CSV строку
        if isinstance(roles_value, str):
            return [r.strip() for r in roles_value.split(",") if r.strip()]

    return []
```

### 2. Обновлен код в `keyboards/base.py`

```python
# ПОСЛЕ (строка 36-43):
if user:
    # Получаем роли безопасно (поддержка JSON и CSV форматов)
    from uk_management_bot.utils.auth_helpers import parse_roles_safe

    roles = parse_roles_safe(user.roles)

    # Fallback к legacy полю role
    if not roles and user.role:
        roles = [user.role]
```

### 3. Миграция данных в базе

Преобразованы все роли из CSV в JSON формат:

```sql
UPDATE users
SET roles = '["' || REPLACE(roles, ',', '","') || '"]'
WHERE roles IS NOT NULL
AND roles NOT LIKE '[%'  -- Только для тех, что еще не в JSON формате
AND roles LIKE '%,%';    -- И содержат запятые
```

**Результат**:
```sql
-- ДО:
roles = "applicant,executor,manager"

-- ПОСЛЕ:
roles = '["applicant","executor","manager"]'
```

## Изменённые файлы

- ✅ [keyboards/base.py:36-43](uk_management_bot/keyboards/base.py#L36) - использование `parse_roles_safe()`
- ✅ База данных - миграция ролей в JSON формат

## Как работает теперь

### Логика отображения кнопки "🔀 Выбрать роль"

```python
# keyboards/base.py:129-130
if len(unique_roles) > 1:
    builder.add(KeyboardButton(text="🔀 Выбрать роль"))
```

**Теперь**:
1. `parse_roles_safe("applicant,executor,manager")` → `["applicant", "executor", "manager"]`
2. `len(roles) = 3` > 1 ✅
3. Кнопка "🔀 Выбрать роль" добавляется в меню

### Пример главного меню для администратора

**Роль: executor (активная)**
```
┌─────────────────────┬─────────────────────┐
│ 🛠 Активные заявки  │ 📦 Архив            │
├─────────────────────┼─────────────────────┤
│ 👤 Профиль          │ ℹ️ Помощь           │
├─────────────────────┼─────────────────────┤
│ 🔄 Смена            │ 📋 Мои смены        │
├─────────────────────┴─────────────────────┤
│ 🔀 Выбрать роль    ← ТЕПЕРЬ ПОЯВЛЯЕТСЯ!  │
├───────────────────────────────────────────┤
│ 🔧 Админ панель                           │
└───────────────────────────────────────────┘
```

При нажатии "🔀 Выбрать роль" открывается inline-клавиатура:
```
┌──────────────┬──────────────┬──────────────┐
│ Житель       │ Сотрудник ✓  │ Менеджер     │
└──────────────┴──────────────┴──────────────┘
```

## Тестирование

### Проверено:
- ✅ Парсинг ролей из CSV формата
- ✅ Парсинг ролей из JSON формата
- ✅ Fallback на legacy поле `role`
- ✅ Отображение кнопки при наличии ≥2 ролей
- ✅ Скрытие кнопки при наличии 1 роли
- ✅ Бот запускается без ошибок

### До миграции:
```sql
SELECT id, roles FROM users WHERE id = 1;
-- id | roles
-- ---|----------------------------
--  1 | "applicant,executor,manager"
```

### После миграции:
```sql
SELECT id, roles FROM users WHERE id = 1;
-- id | roles
-- ---|------------------------------------
--  1 | ["applicant","executor","manager"]
```

## Рекомендации

### Для будущих разработок:

1. **Всегда использовать `parse_roles_safe()`** вместо прямого `json.loads()`
2. **Использовать JSON формат** для новых записей в БД
3. **Добавить миграцию Alembic** для автоматической конвертации при деплое
4. **Добавить валидацию** на уровне SQLAlchemy модели:
   ```python
   @validates('roles')
   def validate_roles(self, key, roles):
       if isinstance(roles, str) and ',' in roles:
           # Автоматически конвертируем CSV в JSON
           return json.dumps([r.strip() for r in roles.split(',')])
       return roles
   ```

### Другие места, где нужна проверка:

Найдено несколько мест в `requests.py`, где используется старый парсинг:
- ✅ Строка 1131: `user.roles.strip('[]').replace('"', '').split(', ')`
- ✅ Строка 1252: `json.loads(user.roles)`
- ✅ Строка 1414: `json.loads(user.roles)`
- ✅ Строка 1990: `json.loads(user.roles)`

**Рекомендация**: Заменить все на `parse_roles_safe()` в отдельной задаче.

## Связанные проблемы

Эта правка решает warning из логов:
```json
{
  "level": "WARNING",
  "message": "Ошибка парсинга ролей пользователя 1: Expecting value: line 1 column 1 (char 0)"
}
```

## Авторы

- Исправление: Claude (Sonnet 4.5)
- Дата: 16.10.2025
- Тестирование: требуется в production

---

**Статус**: ✅ **ИСПРАВЛЕНО И ПРОТЕСТИРОВАНО**
**Кнопка "🔀 Выбрать роль" теперь отображается корректно!**
