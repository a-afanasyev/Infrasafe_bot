# Руководство по локализации в проекте UK Management Bot

## Обзор

В проекте реализована система локализации с поддержкой русского и узбекского языков. Основные компоненты:

- Файлы локализации: `uk_management_bot/config/locales/ru.json` и `uk_management_bot/config/locales/uz.json`
- Утилита для получения локализованных строк: `get_text()` из `utils/helpers.py`
- Безопасное получение локализованных строк: `safe_get_text()` из `utils/safe_localization.py`

## Использование локализации в коде

### Базовое использование

```python
from uk_management_bot.utils.helpers import get_text

# Простое получение текста
text = get_text("key_name", language="ru")

# С параметрами форматирования
text = get_text("welcome_message", language="ru", name="Иван", time="12:00")
```

### Безопасное использование

```python
from uk_management_bot.utils.safe_localization import safe_get_text

# Безопасное получение текста с fallback
text = safe_get_text("key_name", language="ru", default="Текст по умолчанию")

# С fallback-ключом
text = safe_get_text_with_fallback("primary_key", "fallback_key", language="ru")
```

## Стандарты именования ключей

### Структура ключей

Ключи локализации должны быть организованы по секциям:

```json
{
  "section_name": {
    "key_name": "Переведенный текст",
    "key_with_params": "Текст с параметром: {param}"
  }
}
```

### Правила именования

1. Используйте snake_case для ключей: `user_not_found`, `request_created`
2. Группируйте связанные ключи в секции:
   - `errors.*` - сообщения об ошибках
   - `buttons.*` - тексты кнопок
   - `validation.*` - сообщения валидации
   - `admin.*` - сообщения администратора
3. Для параметризованных строк используйте плейсхолдеры `{param_name}`

## Добавление новой локализации

### 1. Добавление ключей в файлы локализации

При добавлении нового текста:

1. Добавьте ключ в `ru.json`:
```json
{
  "new_section": {
    "new_key": "Новый текст на русском"
  }
}
```

2. Добавьте тот же ключ в `uz.json`:
```json
{
  "new_section": {
    "new_key": "Yangi matn o'zbek tilida"
  }
}
```

### 2. Использование в коде

```python
from uk_management_bot.utils.safe_localization import safe_get_text

# Получаем язык пользователя
lang = message.from_user.language_code or "ru"

# Используем локализованный текст
await message.answer(safe_get_text("new_section.new_key", language=lang))
```

## Лучшие практики

### 1. Всегда используйте безопасное получение текста

```python
# Плохо
await message.answer("Текст на русском")

# Хорошо
await message.answer(safe_get_text("key_name", language=lang))
```

### 2. Обрабатывайте отсутствующие ключи

```python
# Плохо
text = get_text("key_name", language=lang)
if text == "key_name":
    text = "Текст по умолчанию"

# Хорошо
text = safe_get_text("key_name", language=lang, default="Текст по умолчанию")
```

### 3. Используйте единый подход к получению языка

```python
# Плохо
lang = "ru"  # хардкодированный язык

# Хорошо
lang = message.from_user.language_code or "ru"
# или
lang = await get_user_language(user_id, db)
```

### 4. Локализуйте все пользовательские сообщения

Все сообщения, которые видит пользователь, должны быть локализованы:

- Сообщения об ошибках
- Тексты кнопок
- Подтверждения действий
- Уведомления

### 5. Используйте параметризацию для динамических данных

```python
# Плохо
await message.answer(f"Заявка #{request_id} создана")

# Хорошо
await message.answer(safe_get_text("request.created", language=lang, request_id=request_id))
```

## Проверка локализации

Для проверки локализации используйте скрипт `check_localization.py`:

```bash
python3 check_localization.py
```

Скрипт проверяет:
- Наличие хардкодированных строк
- Присутствие необходимых ключей локализации
- Соответствие между ru.json и uz.json

## Частые проблемы

### 1. Хардкодированные строки

```python
# Проблема
await message.answer("❌ Ошибка")

# Решение
await message.answer(safe_get_text("errors.error", language=lang))
```

### 2. Отсутствующие ключи

```python
# Проблема
text = get_text("missing_key", language=lang)  # вернет "missing_key"

# Решение
text = safe_get_text("missing_key", language=lang, default="Текст по умолчанию")
```

### 3. Несоответствие между языками

Убедитесь, что все ключи из `ru.json` присутствуют в `uz.json` и наоборот.

## Добавление нового языка

Для добавления нового языка (например, английского):

1. Создайте файл `en.json` в директории `config/locales/`
2. Скопируйте структуру из `ru.json`
3. Переведите все значения
4. Обновите `SUPPORTED_LANGUAGES` в `utils/language_helpers.py`

## Интеграция с CI/CD

Рекомендуется добавить проверку локализации в процесс CI/CD:

```yaml
# .github/workflows/localization.yml
name: Check Localization
on: [push, pull_request]
jobs:
  check-localization:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Check localization
        run: python3 check_localization.py
```

## Заключение

Следование этим рекомендациям обеспечит:
- Полностью локализованный интерфейс
- Легкое добавление новых языков
- Предотвращение регрессий в локализации
- Улучшенный пользовательский опыт
