# ЕДИНЫЙ ИСТОЧНИК ПРАВДЫ: Тексты кнопок для фильтров

**Дата создания**: 6 ноября 2025  
**Статус**: 📋 План создания единого источника правды  
**Приоритет**: 🔴 ВЫСОКИЙ

---

## 🎯 ЦЕЛЬ

Создать единый источник правды для всех текстов кнопок, используемых в фильтрах handlers, чтобы:
- ✅ Автоматически поддерживать все языки из `SUPPORTED_LANGUAGES`
- ✅ Исключить дублирование кода
- ✅ Упростить добавление новых языков
- ✅ Обеспечить синхронизацию между клавиатурами и фильтрами

---

## 📊 АНАЛИЗ ТЕКУЩЕЙ СИТУАЦИИ

### Проблемы текущего подхода:

1. **Дублирование**: Тексты кнопок определены в:
   - `keyboards/base.py` - генерация клавиатур
   - `handlers/*.py` - фильтры handlers (хардкод)
   - `config/locales/*.json` - локализация

2. **Рассинхронизация**: При изменении текста в локализации нужно:
   - Обновить клавиатуру ✅ (уже использует get_text)
   - Обновить фильтр ❌ (хардкод в handler)

3. **Масштабируемость**: При добавлении языка нужно:
   - Обновить локализацию ✅
   - Обновить клавиатуру ✅ (автоматически)
   - Обновить все фильтры ❌ (вручную в каждом handler)

### Найденные handlers с F.text фильтрами:

**Критические** (блокируют узбекских пользователей):
- `requests.py:317` - "📝 Создать заявку" ← Entry Handler
- `requests.py:2057` - "📋 Мои заявки"

**Важные** (используются часто):
- `base.py` - множество кнопок главного меню
- `admin.py` - множество админских кнопок
- `onboarding.py` - кнопки онбординга
- `shifts.py` - кнопки смен
- И другие...

**Всего найдено**: 41 handler с жестко закодированными текстами

---

## 🏗️ АРХИТЕКТУРА ЕДИНОГО ИСТОЧНИКА ПРАВДЫ

### Структура решения:

```
uk_management_bot/utils/
├── language_helpers.py          # SUPPORTED_LANGUAGES (уже есть)
└── button_texts.py              # НОВЫЙ: Единый источник правды для текстов кнопок
```

### Принципы:

1. **Single Source of Truth**: Все тексты кнопок получаются из локализации через `get_text()`
2. **Автоматическое масштабирование**: Использует `SUPPORTED_LANGUAGES`
3. **Кэширование**: Вычисляется один раз при импорте (для фильтров)
4. **Fallback**: Гарантированная работа даже при ошибках локализации

---

## 📋 ПЛАН РЕАЛИЗАЦИИ

### Фаза 1: Создание единого источника правды (30 минут)

#### Задача 1.1: Создать модуль `button_texts.py`

**Файл**: `uk_management_bot/utils/button_texts.py`

**Функциональность**:
- Функции для получения списков текстов кнопок для всех языков
- Кэширование результатов для использования в фильтрах
- Валидация и fallback

**Структура**:
```python
"""
Button Texts Helper - Single Source of Truth for button texts used in filters

Provides functions to get button texts for all supported languages,
automatically scaling when new languages are added to SUPPORTED_LANGUAGES.
"""

from typing import List
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.language_helpers import SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE
import logging

logger = logging.getLogger(__name__)


def get_button_texts_for_all_languages(locale_key: str, fallback_text: str = None) -> List[str]:
    """
    Получить тексты кнопки для всех поддерживаемых языков.
    
    Используется для создания фильтров F.text.in_() в handlers.
    
    Args:
        locale_key: Ключ локализации (например, "main_menu.create_request")
        fallback_text: Текст для fallback, если локализация не загружена
        
    Returns:
        List[str]: Список текстов кнопки на всех языках
        
    Example:
        texts = get_button_texts_for_all_languages("main_menu.create_request")
        # Returns: ["📝 Создать заявку", "📝 Ariza yaratish"]
    """
    texts = []
    
    try:
        for lang in SUPPORTED_LANGUAGES:
            text = get_text(locale_key, language=lang)
            # Проверяем, что это валидный перевод, а не ключ локализации
            if text and "." not in text:
                texts.append(text)
        
        # Если ничего не загрузилось, используем fallback
        if not texts:
            if fallback_text:
                logger.warning(f"Failed to load button texts for '{locale_key}', using fallback")
                texts = [fallback_text]
            else:
                # Пробуем получить хотя бы русский текст
                ru_text = get_text(locale_key, language=DEFAULT_LANGUAGE)
                if ru_text and "." not in ru_text:
                    texts = [ru_text]
                else:
                    logger.error(f"Failed to load button texts for '{locale_key}' and no fallback provided")
                    texts = []
    except Exception as e:
        logger.error(f"Error loading button texts for '{locale_key}': {e}")
        if fallback_text:
            texts = [fallback_text]
        else:
            texts = []
    
    return texts


# Кэшированные константы для использования в фильтрах
# Вычисляются один раз при импорте модуля

def _init_button_texts():
    """Инициализация кэшированных текстов кнопок"""
    button_texts = {}
    
    # Основные кнопки главного меню
    button_texts['create_request'] = get_button_texts_for_all_languages(
        "main_menu.create_request",
        fallback_text="📝 Создать заявку"
    )
    
    button_texts['my_requests'] = get_button_texts_for_all_languages(
        "main_menu.my_requests",
        fallback_text="📋 Мои заявки"
    )
    
    button_texts['profile'] = get_button_texts_for_all_languages(
        "main_menu.profile",
        fallback_text="👤 Профиль"
    )
    
    button_texts['help'] = get_button_texts_for_all_languages(
        "main_menu.help",
        fallback_text="ℹ️ Помощь"
    )
    
    button_texts['active_requests'] = get_button_texts_for_all_languages(
        "main_menu.active_requests",
        fallback_text="🛠 Активные заявки"
    )
    
    button_texts['archive'] = get_button_texts_for_all_languages(
        "main_menu.archive",
        fallback_text="📦 Архив"
    )
    
    button_texts['shift'] = get_button_texts_for_all_languages(
        "main_menu.shift",
        fallback_text="🔄 Смена"
    )
    
    button_texts['my_shifts'] = get_button_texts_for_all_languages(
        "main_menu.my_shifts",
        fallback_text="📋 Мои смены"
    )
    
    button_texts['switch_role'] = get_button_texts_for_all_languages(
        "main_menu.switch_role",
        fallback_text="🔀 Выбрать роль"
    )
    
    button_texts['admin_panel'] = get_button_texts_for_all_languages(
        "main_menu.admin_panel",
        fallback_text="🔧 Админ панель"
    )
    
    button_texts['acceptance'] = get_button_texts_for_all_languages(
        "main_menu.acceptance",
        fallback_text="✅ Ожидают приёмки"
    )
    
    # Кнопки отмены и назад
    button_texts['cancel'] = get_button_texts_for_all_languages(
        "buttons.cancel",
        fallback_text="❌ Отмена"
    )
    
    button_texts['back'] = get_button_texts_for_all_languages(
        "buttons.back",
        fallback_text="🔙 Назад"
    )
    
    # Логирование для отладки
    logger.info(f"Initialized button texts cache: {len(button_texts)} button types")
    for key, texts in button_texts.items():
        logger.debug(f"  {key}: {len(texts)} languages - {texts}")
    
    return button_texts


# Инициализация кэша при импорте модуля
BUTTON_TEXTS = _init_button_texts()


def get_create_request_texts() -> List[str]:
    """Получить тексты кнопки 'Создать заявку' для всех языков"""
    return BUTTON_TEXTS.get('create_request', ["📝 Создать заявку"])


def get_my_requests_texts() -> List[str]:
    """Получить тексты кнопки 'Мои заявки' для всех языков"""
    return BUTTON_TEXTS.get('my_requests', ["📋 Мои заявки"])


def get_profile_texts() -> List[str]:
    """Получить тексты кнопки 'Профиль' для всех языков"""
    return BUTTON_TEXTS.get('profile', ["👤 Профиль"])


def get_help_texts() -> List[str]:
    """Получить тексты кнопки 'Помощь' для всех языков"""
    return BUTTON_TEXTS.get('help', ["ℹ️ Помощь"])


def get_cancel_texts() -> List[str]:
    """Получить тексты кнопки 'Отмена' для всех языков"""
    return BUTTON_TEXTS.get('cancel', ["❌ Отмена"])


def get_back_texts() -> List[str]:
    """Получить тексты кнопки 'Назад' для всех языков"""
    return BUTTON_TEXTS.get('back', ["🔙 Назад"])


# Универсальная функция для получения любых текстов кнопок
def get_button_texts(button_key: str) -> List[str]:
    """
    Универсальная функция для получения текстов кнопки.
    
    Args:
        button_key: Ключ кнопки из BUTTON_TEXTS
        
    Returns:
        List[str]: Список текстов на всех языках
    """
    return BUTTON_TEXTS.get(button_key, [])
```

---

### Фаза 2: Использование в Entry Handler (15 минут)

#### Задача 2.1: Обновить `requests.py` для использования единого источника

**Изменения**:

1. **Добавить импорт**:
```python
from uk_management_bot.utils.button_texts import get_create_request_texts
```

2. **Создать константу** (после импортов):
```python
# Константа для фильтрации сообщений создания заявки
# Использует единый источник правды для автоматического масштабирования
CREATE_REQUEST_TEXTS = get_create_request_texts()
```

3. **Обновить фильтр**:
```python
@router.message(F.text.in_(CREATE_REQUEST_TEXTS))
async def start_request_creation(...):
```

---

### Фаза 3: Расширение на другие handlers (постепенно)

#### Задача 3.1: Добавить остальные кнопки в `button_texts.py`

Добавить функции для всех найденных кнопок:
- Кнопки онбординга
- Кнопки админ-панели
- Кнопки смен
- И другие...

#### Задача 3.2: Постепенно мигрировать handlers

Приоритет:
1. **Критические** (блокируют функциональность)
2. **Важные** (используются часто)
3. **Остальные** (по мере необходимости)

---

## 📋 ДЕТАЛЬНЫЙ ПЛАН ЗАДАЧ

### Задача 1: Создать модуль `button_texts.py`

**Файл**: `uk_management_bot/utils/button_texts.py`

**Шаги**:
1. Создать файл с базовой структурой
2. Реализовать функцию `get_button_texts_for_all_languages()`
3. Реализовать функцию `_init_button_texts()` для кэширования
4. Добавить функции-геттеры для основных кнопок
5. Добавить логирование и обработку ошибок
6. Протестировать импорт модуля

**Оценка времени**: 30 минут

**Критерии успеха**:
- ✅ Модуль импортируется без ошибок
- ✅ Функции возвращают корректные списки текстов
- ✅ Fallback работает при ошибках локализации
- ✅ Логирование показывает загруженные тексты

---

### Задача 2: Использовать в Entry Handler

**Файл**: `uk_management_bot/handlers/requests.py`

**Шаги**:
1. Добавить импорт `get_create_request_texts`
2. Создать константу `CREATE_REQUEST_TEXTS`
3. Изменить фильтр handler'а
4. Обновить логирование
5. Протестировать с русским пользователем
6. Протестировать с узбекским пользователем

**Оценка времени**: 15 минут

**Критерии успеха**:
- ✅ Русский пользователь может создать заявку
- ✅ Узбекский пользователь может создать заявку
- ✅ Логи показывают корректную работу
- ✅ Нет регрессий

---

### Задача 3: Добавить остальные кнопки в `button_texts.py`

**Файл**: `uk_management_bot/utils/button_texts.py`

**Шаги**:
1. Добавить функции для кнопок главного меню:
   - `get_active_requests_texts()`
   - `get_archive_texts()`
   - `get_shift_texts()`
   - `get_my_shifts_texts()`
   - `get_switch_role_texts()`
   - `get_admin_panel_texts()`
   - `get_acceptance_texts()`

2. Добавить функции для кнопок онбординга (если нужно)

3. Обновить `_init_button_texts()` для новых кнопок

**Оценка времени**: 20 минут

**Критерии успеха**:
- ✅ Все функции работают корректно
- ✅ Кэш инициализируется правильно
- ✅ Логи показывают все загруженные тексты

---

### Задача 4: Мигрировать handler "Мои заявки"

**Файл**: `uk_management_bot/handlers/requests.py`

**Шаги**:
1. Добавить импорт `get_my_requests_texts`
2. Создать константу `MY_REQUESTS_TEXTS`
3. Изменить фильтр handler'а (строка 2057)
4. Протестировать

**Оценка времени**: 10 минут

---

### Задача 5: Документация и тестирование

**Файлы**: 
- `MemoryBank/TASK_17_ENTRY_HANDLER_IMPLEMENTATION.md`
- Обновить существующие документы

**Шаги**:
1. Создать документацию по использованию `button_texts.py`
2. Обновить `TASK_17_EXECUTION_ANALYSIS.md`
3. Обновить `TASK_17_REQUESTS_PY_CRITICAL_ISSUES.md`
4. Создать примеры использования

**Оценка времени**: 15 минут

---

## ✅ ПРЕИМУЩЕСТВА ЕДИНОГО ИСТОЧНИКА ПРАВДЫ

### 1. Автоматическое масштабирование

**До**:
```python
# В каждом handler нужно менять код
CREATE_REQUEST_TEXTS = [
    get_text("main_menu.create_request", language="ru"),
    get_text("main_menu.create_request", language="uz")
]
# При добавлении 'en' нужно менять код!
```

**После**:
```python
# Один раз создали функцию
from uk_management_bot.utils.button_texts import get_create_request_texts

CREATE_REQUEST_TEXTS = get_create_request_texts()
# При добавлении 'en' в SUPPORTED_LANGUAGES - автоматически работает!
```

### 2. Единая точка изменений

**До**: Изменение текста кнопки требует:
- Обновить локализацию ✅
- Обновить клавиатуру ✅ (автоматически)
- Обновить все фильтры ❌ (вручную)

**После**: Изменение текста кнопки требует:
- Обновить локализацию ✅
- Все остальное работает автоматически ✅

### 3. Переиспользование

**До**: Каждый handler дублирует логику получения текстов

**После**: Одна функция используется везде

### 4. Тестируемость

**До**: Сложно тестировать (тексты разбросаны по коду)

**После**: Легко тестировать (один модуль)

---

## 📊 ПРИОРИТИЗАЦИЯ ЗАДАЧ

### Критический приоритет (P0):
1. ✅ Задача 1: Создать `button_texts.py`
2. ✅ Задача 2: Использовать в Entry Handler

### Высокий приоритет (P1):
3. ✅ Задача 3: Добавить остальные кнопки
4. ✅ Задача 4: Мигрировать "Мои заявки"

### Средний приоритет (P2):
5. ✅ Задача 5: Документация
6. Миграция остальных handlers (постепенно)

---

## 🎯 ИТОГОВАЯ ОЦЕНКА

**Общее время**: ~90 минут (1.5 часа)

**Разбивка**:
- Создание единого источника: 30 минут
- Использование в Entry Handler: 15 минут
- Расширение на другие кнопки: 20 минут
- Миграция других handlers: 10 минут
- Документация: 15 минут

**Преимущества**:
- ✅ Единый источник правды
- ✅ Автоматическое масштабирование
- ✅ Упрощение поддержки
- ✅ Готовность к будущим языкам

---

**Статус**: 📋 План готов к реализации  
**Следующий шаг**: IMPLEMENT - начать с Задачи 1 (создание `button_texts.py`)

